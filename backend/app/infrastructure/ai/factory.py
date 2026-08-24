"""AI provider registry.

`ANIM_AI_PROVIDER` selects the implementation:

    llm       any OpenAI-compatible chat endpoint (default; see LLMSettings)
    template  offline keyword templates, used by the test suite

Anthropic's Messages API has a different wire format, so it would join as a
third entry here rather than as a flag on the `llm` one.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import urlsplit

from app.core.config import AISettings
from app.domain.errors import ConfigurationError
from app.domain.ports.ai import SceneCodeGenerator
from app.domain.ports.logging import Logger
from app.infrastructure.ai.llm_generator import (
    LOCAL_HOSTS,
    OpenAICompatibleGenerator,
)
from app.infrastructure.ai.template_generator import TemplateSceneCodeGenerator


def _build_template(settings: AISettings, logger: Logger) -> SceneCodeGenerator:
    return TemplateSceneCodeGenerator(
        logger,
        model=settings.model,
        max_prompt_chars=settings.max_prompt_chars,
    )


def _build_llm(settings: AISettings, logger: Logger) -> SceneCodeGenerator:
    llm = settings.llm
    host = urlsplit(llm.base_url).hostname or ""
    if not llm.api_key and host not in LOCAL_HOSTS:
        # Fail at startup with instructions rather than as a 401 mid-render.
        raise ConfigurationError(
            f"ANIM_LLM_BASE_URL points at {host!r}, which needs a credential. "
            "Set ANIM_LLM_API_KEY (or OPENAI_API_KEY), or point "
            "ANIM_LLM_BASE_URL at a local model server."
        )
    logger.info(
        "ai.provider.configured",
        provider=llm.provider_label,
        model=llm.model,
        base_url=llm.base_url,
        authenticated=bool(llm.api_key),
    )
    return OpenAICompatibleGenerator(llm, logger)


_PROVIDERS: dict[str, Callable[[AISettings, Logger], SceneCodeGenerator]] = {
    "llm": _build_llm,
    "template": _build_template,
}


def build_scene_generator(settings: AISettings, logger: Logger) -> SceneCodeGenerator:
    try:
        build = _PROVIDERS[settings.provider]
    except KeyError:
        raise ConfigurationError(
            f"Unknown AI provider {settings.provider!r}; "
            f"available: {', '.join(sorted(_PROVIDERS))}"
        ) from None
    return build(settings, logger)
