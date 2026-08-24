"""LaTeX-availability tests.

Manim shells out to `latex` for Tex/MathTex. Without texlive that surfaces as
`FileNotFoundError: 'latex'` from deep inside the render — after the model call
has already been paid for. The system prompt asks the model to avoid it, but a
prompt is a hint; the validator is the gate, and its message is what the repair
loop feeds back.
"""

from __future__ import annotations

import pytest

from app.core.config import ValidationSettings
from app.infrastructure.validation.ast_validator import AstSceneCodeValidator
from tests.conftest import RecordingLogger

SCENE = "Scene_test"


def scene(body: str) -> str:
    return (
        "from manim import *\n\n\n"
        f"class {SCENE}(Scene):\n"
        "    def construct(self):\n"
        f"        {body}\n"
    )


@pytest.fixture
def no_latex(logger: RecordingLogger) -> AstSceneCodeValidator:
    return AstSceneCodeValidator(ValidationSettings(latex_available=False), logger)


@pytest.fixture
def with_latex(logger: RecordingLogger) -> AstSceneCodeValidator:
    return AstSceneCodeValidator(ValidationSettings(latex_available=True), logger)


def codes(validator: AstSceneCodeValidator, source: str) -> set[str]:
    return {issue.code for issue in validator.validate(source, scene_name=SCENE).issues}


@pytest.mark.parametrize(
    "body",
    [
        'self.play(Write(MathTex("x^2")))',
        'self.play(Write(Tex("hello")))',
        'title = Title("A title")',
        'items = BulletedList("one", "two")',
        "counter = DecimalNumber(0)",
        "n = Integer(5)",
        'm = Matrix([["1", "0"], ["0", "1"]])',
    ],
)
def test_latex_mobjects_are_rejected_without_latex(
    no_latex: AstSceneCodeValidator, body: str
) -> None:
    assert "latex_unavailable" in codes(no_latex, scene(body))


def test_latex_methods_are_rejected(no_latex: AstSceneCodeValidator) -> None:
    assert "latex_unavailable" in codes(
        no_latex, scene("axes = Axes()\n        axes.add_coordinates()")
    )
    assert "latex_unavailable" in codes(
        no_latex, scene("labels = Axes().get_axis_labels()")
    )


def test_include_numbers_is_rejected(no_latex: AstSceneCodeValidator) -> None:
    """Tick labels go through DecimalNumber, so this crashes too."""
    assert "latex_unavailable" in codes(
        no_latex, scene("axes = Axes(include_numbers=True)")
    )


def test_include_numbers_false_is_fine(no_latex: AstSceneCodeValidator) -> None:
    assert "latex_unavailable" not in codes(
        no_latex, scene("axes = Axes(include_numbers=False)")
    )


def test_text_is_always_allowed(no_latex: AstSceneCodeValidator) -> None:
    report = no_latex.validate(scene('self.play(Write(Text("x^2")))'), scene_name=SCENE)
    assert report.is_valid, report.summary()


def test_nothing_is_rejected_when_latex_is_installed(
    with_latex: AstSceneCodeValidator,
) -> None:
    report = with_latex.validate(
        scene('self.play(Write(MathTex("x^2")))'), scene_name=SCENE
    )
    assert report.is_valid, report.summary()


def test_the_message_tells_the_model_what_to_do_instead(
    no_latex: AstSceneCodeValidator,
) -> None:
    """This text becomes the repair prompt, so it has to be actionable."""
    report = no_latex.validate(scene('t = MathTex("x")'), scene_name=SCENE)
    summary = report.summary()
    assert "LaTeX" in summary
    assert "Text(...)" in summary
