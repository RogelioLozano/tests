"""LLM adapter tests.

`httpx.MockTransport` stands in for the provider, so the whole request/response
path is exercised — headers, body, fence stripping, error mapping — without a
network call or a credential.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import AISettings, LLMSettings
from app.domain.errors import ConfigurationError, GenerationError
from app.infrastructure.ai.factory import build_scene_generator
from app.infrastructure.ai.llm_generator import OpenAICompatibleGenerator
from tests.conftest import RecordingLogger

SCENE = "Scene_abc123"

SCENE_CODE = f"""\
from manim import *


class {SCENE}(Scene):
    def construct(self):
        self.play(Create(Circle()))
"""


def completion(content: str) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 60},
    }


def generator_for(handler, logger: RecordingLogger, **overrides):
    settings = LLMSettings(model="test-model", provider_label="stub", **overrides)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleGenerator(settings, logger, client=client)


def run(handler, logger, *, feedback=(), **overrides):
    generator = generator_for(handler, logger, **overrides)
    return generator.generate("draw a circle", scene_name=SCENE, feedback=feedback)


def test_returns_the_models_code(logger: RecordingLogger) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion(SCENE_CODE))

    scene = run(handler, logger)

    assert scene.code == SCENE_CODE.strip()
    assert scene.scene_name == SCENE
    assert scene.provider == "stub"
    assert scene.model == "test-model"


def test_strips_a_markdown_fence(logger: RecordingLogger) -> None:
    """Models add fences even when told not to."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion(f"```python\n{SCENE_CODE}```"))

    assert run(handler, logger).code == SCENE_CODE.strip()


def test_sends_the_prompt_and_scene_name(logger: RecordingLogger) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=completion(SCENE_CODE))

    run(handler, logger)

    assert captured["model"] == "test-model"
    system, user = captured["messages"][0], captured["messages"][1]
    assert system["role"] == "system"
    assert SCENE in system["content"]
    assert "draw a circle" in user["content"]


def test_feedback_becomes_a_repair_turn(logger: RecordingLogger) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=completion(SCENE_CODE))

    run(handler, logger, feedback=["forbidden_import: Import of 'os' is not allowed"])

    last = captured["messages"][-1]
    assert "rejected by the code validator" in last["content"]
    assert "forbidden_import" in last["content"]


def test_sends_the_key_when_configured(logger: RecordingLogger) -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=completion(SCENE_CODE))

    run(handler, logger, api_key="sk-test")
    assert seen["auth"] == "Bearer sk-test"


def test_omits_the_header_without_a_key(logger: RecordingLogger) -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=completion(SCENE_CODE))

    run(handler, logger)
    assert seen["auth"] is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "credentials"),
        (404, "not found"),
        (429, "rate limiting"),
        (500, "HTTP 500"),
    ],
)
def test_maps_provider_errors_to_actionable_messages(
    logger: RecordingLogger, status: int, expected: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "nope"}})

    with pytest.raises(GenerationError) as excinfo:
        run(handler, logger)
    assert expected.lower() in str(excinfo.value).lower()


def test_an_unreachable_provider_is_a_generation_error(logger: RecordingLogger) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(GenerationError) as excinfo:
        run(handler, logger)
    assert "could not reach" in str(excinfo.value).lower()


def test_an_empty_completion_is_an_error(logger: RecordingLogger) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=completion("   "))

    with pytest.raises(GenerationError):
        run(handler, logger)


def test_a_timeout_names_the_limit(logger: RecordingLogger) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    with pytest.raises(GenerationError) as excinfo:
        run(handler, logger, timeout_seconds=12.0)
    assert "12" in str(excinfo.value)


def test_a_remote_url_without_a_key_fails_at_startup(logger: RecordingLogger) -> None:
    """Better a clear error on boot than a 401 in the middle of a render."""
    settings = AISettings(
        provider="llm", llm=LLMSettings(base_url="https://api.openai.com/v1")
    )
    with pytest.raises(ConfigurationError) as excinfo:
        build_scene_generator(settings, logger)
    assert "ANIM_LLM_API_KEY" in str(excinfo.value)


def test_a_local_url_needs_no_key(logger: RecordingLogger) -> None:
    settings = AISettings(
        provider="llm", llm=LLMSettings(base_url="http://127.0.0.1:11434/v1")
    )
    assert build_scene_generator(settings, logger) is not None


def test_the_api_key_stays_out_of_reprs() -> None:
    """A settings dump must never leak the credential into a log line."""
    assert "sk-secret" not in repr(LLMSettings(api_key="sk-secret"))
