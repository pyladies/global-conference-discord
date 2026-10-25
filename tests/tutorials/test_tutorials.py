from pathlib import Path
from types import SimpleNamespace

import pytest

from europython_discord.tutorials.cog import RegistrationStore, TutorialsCog
from europython_discord.tutorials.tutorial import load_tutorials

REPO_ROOT = Path(__file__).parents[2]


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "tutorials.toml"
    path.write_text(content)
    return path


def test_shipped_tutorials_file_is_valid() -> None:
    tutorials = load_tutorials(REPO_ROOT / "tutorials.toml")
    assert tutorials
    assert [t.date for t in tutorials] == sorted(t.date for t in tutorials)


def test_tutorials_are_sorted_and_get_local_time_markup(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        [[tutorial]]
        id = "b"
        title = "Second"
        presenters = ["A", "B"]
        date = 2026-10-27T10:00:00+00:00
        url = "https://example.com/b"

        [[tutorial]]
        id = "a"
        title = "First"
        presenters = ["C"]
        date = 2026-10-26T10:00:00+02:00
        url = "https://example.com/a"
        """,
    )
    first, second = load_tutorials(path)
    assert (first.id, second.id) == ("a", "b")
    assert first.local_time == "<t:1793001600:f>"
    assert second.presenters_text == "A, B"


def test_duplicated_ids_are_rejected(tmp_path: Path) -> None:
    entry = """
        [[tutorial]]
        id = "a"
        title = "T"
        presenters = ["A"]
        date = 2026-10-26T10:00:00+00:00
        url = "https://example.com"
    """
    with pytest.raises(ValueError, match="Duplicated"):
        load_tutorials(_write(tmp_path, entry + entry))


def test_dates_without_offset_are_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        [[tutorial]]
        id = "a"
        title = "T"
        presenters = ["A"]
        date = 2026-10-26T10:00:00
        url = "https://example.com"
        """,
    )
    with pytest.raises(ValueError, match="timezone"):
        load_tutorials(path)


def test_registrations_roundtrip_through_report_embeds() -> None:
    tutorials = load_tutorials(REPO_ROOT / "tutorials.toml")
    tutorial = tutorials[0]

    cog = TutorialsCog.__new__(TutorialsCog)
    cog.tutorials = tutorials
    cog.store = RegistrationStore()
    cog.store.registrations[tutorial.id] = {str(1000 + i): f"user.{i}_x" for i in range(300)}

    embeds = cog._report_embeds(tutorial)  # long list is split over several embeds
    assert len(embeds) > 1

    restored = TutorialsCog.__new__(TutorialsCog)
    restored.tutorials = tutorials
    restored.store = RegistrationStore()
    restored._restore_registrations([SimpleNamespace(embeds=embeds)])
    assert restored.store.registrations == cog.store.registrations


def test_register_and_unregister() -> None:
    store = RegistrationStore()
    user = SimpleNamespace(id=5, name="ana")
    store.set_user_registrations(user, {"a", "b"})
    assert store.registered_ids(5) == {"a", "b"}
    store.set_user_registrations(user, {"b"})
    assert store.registered_ids(5) == {"b"}
    store.set_user_registrations(user, set())
    assert store.registered_ids(5) == set()
