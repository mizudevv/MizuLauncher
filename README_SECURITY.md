# MizuLauncher Security / DRM Architecture

This version adds:

- Supabase Auth + RLS developer/admin authorization.
- Server-side telemetry through Supabase Edge Functions. The browser/launcher never contains a service_role key.
- Windows username + hashed HWID collection, with public IP observed server-side by the telemetry Edge Function.
- External Vercel admin panel.
- Admin actions: play ban, download ban, kill-switch.
- Temporary per-game `mizuapi.dat` DRM grant.
- Near-real-time launcher monitoring of the player's own control state.
- Unity C# verification example.
- Local packaged-build tamper detection via a sidecar SHA-256 manifest.

## Security limits

This is an educational / for-fun DRM system. A client-side launcher or Unity game cannot provide unbreakable DRM because the client machine is controlled by the user. The design is intended to make casual copying, stale tokens, and remote policy changes harder, not to replace commercial DRM.

The launcher contains only a Supabase publishable/anon key. Never ship a `service_role` or `sb_secret` key.

## Opcje instalacji gry
- `extract_to_game_folder`: tworzy osobny katalog gry i zachowuje go jako root instalacji. Gdy wyłączone, launcher spłaszcza pojedynczy folder najwyższego poziomu ZIP-a do katalogu gry.
- `show_install_note`: jeśli włączone i istnieje notatka developera, przed pierwszym pobraniem pokazuje okno z notatką.
- `install_button_label`: tekst przycisku w oknie notatki, np. „Pobierz i zainstaluj”.

Downloader sprawdza również, czy odpowiedź jest rzeczywistym ZIP-em. Jeśli hosting zwróci HTML/JSON zamiast pliku, komunikat zawiera Content-Type, końcowy URL i fragment odpowiedzi, zamiast pokazywać postęp, a następnie kończyć się niejasnym błędem.
