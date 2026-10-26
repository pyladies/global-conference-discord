from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class TutorialsConfig(BaseModel):
    registration_channel_name: str
    report_channel_name: str
    tutorials_file: Path
