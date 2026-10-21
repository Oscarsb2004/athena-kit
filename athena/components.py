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
    python -m athena.components draft <project folder>   # fill `components` from the code (see `draft`)
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


def _signature(fn: ast.AST) -> tuple[list[str], list[str]]:
    """A function's (or a class's `__init__`/`run`'s) parameters and return, as written in its annotations."""
    if isinstance(fn, ast.ClassDef):
        inner = {n.name: n for n in fn.body if isinstance(n, ast.FunctionDef)}
        fn = inner.get("run") or inner.get("__init__") or fn
        if isinstance(fn, ast.ClassDef):
            return ["(see the class)"], ["(see the class)"]
    args = [a for a in fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs if a.arg not in ("self", "cls")]
    ins = [f"{a.arg}: {ast.unparse(a.annotation)}" if a.annotation else a.arg for a in args] or ["(none)"]
    outs = [ast.unparse(fn.returns)] if fn.returns is not None else ["(not annotated: see the code)"]
    return ins, outs


def draft(root: Path) -> dict:
    """Fill a manifest's `components` from the code: one legacy entry per top-level public function or class of each
    module under `covers`. Its section comes from the manifest's `sections` (a path prefix to a section; the longest
    prefix wins), its purpose from the first line of its docstring, its inputs and output from its signature, its
    tests from the test functions that use its name, and its dependencies from the project names it imports. An
    entry marked `reviewed: true`, or of form `component`, is kept as written. Drafted entries say `drafted: true`."""
    path = root / "components.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    keep = {e["id"]: e for e in doc.get("components") or [] if e.get("reviewed") or e.get("form") == "component"}
    prefixes = sorted((doc.get("sections") or {}).items(), key=lambda kv: -len(kv[0]))
    ignored = {Path(p).as_posix() for p in doc.get("ignore") or []}
    files = []
    for cover in doc.get("covers") or []:
        target = root / cover
        files += [target] if target.is_file() else sorted(target.rglob("*.py"))
    used_in: dict[str, list[str]] = {}
    for test_file in sorted((root / doc.get("tests", "tests")).rglob("test_*.py")):
        tree = ast.parse(test_file.read_text(encoding="utf-8"))
        for fn in tree.body:
            if isinstance(fn, ast.FunctionDef) and fn.name.startswith("test_"):
                names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | {
                    n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
                for name in names:
                    used_in.setdefault(name, []).append(f"{test_file.relative_to(root).as_posix()}::{fn.name}")
    entries, by_name = [], {}
    for f in files:
        rel = f.relative_to(root).as_posix()
        if "__pycache__" in rel or f.name == "__init__.py" or rel in ignored:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        section = next((s for p, s in prefixes if rel.startswith(p)), "03 Pipeline")
        imported = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
                    and not n.module.startswith(("athena", "pandas", "numpy", "scipy")) for a in n.names}
        tops = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_")]
        if not tops:  # a module of constants or a script body: one entry for the module itself
            tops = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))][:1]
        for node in tops:
            eid = rel.removesuffix(".py").replace("/", ".") + "." + node.name
            ins, outs = _signature(node)
            purpose = (ast.get_docstring(node) or "").strip().split("\n")[0] or "(no docstring: to be written)"
            calls = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} & imported
            entry = {"id": eid, "section": section, "entry": f"{rel}:{node.name}",
                     "form": "component" if _is_component(node) else "legacy", "purpose": purpose,
                     "inputs": ins, "outputs": outs, "tests": sorted(set(used_in.get(node.name, [])))[:5],
                     "depends_on": sorted(calls), "drafted": True}
            entries.append(keep.get(eid, entry))
            by_name.setdefault(node.name, eid)
    for e in entries:  # a dependency is named by the id it resolves to, and dropped if it is not an entry
        if e.get("drafted"):
            e["depends_on"] = sorted({by_name[d] for d in e["depends_on"] if d in by_name and by_name[d] != e["id"]})
    doc["components"] = entries
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8",
                    newline="\n")
    return doc


def main(argv: list[str]) -> int:
    if argv[:1] == ["draft"] and len(argv) == 2:
        doc = draft(Path(argv[1]))
        print(f"drafted {sum(1 for e in doc['components'] if e.get('drafted'))} entries; "
              f"kept {sum(1 for e in doc['components'] if not e.get('drafted'))} as written")
        return 0
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
