from __future__ import annotations

import sys
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, field_validator

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class Tutorial(BaseModel, frozen=True):
    id: str
    title: str
    presenters: list[str]
    date: AwareDatetime
    url: str

    @field_validator("title")
    @classmethod
    def title_fits_select_option(cls, title: str) -> str:
        # Discord limits the label of a select menu option to 100 characters
        max_length = 100
        if len(title) > max_length:
            raise ValueError(f"Title is longer than {max_length} characters: {title!r}")
        return title

    @property
    def timestamp(self) -> int:
        return int(self.date.timestamp())

    @property
    def local_time(self) -> str:
        """Discord renders this in the timezone of each viewer."""
        return f"<t:{self.timestamp}:f>"

    @property
    def presenters_text(self) -> str:
        return ", ".join(self.presenters)


class _TutorialsFile(BaseModel):
    tutorial: list[Tutorial]


def load_tutorials(path: Path) -> list[Tutorial]:
    """Load the tutorials from the TOML file, in chronological order."""
    tutorials = _TutorialsFile(**tomllib.loads(path.read_text(encoding="utf-8"))).tutorial
    if len({t.id for t in tutorials}) != len(tutorials):
        raise ValueError(f"Duplicated tutorial ids in '{path}'")
    return sorted(tutorials, key=lambda t: t.date)
