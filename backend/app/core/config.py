"""Application settings.

Configuration is read from the environment once, at startup, and passed down
explicitly. Nothing below the composition root reads `os.environ`, so every
component can be constructed with different settings in a test.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.domain.errors import ConfigurationError

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip() or default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from exc


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw and raw.strip() else default


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """Any provider speaking OpenAI's /chat/completions shape.

    Defaults target Groq: hosted, so the container needs no GPU and no model
    weights, which is what makes the image small enough to deploy anywhere.
    """

    base_url: str = "https://api.groq.com/openai/v1"
    model: str = "openai/gpt-oss-120b"
    provider_label: str = "groq"
    # repr=False so a settings dump can never put the key in a log line.
    api_key: str = field(default="", repr=False)
    timeout_seconds: float = 90.0
    temperature: float = 0.2
    # Generous, because a truncated completion is an unterminated string that
    # fails validation as a syntax error, wasting a whole repair attempt.
    max_tokens: int = 2_500
    max_prompt_chars: int = 1_000


@dataclass(frozen=True, slots=True)
class AISettings:
    provider: str = "llm"
    model: str = "manim-templates-v1"
    max_prompt_chars: int = 1_000
    # Attempts per job: the first generation plus repair rounds driven by the
    # validator's complaints.
    max_attempts: int = 3
    llm: LLMSettings = field(default_factory=LLMSettings)


@dataclass(frozen=True, slots=True)
class ValidationSettings:
    max_code_chars: int = 20_000
    max_ast_nodes: int = 4_000
    allowed_imports: tuple[str, ...] = ("manim", "numpy", "math")
    # Manim shells out to `latex` for Tex/MathTex. The container ships without
    # texlive (it would add ~1 GB), so those mobjects have to be rejected
    # before the render rather than blowing up inside it.
    latex_available: bool = False


@dataclass(frozen=True, slots=True)
class RenderSettings:
    backend: str = "manim"
    scratch_dir: Path = field(default=REPO_ROOT / "animations" / "output" / "scratch")
    timeout_seconds: int = 180
    default_quality: str = "low"
    # Peak RSS per render is ~217/388/981 MB for low/medium/high. On a small
    # instance the top of that range is an OOM kill, so it has to be refusable.
    max_quality: str = "high"


@dataclass(frozen=True, slots=True)
class StorageSettings:
    backend: str = "local"
    root: Path = field(default=REPO_ROOT / "animations" / "output" / "library")


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    backend: str = "sqlite"
    path: Path = field(default=REPO_ROOT / "animations" / "output" / "metadata.db")
    timeout_seconds: float = 10.0


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    backend: str = "stdlib"
    level: str = "INFO"
    format: str = "json"
    service_name: str = "animation-studio"


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "local"
    cors_allow_origins: tuple[str, ...] = ("http://localhost:5100", "http://127.0.0.1:5100")
    max_page_size: int = 100
    jobs_backend: str = "inline"
    jobs_max_workers: int = 2
    # When set, the API also serves the built frontend, so one container is a
    # complete deployment.
    static_dir: Path | None = None
    ai: AISettings = field(default_factory=AISettings)
    validation: ValidationSettings = field(default_factory=ValidationSettings)
    render: RenderSettings = field(default_factory=RenderSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)


def load_settings() -> Settings:
    """Build settings from the environment.

    Prefix is `ANIM_` so the variables cannot collide with the ones the static
    server and Manim already read.
    """
    output_dir = _env_path("ANIM_OUTPUT_DIR", REPO_ROOT / "animations" / "output")
    static_raw = os.environ.get("ANIM_STATIC_DIR", "").strip()
    return Settings(
        environment=_env("ANIM_ENV", "local"),
        cors_allow_origins=_env_list(
            "ANIM_CORS_ALLOW_ORIGINS",
            ("http://localhost:5100", "http://127.0.0.1:5100"),
        ),
        max_page_size=_env_int("ANIM_MAX_PAGE_SIZE", 100),
        jobs_backend=_env("ANIM_JOBS_BACKEND", "inline"),
        jobs_max_workers=max(1, _env_int("ANIM_JOBS_MAX_WORKERS", 2)),
        static_dir=Path(static_raw).resolve() if static_raw else None,
        ai=AISettings(
            provider=_env("ANIM_AI_PROVIDER", "llm"),
            model=_env("ANIM_AI_MODEL", "manim-templates-v1"),
            max_prompt_chars=_env_int("ANIM_MAX_PROMPT_CHARS", 1_000),
            max_attempts=max(1, _env_int("ANIM_AI_MAX_ATTEMPTS", 3)),
            llm=LLMSettings(
                base_url=_env("ANIM_LLM_BASE_URL", "https://api.groq.com/openai/v1"),
                model=_env("ANIM_LLM_MODEL", "openai/gpt-oss-120b"),
                provider_label=_env("ANIM_LLM_PROVIDER_LABEL", "groq"),
                # Falls back to the conventional variable so an existing
                # OPENAI_API_KEY in the shell just works.
                api_key=os.environ.get("ANIM_LLM_API_KEY")
                or os.environ.get("OPENAI_API_KEY", ""),
                timeout_seconds=_env_float("ANIM_LLM_TIMEOUT_SECONDS", 90.0),
                temperature=_env_float("ANIM_LLM_TEMPERATURE", 0.2),
                max_tokens=_env_int("ANIM_LLM_MAX_TOKENS", 2_500),
                max_prompt_chars=_env_int("ANIM_MAX_PROMPT_CHARS", 1_000),
            ),
        ),
        validation=ValidationSettings(
            max_code_chars=_env_int("ANIM_MAX_CODE_CHARS", 20_000),
            max_ast_nodes=_env_int("ANIM_MAX_AST_NODES", 4_000),
            allowed_imports=_env_list(
                "ANIM_ALLOWED_IMPORTS", ("manim", "numpy", "math")
            ),
            # Detected rather than assumed, so installing texlive is enough to
            # unlock MathTex with no config change.
            latex_available=_env_bool(
                "ANIM_LATEX_AVAILABLE", shutil.which("latex") is not None
            ),
        ),
        render=RenderSettings(
            backend=_env("ANIM_RENDER_BACKEND", "manim"),
            scratch_dir=_env_path("ANIM_RENDER_SCRATCH_DIR", output_dir / "scratch"),
            timeout_seconds=_env_int("ANIM_RENDER_TIMEOUT_SECONDS", 180),
            default_quality=_env("ANIM_DEFAULT_QUALITY", "low"),
            max_quality=_env("ANIM_MAX_QUALITY", "high"),
        ),
        storage=StorageSettings(
            backend=_env("ANIM_STORAGE_BACKEND", "local"),
            root=_env_path("ANIM_STORAGE_ROOT", output_dir / "library"),
        ),
        database=DatabaseSettings(
            backend=_env("ANIM_DB_BACKEND", "sqlite"),
            path=_env_path("ANIM_DB_PATH", output_dir / "metadata.db"),
            timeout_seconds=float(_env_int("ANIM_DB_TIMEOUT_SECONDS", 10)),
        ),
        logging=LoggingSettings(
            backend=_env("ANIM_LOG_BACKEND", "stdlib"),
            level=_env("ANIM_LOG_LEVEL", "INFO").upper(),
            format=_env("ANIM_LOG_FORMAT", "json"),
            service_name=_env("ANIM_SERVICE_NAME", "animation-studio"),
        ),
    )
