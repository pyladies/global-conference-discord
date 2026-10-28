from datetime import datetime, timedelta, timezone

import pytest

from europython_discord.program_notifications import session_to_embed
from europython_discord.program_notifications.models import Kind, Presenter, Room, Session, Slot
from europython_discord.program_notifications.session_to_embed import (
    _AUTHOR_WIDTH,
    _FIELD_VALUE_EMPTY,
    _SUMMARY_WIDTH,
    _TITLE_WIDTH,
    LevelColors,
)

SESSION_URL = "https://example.com/session"


@pytest.fixture
def session() -> Session:
    """Create a dummy session object."""
    return Session(
        slug="example-session",
        title="Example Session",
        kind=Kind(code="TALK", name="Talk"),
        is_content=True,
        level="BEGINNER",
        duration_minutes=60,
        summary_md="",
        slot=Slot(
            start=datetime.fromisoformat("2026-11-07T08:00:00+00:00"),
            end=datetime.fromisoformat("2026-11-07T09:00:00+00:00"),
            room=Room(name="Main Stream", discord_id="1253767145725235229"),
        ),
        presenters=[
            Presenter(name="Jane Doe", role="Speaker", headshot_url=None),
            Presenter(name="John Doe", role="Speaker", headshot_url=None),
        ],
    )


def test_embed_title_short(session: Session) -> None:
    """Test the title of the embed with a short title."""
    session.title = "Short Session Title"
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.title == "Short Session Title"


def test_embed_title_long(session: Session) -> None:
    """Test the title of the embed with a long title."""
    session.title = (
        "This is a long title which exceeds our maximum embed title length, "
        "so we expect it to be shortened by our session-to-embed converter. "
    )
    assert len(session.title) > _TITLE_WIDTH

    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.title == (
        "This is a long title which exceeds our maximum embed title length, "
        "so we expect it to be shortened by our session-to-embed [...]"
    )


def test_embed_title_with_markdown(session: Session) -> None:
    session.title = "A talk about __slots__ and *things*."
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.title == "A talk about \\_\\_slots\\_\\_ and \\*things\\*."


def test_embed_description_short(session: Session) -> None:
    """Test the description (summary) of the embed with a short summary."""
    session.summary_md = "Short summary."
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.description == f"Short summary.\n\n[Read more about this session]({SESSION_URL})"


def test_embed_description_without_url(session: Session) -> None:
    """Test the description (summary) of the embed when there is nowhere to link."""
    session.summary_md = "Short summary."
    embed = session_to_embed.create_session_embed(session, None)
    assert embed.description == "Short summary."


def test_embed_description_long(session: Session) -> None:
    """Test the description (summary) of the embed with a long summary."""
    session.summary_md = (
        "This is a long summary which exceeds our maximum embed description length, "
        "so we expect it to be shortened by our session-to-embed converter. Adding "
        "more text to make sure it exceeds the limit. And even more text. And more. "
    )
    assert len(session.summary_md) > _SUMMARY_WIDTH

    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.description == (
        "This is a long summary which exceeds our maximum embed description length, "
        "so we expect it to be shortened by our session-to-embed converter. Adding "
        "more text to make sure it exceeds the limit. [...]"
        f"\n\n[Read more about this session]({SESSION_URL})"
    )


def test_embed_description_empty(session: Session) -> None:
    """Test the description (summary) of the embed when summary is empty."""
    session.summary_md = ""
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.description is None


def test_embed_description_with_markdown(session: Session) -> None:
    session.summary_md = "A talk about __slots__ and *things*."
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.description == (
        "A talk about \\_\\_slots\\_\\_ and \\*things\\*.\n\n"
        f"[Read more about this session]({SESSION_URL})"
    )


def test_embed_url(session: Session) -> None:
    """Test the URL of the embed."""
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.url == SESSION_URL


def test_embed_url_none(session: Session) -> None:
    """Test the embed has no URL when there is nowhere to link."""
    embed = session_to_embed.create_session_embed(session, None)
    assert embed.url is None


@pytest.mark.parametrize(
    ("level", "expected_color"),
    [
        ("ALL", LevelColors.ALL.value),
        ("BEGINNER", LevelColors.BEGINNER.value),
        ("INTERMEDIATE", LevelColors.INTERMEDIATE.value),
        ("ADVANCED", LevelColors.ADVANCED.value),
    ],
)
def test_embed_color(session: Session, level: str, expected_color: int) -> None:
    """Test the color of the embed based on session level."""
    session.level = level
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.color.value == expected_color


@pytest.mark.parametrize("level", [None, "EXPERT"])
def test_embed_color_unknown_level(session: Session, level: str | None) -> None:
    """Test the embed has no color for a level without one."""
    session.level = level
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.color is None


def test_embed_fields_start_time(session: Session) -> None:
    """Test the 'Start Time' field of the embed."""
    start_time = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=6)))
    session.slot.start = start_time

    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.fields[0].name == "Start Time"
    assert embed.fields[0].value == f"<t:{int(start_time.timestamp())}>"


def test_embed_fields_room(session: Session) -> None:
    """Test the 'Stream' field of the embed."""
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.fields[1].name == "Stream"
    assert embed.fields[1].value == "Main Stream"


def test_embed_fields_room_all_rooms(session: Session) -> None:
    """Test the 'Stream' field of the embed for a session in all rooms."""
    session.slot.room = None
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.fields[1].name == "Stream"
    assert embed.fields[1].value == "All rooms"


def test_embed_fields_type(session: Session) -> None:
    """Test the 'Type' field of the embed."""
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.fields[2].name == "Type"
    assert embed.fields[2].value == "Talk"


def test_embed_fields_duration(session: Session) -> None:
    """Test the 'Duration' field of the embed."""
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.fields[3].name == "Duration"
    assert embed.fields[3].value == "60 minutes"


def test_embed_fields_duration_from_slot(session: Session) -> None:
    """Test the 'Duration' field comes from the slot when the session has none."""
    session.duration_minutes = None
    session.slot.end = session.slot.start + timedelta(minutes=45)
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.fields[3].value == "45 minutes"


def test_embed_fields_livestream_empty(session: Session) -> None:
    """Test the 'Livestream' field of the embed."""
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.fields[4].name == "Livestream"
    assert embed.fields[4].value == _FIELD_VALUE_EMPTY


def test_embed_fields_livestream_url(session: Session) -> None:
    """Test the 'Livestream' field of the embed."""
    session.youtube_url = "https://livestream.url"
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.fields[4].name == "Livestream"
    assert embed.fields[4].value == "[YouTube](https://livestream.url)"


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("ALL", "All levels"),
        ("BEGINNER", "Beginner"),
        ("INTERMEDIATE", "Intermediate"),
        ("ADVANCED", "Advanced"),
        (None, _FIELD_VALUE_EMPTY),
    ],
)
def test_embed_fields_level(session: Session, level: str | None, expected: str) -> None:
    """Test the 'Level' field of the embed."""
    session.level = level
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.fields[5].name == "Level"
    assert embed.fields[5].value == expected


def test_create_author_from_presenters(session: Session) -> None:
    """Test the author creation."""
    session.presenters[1].headshot_url = "https://example.com/headshot2.jpg"
    author = session_to_embed._create_author_from_presenters(session.presenters)

    # Should combine the names of all presenters
    assert author["name"] == "Jane Doe, John Doe"

    # Should use the headshot of the first presenter with one
    assert author["icon_url"] == "https://example.com/headshot2.jpg"


def test_create_author_from_presenters_with_no_headshot(session: Session) -> None:
    """Test the author creation with no headshot."""
    author = session_to_embed._create_author_from_presenters(session.presenters)
    assert author["icon_url"] is None


def test_create_author_with_long_name(session: Session) -> None:
    """Test the author creation when the presenter has a long name."""
    session.presenters[0].name = (
        "This is a very long speaker name which exceeds our maximum author name length, "
        "so we expect it to be shortened by our session-to-embed converter. "
    )
    assert len(session.presenters[0].name) > _AUTHOR_WIDTH

    author = session_to_embed._create_author_from_presenters(session.presenters)
    assert author["name"] == (
        "This is a very long speaker name which exceeds our maximum author name length, "
        "so we expect it to be shortened by our [...]"
    )


def test_create_author_without_presenters(session: Session) -> None:
    """Test the author creation when session has no presenters."""
    session.presenters = []
    author = session_to_embed._create_author_from_presenters(session.presenters)
    assert author is None

    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.author.name is None


def test_embed_footer(session: Session) -> None:
    """Test the footer of the embed."""
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.footer.text == "This session starts at 08:00 UTC"


def test_embed_footer_converts_to_utc(session: Session) -> None:
    """Test the footer shows UTC whatever the timezone of the start time."""
    session.slot.start = datetime(2026, 11, 7, 10, 0, tzinfo=timezone(timedelta(hours=2)))
    embed = session_to_embed.create_session_embed(session, SESSION_URL)
    assert embed.footer.text == "This session starts at 08:00 UTC"


def test_format_duration(session: Session) -> None:
    """Test the _format_duration function."""
    formatted_duration = session_to_embed._format_duration(session.duration)
    assert formatted_duration == "60 minutes"
