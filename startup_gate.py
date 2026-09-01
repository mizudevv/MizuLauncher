from __future__ import annotations

import sys
import webbrowser
from pathlib import Path
from tkinter import Tk, messagebox

from mizulauncher.deployment import SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, UPDATE_ID, UPDATE_CHECK_ENABLED, UPDATE_DOWNLOAD_URL
from mizulauncher.update_check import fetch_update_info_from_supabase, _write_log


def load_version() -> str:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parent
    return (root / "VERSION.txt").read_text(encoding="utf-8").strip() or "0.0.0"


def fail(title: str, message: str) -> None:
    _write_log(f"FATAL {title}: {message}")
    try:
        root = Tk()
        root.withdraw()
        messagebox.showerror(title, message, parent=root)
        root.destroy()
    except Exception:
        print(f"{title}: {message}")


def required_update_gate() -> bool:
    if not UPDATE_CHECK_ENABLED:
        _write_log("UPDATE CHECK DISABLED")
        return True

    current = load_version()
    _write_log(f"STARTUP GATE current={current}")

    result = fetch_update_info_from_supabase(
        SUPABASE_URL,
        SUPABASE_PUBLISHABLE_KEY,
        current,
        update_id=int(UPDATE_ID),
    )

    if not result.checked:
        fail(
            "Nie można zweryfikować wersji",
            "MizuLauncher nie może potwierdzić aktualnej wersji przez Supabase.\n\n"
            f"{result.error}\n\n"
            "Aplikacja zostanie zamknięta. Sprawdź połączenie, URL Supabase, publishable key oraz tabelę launcher_updates.",
        )
        return False

    if result.available:
        message = (
            f"Obecna wersja: {current}\n"
            f"Najnowsza wersja: {result.latest_version}\n\n"
            f"{result.message or 'Dostępna jest nowa wersja MizuLaunchera.'}\n\n"
            "Launcher zostanie zamknięty."
        )
        _write_log(f"UPDATE REQUIRED current={current} latest={result.latest_version} url={result.page_url!r}")
        root = Tk()
        root.withdraw()
        messagebox.showwarning("Wymagana aktualizacja", message, parent=root)
        root.destroy()
        url = result.page_url or UPDATE_DOWNLOAD_URL
        if url:
            try:
                webbrowser.open(url)
                _write_log(f"OPEN UPDATE URL {url}")
            except Exception as exc:
                _write_log(f"ERROR opening update URL: {exc}")
        return False

    _write_log(f"UP_TO_DATE current={current} latest={result.latest_version}")
    return True


if __name__ == "__main__":
    sys.exit(0 if required_update_gate() else 1)
