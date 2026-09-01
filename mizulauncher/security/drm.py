from __future__ import annotations

import base64
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
import hashlib


class DrmError(RuntimeError):
    pass


@dataclass
class DrmGrant:
    game_id: str
    user_id: str
    token: str
    expires_at: str
    status: str


def _key(game_secret: str, game_id: str, user_id: str = "") -> bytes:
    if not game_secret or game_secret.startswith("CHANGE_ME"):
        raise DrmError("Brak poprawnie ustawionego sekretu DRM dla gry.")
    raw = f"mizulauncher-drm:{game_secret}:{game_id}".encode("utf-8")
    return hashlib.sha256(raw).digest()


def write_mizuapi(game_root: Path, grant: DrmGrant, game_secret: str) -> Path:
    payload = {
        "version": 1,
        "game_id": grant.game_id,
        "user_id": grant.user_id,
        "token": grant.token,
        "expires_at": grant.expires_at,
        "status": grant.status,
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    key = _key(game_secret, grant.game_id, grant.user_id)
    nonce = os.urandom(12)
    cipher = AESGCM(key).encrypt(nonce, raw, grant.game_id.encode("utf-8"))
    encoded = base64.urlsafe_b64encode(nonce + cipher).decode("ascii")
    target = game_root / "mizuapi.dat"
    target.write_text(encoded, encoding="ascii")
    return target


def delete_mizuapi(game_root: Path) -> None:
    try:
        (game_root / "mizuapi.dat").unlink(missing_ok=True)
    except OSError:
        pass


def clear_game_install(game_root: Path) -> None:
    delete_mizuapi(game_root)


def decrypt_mizuapi(path: Path, game_secret: str, game_id: str, user_id: str) -> dict:
    try:
        encoded = path.read_text(encoding="ascii").strip()
        packed = base64.urlsafe_b64decode(encoded.encode("ascii"))
        nonce, cipher = packed[:12], packed[12:]
        raw = AESGCM(_key(game_secret, game_id, user_id)).decrypt(nonce, cipher, game_id.encode("utf-8"))
        payload = json.loads(raw.decode("utf-8"))
        if payload.get("game_id") != game_id or payload.get("user_id") != user_id:
            raise DrmError("mizuapi.dat nie pasuje do tej gry/użytkownika.")
        return payload
    except Exception as exc:
        raise DrmError("Nie można zweryfikować mizuapi.dat.") from exc
