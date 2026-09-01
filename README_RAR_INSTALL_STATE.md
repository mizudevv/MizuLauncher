# RAR + installed-state fix

This version supports ZIP and RAR archives through `rarfile`.

RAR extraction on Windows requires a local extraction backend. The launcher automatically searches for:
- `7z.exe` / `7zz.exe`
- `UnRAR.exe`
- `unrar`
- `unar`

Recommended for end users: install 7-Zip. The next production installer should bundle a redistributable 7zz binary if you want RAR extraction without a separate installation.

The installed-state marker now stores `install_root_rel`, so games extracted into a nested folder are detected correctly after installation. The launcher also re-checks the actual executable before showing `Graj`.
