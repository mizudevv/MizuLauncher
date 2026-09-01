from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import os

import requests


@dataclass(frozen=True)
class UpdateInfo:
    available: bool = False
    latest_version: str = ""
    page_url: str = ""
    message: str = ""
    checked: bool = False
    error: str = ""
    http_status: int | None = None
    source: str = "supabase"


def _version_tuple(value: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", str(value or ""))
    if not nums:
        return (0, 0, 0, 0)
    result = tuple(int(x) for x in nums[:8])
    return result + (0,) * max(0, 4 - len(result))


def is_newer(current: str, latest: str) -> bool:
    return _version_tuple(latest) > _version_tuple(current)


def _write_log(message: str) -> None:
    try:
        local_app_data = os.environ.get("LOCALAPPDATA")
        data_dir = (Path(local_app_data) / "MizuLauncher") if local_app_data else (Path.home() / "AppData" / "Local" / "MizuLauncher")
        data_dir.mkdir(parents=True, exist_ok=True)
        with (data_dir / "update_check.log").open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n")
    except Exception:
        pass


def _safe_json_response(response: requests.Response):
    try:
        return response.json()
    except Exception:
        return response.text[:500]


def fetch_update_info_from_supabase(
    project_url: str,
    publishable_key: str,
    current_version: str,
    update_id: int = 1,
    timeout: float = 8.0,
) -> UpdateInfo:
    base = (project_url or "").strip().rstrip("/")
    key = (publishable_key or "").strip()
    if not base:
        err = "Brak SUPABASE_URL."
        _write_log(f"ERROR {err}")
        return UpdateInfo(checked=False, error=err)
    if not key:
        err = "Brak SUPABASE_PUBLISHABLE_KEY."
        _write_log(f"ERROR {err}")
        return UpdateInfo(checked=False, error=err)

    url = f"{base}/rest/v1/launcher_updates"
    params = {
        "id": f"eq.{int(update_id)}",
        "select": "latest_version,download_url,message,enabled",
        "limit": "1",
    }
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "MizuLauncher-Updater/3.0",
    }

    _write_log(f"CHECK url={url} current={current_version} update_id={update_id}")
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        payload = _safe_json_response(response)
        _write_log(f"HTTP {response.status_code} payload={payload!r}")
        if response.status_code < 200 or response.status_code >= 300:
            return UpdateInfo(
                checked=False,
                error=f"Supabase HTTP {response.status_code}: {str(payload)[:500]}",
                http_status=response.status_code,
            )

        if not isinstance(payload, list):
            return UpdateInfo(checked=False, error="Supabase zwrócił niepoprawny format danych.", http_status=response.status_code)
        if not payload:
            return UpdateInfo(checked=False, error=f"Brak rekordu launcher_updates dla id={int(update_id)}.", http_status=response.status_code)

        row = payload[0]
        if not isinstance(row, dict):
            return UpdateInfo(checked=False, error="Rekord aktualizacji ma niepoprawny format.", http_status=response.status_code)

        latest = str(row.get("latest_version", "")).strip()
        enabled = bool(row.get("enabled", False))
        page_url = str(row.get("download_url", "")).strip()
        message = str(row.get("message", "")).strip()

        if not latest:
            return UpdateInfo(checked=False, error="Rekord aktualizacji nie zawiera latest_version.", http_status=response.status_code)

        available = enabled and is_newer(current_version, latest)
        _write_log(f"RESULT enabled={enabled} latest={latest} current={current_version} available={available}")
        return UpdateInfo(
            available=available,
            latest_version=latest,
            page_url=page_url,
            message=message,
            checked=True,
            http_status=response.status_code,
            source="supabase",
        )

    except requests.RequestException as exc:
        err = f"Błąd sieci Supabase: {exc}"
        _write_log(f"ERROR {err}")
        return UpdateInfo(checked=False, error=err)
    except (ValueError, json.JSONDecodeError) as exc:
        err = f"Błąd JSON Supabase: {exc}"
        _write_log(f"ERROR {err}")
        return UpdateInfo(checked=False, error=err)
    except Exception as exc:
        err = f"Nieoczekiwany błąd checkera: {type(exc).__name__}: {exc}"
        _write_log(f"ERROR {err}")
        return UpdateInfo(checked=False, error=err)


def fetch_update_info(manifest_url: str, current_version: str, timeout: float = 8.0) -> UpdateInfo:
    url = (manifest_url or "").strip()
    if not url:
        return UpdateInfo(checked=False, error="Brak URL manifestu aktualizacji.", source="manifest")
    try:
        response = requests.get(url, headers={"User-Agent": "MizuLauncher-Updater/3.0", "Accept": "application/json"}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return UpdateInfo(checked=False, error="Manifest aktualizacji ma niepoprawny format.", source="manifest")
        latest = str(payload.get("latest_version", "")).strip()
        enabled = bool(payload.get("enabled", True))
        if not latest:
            return UpdateInfo(checked=False, error="Manifest nie zawiera latest_version.", source="manifest")
        return UpdateInfo(
            available=enabled and is_newer(current_version, latest),
            latest_version=latest,
            page_url=str(payload.get("download_url", payload.get("page_url", ""))).strip(),
            message=str(payload.get("message", "")).strip(),
            checked=True,
            source="manifest",
        )
    except Exception as exc:
        return UpdateInfo(checked=False, error=f"Błąd pobierania manifestu: {exc}", source="manifest")
