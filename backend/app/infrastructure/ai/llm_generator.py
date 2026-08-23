"""Chat-completions code generator.

One adapter for every provider that speaks OpenAI's `/chat/completions` shape,
which is nearly all of them — Ollama, Groq, OpenRouter, Cerebras, DeepSeek,
Google AI Studio, vLLM, LM Studio, OpenAI itself. Switching between them is two
environment variables, not a code change.

No agent framework sits under this. The `SceneCodeGenerator` port is already
the abstraction; wrapping one HTTP call in a second one would add a dependency
and hide the seam that makes providers swappable.

The system prompt below restates the validator's rules, so the model aims at
the target the validator actually enforces. It is a hint, never a guarantee:
the validator still rejects whatever comes back, and `feedback` from a rejected
attempt is fed into the next one.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

import httpx

from app.core.config import LLMSettings
from app.domain.errors import GenerationError
from app.domain.models import GeneratedScene
from app.domain.ports.logging import Logger

SYSTEM_PROMPT = """\
You write Manim Community Edition scenes. You output Python source code and \
nothing else.

Rules, all mandatory:
1. Output raw Python only. No markdown fences, no prose, no explanation.
2. Imports: only `from manim import *`, `import numpy as np`, and `import math`.
   No other import is permitted.
3. Define exactly ONE class. It must be named exactly {scene_name} and must \
subclass Scene. It must define construct(self).
4. Module level may contain only those imports and that class.
5. Never use eval, exec, open, __import__, getattr, setattr, globals, locals, \
compile, or input.
6. Never access an attribute that starts with an underscore.
7. No while loops. Bounded for loops are fine.
8. No file, network, or process access of any kind.
9. Keep the animation under 20 seconds. End with self.wait(0.5) or a FadeOut.
10. Use only documented Manim CE APIs. Prefer Create, Write, Transform, \
FadeIn, FadeOut, .animate, Axes.plot, Text, MathTex.

Example of a correct response:
from manim import *


class {scene_name}(Scene):
    def construct(self):
        circle = Circle(radius=1.5)
        circle.set_fill(BLUE, opacity=0.5)
        self.play(Create(circle))
        self.play(circle.animate.shift(RIGHT * 2))
        self.wait(0.5)
"""

_FENCE = re.compile(r"^\s*```(?:python|py)?\s*\n(?P<code>.*?)\n?\s*```\s*$", re.DOTALL)

# Hosts that need no credential. Anything else without a key is a misconfiguration
# worth failing loudly on rather than discovering as a 401 mid-render.
LOCAL_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}
)


class OpenAICompatibleGenerator:
    def __init__(
        self,
        settings: LLMSettings,
        logger: Logger,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._logger = logger
        self._endpoint = f"{settings.base_url.rstrip('/')}/chat/completions"
        # Injected only by tests; in production each call opens and closes its
        # own client, so there is no connection state to manage at shutdown.
        self._client = client

    @property
    def provider(self) -> str:
        return self._settings.provider_label

    @property
    def model(self) -> str:
        return self._settings.model

    def generate(
        self, prompt: str, *, scene_name: str, feedback: Sequence[str] = ()
    ) -> GeneratedScene:
        cleaned = prompt.strip()
        if not cleaned:
            raise GenerationError("Prompt is empty")
        if len(cleaned) > self._settings.max_prompt_chars:
            raise GenerationError(
                f"Prompt exceeds {self._settings.max_prompt_chars} characters"
            )

        messages = self._build_messages(cleaned, scene_name, feedback)
        self._logger.info(
            "ai.generation.started",
            provider=self.provider,
            model=self.model,
            endpoint=self._endpoint,
            prompt_chars=len(cleaned),
            repair_attempt=len(feedback),
        )

        payload = self._request(messages)
        code = _extract_code(_first_message(payload))
        if not code:
            raise GenerationError("The model returned no code")

        usage = payload.get("usage") or {}
        self._logger.info(
            "ai.generation.completed",
            provider=self.provider,
            model=self.model,
            scene_name=scene_name,
            code_chars=len(code),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
        return GeneratedScene(
            code=code,
            scene_name=scene_name,
            provider=self.provider,
            model=self.model,
            metadata={"endpoint": self._endpoint, "repair_attempt": len(feedback)},
        )

    def _build_messages(
        self, prompt: str, scene_name: str, feedback: Sequence[str]
    ) -> list[dict[str, str]]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(scene_name=scene_name)},
            {
                "role": "user",
                "content": (
                    f"Create a Manim scene named {scene_name} for this description:\n\n"
                    f"{prompt}"
                ),
            },
        ]
        for issue in feedback:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous answer was rejected by the code validator:\n"
                        f"{issue}\n\n"
                        "Return the corrected full source. Raw Python only."
                    ),
                }
            )
        return messages

    def _request(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"

        body = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
            "stream": False,
        }

        try:
            if self._client is not None:
                response = self._client.post(self._endpoint, json=body, headers=headers)
            else:
                with httpx.Client(timeout=self._settings.timeout_seconds) as client:
                    response = client.post(self._endpoint, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise GenerationError(
                f"The model did not respond within "
                f"{self._settings.timeout_seconds}s"
            ) from exc
        except httpx.HTTPError as exc:
            # Deliberately does not interpolate the exception: httpx puts the
            # full request URL in it, which can carry a key for some providers.
            self._logger.error(
                "ai.generation.transport_error",
                provider=self.provider,
                endpoint=self._endpoint,
                error_type=type(exc).__name__,
            )
            raise GenerationError(
                f"Could not reach the model at {self._endpoint}"
            ) from exc

        if response.status_code >= 400:
            raise GenerationError(self._describe_failure(response))

        try:
            return response.json()
        except ValueError as exc:
            raise GenerationError("The model returned a malformed response") from exc

    def _describe_failure(self, response: httpx.Response) -> str:
        detail = _provider_message(response)
        self._logger.error(
            "ai.generation.rejected",
            provider=self.provider,
            status_code=response.status_code,
            detail=detail,
        )
        if response.status_code in (401, 403):
            return (
                f"The model provider rejected the credentials "
                f"(HTTP {response.status_code}). Check ANIM_LLM_API_KEY."
            )
        if response.status_code == 404:
            return (
                f"Model {self._settings.model!r} was not found at "
                f"{self._endpoint}. Check ANIM_LLM_MODEL."
            )
        if response.status_code == 429:
            return "The model provider is rate limiting; try again shortly."
        return f"The model provider returned HTTP {response.status_code}: {detail}"


def _provider_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message", ""))[:300]
    if isinstance(error, str):
        return error[:300]
    return str(body)[:300]


def _first_message(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GenerationError("The model returned no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise GenerationError("The model returned no message content")
    return content


def _extract_code(content: str) -> str:
    """Unwrap a markdown fence if the model added one despite being told not to."""
    match = _FENCE.match(content.strip())
    return (match.group("code") if match else content).strip()
