"""Local, deterministic Manim code generator.

Stands in for a hosted model so the pipeline is exercisable end to end with no
network and no credentials. It implements the same `SceneCodeGenerator` port an
LLM adapter will, and it reports the same three generation steps, so swapping
providers changes neither the service nor the logs' shape.

Any text lifted from the prompt is reduced to a safe character set and then
embedded with `repr()`, so a prompt cannot smuggle syntax into the source. The
validator re-checks the result regardless: this is defence in depth, not the
only defence.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from app.domain.errors import GenerationError
from app.domain.models import GeneratedScene
from app.domain.ports.logging import Logger

_QUOTED = re.compile(r"[\"'“”‘’](?P<text>[^\"'“”‘’]{1,60})[\"'“”‘’]")
_UNSAFE_TEXT = re.compile(r"[^A-Za-z0-9 ,.!?:;()\-+=/]")

_COLORS = {
    "red": "RED",
    "blue": "BLUE",
    "green": "GREEN",
    "yellow": "YELLOW",
    "orange": "ORANGE",
    "purple": "PURPLE",
    "pink": "PINK",
    "teal": "TEAL",
    "gold": "GOLD",
    "white": "WHITE",
}

_FUNCTIONS = {
    "sine": ("np.sin(x)", "sin(x)"),
    "sin": ("np.sin(x)", "sin(x)"),
    "cosine": ("np.cos(x)", "cos(x)"),
    "cos": ("np.cos(x)", "cos(x)"),
    "parabola": ("x**2", "x^2"),
    "quadratic": ("x**2", "x^2"),
    "cubic": ("x**3", "x^3"),
    "exponential": ("np.exp(x)", "e^x"),
}


@dataclass(frozen=True, slots=True)
class _Intent:
    template: str
    color: str
    text: str
    expression: str
    label: str


class TemplateSceneCodeGenerator:
    """Keyword-driven template selection. No network, no credentials."""

    def __init__(self, logger: Logger, *, model: str, max_prompt_chars: int) -> None:
        self._logger = logger
        self._model = model
        self._max_prompt_chars = max_prompt_chars
        self._templates: dict[str, Callable[[str, _Intent], str]] = {
            "plot": _plot_template,
            "text": _text_template,
            "transform": _transform_template,
            "shape": _shape_template,
        }

    @property
    def provider(self) -> str:
        return "template"

    @property
    def model(self) -> str:
        return self._model

    def generate(
        self, prompt: str, *, scene_name: str, feedback: Sequence[str] = ()
    ) -> GeneratedScene:
        # Templates are fixed, so there is nothing to correct: `feedback` is
        # accepted to satisfy the port and ignored.
        cleaned = prompt.strip()
        if not cleaned:
            raise GenerationError("Prompt is empty")
        if len(cleaned) > self._max_prompt_chars:
            raise GenerationError(
                f"Prompt exceeds {self._max_prompt_chars} characters"
            )

        self._logger.info(
            "ai.generation.started",
            provider=self.provider,
            model=self._model,
            prompt_chars=len(cleaned),
        )

        intent = self._interpret(cleaned)
        self._logger.info(
            "ai.generation.intent_resolved",
            template=intent.template,
            color=intent.color,
            has_text=bool(intent.text),
        )

        build = self._templates[intent.template]
        code = build(scene_name, intent)
        if not code.strip():
            raise GenerationError("Provider returned empty source")

        self._logger.info(
            "ai.generation.completed",
            scene_name=scene_name,
            code_chars=len(code),
            template=intent.template,
        )
        return GeneratedScene(
            code=code,
            scene_name=scene_name,
            provider=self.provider,
            model=self._model,
            metadata={"template": intent.template, "color": intent.color},
        )

    def _interpret(self, prompt: str) -> _Intent:
        lowered = prompt.lower()
        color = next(
            (name for word, name in _COLORS.items() if word in lowered), "BLUE"
        )
        expression, label = next(
            ((e, l) for word, (e, l) in _FUNCTIONS.items() if word in lowered),
            ("np.sin(x)", "sin(x)"),
        )
        text = self._extract_text(prompt)

        if any(word in lowered for word in ("plot", "graph", "axes", "function", "curve")):
            template = "plot"
        elif text or any(word in lowered for word in ("text", "title", "write", "caption")):
            template = "text"
        elif any(word in lowered for word in ("transform", "morph", "into", "turn")):
            template = "transform"
        else:
            template = "shape"

        return _Intent(
            template=template,
            color=color,
            text=text or "Hello, Manim",
            expression=expression,
            label=label,
        )

    def _extract_text(self, prompt: str) -> str:
        match = _QUOTED.search(prompt)
        if not match:
            return ""
        return _UNSAFE_TEXT.sub("", match.group("text")).strip()


def _header() -> str:
    return "from manim import *\nimport numpy as np\n\n\n"


def _literal(value: Any) -> str:
    """Render `value` as a Python literal safe to embed in generated source."""
    return repr(value)


def _shape_template(scene_name: str, intent: _Intent) -> str:
    return _header() + textwrap.dedent(
        f"""\
        class {scene_name}(Scene):
            def construct(self):
                shape = Circle(radius=1.5)
                shape.set_fill({intent.color}, opacity=0.5)
                shape.set_stroke({intent.color}, width=4)
                self.play(Create(shape))
                self.play(shape.animate.scale(1.3).rotate(PI / 4))
                self.wait(0.5)
                self.play(FadeOut(shape))
        """
    )


def _transform_template(scene_name: str, intent: _Intent) -> str:
    return _header() + textwrap.dedent(
        f"""\
        class {scene_name}(Scene):
            def construct(self):
                square = Square(side_length=2.5)
                square.set_stroke({intent.color}, width=4)
                circle = Circle(radius=1.5)
                circle.set_fill({intent.color}, opacity=0.5)
                self.play(Create(square))
                self.play(Transform(square, circle))
                self.wait(0.5)
                self.play(FadeOut(square))
        """
    )


def _text_template(scene_name: str, intent: _Intent) -> str:
    return _header() + textwrap.dedent(
        f"""\
        class {scene_name}(Scene):
            def construct(self):
                caption = Text({_literal(intent.text)}, font_size=48)
                caption.set_color({intent.color})
                underline = Line(LEFT, RIGHT)
                underline.set_width(caption.width)
                underline.next_to(caption, DOWN, buff=0.25)
                self.play(Write(caption))
                self.play(Create(underline))
                self.wait(0.5)
                self.play(FadeOut(caption), FadeOut(underline))
        """
    )


def _plot_template(scene_name: str, intent: _Intent) -> str:
    return _header() + textwrap.dedent(
        f"""\
        class {scene_name}(Scene):
            def construct(self):
                axes = Axes(
                    x_range=[-4, 4, 1],
                    y_range=[-3, 3, 1],
                    axis_config={{"include_tip": False}},
                )
                curve = axes.plot(lambda x: {intent.expression}, color={intent.color})
                label = Text({_literal(intent.label)}, font_size=32)
                label.next_to(axes, UP)
                self.play(Create(axes))
                self.play(Write(label))
                self.play(Create(curve), run_time=2)
                self.wait(0.5)
                self.play(FadeOut(axes), FadeOut(curve), FadeOut(label))
        """
    )
