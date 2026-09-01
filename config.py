from __future__ import annotations

import json
import os
import re
from pathlib import Path

APP_NAME = "MizuLauncher"
ROOT = Path(__file__).resolve().parent
BUNDLED_DATA_DIR = ROOT / "data"

# Runtime-writable data must never live beside the installed EXE (Program Files/AppData\Programs).
if os.name == "nt":
    _local_appdata = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    DATA_DIR = _local_appdata / APP_NAME
else:
    DATA_DIR = Path.home() / ".mizulauncher"

CONFIG_FILE = DATA_DIR / "launcher_config.json"
SESSION_FILE = DATA_DIR / "session.json"
CACHE_FILE = DATA_DIR / "games_cache.json"
LAYOUT_FILE = DATA_DIR / "layout.json"
LOG_DIR = DATA_DIR / "logs"

DEFAULT_DOWNLOAD_DIR = Path.home() / "MizuLauncherGames"

DEFAULT_CONFIG = {
    "supabase_url": "",
    "supabase_publishable_key": "",
    "catalog_id": 1,
    "developer_email": "",
    "download_directory": str(DEFAULT_DOWNLOAD_DIR),
    "theme": "dark",
    "language": "pl",
    "auto_refresh": True,
    "guest_mode": False,
    "telemetry_enabled": True,
    "admin_panel_url": "",
    "drm_game_secret": "CHANGE_ME_PER_GAME",
    "update_manifest_url": "",
    "update_download_url": "",
    "update_id": 1,
    "game_install_overrides": {},
}


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _safe_json_read(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _migrate_download_directory(value: object) -> str:
    """Convert the old developer-machine default path to this Windows user's path.

    Custom paths chosen later by the user are preserved. The legacy pattern
    C:\\Users\\<name>\\MizuLauncherGames is rewritten to the current user's home.
    """
    if not isinstance(value, str) or not value.strip():
        return str(DEFAULT_DOWNLOAD_DIR)

    raw = value.strip()
    normalized = raw.replace("/", "\\")
    legacy_re = re.compile(r"^[A-Za-z]:\\Users\\[^\\]+\\MizuLauncherGames(?:\\.*)?$", re.IGNORECASE)
    if os.name == "nt" and legacy_re.match(normalized):
        suffix = normalized.split("MizuLauncherGames", 1)[1]
        return str(DEFAULT_DOWNLOAD_DIR) + suffix

    # Also repair an exact old path serialized with another machine's home.
    if Path(raw).name.lower() == "mizulaunchergames" and "\\Users\\" in normalized:
        return str(DEFAULT_DOWNLOAD_DIR)

    return raw


def _seed_from_bundled_config() -> dict:
    bundled = BUNDLED_DATA_DIR / "launcher_config.json"
    if bundled.exists():
        return _safe_json_read(bundled)
    return {}


def load_config() -> dict:
    ensure_data_dir()

    if CONFIG_FILE.exists():
        data = _safe_json_read(CONFIG_FILE)
    else:
        data = _seed_from_bundled_config()

    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    merged["download_directory"] = _migrate_download_directory(merged.get("download_directory"))

    # Save a normalized user-scoped config. This also fixes legacy absolute paths.
    save_config(merged)
    return merged


def save_config(config: dict) -> None:
    ensure_data_dir()
    normalized = dict(config)
    normalized["download_directory"] = _migrate_download_directory(normalized.get("download_directory"))
    CONFIG_FILE.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")


def load_cache() -> list[dict]:
    ensure_data_dir()
    if not CACHE_FILE.exists():
        return []
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_cache(games: list[dict]) -> None:
    ensure_data_dir()
    CACHE_FILE.write_text(json.dumps(games, indent=2, ensure_ascii=False), encoding="utf-8")


def load_session() -> dict:
    ensure_data_dir()
    if not SESSION_FILE.exists():
        return {}
    try:
        payload = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_session(session: dict) -> None:
    ensure_data_dir()
    SESSION_FILE.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")


def clear_session() -> None:
    try:
        SESSION_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def load_layout() -> dict:
    ensure_data_dir()
    if LAYOUT_FILE.exists():
        payload = _safe_json_read(LAYOUT_FILE)
        if payload:
            return payload

    bundled = BUNDLED_DATA_DIR / "layout.json"
    payload = _safe_json_read(bundled) if bundled.exists() else {}
    if payload:
        LAYOUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
