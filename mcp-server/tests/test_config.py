import pytest
from pydantic import ValidationError

from seance_mcp.config import ConfirmMode, Settings


def test_defaults_are_safe():
    s = Settings.from_env({})
    assert s.allow_commit is False
    assert s.confirm_mode is ConfirmMode.ELICIT


def test_reads_env():
    s = Settings.from_env(
        {"SEANCE_ALLOW_COMMIT": "1", "SEANCE_CONFIRM_MODE": "oob", "TN3270_PORT": "3271"}
    )
    assert s.allow_commit is True and s.confirm_mode is ConfirmMode.OOB and s.port == 3271


@pytest.mark.parametrize("bad", ["yes", "true", "2"])
def test_allow_commit_must_be_0_or_1(bad):
    with pytest.raises(ValueError):
        Settings.from_env({"SEANCE_ALLOW_COMMIT": bad})


def test_unknown_confirm_mode_is_an_error_not_a_fallback():
    with pytest.raises(ValidationError):
        Settings.from_env({"SEANCE_CONFIRM_MODE": "auto"})


def test_ttl_must_be_positive():
    with pytest.raises(ValidationError):
        Settings.from_env({"PENDING_TTL_S": "0"})
