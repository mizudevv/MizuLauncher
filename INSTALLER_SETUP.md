# MizuLauncher - instalator Windows

## Co jest używane
- PyInstaller: buduje aplikację Python do `dist/MizuLauncher/`.
- Inno Setup 6: pakuje `dist/MizuLauncher/` do jednego `MizuLauncher-Setup-X.Y.Z.exe`.
- Aplikacja używa trybu `onedir`, dzięki czemu assets i pliki uruchomieniowe są osobno i aktualizowanie jest stabilniejsze.

## 1. Zainstaluj Inno Setup
Pobierz darmowy Inno Setup 6 z oficjalnej strony: https://jrsoftware.org/isinfo.php
Podczas instalacji zostaw domyślną ścieżkę `C:\Program Files (x86)\Inno Setup 6\`.

## 2. Python
W projekcie musi być aktywny interpreter używany do `main.py`.

Uruchom w terminalu projektu:

```powershell
python -m pip install -r requirements.txt
```

## 3. Ustaw wersję

Edytuj `VERSION.txt` i wpisz dokładnie trzy liczby, np.:

```text
0.0.6
```

Ta wersja trafi do nazwy instalatora i `AppVersion` Inno Setup.

## 4. Sprawdź konfigurację produkcyjną

Przed buildem sprawdź `mizulauncher/deployment.py`.
Nie wkładaj tam `service_role` ani `sb_secret`.

## 5. Zbuduj instalator

Uruchom:

```text
build_installer.bat
```

Skrypt:
1. odczyta `VERSION.txt`,
2. zbuduje `dist/MizuLauncher/` przez PyInstaller,
3. utworzy `security_manifest.json`,
4. uruchomi Inno Setup,
5. zapisze instalator w `installer-output/`.

Wynik:

```text
installer-output/MizuLauncher-Setup-0.0.6.exe
```

## 6. Test przed publikacją

Na komputerze testowym uruchom instalator.
Sprawdź:
- Desktop shortcut,
- Start Menu,
- uruchomienie launchera,
- Home/Bibliotekę,
- logowanie,
- pobieranie gry,
- update gate,
- `data/update_check.log` w `%LOCALAPPDATA%\\MizuLauncher`.

## 7. Aktualizacja launchera

Gdy wypuszczasz nową wersję:
1. zmień `VERSION.txt`, np. `0.0.5` -> `0.0.6`,
2. uruchom `build_installer.bat`,
3. opublikuj `MizuLauncher-Setup-0.0.6.exe`,
4. w `launcher_updates` ustaw `latest_version = '0.0.6'`,
5. ustaw `download_url` na stronę/release z nowym instalatorem,
6. ustaw `enabled = true`.

## 8. Gdzie są dane użytkownika

Launcher zapisuje dane użytkownika do:

```text
%LOCALAPPDATA%\\MizuLauncher
```

Instalator nie powinien potrzebować uprawnień administratora. Aktualizacja instaluje nowszy build do tego samego katalogu programu, a dane użytkownika pozostają w `%LOCALAPPDATA%\\MizuLauncher`.
