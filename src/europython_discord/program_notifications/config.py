from __future__ import annotations

from pathlib import Path

from pydantic import AwareDatetime, BaseModel


class ProgramNotificationsConfig(BaseModel):
    # The portal's public API; the conference slug comes from PORTAL_CONFERENCE
    api_base_url: str
    schedule_cache_file: Path
    livestream_url_file: Path
    main_notification_channel_name: str
    # Link for a session's title and "Read more", with {slug} for the session slug
    session_url: str | None = None

    simulated_start_time: AwareDatetime | None = None
    fast_mode: bool = False
