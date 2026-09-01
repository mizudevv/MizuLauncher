# MizuLauncher — dokładna implementacja Security / Admin / DRM

## 0. Ważne założenie bezpieczeństwa

To jest architektura **obronna i edukacyjna**. Launcher nie może zagwarantować „niełamliwego DRM”, ponieważ kod gry i klient są uruchamiane na komputerze użytkownika. `mizuapi.dat` + serwerowa weryfikacja ograniczają proste kopiowanie/stare tokeny i pozwalają reagować na blokady administratora, ale zdeterminowany reverse engineer może patchować klienta.

Drugi ważny punkt: telemetrykę traktuj jako dane techniczne gracza. W tym projekcie zapisujemy nazwę użytkownika Windows, hash HWID, lokalny adres IP oraz publiczny adres IP zaobserwowany przez funkcję serwerową. Przed publicznym użyciem projektu pokaż użytkownikowi informację o tej telemetrii i politykę prywatności.

## 1. Struktura

```text
mizulauncher/
├── admin-panel/
│   ├── index.html
│   ├── config.example.js
│   ├── config.js
│   ├── vercel.json
│   └── README.md
├── mizulauncher/
│   ├── security/
│   │   ├── device.py
│   │   ├── drm.py
│   │   ├── integrity.py
│   │   └── monitor.py
│   ├── api.py
│   ├── config.py
│   └── ...
├── supabase/
│   ├── config.toml
│   └── functions/
│       ├── mizu-telemetry/
│       ├── mizu-drm-issue/
│       ├── mizu-drm-verify/
│       └── mizu-admin-action/
├── supabase_security_setup.sql
├── mizulauncher/deployment.py
├── unity-drm-example/MizuDrmGuard.cs
├── .clineignore
└── build_exe.bat
```

## 2. Supabase — baza danych

Otwórz **Supabase → SQL Editor** i uruchom:

```text
supabase_security_setup.sql
```

Ten plik tworzy:

- `player_control` — role, blokady, telemetria i daty aktywności;
- `drm_tokens` — hashe krótkotrwałych tokenów DRM;
- prywatne funkcje `private.is_admin()` i `private.is_developer()`;
- trigger tworzący rekord gracza po rejestracji Auth;
- RLS pozwalający graczowi czytać tylko własny stan, a administratorowi czytać wszystkich;
- RPC `admin_set_player_status` jako dodatkową bezpieczną ścieżkę administracyjną.

Supabase RLS jest właściwym mechanizmem autoryzacji danych po stronie bazy i powinien być używany razem z Auth. Supabase wyraźnie zaleca ochronę tabel przez RLS oraz ostrzega, że dane w `raw_user_meta_data` nie są odpowiednim miejscem dla autoryzacji. citeturn446069search1

### 2.1. Zrób konto administratora

1. Supabase → Authentication → Users.
2. Utwórz zwykłe konto.
3. Skopiuj jego UUID.
4. SQL Editor:

```sql
update public.player_control
set is_developer = true,
    is_admin = true,
    updated_at = now()
where user_id = 'TU_UUID';
```

`is_developer=true` daje dostęp do Developer Center w Pythonie.
`is_admin=true` daje dostęp do zewnętrznego panelu Vercel.

## 3. Edge Functions

Projekt ma cztery funkcje:

```text
mizu-telemetry
mizu-drm-issue
mizu-drm-verify
mizu-admin-action
```

Supabase obecnie wdraża Edge Functions przez CLI; możesz połączyć projekt komendą `supabase link` i wdrożyć wszystkie funkcje przez `supabase functions deploy`. citeturn610200search0turn610200search1

### 3.1. Zainstaluj Supabase CLI

Oficjalnie zainstaluj CLI zgodnie z dokumentacją Supabase, a potem:

```powershell
supabase login
supabase projects list
supabase link --project-ref TWOJ_PROJECT_REF
```

### 3.2. Wdróż funkcje

W katalogu projektu:

```powershell
supabase functions deploy
```

albo pojedynczo:

```powershell
supabase functions deploy mizu-telemetry
supabase functions deploy mizu-drm-issue
supabase functions deploy mizu-drm-verify
supabase functions deploy mizu-admin-action
```

`mizu-drm-verify` jest skonfigurowany jako publiczna funkcja (`verify_jwt=false`), bo Unity uruchamia weryfikację bez sesji launchera. Pozostałe funkcje wymagają JWT.

Supabase automatycznie udostępnia funkcjom produkcyjnym wartości konfiguracyjne projektu; sekretów serwerowych nie wolno wkładać do kodu przeglądarki ani launchera. `service_role` / secret keys omijają RLS i powinny pozostać wyłącznie po stronie serwera. citeturn610200search2turn610200search5

## 4. Python launcher — konfiguracja produkcyjna

Otwórz:

```text
mizulauncher/deployment.py
```

Wpisz:

```python
SUPABASE_URL = "https://TWOJ_PROJECT.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_..."
CATALOG_ID = 1
ADMIN_PANEL_URL = "https://twoj-panel.vercel.app/"
DRM_MASTER_SECRET = "BARDZO_DLUGA_LOSOWA_WARTOSC"
```

Do launchera wpisujesz wyłącznie **publishable/anon key**. Nigdy `service_role` albo `sb_secret`. Supabase wskazuje publishable key jako bezpieczny do aplikacji klienckich przy poprawnym RLS, a secret/service-role jako sekret przeznaczony na serwer. citeturn610200search2

### 4.1. Generowanie DRM secret

Możesz wygenerować długi losowy sekret w Pythonie:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Skopiuj wynik do `DRM_MASTER_SECRET`.

**Ten sam sekret + `gameId` musi być użyty w Unity.** Nie publikuj tego sekretu w repozytorium publicznym. Dla publicznego projektu pamiętaj jednak, że sekret w kliencie gry/launchera nie jest absolutnym sekretem przeciw reverse engineeringowi.

## 5. Telemetria

Po zalogowaniu launcher wysyła do `mizu-telemetry`:

```text
windows_username = os.getlogin() / fallback getpass.getuser()
hwid_hash        = SHA-256 z fingerprintu urządzenia
local_ip         = lokalny adres IPv4
```

Publiczny IP jest odczytywany po stronie Edge Function z nagłówków połączenia, więc launcher nie potrzebuje osobnego zewnętrznego serwisu „what is my IP”.

Funkcja ustala użytkownika z JWT, więc klient nie może wysłać telemetrii dla innego `user_id`.

Telemetria jest wykonywana:

```text
start launchera
login
uruchomienie gry
pobieranie gry
```

Błąd telemetrii nie blokuje aplikacji.

## 6. Zdalne blokady

`player_control` ma:

```text
can_play
can_download
kill_switch
```

### Zablokuj Granie

Launcher nie pozwoli uruchomić gry.

### Zablokuj Pobieranie

Launcher sprawdza `can_download` przed rozpoczęciem pobierania.

### Kill-Switch

Launcher odpytuje stan konta co około 10 sekund.

Jeżeli:

```text
kill_switch = true
```

launcher:

1. usuwa `mizuapi.dat` ze znanych instalacji;
2. pokazuje komunikat;
3. zamyka aplikację.

Jeżeli gra jest uruchomiona, `GameSecurityMonitor` sprawdza stan co około 4 sekundy. Gdy `can_play=false` albo `kill_switch=true`:

1. usuwa `mizuapi.dat`;
2. zatrzymuje proces gry uruchomiony przez launcher;
3. pokazuje komunikat.

Monitor nie zabija przypadkowych procesów systemowych — pracuje wyłącznie na procesie `Popen` uruchomionym dla danej gry.

## 7. mizuapi.dat / DRM

Po instalacji launcher wywołuje `mizu-drm-issue`.

Serwer generuje losowy token i zapisuje **tylko jego hash** do:

```text
public.drm_tokens
```

Token jest ważny 15 minut.

Launcher zapisuje w katalogu gry:

```text
mizuapi.dat
```

Plik jest szyfrowany AES-GCM i zawiera:

```json
{
  "version": 1,
  "game_id": "...",
  "user_id": "...",
  "token": "...",
  "expires_at": "...",
  "status": "authorized"
}
```

## 8. Unity

Do Unity dołącz:

```text
unity-drm-example/MizuDrmGuard.cs
```

Dodaj skrypt do pierwszego obiektu ładowanego przy starcie gry.

W Inspectorze ustaw:

```text
Game Id:
ID gry z MizuLauncher

Game Secret:
DRM_MASTER_SECRET

Verify Function Url:
https://TWOJ_PROJECT.supabase.co/functions/v1/mizu-drm-verify
```

Skrypt:

1. szuka `mizuapi.dat` obok katalogu `*_Data`;
2. deszyfruje go;
3. sprawdza `game_id`, użytkownika, status i czas wygaśnięcia;
4. wysyła token do `mizu-drm-verify`;
5. serwer sprawdza hash tokenu i aktualny `can_play/kill_switch`;
6. przy niepowodzeniu wykonuje `Application.Quit()`.

To jest celowo prosty przykład, który pasuje do Windowsowych buildów Unity. Dla własnej gry możesz później przenieść weryfikację do wcześniejszej sceny bootstrap.

## 9. Panel administratora Vercel

Wejdź do:

```text
admin-panel/
```

Skopiuj:

```text
config.example.js
```

do:

```text
config.js
```

i uzupełnij:

```javascript
window.MIZU_CONFIG = {
  SUPABASE_URL: "https://TWOJ_PROJECT.supabase.co",
  SUPABASE_PUBLISHABLE_KEY: "sb_publishable_..."
};
```

W panelu nie ma miejsca na `service_role`.

Panel:

```text
Login
↓
Supabase Auth
↓
player_control RLS
↓
is_admin
↓
Dashboard
```

Pokazuje:

- email;
- UUID;
- Windows username;
- publiczny IP;
- ostatnią aktywność;
- ostatni login;
- role DEV/ADMIN;
- Can Play;
- Can Download;
- Kill-Switch.

Akcje używają `mizu-admin-action`, który ponownie sprawdza `is_admin` po stronie serwera.

## 10. Wdrożenie na Vercel

W Vercel utwórz projekt wskazujący na folder:

```text
admin-panel
```

Nie potrzebujesz backendu Node — strona jest statycznym HTML + JavaScript.

Po wdrożeniu dostaniesz URL w rodzaju:

```text
https://mizulauncher-admin.vercel.app/
```

Wklej ten URL do:

```python
ADMIN_PANEL_URL
```

w `mizulauncher/deployment.py`.

## 11. Otwieranie panelu z launchera

Developer Center ma:

```text
Otwórz Panel Administratora
```

Wykorzystywany jest systemowy:

```python
webbrowser.open(url)
```

Przycisk jest widoczny tylko po pozytywnym sprawdzeniu `is_developer` w Supabase.

## 12. Blokada lokalnego Developer Mode

Nie ma już `x10x`.

Dostęp do Developer Center wynika wyłącznie z:

```text
Supabase Auth session
+
player_control.is_developer = true
```

Zmiana lokalnego JSON-a nie nadaje uprawnień.

W spakowanym EXE jest również sidecar:

```text
security_manifest.json
```

który zawiera SHA-256 EXE. Przy starcie launcher może wykryć zmianę programu i — jeżeli konto nie jest zweryfikowanym developerem — zamknąć się.

To jest **detekcja ingerencji**, nie absolutne zabezpieczenie przed patchowaniem klienta.

## 13. Budowanie EXE

Najpierw:

```powershell
python -m pip install -r requirements.txt
```

Następnie:

```text
build_exe.bat
```

Powstanie:

```text
dist/MizuLauncher.exe
dist/security_manifest.json
```

Oba pliki muszą być obok siebie.

## 14. Najważniejszy test end-to-end

### Test A — zwykły gracz

1. Rejestracja.
2. Login.
3. `player_control` pojawia się w Supabase.
4. Nie ma Developer w launcherze.
5. Nie ma dostępu do Developer Settings.
6. Pojawia się telemetria.

### Test B — developer

1. `is_developer=true`.
2. Login.
3. Pojawia się Developer.
4. Developer Center działa.
5. Otwórz Panel Administratora.
6. Panel Vercel loguje się osobno.

### Test C — ban grania

1. Uruchom grę.
2. Admin → Zablokuj Granie.
3. W ciągu kilku sekund monitor zauważy blokadę.
4. `mizuapi.dat` zostanie usunięty.
5. Proces gry uruchomiony przez launcher zostanie zatrzymany.

### Test D — ban pobierania

1. Odinstaluj grę.
2. Admin → Zablokuj Pobieranie.
3. Kliknij Pobierz.
4. Launcher powinien zatrzymać operację przed pobraniem.

### Test E — Kill-Switch

1. Launcher jest otwarty.
2. Admin → Zatrzymaj Aplikację.
3. Launcher wykryje `kill_switch`.
4. usunie `mizuapi.dat`;
5. zamknie się.

## 15. Co pozostaje celowo poza klientem

Nigdy nie dodawaj do:

```text
main.py
api.py
admin-panel/index.html
```

wartości:

```text
service_role
sb_secret
SUPABASE_SECRET_KEYS
```

Supabase wskazuje, że secret/service-role keys omijają RLS i powinny być używane wyłącznie po stronie serwera. citeturn610200search2
