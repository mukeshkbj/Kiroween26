"""The labels artefact (`gss.labels/1`): business meaning with confidence, stored apart from
the map. Labels never configure safety (REQ-017); the generator reads them, the explorer and
the key policy never do.

All strings here are sanitised: control characters stripped, length-capped, and identifiers
forced to ``[a-z][a-z0-9_]*``. A label that fails validation is dropped and the heuristic one
stands (REQ-016).
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA = "gss.labels/1"
NODE_KINDS = ("menu", "enquiry", "list", "form", "confirm", "error", "other")
FIELD_ROLES = ("identifier", "display", "input", "selector", "status", "other")
MIN_CONFIDENCE = 0.6

_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_WS = re.compile(r"\s+")


def clean_text(text: str, *, max_len: int = 200) -> str:
    """Strip control chars, collapse whitespace, cap length. Screen text is data; this makes
    sure a label can never carry newlines or escapes into an artefact or a prompt echo."""
    return _WS.sub(" ", _CTRL.sub(" ", text or "")).strip()[:max_len]


def snake(text: str, *, max_len: int = 40) -> str:
    """Force an identifier to ``[a-z][a-z0-9_]*`` (REQ-016)."""
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    key = "_".join(w.lower() for w in words)[:max_len].strip("_")
    if not key or not key[0].isalpha():
        key = ("x_" + key).strip("_") if key else "x"
    return key


class _M(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


def _confidence(v: object) -> float:
    try:
        return max(0.0, min(1.0, float(v)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


class NodeLabel(_M):
    name: str = Field(max_length=80)
    kind: str = "other"
    purpose: str = Field(default="", max_length=200)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v: object) -> float:
        return _confidence(v)

    @field_validator("name", "purpose", mode="before")
    @classmethod
    def _clean(cls, v: object) -> str:
        if not isinstance(v, (str, int, float)):
            raise ValueError("expected a string")
        return clean_text(str(v))

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        return s if s in NODE_KINDS else "other"

    @property
    def needs_review(self) -> bool:
        return self.confidence < MIN_CONFIDENCE


class FieldLabel(_M):
    business_name: str = Field(max_length=80)
    role: str = "other"
    data_type: str = Field(default="string", max_length=20)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v: object) -> float:
        return _confidence(v)

    @field_validator("business_name", mode="before")
    @classmethod
    def _clean(cls, v: object) -> str:
        if not isinstance(v, (str, int, float)):
            raise ValueError("expected a string")
        return clean_text(str(v))

    @field_validator("role", mode="before")
    @classmethod
    def _role(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        return s if s in FIELD_ROLES else "other"

    @field_validator("data_type", mode="before")
    @classmethod
    def _dt(cls, v: object) -> str:
        return snake(str(v or "string"), max_len=20) or "string"

    @property
    def needs_review(self) -> bool:
        return self.confidence < MIN_CONFIDENCE


class EdgeLabel(_M):
    meaning: str = Field(default="", max_length=120)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v: object) -> float:
        return _confidence(v)

    @field_validator("meaning", mode="before")
    @classmethod
    def _clean(cls, v: object) -> str:
        if not isinstance(v, (str, int, float)):
            raise ValueError("expected a string")
        return clean_text(str(v), max_len=120)


class Labels(_M):
    model_config = ConfigDict(extra="ignore")

    schema_: str = Field(default=SCHEMA, alias="schema")
    app_id: str
    map_hash: str = ""
    source: str = "heuristic"
    nodes: dict[str, NodeLabel] = {}
    fields: dict[str, FieldLabel] = {}  # key "<node_id>:<field_key>"
    edges: dict[str, EdgeLabel] = {}
    dropped: list[str] = []  # ids whose model output failed validation (heuristic kept)

    def node(self, node_id: str) -> NodeLabel | None:
        return self.nodes.get(node_id)

    def field(self, node_id: str, field_key: str) -> FieldLabel | None:
        return self.fields.get(f"{node_id}:{field_key}")

    def edge(self, edge_id: str) -> EdgeLabel | None:
        return self.edges.get(edge_id)
