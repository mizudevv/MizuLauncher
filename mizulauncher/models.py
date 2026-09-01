from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Game:
    id: str
    name: str
    version: str
    description: str
    download_url: str
    executable: str = ""
    install_folder: str = ""
    arguments: str = ""
    icon_url: str = ""
    banner_url: str = ""
    category: str = "Other"
    tags: list[str] = field(default_factory=list)
    featured: bool = False
    enabled: bool = True
    developer: str = "Mizu"
    size_mb: float = 0.0
    release_date: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    homepage_url: str = ""
    notes: str = ""
    preserve_paths: list[str] = field(default_factory=list)
    extract_to_game_folder: bool = True
    show_install_note: bool = False
    install_button_label: str = "Rozpocznij pobieranie"

    @classmethod
    def new(cls, **kwargs: Any) -> "Game":
        now = utc_now()
        return cls(
            id=kwargs.pop("id", None) or uuid.uuid4().hex[:12],
            name=kwargs.pop("name", "Nowa gra"),
            version=kwargs.pop("version", "1.0.0"),
            description=kwargs.pop("description", ""),
            download_url=kwargs.pop("download_url", ""),
            release_date=kwargs.pop("release_date", now),
            updated_at=kwargs.pop("updated_at", now),
            **kwargs,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Game":
        allowed = cls.__dataclass_fields__.keys()
        cleaned = {k: v for k, v in data.items() if k in allowed}
        cleaned.setdefault("id", uuid.uuid4().hex[:12])
        cleaned.setdefault("name", "Bez nazwy")
        cleaned.setdefault("version", "1.0.0")
        cleaned.setdefault("description", "")
        cleaned.setdefault("download_url", "")
        cleaned.setdefault("tags", [])
        cleaned.setdefault("enabled", True)
        cleaned.setdefault("featured", False)
        cleaned.setdefault("preserve_paths", [])
        cleaned.setdefault("extract_to_game_folder", True)
        cleaned.setdefault("show_install_note", False)
        cleaned.setdefault("install_button_label", "Rozpocznij pobieranie")
        return cls(**cleaned)


@dataclass
class Catalog:
    schema_version: int = 1
    updated_at: str = field(default_factory=utc_now)
    games: list[dict] = field(default_factory=list)

    def normalized_games(self) -> list[Game]:
        return [Game.from_dict(g) for g in self.games]

    def to_dict(self) -> dict:
        return {"schema_version": self.schema_version, "updated_at": self.updated_at, "games": self.games}

    @classmethod
    def from_dict(cls, data: dict) -> "Catalog":
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            updated_at=data.get("updated_at", utc_now()),
            games=data.get("games", []) or [],
        )
