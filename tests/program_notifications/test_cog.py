from __future__ import annotations

import json
from pathlib import Path

import pytest

from europython_discord.program_notifications.cog import ProgramNotificationsCog
from europython_discord.program_notifications.config import ProgramNotificationsConfig
from europython_discord.program_notifications.models import Room

mock_schedule_file = Path(__file__).parent / "mock_schedule.json"

MAIN_ID = 1253767145725235229
ACTIVITIES_ID = 1253767145725235230


class FakeChannel:
    def __init__(self, name: str) -> None:
        self.name = name
        self.sent = []
        self.purged = False

    async def send(self, content=None, embed=None) -> None:
        self.sent.append((content, embed))

    async def purge(self) -> None:
        self.purged = True


class FakeBot:
    def __init__(self, channels: dict[int, FakeChannel]) -> None:
        self.channels = channels

    def get_channel(self, channel_id: int) -> FakeChannel | None:
        return self.channels.get(channel_id)

    def get_all_channels(self) -> list[FakeChannel]:
        return list(self.channels.values())


@pytest.fixture
def channels():
    return {
        1: FakeChannel("session-notifications"),
        MAIN_ID: FakeChannel("main-stream"),
        ACTIVITIES_ID: FakeChannel("activities-open-spaces"),
    }


@pytest.fixture
def config(tmp_path):
    return ProgramNotificationsConfig(
        api_base_url="https://portal.example/api/v1/",
        schedule_cache_file=tmp_path / "cache.json",
        livestream_url_file=tmp_path / "livestreams.toml",
        main_notification_channel_name="session-notifications",
        session_url="https://example.com/schedule/#{slug}",
    )


@pytest.fixture
async def cog(channels, config):
    cog = ProgramNotificationsCog(FakeBot(channels), config, "pyladiescon-2026")
    with mock_schedule_file.open() as f:
        schedule = json.load(f)
    connector = cog.program_connector
    connector.sessions_by_day = await connector.parse_schedule(schedule)
    return cog


def upcoming(cog, monkeypatch, *slugs):
    sessions = [
        session
        for sessions in cog.program_connector.sessions_by_day.values()
        for session in sessions
        if session.slug in slugs
    ]

    async def get_upcoming_sessions():
        return sessions

    monkeypatch.setattr(cog.program_connector, "get_upcoming_sessions", get_upcoming_sessions)
    return sessions


def test_api_url_from_conference(cog):
    assert (
        cog.program_connector._api_url
        == "https://portal.example/api/v1/pyladiescon-2026/sessions/"
    )


async def test_session_in_a_room(cog, channels, monkeypatch):
    upcoming(cog, monkeypatch, "testing-in-python")

    await cog.notify_sessions.coro(cog)

    main = channels[1].sent
    assert main[0] == ("# Sessions starting in 5 minutes:", None)
    assert main[1][1].title == "Testing in Python"
    assert main[1][1].url == "https://example.com/schedule/#testing-in-python"
    assert [content for content, _ in channels[MAIN_ID].sent] == [
        "# Starting in 5 minutes @ Main Stream"
    ]
    assert channels[ACTIVITIES_ID].sent == []


async def test_session_in_all_rooms(cog, channels, monkeypatch):
    upcoming(cog, monkeypatch, "opening-keynote")

    await cog.notify_sessions.coro(cog)

    assert len(channels[1].sent) == 2
    for channel_id in (MAIN_ID, ACTIVITIES_ID):
        assert [content for content, _ in channels[channel_id].sent] == [
            "# Starting in 5 minutes @ all rooms"
        ]


async def test_nothing_upcoming(cog, channels, monkeypatch):
    upcoming(cog, monkeypatch)

    await cog.notify_sessions.coro(cog)

    assert channels[1].sent == []


async def test_edited_session_is_not_posted_again(cog, channels, monkeypatch):
    sessions = upcoming(cog, monkeypatch, "testing-in-python")
    await cog.notify_sessions.coro(cog)

    edited = sessions[0].model_copy(update={"youtube_url": "https://youtube.com/watch?v=x"})

    async def get_upcoming_sessions():
        return [edited]

    monkeypatch.setattr(cog.program_connector, "get_upcoming_sessions", get_upcoming_sessions)
    await cog.notify_sessions.coro(cog)

    assert len(channels[MAIN_ID].sent) == 1


async def test_room_with_a_bad_id_is_skipped(cog, channels, monkeypatch):
    sessions = upcoming(cog, monkeypatch, "testing-in-python", "intro-to-pandas")
    sessions[0].slot.room.discord_id = "main-stream"

    await cog.notify_sessions.coro(cog)

    assert channels[MAIN_ID].sent == []
    assert len(channels[ACTIVITIES_ID].sent) == 1
    assert len(channels[1].sent) == 3


@pytest.mark.parametrize(
    ("discord_id", "reason"),
    [(None, "No Discord channel id"), ("42", "not found"), ("main-stream", "not a number")],
)
def test_get_room_channel_missing(cog, caplog, discord_id, reason):
    assert cog._get_room_channel(Room(name="Main Stream", discord_id=discord_id)) is None
    assert reason in caplog.text


def test_get_room_channel(cog, channels):
    room = Room(name="Main Stream", discord_id=str(MAIN_ID))
    assert cog._get_room_channel(room) is channels[MAIN_ID]


async def test_purge_all_room_channels(cog, channels):
    await cog.purge_all_room_channels()

    assert channels[MAIN_ID].purged
    assert channels[ACTIVITIES_ID].purged
    assert not channels[1].purged


async def test_purge_fetches_the_schedule_first(cog, channels, monkeypatch):
    loaded = cog.program_connector.sessions_by_day
    cog.program_connector.sessions_by_day = None

    async def fetch_schedule():
        cog.program_connector.sessions_by_day = loaded

    monkeypatch.setattr(cog.program_connector, "fetch_schedule", fetch_schedule)
    await cog.purge_all_room_channels()

    assert channels[MAIN_ID].purged


def test_session_url_without_config(cog):
    cog.config.session_url = None
    session = next(iter(cog.program_connector.sessions_by_day.values()))[0]
    assert cog._session_url(session) is None


async def test_refresh_interval(channels, config, monkeypatch):
    cog = ProgramNotificationsCog(
        FakeBot(channels), config, "pyladiescon-2026", refresh_minutes=2.5
    )

    async def fetch_schedule():
        pass

    monkeypatch.setattr(cog.program_connector, "fetch_schedule", fetch_schedule)
    await cog.cog_load()
    try:
        assert cog.fetch_schedule.minutes == 2.5
    finally:
        cog.fetch_schedule.cancel()
