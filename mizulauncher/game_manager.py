from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from .downloads import download_file, find_executable, find_game_root, safe_extract_archive
from .models import Game


class GameInstallError(RuntimeError):
    pass

MARKER_NAME = ".mizu_game.json"
STATE_NAME = "installed_state.json"
DEFAULT_PRESERVE = ["Saves", "saves", "save", "userdata", "UserData"]


def _version_tuple(value: str) -> tuple[int, ...]:
    import re
    nums = re.findall(r"\d+", str(value or ""))
    if not nums:
        return (0, 0, 0, 0)
    result = tuple(int(x) for x in nums[:8])
    return result + (0,) * max(0, 4 - len(result))


def is_version_newer(remote: str, installed: str) -> bool:
    return _version_tuple(remote) > _version_tuple(installed)


class GameManager:
    def __init__(self, download_directory: str, install_overrides: dict[str, str] | None = None):
        self.base = Path(download_directory).expanduser().resolve()
        self.install_overrides = {str(k): str(v) for k, v in (install_overrides or {}).items() if str(v).strip()}
        self.base.mkdir(parents=True, exist_ok=True)
        self.installs = self.base / "installed"
        self.installs.mkdir(parents=True, exist_ok=True)
        self.cache = self.base / "cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.staging = self.base / ".staging"
        self.staging.mkdir(parents=True, exist_ok=True)
        self.state_file = self.base / STATE_NAME
        self.state = self._load_state()

    def _load_state(self) -> dict:
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_state(self) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.state_file)

    def game_root(self, game: Game) -> Path:
        override = self.install_overrides.get(game.id, "").strip()
        if override:
            return Path(os.path.expandvars(os.path.expanduser(override))).resolve()
        return self.installs / game.id

    def set_install_location(self, game: Game, folder: str) -> None:
        folder = str(folder or "").strip()
        if folder:
            path = Path(os.path.expandvars(os.path.expanduser(folder))).resolve()
            self.install_overrides[game.id] = str(path)
            path.mkdir(parents=True, exist_ok=True)
        else:
            self.install_overrides.pop(game.id, None)

    def clear_install_location(self, game: Game) -> None:
        self.install_overrides.pop(game.id, None)
        self.state.pop(game.id, None)
        self._save_state()

    def _marker_candidates(self, game: Game) -> list[Path]:
        root = self.game_root(game)
        if not root.exists():
            return []
        candidates = []
        direct = root / MARKER_NAME
        if direct.is_file():
            candidates.append(direct)
        try:
            candidates.extend(p for p in root.rglob(MARKER_NAME) if p.is_file() and p not in candidates)
        except OSError:
            pass
        saved = self.state.get(game.id)
        if isinstance(saved, dict):
            saved_root = Path(str(saved.get("root", "")))
            if saved_root.is_dir():
                p = saved_root / MARKER_NAME
                if p.is_file() and p not in candidates:
                    candidates.insert(0, p)
        return candidates

    def _read_install_record(self, game: Game) -> tuple[Path, dict] | None:
        for marker in self._marker_candidates(game):
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
                if data.get("game_id") != game.id or not data.get("version"):
                    continue
                root = marker.parent.resolve()
                return root, data
            except Exception:
                continue
        saved = self.state.get(game.id)
        if isinstance(saved, dict):
            root = Path(str(saved.get("root", ""))).expanduser()
            if root.is_dir():
                return root.resolve(), saved
        return None

    def _content_root(self, game: Game) -> Path:
        record = self._read_install_record(game)
        if record:
            return record[0]
        base = self.game_root(game)
        if not base.exists():
            return base
        try:
            return find_game_root(base)
        except Exception:
            return base

    def _write_marker(self, game: Game, root: Path, executable: Path | None = None) -> None:
        root = root.resolve()
        try:
            rel_root = str(root.relative_to(self.game_root(game).resolve())).replace("\\", "/")
        except Exception:
            rel_root = "."
        exe_rel = ""
        if executable:
            try:
                exe_rel = str(executable.resolve().relative_to(root)).replace("\\", "/")
            except Exception:
                exe_rel = executable.name
        payload = {
            "game_id": game.id,
            "version": game.version,
            "updated_at": game.updated_at,
            "install_root_rel": rel_root,
            "executable_rel": exe_rel,
        }
        (root / MARKER_NAME).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self.state[game.id] = {
            "root": str(root),
            "version": game.version,
            "executable": str(executable.resolve()) if executable else "",
        }
        self._save_state()

    def installed_version(self, game: Game) -> str:
        record = self._read_install_record(game)
        if not record:
            return ""
        root, data = record
        exe = self.get_expected_executable(game, root_override=root)
        if not exe:
            return ""
        return str(data.get("version", self.state.get(game.id, {}).get("version", "0.0.0")))

    def update_available(self, game: Game) -> bool:
        installed = self.installed_version(game)
        return bool(installed) and is_version_newer(game.version, installed)

    def get_expected_executable(self, game: Game, root_override: Path | None = None) -> Path | None:
        root = root_override or self._content_root(game)
        if not root.exists():
            return None
        record = self._read_install_record(game)
        data = record[1] if record else {}
        explicit = game.executable.strip() if getattr(game, "executable", "") else ""
        candidates = []
        if data.get("executable_rel"):
            candidates.append(root / str(data["executable_rel"]))
        if explicit:
            candidates.append(root / explicit)
        for candidate in candidates:
            try:
                if candidate.is_file() and candidate.suffix.lower() == ".exe":
                    return candidate.resolve()
            except OSError:
                pass
        return find_executable(root)

    def is_installed(self, game: Game) -> bool:
        record = self._read_install_record(game)
        if not record:
            return False
        root, data = record
        if data.get("game_id") not in (None, "", game.id):
            return False
        exe = self.get_expected_executable(game, root_override=root)
        if not exe:
            return False
        # Self-heal the persistent state whenever the game exists.
        self.state[game.id] = {"root": str(root), "version": str(data.get("version", "0.0.0")), "executable": str(exe)}
        self._save_state()
        return True

    def _prepare_archive(self, game: Game, update: bool) -> Path:
        suffix = ".update.archive" if update else ".archive"
        return self.cache / f"{game.id}{suffix}"

    def _verify_install(self, game: Game, root: Path) -> Path:
        exe = self.get_expected_executable(game, root_override=root)
        if not exe or not exe.is_file():
            raise GameInstallError(
                "Archiwum zostało rozpakowane, ale nie znaleziono pliku EXE gry. "
                "Ustaw 'Plik wykonywalny' w edycji gry albo sprawdź zawartość archiwum."
            )
        return exe

    def install(self, game: Game, progress=None, progress_info=None) -> Path:
        if not game.download_url:
            raise GameInstallError("Ta gra nie ma ustawionego linku do archiwum.")
        game_dir = self.game_root(game)
        archive = self._prepare_archive(game, False)
        download_file(game.download_url, archive, progress=progress, progress_info=progress_info)
        if game_dir.exists():
            shutil.rmtree(game_dir, ignore_errors=True)
        game_dir.mkdir(parents=True, exist_ok=True)
        safe_extract_archive(archive, game_dir, progress=progress)

        actual_root = find_game_root(game_dir) if game.extract_to_game_folder else game_dir
        if not game.extract_to_game_folder:
            entries=[p for p in game_dir.iterdir() if p.name != "__MACOSX"]
            dirs=[p for p in entries if p.is_dir()]; files=[p for p in entries if p.is_file()]
            if len(dirs)==1 and not files:
                nested=dirs[0]
                for child in list(nested.iterdir()):
                    target=game_dir/child.name
                    if target.exists():
                        shutil.rmtree(target,ignore_errors=True) if target.is_dir() else target.unlink(missing_ok=True)
                    shutil.move(str(child), str(target))
                nested.rmdir()
            actual_root=game_dir

        exe = self._verify_install(game, actual_root)
        self._write_marker(game, actual_root, exe)
        archive.unlink(missing_ok=True)
        return actual_root

    def update(self, game: Game, progress=None, progress_info=None) -> Path:
        if not self.is_installed(game):
            return self.install(game, progress=progress, progress_info=progress_info)
        if not game.download_url:
            raise GameInstallError("Ta gra nie ma ustawionego linku do archiwum.")

        archive=self._prepare_archive(game, True)
        stage=self.staging / game.id
        backup=self.staging / f"{game.id}.backup"
        shutil.rmtree(stage,ignore_errors=True); shutil.rmtree(backup,ignore_errors=True)
        stage.mkdir(parents=True,exist_ok=True)
        download_file(game.download_url,archive,progress=progress,progress_info=progress_info)
        safe_extract_archive(archive,stage,progress=None)
        new_root=find_game_root(stage) if game.extract_to_game_folder else stage
        old_root=self._content_root(game)
        preserve=[x for x in (game.preserve_paths or DEFAULT_PRESERVE) if x.strip().strip("/\\") != MARKER_NAME]
        for rel in preserve:
            rel=rel.strip().strip("/\\")
            if not rel: continue
            src=old_root/rel
            if src.exists():
                dst=backup/rel; dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copytree(src,dst,dirs_exist_ok=True) if src.is_dir() else shutil.copy2(src,dst)
        for child in list(old_root.iterdir()):
            if child.name == MARKER_NAME: continue
            shutil.rmtree(child,ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
        for child in new_root.iterdir():
            target=old_root/child.name
            shutil.copytree(child,target,dirs_exist_ok=True) if child.is_dir() else shutil.copy2(child,target)
        for rel in preserve:
            src=backup/rel; dst=old_root/rel
            if src.exists(): shutil.copytree(src,dst,dirs_exist_ok=True) if src.is_dir() else (dst.parent.mkdir(parents=True,exist_ok=True) or shutil.copy2(src,dst))
        exe=self._verify_install(game,old_root)
        self._write_marker(game,old_root,exe)
        shutil.rmtree(stage,ignore_errors=True); shutil.rmtree(backup,ignore_errors=True); archive.unlink(missing_ok=True)
        return old_root

    def uninstall(self, game: Game) -> None:
        shutil.rmtree(self.game_root(game),ignore_errors=True)
        self.state.pop(game.id,None)
        self._save_state()
        for name in (f"{game.id}.archive",f"{game.id}.update.archive"):
            (self.cache/name).unlink(missing_ok=True)

    def launch(self, game: Game) -> subprocess.Popen:
        if not self.is_installed(game):
            raise GameInstallError("Gra nie jest poprawnie zainstalowana.")
        exe=self.get_expected_executable(game)
        if not exe: raise GameInstallError("Nie znaleziono EXE gry.")
        args=shlex.split(game.arguments,posix=False) if game.arguments.strip() else []
        return subprocess.Popen([str(exe),*args],cwd=str(exe.parent))
