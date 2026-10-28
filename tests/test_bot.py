import pytest

from europython_discord.bot import _program_refresh_minutes


def test_program_refresh_minutes_default(monkeypatch):
    monkeypatch.delenv("PROGRAM_REFRESH_MINUTES", raising=False)
    assert _program_refresh_minutes() == 1


def test_program_refresh_minutes_from_env(monkeypatch):
    monkeypatch.setenv("PROGRAM_REFRESH_MINUTES", "2.5")
    assert _program_refresh_minutes() == 2.5


@pytest.mark.parametrize("value", ["abc", "0", "-1", "nan", "inf"])
def test_program_refresh_minutes_invalid(monkeypatch, value):
    monkeypatch.setenv("PROGRAM_REFRESH_MINUTES", value)
    with pytest.raises(RuntimeError, match="PROGRAM_REFRESH_MINUTES"):
        _program_refresh_minutes()
