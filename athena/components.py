"""A project's component manifest, `components.yaml`, and its check (Athena Charter L26, P112).

The manifest is the map a Cleaner will cut along: every component and every legacy function of the project, with
its section, entry, inputs, outputs, tests and dependencies.

    format: athena.components/1
    covers: [asi, verify, 02_panel.py]       # the folders and files every module of which must be listed
    ignore: [asi/__init__.py]                # modules deliberately left out, each a path
    components:
      - id: panel.window_value
        section: 03 Pipeline
        entry: asi/pipeline/panel.py:window_value     # file and top-level name
        form: legacy                                  # or component (a subclass of athena.component.Component)
        purpose: Derive each year's value from the observations at or before it.
        inputs: [observations table]
        outputs: [panel table]
        tests: [tests/test_panel_derived.py::test_a_rolling_mean_never_looks_forward]
        depends_on: []

The check reads the code without running it (Python's own parser), and fails when:
- an entry's file or name does not exist, or a `component` is not a class deriving from Component with `run`,
  `Input` and `Output`;
- a section is not one of the nine, an id repeats, a purpose, input or output is missing;
- a listed test does not exist, or a dependency names no listed id;
- a module under `covers` has no entry and is not ignored.

    python -m athena.components check <project folder>
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from athena.component import SECTIONS

FORMAT = "athena.components/1"
FORMS = ("component", "legacy")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    entries: int = 0
    components: int = 0
    modules: int = 0


def _names(tree: ast.Module) -> dict[str, ast.AST]:
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _is_component(node: ast.AST) -> bool:
    if not isinstance(node, ast.ClassDef):
        return False
    bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases}
    body = {n.name for n in node.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    return "Component" in bases and {"run", "Input", "Output"} <= body


def check(root: Path) -> Report:
    """Check a project's manifest against its code."""
    report = Report()
    path = root / "components.yaml"
    if not path.exists():
        report.errors.append("no components.yaml")
        return report
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if doc.get("format") != FORMAT:
        report.errors.append(f"components.yaml: format must be {FORMAT}")
    entries = doc.get("components") or []
    report.entries = len(entries)
    ids = [e.get("id") for e in entries]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        report.errors.append(f"{dup}: listed twice")
    trees: dict[Path, dict[str, ast.AST]] = {}

    def names_in(file: Path) -> dict[str, ast.AST] | None:
        if file not in trees:
            if not file.exists():
                return None
            trees[file] = _names(ast.parse(file.read_text(encoding="utf-8"), filename=str(file)))
        return trees[file]

    listed_files = set()
    for e in entries:
        who = e.get("id", "?")
        if e.get("section") not in SECTIONS:
            report.errors.append(f"{who}: section {e.get('section')!r} is not one of the nine")
        if e.get("form") not in FORMS:
            report.errors.append(f"{who}: form must be one of {FORMS}")
        for key in ("purpose", "inputs", "outputs"):
            if not e.get(key):
                report.errors.append(f"{who}: no {key}")
        file, _, name = str(e.get("entry", "")).partition(":")
        listed_files.add(Path(file).as_posix())
        found = names_in(root / file)
        if found is None:
            report.errors.append(f"{who}: {file} does not exist")
        elif name not in found:
            report.errors.append(f"{who}: {file} has no top-level {name!r}")
        elif e.get("form") == "component":
            report.components += 1
            if not _is_component(found[name]):
                report.errors.append(f"{who}: {name} is not a Component with run, Input and Output")
        for test in e.get("tests") or []:
            tfile, _, tname = test.partition("::")
            tnames = names_in(root / tfile)
            if tnames is None or (tname and tname not in tnames):
                report.errors.append(f"{who}: test {test} does not exist")
        for dep in e.get("depends_on") or []:
            if dep not in ids:
                report.errors.append(f"{who}: depends on {dep!r}, which is not listed")
    ignored = {Path(p).as_posix() for p in doc.get("ignore") or []}
    for cover in doc.get("covers") or []:
        target = root / cover
        files = [target] if target.is_file() else sorted(target.rglob("*.py"))
        for f in files:
            rel = f.relative_to(root).as_posix()
            if "__pycache__" in rel or f.name == "__init__.py" or rel in ignored:
                continue
            report.modules += 1
            if rel not in listed_files:
                report.errors.append(f"{rel}: a module under `covers` with no entry (list it, or ignore it)")
    return report


def main(argv: list[str]) -> int:
    if argv[:1] != ["check"] or len(argv) != 2:
        print(__doc__)
        return 2
    r = check(Path(argv[1]))
    for e in r.errors:
        print(f"ERROR   {e}")
    print(f"{r.entries} entries ({r.components} components) over {r.modules} modules; {len(r.errors)} errors")
    return 1 if r.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
