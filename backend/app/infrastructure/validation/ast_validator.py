"""Static safety check for generated Manim source.

This runs before anything is written to disk or handed to a renderer, and it
never imports, compiles, or executes the code it inspects — it only walks the
parse tree.

The policy is deliberately narrow: generated source is expected to look like
one Manim `Scene` subclass and nothing else. Module level is restricted to
imports and that class, so no statement can run merely because the file was
imported. Names and attributes that reach the filesystem, the process, or the
interpreter internals are rejected outright.

Not a sandbox. It raises the cost of a malicious or prompt-injected generation
sharply, but running untrusted code safely needs OS-level isolation (separate
user, container, seccomp) around the renderer as well.
"""

from __future__ import annotations

import ast
from typing import Iterator

from app.core.config import ValidationSettings
from app.domain.models import ValidationIssue, ValidationReport
from app.domain.ports.logging import Logger

# Manim scene bases a generated file may subclass.
ALLOWED_BASES = frozenset(
    {
        "Scene",
        "MovingCameraScene",
        "ZoomedScene",
        "ThreeDScene",
        "VectorScene",
        "LinearTransformationScene",
    }
)

# Builtins that hand back arbitrary execution, imports, or attribute traversal.
FORBIDDEN_NAMES = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "exit",
        "getattr",
        "globals",
        "help",
        "input",
        "locals",
        "memoryview",
        "open",
        "quit",
        "setattr",
        "vars",
    }
)

# Attribute names that reach the filesystem or spawn processes. Manim's own API
# is CamelCase or scene methods (play, wait, add), so this costs nothing here
# but blocks e.g. numpy's file and pickle entry points.
FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "call",
        "check_call",
        "check_output",
        "communicate",
        "execl",
        "execv",
        "fdopen",
        "fromfile",
        "frombuffer",
        "genfromtxt",
        "getattr",
        "load",
        "loads",
        "loadtxt",
        "memmap",
        "mkdir",
        "open",
        "popen",
        "read",
        "remove",
        "rmtree",
        "run",
        "save",
        "savetxt",
        "savez",
        "spawn",
        "startfile",
        "system",
        "tofile",
        "unlink",
        "write",
    }
)


# Manim mobjects that shell out to `latex`. Without texlive installed these
# raise FileNotFoundError deep inside the render, so they are rejected here
# where the message can be fed back to the model instead.
LATEX_NAMES = frozenset(
    {
        "BulletedList",
        "DecimalMatrix",
        "DecimalNumber",
        "DecimalTable",
        "Integer",
        "IntegerMatrix",
        "IntegerTable",
        "MathTable",
        "MathTex",
        "Matrix",
        "MobjectMatrix",
        "SingleStringMathTex",
        "Tex",
        "TexTemplate",
        "Title",
        "Variable",
    }
)

# Methods that build LaTeX labels internally.
LATEX_ATTRIBUTES = frozenset(
    {"add_coordinates", "get_axis_labels", "get_graph_label", "get_field_label"}
)

# Axes(..., include_numbers=True) renders tick labels with DecimalNumber.
LATEX_KEYWORDS = frozenset({"include_numbers", "add_coordinates"})

_USE_TEXT = "use Text(...) instead"


class AstSceneCodeValidator:
    """Allowlist validator over the abstract syntax tree."""

    def __init__(self, settings: ValidationSettings, logger: Logger) -> None:
        self._settings = settings
        self._logger = logger

    def validate(self, code: str, *, scene_name: str) -> ValidationReport:
        self._logger.info(
            "validation.started", scene_name=scene_name, code_chars=len(code)
        )
        report = ValidationReport(tuple(self._check(code, scene_name)))
        if report.is_valid:
            self._logger.info("validation.passed", scene_name=scene_name)
        else:
            self._logger.warning(
                "validation.failed",
                scene_name=scene_name,
                issue_count=len(report.issues),
                issues=[issue.code for issue in report.issues],
                detail=report.summary(),
            )
        return report

    def _check(self, code: str, scene_name: str) -> Iterator[ValidationIssue]:
        if not code.strip():
            yield ValidationIssue("empty_source", "Generated source is empty")
            return
        if len(code) > self._settings.max_code_chars:
            yield ValidationIssue(
                "source_too_large",
                f"Source exceeds {self._settings.max_code_chars} characters",
            )
            return
        if "\x00" in code:
            yield ValidationIssue("null_byte", "Source contains a null byte")
            return

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            yield ValidationIssue("syntax_error", str(exc.msg), exc.lineno)
            return
        except (ValueError, RecursionError, MemoryError) as exc:
            yield ValidationIssue("unparseable", f"Source could not be parsed: {exc}")
            return

        nodes = list(ast.walk(tree))
        if len(nodes) > self._settings.max_ast_nodes:
            yield ValidationIssue(
                "source_too_complex",
                f"Source exceeds {self._settings.max_ast_nodes} AST nodes",
            )
            return

        yield from self._check_module_level(tree)
        yield from self._check_scene_class(tree, scene_name)
        yield from self._check_nodes(nodes)

    def _check_module_level(self, tree: ast.Module) -> Iterator[ValidationIssue]:
        """Nothing at module level may execute when the file is imported.

        Definitions are fine — a `def` binds a name without running its body,
        and that body is walked like everything else. A literal assignment is
        fine for the same reason: no call, no attribute access. A bare
        expression or a call is not.
        """
        for node in tree.body:
            if isinstance(
                node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef)
            ):
                continue
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue  # docstring
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and _is_literal(
                node.value
            ):
                continue
            yield ValidationIssue(
                "module_level_statement",
                f"Only imports, definitions, and literal constants are allowed at "
                f"module level, found {type(node).__name__}",
                getattr(node, "lineno", None),
            )

    def _check_scene_class(
        self, tree: ast.Module, scene_name: str
    ) -> Iterator[ValidationIssue]:
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        if len(classes) != 1:
            yield ValidationIssue(
                "scene_class_count",
                f"Expected exactly one class, found {len(classes)}",
            )
            return
        scene = classes[0]
        if scene.name != scene_name:
            yield ValidationIssue(
                "scene_name_mismatch",
                f"Expected class {scene_name!r}, found {scene.name!r}",
                scene.lineno,
            )
        if scene.keywords or any(
            not isinstance(base, ast.Name) for base in scene.bases
        ):
            yield ValidationIssue(
                "unsupported_base",
                "Scene class must subclass a plain Manim scene name",
                scene.lineno,
            )
        else:
            bases = {base.id for base in scene.bases if isinstance(base, ast.Name)}
            if not bases or not bases <= ALLOWED_BASES:
                yield ValidationIssue(
                    "unsupported_base",
                    f"Scene class must subclass one of "
                    f"{', '.join(sorted(ALLOWED_BASES))}",
                    scene.lineno,
                )
        if not any(
            isinstance(node, ast.FunctionDef) and node.name == "construct"
            for node in scene.body
        ):
            yield ValidationIssue(
                "missing_construct",
                "Scene class must define a construct() method",
                scene.lineno,
            )

    def _check_nodes(self, nodes: list[ast.AST]) -> Iterator[ValidationIssue]:
        allowed_imports = frozenset(self._settings.allowed_imports)
        latex = self._settings.latex_available
        for node in nodes:
            line = getattr(node, "lineno", None)

            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root not in allowed_imports:
                        yield ValidationIssue(
                            "forbidden_import",
                            f"Import of {alias.name!r} is not allowed",
                            line,
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    yield ValidationIssue(
                        "relative_import", "Relative imports are not allowed", line
                    )
                    continue
                root = (node.module or "").split(".")[0]
                if root not in allowed_imports:
                    yield ValidationIssue(
                        "forbidden_import",
                        f"Import from {node.module!r} is not allowed",
                        line,
                    )
            elif isinstance(node, ast.Name):
                if node.id in FORBIDDEN_NAMES:
                    yield ValidationIssue(
                        "forbidden_name", f"Use of {node.id!r} is not allowed", line
                    )
                elif not latex and node.id in LATEX_NAMES:
                    yield ValidationIssue(
                        "latex_unavailable",
                        f"{node.id} requires LaTeX, which is not installed; "
                        f"{_USE_TEXT}",
                        line,
                    )
            elif isinstance(node, ast.keyword):
                if (
                    not latex
                    and node.arg in LATEX_KEYWORDS
                    and getattr(node.value, "value", False) is True
                ):
                    yield ValidationIssue(
                        "latex_unavailable",
                        f"{node.arg}=True renders labels with LaTeX, which is "
                        f"not installed; omit it and add Text labels instead",
                        line,
                    )
            elif isinstance(node, ast.Attribute):
                if node.attr.startswith("_"):
                    yield ValidationIssue(
                        "dunder_access",
                        f"Access to private attribute {node.attr!r} is not allowed",
                        line,
                    )
                elif node.attr in FORBIDDEN_ATTRIBUTES:
                    yield ValidationIssue(
                        "forbidden_attribute",
                        f"Access to {node.attr!r} is not allowed",
                        line,
                    )
                elif not latex and node.attr in LATEX_ATTRIBUTES:
                    yield ValidationIssue(
                        "latex_unavailable",
                        f"{node.attr}() builds LaTeX labels, which is not "
                        f"available; {_USE_TEXT}",
                        line,
                    )
            elif isinstance(node, ast.While):
                yield ValidationIssue(
                    "forbidden_loop",
                    "while loops are not allowed; use a bounded for loop",
                    line,
                )
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                yield ValidationIssue(
                    "forbidden_scope",
                    "global/nonlocal statements are not allowed",
                    line,
                )
            elif isinstance(
                node,
                (
                    ast.AsyncFunctionDef,
                    ast.AsyncFor,
                    ast.AsyncWith,
                    ast.Await,
                    ast.Yield,
                    ast.YieldFrom,
                ),
            ):
                yield ValidationIssue(
                    "forbidden_construct",
                    f"{type(node).__name__} is not allowed in a scene",
                    line,
                )


def _is_literal(node: ast.AST | None) -> bool:
    """True for constants and flat containers of them — nothing that can run."""
    if node is None:
        return False
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp):
        return _is_literal(node.operand)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_literal(element) for element in node.elts)
    if isinstance(node, ast.Dict):
        return all(_is_literal(key) for key in node.keys) and all(
            _is_literal(value) for value in node.values
        )
    return False
