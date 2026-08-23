"""Animation Studio backend.

A modular monolith laid out by dependency direction, not by file type:

    api            HTTP surface: routing, DTOs, error mapping. Depends on
                   application; knows nothing about adapters.
    application    Use cases and orchestration. Depends on domain ports only.
    domain         Entities and port definitions. Depends on nothing.
    infrastructure Adapters that implement the ports: Manim, SQLite, local
                   disk, stdlib logging, the template AI provider.
    core           Settings, ambient context, and the composition root that
                   binds ports to adapters.

Imports run inward only (api -> application -> domain). `core.container` is the
one place allowed to name a concrete adapter, which is what makes each local
implementation swappable for a hosted one later.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
