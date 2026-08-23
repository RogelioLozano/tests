"""Validator tests.

The rejection cases are the point: this is the gate that stands between a
prompt-injected model response and `subprocess.run`, so each escape route gets
an explicit test.
"""

from __future__ import annotations

import pytest

from app.core.config import ValidationSettings
from app.infrastructure.ai.template_generator import TemplateSceneCodeGenerator
from app.infrastructure.validation.ast_validator import AstSceneCodeValidator
from tests.conftest import VALID_SCENE, RecordingLogger

SCENE = "Scene_test"


@pytest.fixture
def validator(logger: RecordingLogger) -> AstSceneCodeValidator:
    return AstSceneCodeValidator(ValidationSettings(), logger)


def codes(validator: AstSceneCodeValidator, source: str) -> set[str]:
    return {issue.code for issue in validator.validate(source, scene_name=SCENE).issues}


def test_accepts_a_plain_scene(validator: AstSceneCodeValidator) -> None:
    report = validator.validate(VALID_SCENE.format(name=SCENE), scene_name=SCENE)
    assert report.is_valid, report.summary()


@pytest.mark.parametrize(
    "prompt",
    [
        "draw a red circle",
        "transform a square into a circle",
        'write the text "Hello there"',
        "plot a sine wave in green",
    ],
)
def test_accepts_everything_the_generator_produces(
    validator: AstSceneCodeValidator, logger: RecordingLogger, prompt: str
) -> None:
    generator = TemplateSceneCodeGenerator(logger, model="test", max_prompt_chars=1000)
    scene = generator.generate(prompt, scene_name=SCENE)
    report = validator.validate(scene.code, scene_name=SCENE)
    assert report.is_valid, report.summary()


def test_rejects_syntax_errors(validator: AstSceneCodeValidator) -> None:
    assert "syntax_error" in codes(validator, "class Broken(:\n")


def test_rejects_forbidden_imports(validator: AstSceneCodeValidator) -> None:
    source = f"import os\n\n\nclass {SCENE}(Scene):\n    def construct(self):\n        pass\n"
    assert "forbidden_import" in codes(validator, source)


def test_rejects_import_from_outside_the_allowlist(
    validator: AstSceneCodeValidator,
) -> None:
    source = (
        f"from subprocess import run\n\n\nclass {SCENE}(Scene):\n"
        "    def construct(self):\n        pass\n"
    )
    assert "forbidden_import" in codes(validator, source)


def test_rejects_exec_and_eval(validator: AstSceneCodeValidator) -> None:
    source = (
        f"from manim import *\n\n\nclass {SCENE}(Scene):\n"
        "    def construct(self):\n        exec('print(1)')\n"
    )
    assert "forbidden_name" in codes(validator, source)


def test_rejects_dunder_traversal(validator: AstSceneCodeValidator) -> None:
    """The classic sandbox escape: reach the interpreter through object.__class__."""
    source = (
        f"from manim import *\n\n\nclass {SCENE}(Scene):\n"
        "    def construct(self):\n"
        "        cls = ().__class__.__base__.__subclasses__()\n"
    )
    assert "dunder_access" in codes(validator, source)


def test_rejects_filesystem_attributes(validator: AstSceneCodeValidator) -> None:
    source = (
        f"from manim import *\nimport numpy as np\n\n\nclass {SCENE}(Scene):\n"
        "    def construct(self):\n        data = np.load('/etc/passwd')\n"
    )
    assert "forbidden_attribute" in codes(validator, source)


def test_rejects_module_level_execution(validator: AstSceneCodeValidator) -> None:
    """Import-time side effects would run before the renderer reached construct()."""
    source = (
        f"from manim import *\nprint('side effect')\n\n\nclass {SCENE}(Scene):\n"
        "    def construct(self):\n        pass\n"
    )
    assert "module_level_statement" in codes(validator, source)


def test_rejects_a_mismatched_scene_name(validator: AstSceneCodeValidator) -> None:
    assert "scene_name_mismatch" in codes(validator, VALID_SCENE.format(name="Other"))


def test_rejects_extra_classes(validator: AstSceneCodeValidator) -> None:
    source = VALID_SCENE.format(name=SCENE) + "\n\nclass Extra:\n    pass\n"
    assert "scene_class_count" in codes(validator, source)


def test_rejects_a_non_scene_base(validator: AstSceneCodeValidator) -> None:
    source = (
        f"from manim import *\n\n\nclass {SCENE}(object):\n"
        "    def construct(self):\n        pass\n"
    )
    assert "unsupported_base" in codes(validator, source)


def test_rejects_a_missing_construct(validator: AstSceneCodeValidator) -> None:
    source = f"from manim import *\n\n\nclass {SCENE}(Scene):\n    x = 1\n"
    assert "missing_construct" in codes(validator, source)


def test_rejects_while_loops(validator: AstSceneCodeValidator) -> None:
    source = (
        f"from manim import *\n\n\nclass {SCENE}(Scene):\n"
        "    def construct(self):\n        while True:\n            pass\n"
    )
    assert "forbidden_loop" in codes(validator, source)


def test_rejects_oversized_source(logger: RecordingLogger) -> None:
    validator = AstSceneCodeValidator(ValidationSettings(max_code_chars=50), logger)
    assert "source_too_large" in codes(validator, VALID_SCENE.format(name=SCENE))


def test_logs_a_failure_with_the_issue_codes(
    validator: AstSceneCodeValidator, logger: RecordingLogger
) -> None:
    validator.validate("import os\n", scene_name=SCENE)
    assert "validation.failed" in logger.names()
