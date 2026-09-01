from __future__ import annotations

import threading
import time
from pathlib import Path

from .drm import delete_mizuapi


class GameSecurityMonitor:
    """Near-real-time monitor for a game process started by MizuLauncher."""

    def __init__(self, api, game, process, game_root: Path, on_blocked=None, interval: float = 4.0):
        self.api = api
        self.game = game
        self.process = process
        self.game_root = game_root
        self.on_blocked = on_blocked
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="MizuGameSecurity", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _terminate_owned_process(self):
        if self.process.poll() is not None:
            return
        try:
            self.process.terminate()
            self.process.wait(timeout=3)
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass

    def _run(self):
        while not self._stop.wait(self.interval):
            if self.process.poll() is not None:
                return
            try:
                state = self.api.fetch_player_control()
            except Exception:
                # Network loss alone must not kill an already running game.
                continue
            can_play = bool(state.get("can_play", True))
            kill_switch = bool(state.get("kill_switch", False))
            if not can_play or kill_switch:
                delete_mizuapi(self.game_root)
                self._terminate_owned_process()
                if self.on_blocked:
                    self.on_blocked(state)
                return
