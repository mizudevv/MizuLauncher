from __future__ import annotations

import getpass
import hashlib
import os
import platform
import socket
import uuid
from pathlib import Path


def windows_username() -> str:
    try:
        return os.getlogin()
    except OSError:
        try:
            return getpass.getuser()
        except Exception:
            return "unknown"


def _machine_guid() -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception:
        return ""



def local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("1.1.1.1", 80))
        value = sock.getsockname()[0]
        sock.close()
        return value
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return ""


def hwid_fingerprint() -> str:
    """Return a privacy-reduced hardware fingerprint (SHA-256, not raw identifiers)."""
    parts = [
        _machine_guid(),
        platform.machine(),
        platform.system(),
        str(uuid.getnode()),
    ]
    raw = "|".join(x for x in parts if x)
    if not raw:
        raw = "unknown-device"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def collect_device_snapshot() -> dict[str, str]:
    return {
        "windows_username": windows_username(),
        "hwid_hash": hwid_fingerprint(),
        "local_ip": local_ip(),
    }
