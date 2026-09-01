# Portable configuration fix

MizuLauncher no longer stores runtime settings beside the installed EXE.

On Windows the launcher uses:
`%LOCALAPPDATA%\\MizuLauncher`

Games default to:
`%USERPROFILE%\\MizuLauncherGames`

A legacy config containing `C:\\Users\\<old-user>\\MizuLauncherGames` is automatically migrated to the current Windows user.
