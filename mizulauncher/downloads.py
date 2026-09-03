from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
import re
from pathlib import Path
from typing import Callable, Any
import time
from urllib.parse import urlparse

import requests

try:
    import rarfile
except Exception:  # pragma: no cover
    rarfile = None


class DownloadError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Archive extraction
# ---------------------------------------------------------------------------

def _safe_member_name(name: str) -> str:
    name = name.replace("\\", "/")
    p = Path(name)
    if name.startswith("/") or (len(name) >= 2 and name[1] == ":") or ".." in p.parts:
        raise DownloadError(f"Niebezpieczna ścieżka w archiwum: {name}")
    return name


def safe_extract_zip(zip_path: Path, destination: Path, progress: Callable[[int], None] | None = None) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    dest = destination.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        total = max(1, len(members))
        for i, member in enumerate(members, 1):
            name = _safe_member_name(member.filename)
            target = (destination / name).resolve()
            if dest not in target.parents and target != dest:
                raise DownloadError(f"Niebezpieczna ścieżka w ZIP: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member, "r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
            if progress:
                progress(int(i * 100 / total))
    return destination


# WinRAR bootstrap
# RARLAB currently publishes WinRAR x64 7.23 for Windows.
_WINRAR_INSTALLER_URL = "https://www.rarlab.com/rar/winrar-x64-723.exe"
_WINRAR_MIN_SIZE = 2_000_000
_WINRAR_INSTALLER_TIMEOUT = (15, 180)


def _winrar_candidates() -> list[Path]:
    """Return likely WinRAR.exe locations on Windows."""
    candidates: list[Path] = []

    # 1. PATH / App Paths are handled separately, but these are the common
    # installations and also cover portable/user installations.
    env = os.environ
    program_files = env.get("ProgramFiles")
    program_files_x86 = env.get("ProgramFiles(x86)")
    local_appdata = env.get("LOCALAPPDATA")
    appdata = env.get("APPDATA")

    roots = [
        Path(program_files) / "WinRAR" if program_files else None,
        Path(program_files_x86) / "WinRAR" if program_files_x86 else None,
        Path(local_appdata) / "Programs" / "WinRAR" if local_appdata else None,
        Path(local_appdata) / "WinRAR" if local_appdata else None,
        Path(appdata) / "WinRAR" if appdata else None,
        Path(r"C:\Program Files\WinRAR"),
        Path(r"C:\Program Files (x86)\WinRAR"),
    ]
    for root in roots:
        if root:
            candidates.append(root / "WinRAR.exe")
            candidates.append(root / "Rar.exe")

    # 2. If the launcher is frozen, also check next to the application.
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir / "WinRAR.exe", exe_dir / "Rar.exe"])
    except Exception:
        pass

    return candidates


def _find_installed_winrar() -> Path | None:
    """Find an already installed WinRAR/RAR executable without installing anything."""
    seen: set[str] = set()

    for p in _winrar_candidates():
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if p.exists() and p.is_file():
                # Prefer WinRAR.exe because this is what the user requested.
                if p.name.lower() == "winrar.exe":
                    return p
        except OSError:
            pass

    # PATH lookup.
    for name in ("WinRAR.exe", "winrar", "Rar.exe", "rar"):
        found = shutil.which(name)
        if found:
            return Path(found)

    # Windows App Paths registry entries are useful for custom installation
    # locations. Importing winreg is Windows-only, so keep this optional.
    if os.name == "nt":
        try:
            import winreg
            registry_locations = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WinRAR.exe"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\WinRAR.exe"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WinRAR.exe"),
            ]
            for hive, subkey in registry_locations:
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        value, _ = winreg.QueryValueEx(key, None)
                        candidate = Path(str(value).strip().strip('"'))
                        if candidate.exists() and candidate.is_file():
                            return candidate
                except OSError:
                    continue
        except Exception:
            pass

    return None


def _download_winrar_installer() -> Path:
    """Download the official WinRAR x64 installer to a temporary directory."""
    tools_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MizuLauncher" / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    installer = tools_dir / "winrar-x64-723.exe"
    tmp = installer.with_suffix(".part")

    if installer.exists() and installer.stat().st_size >= _WINRAR_MIN_SIZE:
        return installer

    session = requests.Session()
    session.headers.update({
        "User-Agent": "MizuLauncher/1.0",
        "Accept": "application/octet-stream,*/*",
    })
    try:
        with session.get(
            _WINRAR_INSTALLER_URL,
            stream=True,
            allow_redirects=True,
            timeout=_WINRAR_INSTALLER_TIMEOUT,
        ) as r:
            r.raise_for_status()
            content_type = (r.headers.get("content-type") or "").lower()
            if "text/html" in content_type:
                raise DownloadError("RARLAB zwrócił stronę HTML zamiast instalatora WinRAR.")
            with tmp.open("wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
            if tmp.stat().st_size < _WINRAR_MIN_SIZE:
                raise DownloadError("Pobrany instalator WinRAR jest niekompletny.")
            tmp.replace(installer)
            return installer
    except requests.RequestException as exc:
        tmp.unlink(missing_ok=True)
        raise DownloadError(f"Nie udało się pobrać WinRAR z RARLAB: {exc}") from exc
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise DownloadError(f"Nie można zapisać instalatora WinRAR: {exc}") from exc


def _install_winrar() -> Path:
    """Install WinRAR when it is missing and return WinRAR.exe."""
    existing = _find_installed_winrar()
    if existing:
        return existing

    if os.name != "nt":
        raise DownloadError("Automatyczna instalacja WinRAR jest dostępna tylko na Windows.")

    installer = _download_winrar_installer()

    # WinRAR's installer supports silent installation with /S. Windows may still
    # show an elevation/UAC prompt when system-wide installation needs admin rights.
    try:
        proc = subprocess.run(
            [str(installer), "/S"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except OSError as exc:
        raise DownloadError(f"Nie można uruchomić instalatora WinRAR: {exc}") from exc

    # Give Windows a moment to finish registering App Paths / copying files.
    for _ in range(20):
        found = _find_installed_winrar()
        if found:
            return found
        time.sleep(0.5)

    details = (proc.stderr or proc.stdout or "").strip()
    if proc.returncode not in (0, None):
        details = f"Kod instalatora: {proc.returncode}. {details}".strip()

    # If silent mode was blocked by policy/elevation, launch the installer
    # normally so Windows can show the required UAC/installer interface.
    try:
        subprocess.run([str(installer)], check=False, timeout=300)
    except OSError as exc:
        raise DownloadError(
            f"Nie udało się zainstalować WinRAR. {details or str(exc)}"
        ) from exc

    found = _find_installed_winrar()
    if found:
        return found

    raise DownloadError(
        "WinRAR został pobrany, ale nie udało się potwierdzić instalacji. "
        f"{details}".strip()
    )


def _validate_archive_with_winrar(archive_path: Path, tool: Path) -> None:
    """Validate archive member paths before extraction."""
    try:
        proc = subprocess.run(
            [str(tool), "l", "-c-", "-cfg-", "-idq", str(archive_path)],
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise DownloadError(f"Nie można uruchomić WinRAR: {exc}") from exc

    if proc.returncode != 0:
        text = (proc.stderr or proc.stdout or "WinRAR nie rozpoznał archiwum.").strip()
        raise DownloadError(f"Nieprawidłowe archiwum RAR: {text[-1200:]}")

    # The detailed WinRAR listing is human-oriented, so path validation is
    # additionally performed when possible through rarfile. If rarfile isn't
    # available, extraction is still protected by WinRAR's own current
    # directory-traversal fixes.
    if rarfile is not None:
        try:
            with rarfile.RarFile(str(archive_path)) as rf:
                for info in rf.infolist():
                    _safe_member_name(info.filename)
        except Exception:
            # Do not make rarfile a required backend. WinRAR remains the actual
            # extraction engine.
            pass


def safe_extract_rar(rar_path: Path, destination: Path, progress: Callable[[int], None] | None = None) -> Path:
    if os.name != "nt":
        raise DownloadError("Rozpakowywanie RAR przez WinRAR jest dostępne tylko na Windows.")

    tool = _find_installed_winrar()
    if tool is None:
        tool = _install_winrar()

    destination.mkdir(parents=True, exist_ok=True)
    destination = destination.resolve()
    _validate_archive_with_winrar(rar_path, tool)

    try:
        proc = subprocess.run(
            [
                str(tool),
                "x",
                "-y",
                "-o+",
                "-cfg-",
                "-idq",
                f"-op{destination}",
                str(rar_path),
            ],
            capture_output=True,
            text=True,
            timeout=60 * 30,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise DownloadError(f"Nie można uruchomić WinRAR: {exc}") from exc

    if proc.returncode != 0:
        text = (proc.stderr or proc.stdout or "Nieznany błąd WinRAR").strip()
        raise DownloadError(f"Nie udało się rozpakować RAR: {text[-1200:]}")

    if progress:
        progress(100)
    return destination


def _normalize_archive_destination(destination: Path) -> Path:
    """Use a real .rar suffix instead of the old .archivum pseudo-extension."""
    if destination.suffix.lower() == ".archivum":
        return destination.with_suffix(".rar")
    return destination


def safe_extract_archive(archive_path: Path, destination: Path, progress: Callable[[int], None] | None = None) -> Path:
    if zipfile.is_zipfile(archive_path):
        return safe_extract_zip(archive_path, destination, progress)
    try:
        if rarfile is not None and rarfile.is_rarfile(archive_path):
            return safe_extract_rar(archive_path, destination, progress)
    except Exception:
        # 7-Zip detection below is the source of truth for modern RAR formats.
        pass
    try:
        with archive_path.open("rb") as f:
            sig = f.read(8)
        if sig.startswith(b"Rar!\x1a\x07"):
            return safe_extract_rar(archive_path, destination, progress)
    except OSError as exc:
        raise DownloadError(f"Nie można odczytać archiwum: {exc}") from exc
    raise DownloadError("Pobrany plik nie jest obsługiwanym archiwum ZIP ani RAR.")


# ---------------------------------------------------------------------------
# GoFile resolver
# ---------------------------------------------------------------------------

def _is_gofile_page(url: str) -> bool:
    try:
        p = urlparse(url.strip())
        return p.netloc.lower().split(":",1)[0] in {"gofile.io","www.gofile.io"} and re.match(r"^/d/[^/]+/?$", p.path) is not None
    except Exception:
        return False


def _generate_gofile_website_token(account_token: str, window_offset: int = 0) -> str:
    import hashlib
    ua = os.environ.get("GOFILE_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36")
    language = os.environ.get("GOFILE_LANGUAGE", "en-US")
    salt = os.environ.get("GOFILE_WT_SALT", "12af056dacea0b")
    window = int(time.time() // 14400) + window_offset
    return hashlib.sha256(f"{ua}::{language}::{account_token}::{window}::{salt}".encode()).hexdigest()


def _extract_gofile_children(data: dict) -> list[dict]:
    candidates=[]
    for key in ("contents","children"):
        raw=data.get(key)
        if isinstance(raw,dict): candidates.extend(v for v in raw.values() if isinstance(v,dict))
        elif isinstance(raw,list): candidates.extend(v for v in raw if isinstance(v,dict))
    return candidates


def resolve_gofile_url(url: str, session: requests.Session | None = None) -> tuple[str, requests.Session | None]:
    clean=url.strip()
    if not _is_gofile_page(clean): return clean, session
    m=re.search(r"/d/([^/?#]+)", urlparse(clean).path)
    if not m: raise DownloadError("Nieprawidłowy link Gofile. Oczekiwano https://gofile.io/d/XXXXXXX")
    cid=m.group(1); s=session or requests.Session()
    ua=os.environ.get("GOFILE_USER_AGENT","Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36")
    language=os.environ.get("GOFILE_LANGUAGE","en-US")
    s.headers.update({"User-Agent":ua,"Accept":"*/*","Accept-Language":f"{language},en;q=0.9","Origin":"https://gofile.io","Referer":"https://gofile.io/"})
    try:
        tr=s.post("https://api.gofile.io/accounts",timeout=(15,45)); tr.raise_for_status(); token=(tr.json().get("data") or {}).get("token")
        if not token: raise DownloadError("Gofile nie zwrócił tokenu dostępu.")
        s.cookies.set("accountToken",token,domain="gofile.io",path="/")
        wt=_generate_gofile_website_token(token)
        headers={"Authorization":f"Bearer {token}","X-Website-Token":wt,"X-BL":language}
        params={"contentFilter":"","page":"1","pageSize":"1000","sortField":"createTime","sortDirection":"-1","wt":wt,"cache":"false"}
        r=s.get(f"https://api.gofile.io/contents/{cid}",headers=headers,params=params,timeout=(15,45))
        if r.status_code==401:
            wt=_generate_gofile_website_token(token,-1); headers["X-Website-Token"]=wt; params["wt"]=wt
            r=s.get(f"https://api.gofile.io/contents/{cid}",headers=headers,params=params,timeout=(15,45))
        r.raise_for_status(); payload=r.json()
    except requests.RequestException as exc:
        raise DownloadError(f"Nie udało się połączyć z Gofile: {exc}") from exc
    except ValueError as exc:
        raise DownloadError("Gofile zwrócił nieprawidłową odpowiedź API.") from exc
    data=payload.get("data") or {}
    candidates=_extract_gofile_children(data)
    if str(data.get("type","")).lower()=="file": candidates=[data]
    child_ids=data.get("childs") or data.get("childrenIds")
    if isinstance(child_ids,list) and not candidates:
        for child_id in child_ids:
            if not isinstance(child_id,str): continue
            child_params={"contentFilter":"","page":"1","pageSize":"1000","sortField":"createTime","sortDirection":"-1","wt":_generate_gofile_website_token(token),"cache":"false"}
            cr=s.get(f"https://api.gofile.io/contents/{child_id}",headers=headers,params=child_params,timeout=(15,45))
            if cr.ok:
                cd=cr.json().get("data") or {}
                if cd: candidates.append(cd)
    files=[c for c in candidates if str(c.get("type","")).lower()=="file"]
    archives=[c for c in files if str(c.get("name","")).lower().endswith((".zip",".rar"))]
    chosen=archives[0] if archives else (files[0] if len(files)==1 else None)
    if not chosen:
        names=", ".join(str(c.get("name","plik")) for c in files[:8])
        raise DownloadError("Gofile nie zawiera jednoznacznego pliku ZIP/RAR." + (f" Znalezione: {names}" if names else ""))
    direct=chosen.get("directLink") or chosen.get("link") or chosen.get("downloadPage")
    if not direct: raise DownloadError("Gofile zwrócił plik, ale nie podał adresu pobierania.")
    return str(direct),s


def download_file(url: str, destination: Path, progress: Callable[[int],None]|None=None, progress_info: Callable[[dict[str,Any]],None]|None=None) -> Path:
    if not url.strip(): raise DownloadError("Brak linku pobierania.")
    session=requests.Session(); session.headers.update({"User-Agent":"MizuLauncher/1.0"})
    resolved, gofile_session=resolve_gofile_url(url,session); client=gofile_session or session
    destination=_normalize_archive_destination(destination)
    destination.parent.mkdir(parents=True,exist_ok=True); tmp=destination.with_suffix(destination.suffix+".part")
    for attempt in range(1,4):
        try:
            tmp.unlink(missing_ok=True)
            with client.get(resolved.strip(),stream=True,allow_redirects=True,timeout=(15,180),headers={"User-Agent":client.headers.get("User-Agent","Mozilla/5.0"),"Referer":"https://gofile.io/" if "gofile.io" in resolved.lower() else url,"Accept":"application/octet-stream,*/*"}) as r:
                r.raise_for_status(); content_type=(r.headers.get("content-type") or "").lower(); final_url=str(r.url); total=int(r.headers.get("content-length") or 0)
                if any(x in content_type for x in ("text/html","application/json")):
                    raise DownloadError(f"Serwer zwrócił {content_type or 'dane tekstowe'} zamiast archiwum. URL: {final_url}")
                received=0; started=time.monotonic(); last_emit=0.0
                with tmp.open("wb") as f:
                    for chunk in r.iter_content(1024*1024):
                        if not chunk: continue
                        f.write(chunk); received+=len(chunk); now=time.monotonic(); speed=received/max(now-started,0.001); eta=((total-received)/speed) if total and speed else None; pct=min(100,int(received*100/total)) if total else 0
                        if progress and total: progress(pct)
                        if progress_info and (now-last_emit>=0.2 or (total and received>=total)):
                            progress_info({"received":received,"total":total,"percent":pct,"speed_bps":speed,"eta_seconds":eta,"elapsed_seconds":now-started,"attempt":attempt,"final_url":final_url}); last_emit=now
            if tmp.stat().st_size==0: raise DownloadError("Serwer zwrócił pusty plik.")
            ok=zipfile.is_zipfile(tmp)
            if not ok:
                try: ok=tmp.open("rb").read(8).startswith(b"Rar!\x1a\x07")
                except OSError: pass
                if not ok:
                    sample=tmp.open("rb").read(120).decode("utf-8",errors="replace").replace("\n"," ")
                    raise DownloadError(f"Pobrany plik nie jest ZIP/RAR. Content-Type: {content_type or 'brak'}; URL: {final_url}; początek: {sample[:100]}")
            tmp.replace(destination)
            if progress: progress(100)
            if progress_info:
                elapsed=max(time.monotonic()-started,0.001); size=destination.stat().st_size
                progress_info({"received":size,"total":total or size,"percent":100,"speed_bps":size/elapsed,"eta_seconds":0,"elapsed_seconds":elapsed,"attempt":attempt,"final_url":final_url})
            return destination
        except DownloadError:
            if attempt>=3: tmp.unlink(missing_ok=True); raise
            time.sleep(1.5*attempt)
        except requests.RequestException as exc:
            if attempt>=3: tmp.unlink(missing_ok=True); raise DownloadError(f"Pobieranie nieudane po 3 próbach: {exc}") from exc
            time.sleep(1.5*attempt)
        except Exception as exc:
            if attempt>=3: tmp.unlink(missing_ok=True); raise DownloadError(f"Pobieranie nieudane po 3 próbach: {exc}") from exc
            time.sleep(1.5*attempt)
    raise DownloadError("Pobieranie nieudane.")


def find_game_root(extract_dir: Path) -> Path:
    entries=[p for p in extract_dir.iterdir() if p.name!="__MACOSX"]
    dirs=[p for p in entries if p.is_dir()]; files=[p for p in entries if p.is_file()]
    return dirs[0] if len(dirs)==1 and not files else extract_dir


def find_executable(root: Path) -> Path | None:
    if not root.exists(): return None
    candidates=[]
    for p in root.rglob("*.exe"):
        n=p.name.lower()
        if n in {"uninstall.exe","unins000.exe"} or "crashhandler" in n or "unitycrashhandler" in n: continue
        candidates.append(p)
    candidates.sort(key=lambda p:(len(p.parts),p.name.lower()))
    return candidates[0] if candidates else None


def remove_directory(path: Path) -> None:
    if path.exists(): shutil.rmtree(path,ignore_errors=True)
