from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import aiofiles
import aiohttp

from europython_discord.program_notifications.models import Program, Room, Session

_logger = logging.getLogger(__name__)


class ProgramConnector:
    def __init__(
        self,
        api_url: str,
        cache_file: Path,
        simulated_start_time: datetime | None = None,
        *,
        fast_mode: bool = False,
    ) -> None:
        self._api_url = api_url
        self._cache_file = cache_file

        # time travel parameters for testing
        self._simulated_start_time = simulated_start_time
        if self._simulated_start_time:
            self._time_multiplier = 60 if fast_mode else 1
            self._real_start_time = datetime.now(tz=UTC)

        self._fetch_lock = asyncio.Lock()
        self.sessions_by_day: dict[date, list[Session]] | None = None

    async def parse_schedule(self, schedule: dict) -> dict[date, list[Session]]:
        """Parse the portal's sessions and return them grouped by their UTC date.

        Breaks and other non-content slots are left out.
        """
        program: Program = Program.model_validate(schedule)

        sessions_by_day = {}
        for session in program.sessions:
            if not session.is_content:
                continue
            day = session.start.astimezone(UTC).date()
            sessions_by_day.setdefault(day, []).append(session)

        return sessions_by_day

    def get_rooms(self) -> list[Room]:
        """Rooms of the loaded schedule that have a Discord channel."""
        rooms = {}
        for sessions in (self.sessions_by_day or {}).values():
            for session in sessions:
                if session.room is not None and session.room.discord_id:
                    rooms.setdefault(session.room.discord_id, session.room)
        return list(rooms.values())

    async def fetch_schedule(self) -> None:
        """Fetch schedule data from the portal API and write it to a file as backup."""
        async with self._fetch_lock:
            try:
                async with (
                    aiohttp.ClientSession() as session,
                    session.get(self._api_url) as response,
                ):
                    response.raise_for_status()
                    schedule = await response.json()
                # parse before writing, so a payload the bot cannot read never replaces the cache
                sessions_by_day = await self.parse_schedule(schedule)

            # ValueError covers invalid JSON and a payload that fails validation
            except (aiohttp.ClientError, ValueError) as e:
                _logger.warning(f"Error fetching schedule: {e}.")

                if self.sessions_by_day is not None:
                    _logger.info("Schedule not updated, using the one loaded in memory.")
                    return

                self.sessions_by_day = await self._get_schedule_from_cache()
                _logger.info("Schedule loaded from cache file.")
                return

            _logger.info("Schedule fetched successfully.")

            # write schedule to file in case the API goes down
            _logger.info(f"Writing schedule to {self._cache_file}...")
            Path(self._cache_file).parent.mkdir(exist_ok=True, parents=True)
            async with aiofiles.open(self._cache_file, "w") as f:
                await f.write(json.dumps(schedule, indent=2))
            _logger.info("Schedule written to cache file.")

            self.sessions_by_day = sessions_by_day
            _logger.info("Schedule parsed and loaded.")

    async def _get_schedule_from_cache(self) -> dict[date, list[Session]] | None:
        """Get the schedule data from the cache file."""
        try:
            _logger.info(f"Getting schedule from cache file {self._cache_file}...")
            async with aiofiles.open(self._cache_file) as f:
                schedule = json.loads(await f.read())

            return await self.parse_schedule(schedule)

        except FileNotFoundError:
            _logger.exception("Schedule cache file not found and no schedule is already loaded.")
        except ValueError:
            _logger.exception("Schedule cache file cannot be read and no schedule is loaded.")
        return None

    async def _get_now(self) -> datetime:
        """Get the current time in the conference timezone."""
        if self._simulated_start_time:
            elapsed = datetime.now(tz=UTC) - self._real_start_time
            simulated_now = self._simulated_start_time + elapsed * self._time_multiplier
            return simulated_now.astimezone(UTC)

        return datetime.now(tz=UTC)

    async def get_sessions_by_date(self, date_now: date) -> list[Session]:
        if self.sessions_by_day is None:
            await self.fetch_schedule()

        sessions_on_day = []

        try:
            sessions_on_day = self.sessions_by_day[date_now]
        except KeyError:
            # debug to keep the logs clean,
            # because this is expected on non-conference days
            _logger.debug(f"No sessions found on {date_now}")
        except TypeError:
            _logger.exception("Schedule data is not loaded.")

        return sessions_on_day

    async def get_upcoming_sessions(self) -> list[Session]:
        # upcoming sessions are those that start in 5 minutes or less
        # and the start time is after the current time
        now = await self._get_now()

        if self._simulated_start_time:
            _logger.debug(f"Simulated time now: {now}")

        sessions = await self.get_sessions_by_date(now.date())
        # in the last minutes of a UTC day, the next sessions are on the next day
        soon = (now + timedelta(minutes=5)).date()
        if soon != now.date():
            sessions = sessions + await self.get_sessions_by_date(soon)

        return [
            session for session in sessions if now < session.start <= now + timedelta(minutes=5)
        ]
