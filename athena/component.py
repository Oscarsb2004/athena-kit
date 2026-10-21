"""The component standard (Athena Charter L26, P112): object-oriented components with declared input and output.

A component is a class that does one thing, written so that a Cleaner can later lift it out whole:
- `section`: the project section it belongs to, one of SECTIONS;
- `Input` and `Output`: frozen dataclasses naming everything it takes and returns (a table is described by its
  pandera schema in the common format);
- one public entry, `run(inp) -> Output`;
- no hidden I/O: only components whose purpose is reading or writing touch files or the network, and they say so;
- a test on a synthetic fixture, with a negative control.

Pure helpers a component calls stay functions. Working code written before the standard is not rewritten; it is
listed as `legacy` in the project's `components.yaml` (athena.components), with its inputs and outputs, so the map
exists before anything is cut.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

SECTIONS = ("00 Overview", "01 Goals and Rulings", "02 Inputs and Sources", "03 Pipeline", "04 Methods",
            "05 Verification", "06 Outputs and Site", "07 Lessons", "08 Status and Roadmap")


class Component(ABC):
    """One step with declared input and output. Subclasses define `section`, `Input`, `Output` and `run`."""

    section: ClassVar[str]
    Input: ClassVar[type]
    Output: ClassVar[type]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "__abstractmethods__", None):
            return  # an intermediate abstract class
        missing = [k for k in ("section", "Input", "Output") if not hasattr(cls, k)]
        if missing:
            raise TypeError(f"{cls.__name__} lacks {missing}: a component declares its section, Input and Output")
        if cls.section not in SECTIONS:
            raise TypeError(f"{cls.__name__}: section {cls.section!r} is not one of the nine")

    @abstractmethod
    def run(self, inp: Any) -> Any:
        """Turn the Input into the Output."""
