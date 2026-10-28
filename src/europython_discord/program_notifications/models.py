from __future__ import annotations

from datetime import timedelta

from pydantic import AwareDatetime, BaseModel


class Program(BaseModel):
    """Response of the PyLadiesCon portal's sessions endpoint."""

    sessions: list[Session]


class Kind(BaseModel):
    """Session type, such as a talk or a break."""

    code: str
    name: str


class Room(BaseModel):
    """Room of a slot, with the Discord channel the bot posts in."""

    name: str
    url: str | None = None
    discord_id: str | None = None


class Slot(BaseModel):
    """Where and when a session is on the schedule. No room means all rooms."""

    start: AwareDatetime
    end: AwareDatetime
    room: Room | None


class Presenter(BaseModel):
    """Presenter of a Session."""

    name: str
    role: str
    headshot_url: str | None = None


class Session(BaseModel):
    """Session in the PyLadiesCon schedule."""

    slug: str
    title: str
    kind: Kind
    is_content: bool
    level: str | None
    duration_minutes: int | None
    summary_md: str = ""
    youtube_url: str | None = None
    slot: Slot
    presenters: list[Presenter]

    @property
    def start(self) -> AwareDatetime:
        return self.slot.start

    @property
    def room(self) -> Room | None:
        return self.slot.room

    @property
    def duration(self) -> int:
        """Duration in minutes, from the slot when the session has none of its own."""
        if self.duration_minutes is not None:
            return self.duration_minutes
        return (self.slot.end - self.slot.start) // timedelta(minutes=1)

    def __hash__(self) -> int:
        return hash(self.slug + str(self.start))
