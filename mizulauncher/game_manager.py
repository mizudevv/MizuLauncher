from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from .downloads import (
    download_file,
    find_game_root,
    safe_extract_archive,
)
from .models import Game


class GameInstallError(RuntimeError):
    pass


MARKER_NAME = ".mizu_game.json"
STATE_NAME = "installed_state.json"

DEFAULT_PRESERVE = [
    "Saves",
    "saves",
    "save",
    "userdata",
    "UserData",
]


def _version_tuple(value: str) -> tuple[int, ...]:
    import re

    nums = re.findall(
        r"\d+",
        str(value or ""),
    )

    if not nums:
        return (
            0,
            0,
            0,
            0,
        )

    result = tuple(
        int(x)
        for x in nums[:8]
    )

    return result + (
        0,
    ) * max(
        0,
        4 - len(result),
    )


def is_version_newer(
    remote: str,
    installed: str,
) -> bool:
    return _version_tuple(
        remote
    ) > _version_tuple(
        installed
    )


class GameManager:
    def __init__(
        self,
        download_directory: str,
        install_overrides: dict[str, str] | None = None,
    ):
        self.base = (
            Path(download_directory)
            .expanduser()
            .resolve()
        )

        self.install_overrides = {
            str(k): str(v)
            for k, v in (
                install_overrides or {}
            ).items()
            if str(v).strip()
        }

        self.base.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.installs = (
            self.base
            / "installed"
        )

        self.installs.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.cache = (
            self.base
            / "cache"
        )

        self.cache.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.staging = (
            self.base
            / ".staging"
        )

        self.staging.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.state_file = (
            self.base
            / STATE_NAME
        )

        self.state = (
            self._load_state()
        )

    # ==============================================================
    # STATE
    # ==============================================================

    def _load_state(self) -> dict:
        try:
            data = json.loads(
                self.state_file.read_text(
                    encoding="utf-8"
                )
            )

            return (
                data
                if isinstance(
                    data,
                    dict,
                )
                else {}
            )

        except Exception:
            return {}

    def _save_state(self) -> None:
        tmp = self.state_file.with_suffix(
            ".tmp"
        )

        tmp.write_text(
            json.dumps(
                self.state,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        tmp.replace(
            self.state_file
        )

    # ==============================================================
    # INSTALL LOCATION
    # ==============================================================

    def game_root(
        self,
        game: Game,
    ) -> Path:
        override = (
            self.install_overrides.get(
                game.id,
                "",
            ).strip()
        )

        if override:
            return Path(
                os.path.expandvars(
                    os.path.expanduser(
                        override
                    )
                )
            ).resolve()

        return (
            self.installs
            / game.id
        )

    def set_install_location(
        self,
        game: Game,
        folder: str,
    ) -> None:
        folder = str(
            folder or ""
        ).strip()

        if folder:
            path = Path(
                os.path.expandvars(
                    os.path.expanduser(
                        folder
                    )
                )
            ).resolve()

            self.install_overrides[
                game.id
            ] = str(path)

            path.mkdir(
                parents=True,
                exist_ok=True,
            )

        else:
            self.install_overrides.pop(
                game.id,
                None,
            )

    def clear_install_location(
        self,
        game: Game,
    ) -> None:
        self.install_overrides.pop(
            game.id,
            None,
        )

        self.state.pop(
            game.id,
            None,
        )

        self._save_state()

    # ==============================================================
    # MARKER
    # ==============================================================

    def _marker_candidates(
        self,
        game: Game,
    ) -> list[Path]:
        root = self.game_root(
            game
        )

        if not root.exists():
            return []

        candidates: list[Path] = []

        direct = (
            root
            / MARKER_NAME
        )

        if direct.is_file():
            candidates.append(
                direct
            )

        try:
            candidates.extend(
                p
                for p in root.rglob(
                    MARKER_NAME
                )
                if p.is_file()
                and p not in candidates
            )

        except OSError:
            pass

        saved = self.state.get(
            game.id
        )

        if isinstance(
            saved,
            dict,
        ):
            saved_root = Path(
                str(
                    saved.get(
                        "root",
                        "",
                    )
                )
            )

            if saved_root.is_dir():
                p = (
                    saved_root
                    / MARKER_NAME
                )

                if (
                    p.is_file()
                    and p not in candidates
                ):
                    candidates.insert(
                        0,
                        p,
                    )

        return candidates

    def _read_install_record(
        self,
        game: Game,
    ) -> tuple[Path, dict] | None:
        for marker in self._marker_candidates(
            game
        ):
            try:
                data = json.loads(
                    marker.read_text(
                        encoding="utf-8"
                    )
                )

                if (
                    data.get(
                        "game_id"
                    )
                    != game.id
                    or not data.get(
                        "version"
                    )
                ):
                    continue

                root = (
                    marker.parent.resolve()
                )

                return (
                    root,
                    data,
                )

            except Exception:
                continue

        saved = self.state.get(
            game.id
        )

        if isinstance(
            saved,
            dict,
        ):
            root = Path(
                str(
                    saved.get(
                        "root",
                        "",
                    )
                )
            ).expanduser()

            if root.is_dir():
                return (
                    root.resolve(),
                    saved,
                )

        return None

    def _content_root(
        self,
        game: Game,
    ) -> Path:
        record = (
            self._read_install_record(
                game
            )
        )

        if record:
            return record[0]

        base = self.game_root(
            game
        )

        if not base.exists():
            return base

        try:
            return find_game_root(
                base
            )

        except Exception:
            return base

    # ==============================================================
    # EXECUTABLE STORAGE
    # ==============================================================

    def get_saved_executable(
        self,
        game: Game,
    ) -> Path | None:
        """
        Zwraca EXE ustawiony przez użytkownika.

        Najpierw sprawdzany jest stan launchera.
        Potem marker .mizu_game.json.
        """

        saved = self.state.get(
            game.id
        )

        if isinstance(
            saved,
            dict,
        ):
            executable = str(
                saved.get(
                    "executable",
                    "",
                )
                or ""
            ).strip()

            if executable:
                path = Path(
                    os.path.expandvars(
                        os.path.expanduser(
                            executable
                        )
                    )
                )

                if (
                    path.is_file()
                    and path.suffix.lower()
                    == ".exe"
                ):
                    return path.resolve()

        record = (
            self._read_install_record(
                game
            )
        )

        if record:
            root, data = record

            relative = str(
                data.get(
                    "executable_rel",
                    "",
                )
                or ""
            ).strip()

            if relative:
                path = (
                    root
                    / relative
                )

                if (
                    path.is_file()
                    and path.suffix.lower()
                    == ".exe"
                ):
                    return path.resolve()

        return None

    def set_executable(
        self,
        game: Game,
        executable: str | Path,
    ) -> Path:
        """
        Ustawia EXE wskazany przez gracza.
        """

        path = Path(
            os.path.expandvars(
                os.path.expanduser(
                    str(executable)
                )
            )
        ).resolve()

        if not path.exists():
            raise GameInstallError(
                "Wybrany plik EXE nie istnieje."
            )

        if not path.is_file():
            raise GameInstallError(
                "Wybrana ścieżka nie jest plikiem."
            )

        if path.suffix.lower() != ".exe":
            raise GameInstallError(
                "Wybierz plik .exe."
            )

        root = self._content_root(
            game
        )

        try:
            relative = str(
                path.relative_to(
                    root
                )
            ).replace(
                "\\",
                "/",
            )
        except ValueError:
            relative = path.name

        self.state[game.id] = {
            "root": str(root),
            "version": str(
                self.state.get(
                    game.id,
                    {},
                ).get(
                    "version",
                    game.version,
                )
            ),
            "executable": str(
                path
            ),
        }

        self._save_state()

        marker = (
            root
            / MARKER_NAME
        )

        marker_data: dict = {}

        try:
            if marker.is_file():
                marker_data = json.loads(
                    marker.read_text(
                        encoding="utf-8"
                    )
                )

        except Exception:
            marker_data = {}

        marker_data.update({
            "game_id": game.id,
            "version": str(
                marker_data.get(
                    "version",
                    game.version,
                )
            ),
            "updated_at": str(
                marker_data.get(
                    "updated_at",
                    game.updated_at,
                )
            ),
            "executable_rel": relative,
        })

        root.mkdir(
            parents=True,
            exist_ok=True,
        )

        marker.write_text(
            json.dumps(
                marker_data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return path

    def clear_executable(
        self,
        game: Game,
    ) -> None:
        saved = self.state.get(
            game.id
        )

        if isinstance(
            saved,
            dict,
        ):
            saved = dict(saved)

            saved.pop(
                "executable",
                None,
            )

            self.state[
                game.id
            ] = saved

        self._save_state()

    # ==============================================================
    # MARKER WRITE
    # ==============================================================

    def _write_marker(
        self,
        game: Game,
        root: Path,
        executable: Path | None = None,
    ) -> None:
        root = root.resolve()

        try:
            rel_root = str(
                root.relative_to(
                    self.game_root(
                        game
                    ).resolve()
                )
            ).replace(
                "\\",
                "/",
            )

        except Exception:
            rel_root = "."

        executable_rel = ""

        if executable:
            try:
                executable_rel = str(
                    executable.resolve().relative_to(
                        root
                    )
                ).replace(
                    "\\",
                    "/",
                )

            except Exception:
                executable_rel = executable.name

        payload = {
            "game_id": game.id,
            "version": game.version,
            "updated_at": game.updated_at,
            "install_root_rel": rel_root,
            "executable_rel": executable_rel,
        }

        (
            root
            / MARKER_NAME
        ).write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        self.state[game.id] = {
            "root": str(root),
            "version": game.version,
            "executable": (
                str(
                    executable.resolve()
                )
                if executable
                else ""
            ),
        }

        self._save_state()

    # ==============================================================
    # VERSION
    # ==============================================================

    def installed_version(
        self,
        game: Game,
    ) -> str:
        record = (
            self._read_install_record(
                game
            )
        )

        if not record:
            return ""

        _, data = record

        executable = (
            self.get_saved_executable(
                game
            )
        )

        # Gra jest uznawana za skonfigurowaną
        # dopiero po wskazaniu EXE.
        if not executable:
            return ""

        return str(
            data.get(
                "version",
                self.state.get(
                    game.id,
                    {},
                ).get(
                    "version",
                    "0.0.0",
                ),
            )
        )

    def update_available(
        self,
        game: Game,
    ) -> bool:
        installed = (
            self.installed_version(
                game
            )
        )

        return (
            bool(installed)
            and is_version_newer(
                game.version,
                installed,
            )
        )

    # ==============================================================
    # INSTALLED
    # ==============================================================

    def is_installed(
        self,
        game: Game,
    ) -> bool:
        """
        Gra jest poprawnie skonfigurowana dopiero wtedy,
        gdy istnieje instalacja oraz użytkownik ustawił EXE.
        """

        record = (
            self._read_install_record(
                game
            )
        )

        if not record:
            return False

        root, data = record

        if data.get(
            "game_id"
        ) not in (
            None,
            "",
            game.id,
        ):
            return False

        executable = (
            self.get_saved_executable(
                game
            )
        )

        if not executable:
            return False

        if not executable.is_file():
            return False

        self.state[game.id] = {
            "root": str(root),
            "version": str(
                data.get(
                    "version",
                    "0.0.0",
                )
            ),
            "executable": str(
                executable
            ),
        }

        self._save_state()

        return True

    # ==============================================================
    # ARCHIVE
    # ==============================================================

    def _prepare_archive(
        self,
        game: Game,
        update: bool,
    ) -> Path:
        suffix = (
            ".update.archive"
            if update
            else ".archive"
        )

        return (
            self.cache
            / f"{game.id}{suffix}"
        )

    # ==============================================================
    # VERIFY
    # ==============================================================

    def _verify_install(
        self,
        game: Game,
        root: Path,
    ) -> Path | None:
        """
        Przy instalacji NIE próbujemy zgadywać EXE.

        Po prostu sprawdzamy, czy użytkownik wskazał już plik.
        """

        executable = (
            self.get_saved_executable(
                game
            )
        )

        if executable:
            return executable

        return None

    # ==============================================================
    # INSTALL
    # ==============================================================

    def install(
        self,
        game: Game,
        progress=None,
        progress_info=None,
    ) -> Path:
        if not game.download_url:
            raise GameInstallError(
                "Ta gra nie ma ustawionego "
                "linku do archiwum."
            )

        game_dir = (
            self.game_root(
                game
            )
        )

        archive = (
            self._prepare_archive(
                game,
                False,
            )
        )

        download_file(
            game.download_url,
            archive,
            progress=progress,
            progress_info=progress_info,
        )

        if game_dir.exists():
            shutil.rmtree(
                game_dir,
                ignore_errors=True,
            )

        game_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        safe_extract_archive(
            archive,
            game_dir,
            progress=progress,
        )

        if game.extract_to_game_folder:
            actual_root = (
                find_game_root(
                    game_dir
                )
            )
        else:
            entries = [
                p
                for p in game_dir.iterdir()
                if p.name != "__MACOSX"
            ]

            dirs = [
                p
                for p in entries
                if p.is_dir()
            ]

            files = [
                p
                for p in entries
                if p.is_file()
            ]

            if (
                len(dirs) == 1
                and not files
            ):
                nested = dirs[0]

                for child in list(
                    nested.iterdir()
                ):
                    target = (
                        game_dir
                        / child.name
                    )

                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(
                                target,
                                ignore_errors=True,
                            )
                        else:
                            target.unlink(
                                missing_ok=True
                            )

                    shutil.move(
                        str(child),
                        str(target),
                    )

                nested.rmdir()

            actual_root = game_dir

        # ==========================================================
        # NIE SZUKAMY EXE.
        #
        # Instalacja kończy się stanem:
        #
        # "zainstalowane, ale lokalizacja EXE nieustawiona"
        #
        # GUI pokaże "Ustaw lokalizację".
        # ==========================================================

        self.state[game.id] = {
            "root": str(
                actual_root.resolve()
            ),
            "version": game.version,
            "executable": "",
        }

        self._write_marker(
            game,
            actual_root,
            executable=None,
        )

        archive.unlink(
            missing_ok=True
        )

        return actual_root

    # ==============================================================
    # UPDATE
    # ==============================================================

    def update(
        self,
        game: Game,
        progress=None,
        progress_info=None,
    ) -> Path:
        if not self.is_installed(
            game
        ):
            return self.install(
                game,
                progress=progress,
                progress_info=progress_info,
            )

        if not game.download_url:
            raise GameInstallError(
                "Ta gra nie ma ustawionego "
                "linku do archiwum."
            )

        old_executable = (
            self.get_saved_executable(
                game
            )
        )

        archive = (
            self._prepare_archive(
                game,
                True,
            )
        )

        stage = (
            self.staging
            / game.id
        )

        backup = (
            self.staging
            / f"{game.id}.backup"
        )

        shutil.rmtree(
            stage,
            ignore_errors=True,
        )

        shutil.rmtree(
            backup,
            ignore_errors=True,
        )

        stage.mkdir(
            parents=True,
            exist_ok=True,
        )

        download_file(
            game.download_url,
            archive,
            progress=progress,
            progress_info=progress_info,
        )

        safe_extract_archive(
            archive,
            stage,
            progress=None,
        )

        new_root = (
            find_game_root(stage)
            if game.extract_to_game_folder
            else stage
        )

        old_root = (
            self._content_root(
                game
            )
        )

        preserve = [
            x
            for x in (
                game.preserve_paths
                or DEFAULT_PRESERVE
            )
            if x.strip().strip(
                "/\\"
            ) != MARKER_NAME
        ]

        # ----------------------------------------------------------
        # Backup save'ów
        # ----------------------------------------------------------

        for rel in preserve:
            rel = rel.strip().strip(
                "/\\"
            )

            if not rel:
                continue

            src = (
                old_root
                / rel
            )

            if src.exists():
                dst = (
                    backup
                    / rel
                )

                dst.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                if src.is_dir():
                    shutil.copytree(
                        src,
                        dst,
                        dirs_exist_ok=True,
                    )
                else:
                    shutil.copy2(
                        src,
                        dst,
                    )

        # ----------------------------------------------------------
        # Remove old version
        # ----------------------------------------------------------

        for child in list(
            old_root.iterdir()
        ):
            if child.name == MARKER_NAME:
                continue

            if child.is_dir():
                shutil.rmtree(
                    child,
                    ignore_errors=True,
                )
            else:
                child.unlink(
                    missing_ok=True
                )

        # ----------------------------------------------------------
        # Copy new version
        # ----------------------------------------------------------

        for child in new_root.iterdir():
            target = (
                old_root
                / child.name
            )

            if child.is_dir():
                shutil.copytree(
                    child,
                    target,
                    dirs_exist_ok=True,
                )
            else:
                shutil.copy2(
                    child,
                    target,
                )

        # ----------------------------------------------------------
        # Restore saves
        # ----------------------------------------------------------

        for rel in preserve:
            src = (
                backup
                / rel
            )

            dst = (
                old_root
                / rel
            )

            if not src.exists():
                continue

            if src.is_dir():
                shutil.copytree(
                    src,
                    dst,
                    dirs_exist_ok=True,
                )
            else:
                dst.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                shutil.copy2(
                    src,
                    dst,
                )

        # ----------------------------------------------------------
        # PRÓBUJEMY ZACHOWAĆ WYBRANĄ LOKALIZACJĘ EXE
        # ----------------------------------------------------------

        new_executable = None

        if old_executable:
            try:
                relative = old_executable.relative_to(
                    old_root
                )

                candidate = (
                    old_root
                    / relative
                )

                if (
                    candidate.is_file()
                    and candidate.suffix.lower()
                    == ".exe"
                ):
                    new_executable = (
                        candidate.resolve()
                    )

            except ValueError:
                pass

        # Jeśli stary EXE zniknął podczas aktualizacji,
        # użytkownik będzie musiał ponownie wskazać EXE.
        self.state[game.id] = {
            "root": str(
                old_root.resolve()
            ),
            "version": game.version,
            "executable": (
                str(new_executable)
                if new_executable
                else ""
            ),
        }

        self._write_marker(
            game,
            old_root,
            executable=new_executable,
        )

        shutil.rmtree(
            stage,
            ignore_errors=True,
        )

        shutil.rmtree(
            backup,
            ignore_errors=True,
        )

        archive.unlink(
            missing_ok=True
        )

        return old_root

    # ==============================================================
    # UNINSTALL
    # ==============================================================

    def uninstall(
        self,
        game: Game,
    ) -> None:
        shutil.rmtree(
            self.game_root(game),
            ignore_errors=True,
        )

        self.state.pop(
            game.id,
            None,
        )

        self._save_state()

        for name in (
            f"{game.id}.archive",
            f"{game.id}.update.archive",
        ):
            (
                self.cache
                / name
            ).unlink(
                missing_ok=True
            )

    # ==============================================================
    # LAUNCH
    # ==============================================================

    def launch(
        self,
        game: Game,
    ) -> subprocess.Popen:
        executable = (
            self.get_saved_executable(
                game
            )
        )

        if not executable:
            raise GameInstallError(
                "Najpierw ustaw lokalizację pliku EXE gry."
            )

        if not executable.is_file():
            raise GameInstallError(
                "Ustawiony plik EXE nie istnieje. "
                "Użyj „Ustaw nową lokalizację”."
            )

        args = (
            shlex.split(
                game.arguments,
                posix=False,
            )
            if game.arguments.strip()
            else []
        )

        # WAŻNE:
        # cwd = katalog EXE.
        #
        # Dzięki temu Unity znajdzie:
        # Game.exe
        # Game_Data/
        #
        # dokładnie tak, jak wymaga tego Unity.
        return subprocess.Popen(
            [
                str(executable),
                *args,
            ],
            cwd=str(
                executable.parent
            ),
        )
