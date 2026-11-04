"""Reading and writing artefacts: atomic, canonical, and leak-checked on every write.

A leak is a hard error, never a warning: a hidden-field sentinel (or any caller
supplied secret string) in the output, or a hidden / credential-labelled field whose
screen cells are not blank in a stored node.
"""
from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .graph import SpiritMap
from .ids import looks_credential


class LeakError(Exception):
    """An artefact would contain a hidden value or a credential-labelled value."""


def dumps(obj: Any) -> str:
    """Canonical JSON: sorted keys, 2-space indent, trailing newline, unicode kept."""
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def check_text(text: str, sentinels: Iterable[str]) -> None:
    for s in sentinels:
        if s and s in text:
            raise LeakError("a hidden-value sentinel is present in the output; nothing was written")


def check_map(m: SpiritMap) -> None:
    """Structural check: cells of hidden and credential-labelled fields are blank in node rows."""
    for n in m.nodes:
        for f in n.fields:
            if not (f.hidden or looks_credential(f.label)):
                continue
            start, end = f.span
            for pos in range(start, min(end, 1920)):
                if n.rows[pos // 80][pos % 80] != " ":
                    raise LeakError(f"node {n.id}: cells of field {f.key!r} are not blank")


def map_to_obj(m: SpiritMap) -> dict[str, Any]:
    return m.canonical().model_dump(by_alias=True, mode="json")


def write_json(path: Path, obj: Any, sentinels: Iterable[str] = ()) -> None:
    """Atomically write canonical JSON. Leak-checks the exact bytes that would be written."""
    text = dumps(obj)
    check_text(text, sentinels)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_map(path: Path, m: SpiritMap, sentinels: Iterable[str] = ()) -> None:
    check_map(m)
    write_json(path, map_to_obj(m), sentinels)


def read_map(path: Path) -> SpiritMap:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return SpiritMap.model_validate(raw)
