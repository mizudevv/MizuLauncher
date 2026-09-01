# MizuLauncher — secure/admin/DRM build

Use `IMPLEMENTACJA_SECURITY.md` for the full setup.

The public launcher no longer uses a developer code. Developer access is granted only by a verified Supabase session where `player_control.is_developer = true`.

The project contains:

- Python/CustomTkinter launcher;
- Supabase Auth + RLS;
- server-side telemetry Edge Function;
- admin panel for Vercel;
- play/download/kill-switch controls;
- temporary `mizuapi.dat` DRM grants;
- Unity verification sample;
- `.clineignore`;
- build-time EXE integrity manifest.

## Windows Installer
Use `build_installer.bat` after installing Inno Setup 6. See `INSTALLER_SETUP.md`.
