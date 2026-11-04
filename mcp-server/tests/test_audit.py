"""Audit log: hash chain, tamper detection, redaction (incl. property tests)."""
import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from seance_mcp.audit import HIDDEN, REDACTED, AuditLog, redact

_S = dict(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])

_ops = st.lists(
    st.fixed_dictionaries(
        {
            "tool": st.sampled_from(["read_screen", "fill_field", "press_key", "confirm_action"]),
            "outcome": st.sampled_from(["ok", "error", "proposed", "expired"]),
            "value": st.one_of(st.none(), st.text(max_size=20)),
            "field_hidden": st.booleans(),
            "key": st.one_of(st.none(), st.sampled_from(["Enter", "PF3", "Clear"])),
        }
    ),
    min_size=1,
    max_size=15,
)


def _fresh() -> AuditLog:
    d = tempfile.mkdtemp()
    return AuditLog(Path(d) / "audit.jsonl")


@settings(max_examples=60, **_S)
@given(_ops)
def test_chain_verifies_for_any_operation_sequence(ops):
    log = _fresh()
    for op in ops:
        log.append(**op)
    assert log.verify() is None
    assert [e.seq for e in log.read()] == list(range(1, len(ops) + 1))
    # Re-opening a valid log continues the chain.
    again = AuditLog(log.path)
    again.append("read_screen", "ok")
    assert again.verify() is None


@settings(max_examples=100, **_S)
@given(_ops, st.data())
def test_any_single_byte_tamper_is_detected(ops, data):
    log = _fresh()
    for op in ops:
        log.append(**op)
    raw = bytearray(log.path.read_bytes())
    # Flip one byte that is not a line terminator.
    positions = [i for i, b in enumerate(raw) if b != 0x0A]
    i = data.draw(st.sampled_from(positions))
    raw[i] = (raw[i] + 1) % 256 if raw[i] != 0x09 else 0x20
    if raw[i] == 0x0A:
        raw[i] = 0x21
    log.path.write_bytes(bytes(raw))
    line_no = raw[:i].count(b"\n") + 1
    broken = log.verify()
    assert broken is not None and broken <= line_no


def test_deleting_or_reordering_lines_is_detected():
    log = _fresh()
    for n in range(4):
        log.append("read_screen", "ok", detail=str(n))
    lines = log.path.read_text(encoding="utf-8").splitlines()
    log.path.write_text("\n".join([lines[0], lines[2], lines[3]]) + "\n", encoding="utf-8")
    assert log.verify() == 2
    log.path.write_text("\n".join([lines[1], lines[0], *lines[2:]]) + "\n", encoding="utf-8")
    assert log.verify() == 1


def test_corrupted_utf8_is_reported_not_raised():
    log = _fresh()
    log.append("fill_field", "ok", value="caf\u00e9 \u2603")
    raw = bytearray(log.path.read_bytes())
    i = raw.index("\u2603".encode()[0])
    raw[i + 1] = 0x00  # break the multi-byte sequence
    log.path.write_bytes(bytes(raw))
    assert log.verify() == 1


def test_refuses_to_extend_a_tampered_log():
    log = _fresh()
    log.append("read_screen", "ok")
    entry = json.loads(log.path.read_text(encoding="utf-8"))
    entry["outcome"] = "error"
    log.path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        AuditLog(log.path)


def test_hidden_value_never_written():
    log = _fresh()
    log.append("fill_field", "ok", field="3", value="S3CR3T!", field_hidden=True)
    text = log.path.read_text(encoding="utf-8")
    assert "S3CR3T!" not in text
    assert log.read()[0].value == HIDDEN


@pytest.mark.parametrize("label", ["PASSWORD ===>", "Passwd:", "PIN", "Secret word", "API token"])
def test_credential_like_label_is_redacted(label):
    log = _fresh()
    log.append("fill_field", "ok", value="hunter2", field_label=label)
    assert "hunter2" not in log.path.read_text(encoding="utf-8")
    assert log.read()[0].value == REDACTED


def test_ordinary_label_keeps_value():
    log = _fresh()
    log.append("fill_field", "ok", value="P00123", field_label="POLICY NO ===>")
    assert log.read()[0].value == "P00123"


@settings(max_examples=200, deadline=None)
@given(st.text(max_size=30), st.booleans(), st.one_of(st.none(), st.text(max_size=20)))
def test_redaction_is_idempotent_and_never_leaks(value, hidden, label):
    once = redact(value, hidden=hidden, label=label)
    assert redact(once, hidden=hidden, label=label) == once
    if once in (HIDDEN, REDACTED) and value not in (HIDDEN, REDACTED):
        assert once != value
    if hidden:
        assert once == HIDDEN or value in (HIDDEN, REDACTED)
