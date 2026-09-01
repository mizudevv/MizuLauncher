# Edge Functions — MizuLauncher

Jeśli panel Vercel pokazuje `Failed to send a request to the Edge Function` przy klikaniu akcji, panel najczęściej nie ma wdrożonej funkcji `mizu-admin-action` albo funkcja ma problem z CORS/JWT/sekretami. Supabase zaleca sprawdzenie wdrożenia, logów, CORS i uwierzytelnienia.

## 1. Uruchom CLI

W PowerShell sprawdź:

```powershell
npx supabase --version
```

## 2. Otwórz katalog projektu

Musisz być w katalogu zawierającym folder `supabase` z tej paczki.

```powershell
cd "C:\Users\MaciejTVV\PycharmProjects\mizulauncher-security"
```

Sprawdź:

```powershell
dir .\supabase\functions
```

Powinny istnieć:

```text
mizu-admin-action
mizu-telemetry
mizu-drm-issue
mizu-drm-verify
```

## 3. Zaloguj CLI

```powershell
npx supabase login
```

## 4. Podepnij projekt

W Supabase Dashboard otwórz `Settings -> General` i skopiuj `Reference ID` projektu.

```powershell
npx supabase link --project-ref TWOJ_REFERENCE_ID
```

## 5. Wdróż funkcję używaną przez panel

```powershell
npx supabase functions deploy mizu-admin-action --debug
```

Potem pozostałe:

```powershell
npx supabase functions deploy mizu-telemetry --debug
npx supabase functions deploy mizu-drm-issue --debug
npx supabase functions deploy mizu-drm-verify --debug
```

Po deployu funkcja jest dostępna pod:

```text
https://TWOJ_PROJECT_REF.supabase.co/functions/v1/mizu-admin-action
```

## 6. Sprawdź Dashboard

`Supabase -> Edge Functions`

Musi być widoczna:

```text
mizu-admin-action
```

Jeżeli jej nie ma, panel Vercel nie może jej wywołać.

## 7. Sekrety funkcji

`mizu-admin-action` używa:

```text
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
```

`SUPABASE_SERVICE_ROLE_KEY` ma być dostępny wyłącznie w Edge Function. Nie wolno go umieszczać w `admin-panel/config.js`, Vercel frontendzie ani launcherze.

## 8. Sprawdź logi

`Supabase -> Edge Functions -> mizu-admin-action -> Logs`

Po kliknięciu np. `Zablokuj Granie` powinno pojawić się invocation.

- `404` / `NOT_FOUND` = funkcja nie jest wdrożona albo nazwa jest zła.
- `401` = brak/niepoprawny JWT.
- `403` / `not_admin` = funkcja działa, ale konto nie ma admina.
- `500` / `BOOT_ERROR` = problem z kodem/importem/sekretem.

## 9. CORS

Funkcja musi odpowiadać na `OPTIONS` i zwracać nagłówki CORS. Aktualna wersja `mizu-admin-action` już to robi.

## 10. Test preflight

```powershell
curl.exe -i -X OPTIONS "https://TWOJ_PROJECT_REF.supabase.co/functions/v1/mizu-admin-action"
```

Powinieneś dostać `200 OK`.

Nie testuj `POST` bez poprawnego JWT — funkcja prawidłowo odrzuci nieautoryzowane żądanie.
