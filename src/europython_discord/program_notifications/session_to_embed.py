from __future__ import annotations

import textwrap
from datetime import UTC, datetime
from enum import Enum
from typing import Final

from discord import Embed
from discord.utils import escape_markdown, format_dt

from europython_discord.program_notifications.models import Presenter, Room, Session

_AUTHOR_WIDTH: Final = 128
_SUMMARY_WIDTH: Final = 200
_TITLE_WIDTH: Final = 128
_FIELD_VALUE_EMPTY: Final = "—"


class LevelColors(Enum):
    ALL = 0x4A90E2
    ADVANCED = 0xD34847
    INTERMEDIATE = 0xFFCD45
    BEGINNER = 0x63D452


def create_session_embed(session: Session, website_url: str | None) -> Embed:
    """Create a Discord embed for a conference session.

    :param session: The session information as provided by the portal
    :param website_url: Where the title and "Read more" link to, if anywhere
    :return: A Discord embed for this session
    """
    embed = Embed(
        title=_format_title(escape_markdown(session.title)),
        description=_create_description(session, website_url),
        url=website_url,
        color=_get_color(session.level),
    )

    embed.add_field(name="Start Time", value=format_dt(session.start), inline=True)
    embed.add_field(name="Stream", value=_format_room(session.room), inline=True)
    embed.add_field(name="Type", value=session.kind.name, inline=True)
    embed.add_field(name="Duration", value=_format_duration(session.duration), inline=True)
    #embed.add_field(name="Livestream", value=_format_live_stream(livestream_url), inline=True)
    embed.add_field(name="Livestream", value=_format_live_stream(session.youtube_url), inline=True)  # Add PyLadiesCon
    embed.add_field(name="Level", value=_format_level(session.level), inline=True)

    author = _create_author_from_presenters(session.presenters)
    if author:
        embed.set_author(name=author["name"], icon_url=author.get("icon_url"))

    embed.set_footer(text=_format_footer(session.start))

    return embed


def _create_author_from_presenters(presenters: list[Presenter]) -> dict | None:
    """Create a single embed author from the session presenters.

    :param presenters: A list of presenters
    :return: An author for a Discord embed
    """
    if not presenters:
        return None

    author_name = ", ".join(presenter.name for presenter in presenters)
    author_name = textwrap.shorten(author_name, width=_AUTHOR_WIDTH)
    icon_urls = [presenter.headshot_url for presenter in presenters if presenter.headshot_url]
    icon_url = icon_urls[0] if icon_urls else None

    return {"name": author_name, "icon_url": icon_url}


def _create_description(session: Session, website_url: str | None) -> str | None:
    """Create an embed description from the session summary.

    :param session: The session
    :param website_url: Where "Read more" links to, if anywhere
    :return: The embed description
    """
    if not session.summary_md:
        return None
    summary_short = textwrap.shorten(escape_markdown(session.summary_md), width=_SUMMARY_WIDTH)
    if not website_url:
        return summary_short
    return f"{summary_short}\n\n[Read more about this session]({website_url})"


def _format_title(title: str) -> str:
    """Format a session title for a Discord embed.

    :param title: The title
    :return: The title for an embed
    """
    return textwrap.shorten(title, width=_TITLE_WIDTH)


def _format_footer(start_time: datetime) -> str:
    """Create a footer with the local conference time.

    :param start_time: The start time
    :return: A footer text
    """
    formatted_time = start_time.astimezone(UTC).strftime("%H:%M")
    return f"This session starts at {formatted_time} UTC"


def _format_room(room: Room | None) -> str:
    """Format the room name for a Discord embed.

    :param room: The room, or None for a session in all rooms
    :return: The name of the room
    """
    return room.name if room else "All rooms"


def _format_level(level: str | None) -> str:
    """Format the audience level of a session.

    :param level: The level, such as "BEGINNER" or "ALL"
    :return: The level name or a placeholder value.
    """
    if not level:
        return _FIELD_VALUE_EMPTY
    if level.upper() == "ALL":
        return "All levels"
    return level.capitalize()


def _format_duration(duration: int) -> str:
    """Format the duration of a session.

    :param duration: The duration of a session
    :return: The duration in minutes
    """
    return f"{duration} minutes"


def _format_live_stream(livestream_url: str) -> str:
    """Format the livestream URL for the embed.

    :param livestream_url: The URL of the livestream
    :return: A formatted string for the livestream URL
    """
    return f"[YouTube]({livestream_url})" if livestream_url else _FIELD_VALUE_EMPTY


def _get_color(level: str | None) -> int | None:
    """Get the color for the embed based on the audience level.

    :param level: The expected audience level
    :return: A color (int), or None for a level without one
    """
    if not level or level.upper() not in LevelColors.__members__:
        return None
    return LevelColors[level.upper()].value
