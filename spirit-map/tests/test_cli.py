import argparse

import anyio

from seance_mcp.fake import fake_insurance
from seance_spirit.__main__ import _target, main

ENV = {"TN3270_HOST": "mainframe.example", "TN3270_PORT": "3271"}


def ns(**kw) -> argparse.Namespace:
    return argparse.Namespace(**kw)


def test_env_is_ignored_unless_asked() -> None:
    assert _target(ns(), ENV) == ("localhost", 3270)
    assert _target(ns(from_env=False, host=None, port=None), ENV) == ("localhost", 3270)


def test_from_env_reads_host_and_port() -> None:
    assert _target(ns(from_env=True), ENV) == ("mainframe.example", 3271)
    assert _target(ns(from_env=True), {}) == ("localhost", 3270)


def test_explicit_flags_win_over_env() -> None:
    assert _target(ns(from_env=True, host="h", port=9), ENV) == ("h", 9)
    assert _target(ns(host="h2"), ENV) == ("h2", 3270)


def test_explore_passes_the_target_to_connect(monkeypatch, tmp_path) -> None:
    """End to end through main(): the fake records the host/port it was connected with."""
    import shutil
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "docs" / "spirit-map" / "fake-insurance"
    d = tmp_path / "fake-insurance"
    d.mkdir()
    shutil.copy(src / "explore.seed.json", d / "explore.seed.json")
    app = fake_insurance()
    monkeypatch.setattr("seance_spirit.__main__._port", lambda args: app)
    monkeypatch.setenv("TN3270_HOST", "should-be-ignored")
    monkeypatch.setenv("TN3270_PORT", "1")
    assert main(["explore", "--app", "fake-insurance", "--dir", str(d)]) == 0
    assert ("connect", "localhost", 3270) in app.calls
    app2 = fake_insurance()
    monkeypatch.setattr("seance_spirit.__main__._port", lambda args: app2)
    assert main(["explore", "--app", "fake-insurance", "--dir", str(d), "--host", "h", "--port", "7"]) == 0
    assert ("connect", "h", 7) in app2.calls
    app3 = fake_insurance()
    monkeypatch.setattr("seance_spirit.__main__._port", lambda args: app3)
    assert main(["explore", "--app", "fake-insurance", "--dir", str(d), "--from-env"]) == 0
    assert ("connect", "should-be-ignored", 1) in app3.calls
