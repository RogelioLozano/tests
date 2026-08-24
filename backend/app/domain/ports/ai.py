"""AI port.

One abstraction covers every way of turning a prompt into Manim source: a local
template provider, a self-hosted model, a hosted API. Providers are responsible
for producing source only; they never execute it.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from app.domain.models import GeneratedScene


class SceneCodeGenerator(Protocol):
    @property
    def provider(self) -> str:
        """Stable identifier recorded on the job (e.g. "template", "openai")."""
        ...

    @property
    def model(self) -> str: ...

    def generate(
        self, prompt: str, *, scene_name: str, feedback: Sequence[str] = ()
    ) -> GeneratedScene:
        """Produce a Manim scene named `scene_name` for `prompt`.

        `feedback` carries validation errors from previous attempts, newest
        last, so a model-backed provider can correct itself. Providers that
        cannot use it ignore it.

        Raises:
            GenerationError: the provider could not produce source.
        """
        ...
