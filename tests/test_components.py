"""athena.component and athena.components: the standard and the manifest check, on an invented project. Each rule
has a negative control."""

from dataclasses import dataclass

import pytest

from athena.component import Component
from athena.components import check

CODE = '''
from athena.component import Component


class Double(Component):
    section = "04 Methods"

    class Input:
        pass

    class Output:
        pass

    def run(self, inp):
        return inp


def legacy_sum(xs):
    return sum(xs)
'''
TEST = "def test_double():\n    assert Double\n"


def write(tmp_path, manifest: str, code: str = CODE):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "steps.py").write_text(code)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_steps.py").write_text(TEST)
    (tmp_path / "components.yaml").write_text(manifest)
    return tmp_path


GOOD = """format: athena.components/1
covers: [pkg]
components:
  - {id: double, section: 04 Methods, entry: pkg/steps.py:Double, form: component, purpose: Doubles.,
     inputs: [a number], outputs: [a number], tests: [tests/test_steps.py::test_double], depends_on: [sum]}
  - {id: sum, section: 04 Methods, entry: pkg/steps.py:legacy_sum, form: legacy, purpose: Sums.,
     inputs: [numbers], outputs: [a number], tests: [], depends_on: []}
"""


def test_a_complete_manifest_passes(tmp_path):
    r = check(write(tmp_path, GOOD))
    assert r.errors == [] and (r.entries, r.components, r.modules) == (2, 1, 1)


def test_each_broken_rule_is_reported(tmp_path):
    bad = (GOOD.replace("pkg/steps.py:Double", "pkg/steps.py:Triple").replace("04 Methods, entry: pkg/steps.py:legacy",
           "11 Nowhere, entry: pkg/steps.py:legacy").replace("test_double]", "test_missing]")
           .replace("depends_on: [sum]", "depends_on: [nothing]"))
    errors = "\n".join(check(write(tmp_path, bad)).errors)
    for expected in ["no top-level 'Triple'", "not one of the nine", "test tests/test_steps.py::test_missing",
                     "depends on 'nothing'"]:
        assert expected in errors


def test_an_unlisted_module_under_covers_is_an_error(tmp_path):
    root = write(tmp_path, GOOD)
    (root / "pkg" / "extra.py").write_text("x = 1\n")
    assert any("pkg/extra.py" in e for e in check(root).errors)


def test_a_component_must_declare_its_section_input_and_output():
    with pytest.raises(TypeError, match="lacks"):
        class Broken(Component):  # noqa: F841
            def run(self, inp):
                return inp

    @dataclass(frozen=True)
    class In:
        x: int

    class Fine(Component):
        section = "03 Pipeline"
        Input = In
        Output = In

        def run(self, inp):
            return inp

    assert Fine().run(In(2)) == In(2)


def test_a_drafted_manifest_passes_the_check_and_keeps_reviewed_entries(tmp_path):
    from athena.components import draft
    head = "format: athena.components/1\ncovers: [pkg]\nsections: {pkg/: 04 Methods}\n"
    root = write(tmp_path, head + "components:\n  - {id: pkg.steps.legacy_sum, section: 04 Methods, entry: "
                 "pkg/steps.py:legacy_sum, form: legacy, purpose: Hand-written., inputs: [numbers], "
                 "outputs: [a number], tests: [], depends_on: [], reviewed: true}\n")
    doc = draft(root)
    by_id = {e["id"]: e for e in doc["components"]}
    assert by_id["pkg.steps.legacy_sum"]["purpose"] == "Hand-written."  # a reviewed entry is kept as written
    assert by_id["pkg.steps.Double"]["form"] == "component" and by_id["pkg.steps.Double"]["drafted"]
    assert by_id["pkg.steps.Double"]["tests"] == ["tests/test_steps.py::test_double"]
    assert check(root).errors == []


def test_a_module_of_constants_is_one_entry_naming_the_file(tmp_path):
    from athena.components import draft
    root = write(tmp_path, "format: athena.components/1\ncovers: [pkg]\nsections: {pkg/: 04 Methods}\n")
    (root / "pkg" / "limits.py").write_text('"""The limits."""\nLOW = 1\nHIGH: int = 9\n')
    by_id = {e["id"]: e for e in draft(root)["components"]}
    assert by_id["pkg.limits"]["entry"] == "pkg/limits.py" and by_id["pkg.limits"]["outputs"] == ["LOW", "HIGH"]
    assert by_id["pkg.limits"]["purpose"] == "The limits."
    assert check(root).errors == []
    (root / "pkg" / "limits.py").unlink()  # negative control: the file it names is gone
    assert any("pkg/limits.py does not exist" in e for e in check(root).errors)
