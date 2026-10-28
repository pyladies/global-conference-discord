import asyncio
import json
from datetime import UTC, date, datetime
from http import HTTPStatus
from pathlib import Path

import aiofiles
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from europython_discord.program_notifications.program_connector import ProgramConnector

mock_schedule_file = Path(__file__).parent / "mock_schedule.json"


@pytest.fixture
def mock_schedule():
    with mock_schedule_file.open() as f:
        return json.load(f)


@pytest.fixture
def cache_file(tmp_path):
    return tmp_path / "cache.json"


@pytest.fixture
async def program_connector(cache_file):
    return ProgramConnector(api_url="http://test.api/schedule", cache_file=cache_file)


@pytest.fixture
async def mock_client(aiohttp_client, unused_tcp_port_factory, mock_schedule):
    async def mock_api_handler(request):  # noqa: ARG001 (unused argument)
        return web.json_response(mock_schedule)

    app = web.Application()
    app.router.add_get("/schedule", mock_api_handler)

    server = TestServer(app, port=unused_tcp_port_factory())
    return await aiohttp_client(server)


@pytest.fixture
async def mock_schedule_url(mock_client):
    return str(mock_client.make_url("/schedule"))


@pytest.mark.asyncio
async def test_parse_schedule(program_connector, mock_schedule):
    sessions_by_day = await program_connector.parse_schedule(mock_schedule)

    assert len(sessions_by_day) == 3

    # the break is left out
    assert len(sessions_by_day[date(2026, 11, 7)]) == 3
    assert len(sessions_by_day[date(2026, 11, 8)]) == 2
    assert len(sessions_by_day[date(2026, 11, 9)]) == 1


@pytest.mark.asyncio
async def test_parse_schedule_empty_program(program_connector, mock_schedule):
    mock_schedule["program"] = "internal"
    mock_schedule["sessions"] = []

    assert await program_connector.parse_schedule(mock_schedule) == {}


@pytest.mark.asyncio
async def test_fetch_schedule(program_connector, mock_schedule_url, cache_file, mock_schedule):
    program_connector._api_url = mock_schedule_url

    await program_connector.fetch_schedule()

    async with aiofiles.open(cache_file) as f:
        cached_data = json.loads(await f.read())
        assert cached_data == mock_schedule


@pytest.mark.asyncio
async def test_get_schedule_from_cache(program_connector, mock_schedule, cache_file):
    async with aiofiles.open(cache_file, "w") as f:
        await f.write(json.dumps(mock_schedule))

    sessions_by_day = await program_connector._get_schedule_from_cache()

    assert len(sessions_by_day) == 3
    assert len(sessions_by_day[date(2026, 11, 7)]) == 3
    assert len(sessions_by_day[date(2026, 11, 8)]) == 2
    assert len(sessions_by_day[date(2026, 11, 9)]) == 1


@pytest.mark.asyncio
async def test_get_sessions_by_date(program_connector, mock_schedule_url):
    program_connector._api_url = mock_schedule_url

    await program_connector.fetch_schedule()

    sessions = await program_connector.get_sessions_by_date(date(2026, 11, 7))
    assert [session.title for session in sessions] == [
        "Opening Keynote",
        "Testing in Python",
        "Intro to pandas",
    ]

    sessions = await program_connector.get_sessions_by_date(date(2026, 11, 8))
    assert [session.title for session in sessions] == [
        "Packaging Python",
        "Late Night Lightning Talks",
    ]

    sessions = await program_connector.get_sessions_by_date(date(2026, 11, 9))
    assert [session.title for session in sessions] == ["Closing"]

    # Test for a day with no sessions
    sessions = await program_connector.get_sessions_by_date(date(2026, 11, 10))
    assert len(sessions) == 0


@pytest.mark.asyncio
async def test_get_upcoming_sessions(program_connector, mock_schedule_url):
    program_connector._api_url = mock_schedule_url

    await program_connector.fetch_schedule()

    program_connector._real_start_time = datetime.now(tz=UTC)
    program_connector._time_multiplier = 1

    # Test with a simulated time in 5 minutes range before a session in all rooms
    program_connector._simulated_start_time = datetime(2026, 11, 7, 13, 57, 0, tzinfo=UTC)
    upcoming_sessions = await program_connector.get_upcoming_sessions()
    assert [session.title for session in upcoming_sessions] == ["Opening Keynote"]
    assert upcoming_sessions[0].room is None

    # Test with a simulated time in 5 minutes range where there are 2 upcoming sessions
    program_connector._simulated_start_time = datetime(2026, 11, 7, 14, 41, 0, tzinfo=UTC)
    upcoming_sessions = await program_connector.get_upcoming_sessions()
    assert len(upcoming_sessions) == 2

    # Test with a simulated time before any session in the mock schedule
    program_connector._simulated_start_time = datetime(2026, 11, 7, 13, 0, 0, tzinfo=UTC)
    upcoming_sessions = await program_connector.get_upcoming_sessions()
    assert len(upcoming_sessions) == 0

    # Test with a simulated time after all sessions in the mock schedule
    program_connector._simulated_start_time = datetime(2026, 11, 9, 11, 0, 0, tzinfo=UTC)
    upcoming_sessions = await program_connector.get_upcoming_sessions()
    assert len(upcoming_sessions) == 0

    # Test with a simulated time in 5 minutes range before a break
    program_connector._simulated_start_time = datetime(2026, 11, 7, 14, 26, 0, tzinfo=UTC)
    upcoming_sessions = await program_connector.get_upcoming_sessions()
    assert len(upcoming_sessions) == 0


@pytest.mark.asyncio
async def test_get_rooms(program_connector, mock_schedule):
    assert program_connector.get_rooms() == []

    program_connector.sessions_by_day = await program_connector.parse_schedule(mock_schedule)

    rooms = program_connector.get_rooms()
    assert [room.name for room in rooms] == ["Main Stream", "Activities & Open Spaces"]
    assert rooms[0].discord_id == "1253767145725235229"


@pytest.mark.asyncio
async def test_get_rooms_skips_rooms_without_discord_id(program_connector, mock_schedule):
    for session in mock_schedule["sessions"]:
        room = session["slot"]["room"]
        if room and room["name"] == "Main Stream":
            room["discord_id"] = None

    program_connector.sessions_by_day = await program_connector.parse_schedule(mock_schedule)

    assert [room.name for room in program_connector.get_rooms()] == ["Activities & Open Spaces"]


@pytest.mark.asyncio
async def test_fetch_schedule_error_handling(
    program_connector, unused_tcp_port_factory, aiohttp_client
):
    async def mock_api_handler(request):  # noqa: ARG001 (unused argument)
        return web.Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    app = web.Application()
    app.router.add_get("/schedule", mock_api_handler)

    server = TestServer(app, port=unused_tcp_port_factory())
    client = await aiohttp_client(server)

    program_connector._api_url = str(client.make_url("/schedule"))

    await program_connector.fetch_schedule()

    assert program_connector.sessions_by_day is None


@pytest.mark.asyncio
async def test_get_sessions_by_date_with_empty_schedule(program_connector):
    sessions = await program_connector.get_sessions_by_date(date(2026, 11, 7))
    assert len(sessions) == 0


@pytest.mark.asyncio
async def test_get_now_with_simulation(program_connector):
    simulated_start_time = datetime(2026, 11, 7, 14, 0, 0, tzinfo=UTC)
    program_connector._simulated_start_time = simulated_start_time
    program_connector._real_start_time = datetime.now(tz=UTC)
    program_connector._time_multiplier = 60

    # ensure time is ticking between start and finish of this test
    await asyncio.sleep(0.001)

    assert await program_connector._get_now() > simulated_start_time


@pytest.mark.asyncio
async def test_get_now_without_simulation(program_connector):
    now = await program_connector._get_now()

    # ensure time is ticking between start and finish of this test
    await asyncio.sleep(0.001)

    assert datetime.now(tz=UTC) > now


@pytest.mark.asyncio
async def test_get_upcoming_sessions_across_midnight(program_connector, mock_schedule):
    midnight = {
        **mock_schedule["sessions"][2],
        "slug": "midnight-talk",
        "title": "Midnight Talk",
        "slot": {
            "start": "2026-11-08T00:00:00Z",
            "end": "2026-11-08T00:30:00Z",
            "room": mock_schedule["sessions"][2]["slot"]["room"],
        },
    }
    mock_schedule["sessions"].append(midnight)
    program_connector.sessions_by_day = await program_connector.parse_schedule(mock_schedule)

    program_connector._simulated_start_time = datetime(2026, 11, 7, 23, 57, 0, tzinfo=UTC)
    program_connector._real_start_time = datetime.now(tz=UTC)
    program_connector._time_multiplier = 1

    upcoming_sessions = await program_connector.get_upcoming_sessions()
    assert [session.title for session in upcoming_sessions] == ["Midnight Talk"]


@pytest.mark.asyncio
async def test_fetch_schedule_invalid_payload_keeps_schedule(
    program_connector, mock_schedule_url, cache_file, mock_schedule, aiohttp_client,
    unused_tcp_port_factory,
):
    program_connector._api_url = mock_schedule_url
    await program_connector.fetch_schedule()
    loaded = program_connector.sessions_by_day

    async def bad_api_handler(request):  # noqa: ARG001 (unused argument)
        return web.json_response({"sessions": [{"slug": "x"}]})

    app = web.Application()
    app.router.add_get("/schedule", bad_api_handler)
    client = await aiohttp_client(TestServer(app, port=unused_tcp_port_factory()))
    program_connector._api_url = str(client.make_url("/schedule"))

    await program_connector.fetch_schedule()

    assert program_connector.sessions_by_day is loaded
    async with aiofiles.open(cache_file) as f:
        assert json.loads(await f.read()) == mock_schedule


@pytest.mark.asyncio
async def test_fetch_schedule_invalid_json_falls_back_to_cache(
    program_connector, cache_file, mock_schedule, aiohttp_client, unused_tcp_port_factory
):
    async with aiofiles.open(cache_file, "w") as f:
        await f.write(json.dumps(mock_schedule))

    async def bad_api_handler(request):  # noqa: ARG001 (unused argument)
        return web.Response(text="not json", content_type="application/json")

    app = web.Application()
    app.router.add_get("/schedule", bad_api_handler)
    client = await aiohttp_client(TestServer(app, port=unused_tcp_port_factory()))
    program_connector._api_url = str(client.make_url("/schedule"))

    await program_connector.fetch_schedule()

    assert len(program_connector.sessions_by_day[date(2026, 11, 7)]) == 3


@pytest.mark.asyncio
async def test_get_schedule_from_unreadable_cache(program_connector, cache_file):
    async with aiofiles.open(cache_file, "w") as f:
        await f.write(json.dumps({"days": {}}))

    assert await program_connector._get_schedule_from_cache() is None
