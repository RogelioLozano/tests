"""Ports: the interfaces the application depends on.

Every port is a `Protocol`, so an adapter satisfies it structurally and never
has to import from the domain to be usable. Swapping local implementations for
cloud ones is a change in the composition root only.
"""

from app.domain.ports.ai import SceneCodeGenerator
from app.domain.ports.clock import Clock, IdGenerator
from app.domain.ports.jobs import JobQueue
from app.domain.ports.logging import Logger, LoggerFactory
from app.domain.ports.rendering import SceneRenderer
from app.domain.ports.repository import RenderJobRepository
from app.domain.ports.storage import ArtifactStorage
from app.domain.ports.validation import SceneCodeValidator

__all__ = [
    "ArtifactStorage",
    "Clock",
    "IdGenerator",
    "JobQueue",
    "Logger",
    "LoggerFactory",
    "RenderJobRepository",
    "SceneCodeGenerator",
    "SceneRenderer",
    "SceneCodeValidator",
]
