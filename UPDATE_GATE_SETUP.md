# MizuLauncher Update Gate

1. Keep `VERSION.txt` in the project root, e.g. `0.0.5`.
2. In Supabase, table `launcher_updates`, row `id=1` must contain:
   - `latest_version`: e.g. `0.0.6`
   - `download_url`: URL to the new EXE/release page
   - `message`: optional message
   - `enabled`: `true`
3. `mizulauncher/deployment.py` must contain the real Supabase URL and publishable key.
4. Start `python main.py`.
5. Diagnostics are written to `data/update_check.log` before the GUI opens.
6. If Supabase cannot be reached or returns a malformed response, the launcher closes instead of bypassing the mandatory gate.
