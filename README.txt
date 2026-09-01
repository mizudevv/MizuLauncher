# MizuLauncher — Supabase edition

Pełny launcher gier w Pythonie + CustomTkinter. Pliki gier są pobierane jako ZIP z podanego URL (np. Gofile). Katalog metadanych jest przechowywany w Supabase.

## Najważniejsza zmiana bezpieczeństwa

Launcher **nie zawiera żadnego klucza pozwalającego na zapis**. W aplikacji znajduje się wyłącznie Supabase Publishable Key (dawny `anon` key). Zgodnie z modelem Supabase ten klucz może być używany w aplikacji klienckiej, ale dostęp do danych musi być ograniczony przez RLS. Sekretne `service_role` / secret keys nie mogą być umieszczane w aplikacji. RLS decyduje, czy zalogowany developer może wykonać UPDATE katalogu.

Developer Mode nadal wymaga kodu `x10x`, ale ten kod jest **tylko blokadą UI**. Prawdziwą autoryzację zapewnia Supabase Auth + tabela `launcher_admins` + polityka RLS.

## 1. Wymagania

Zalecam Python 3.12 albo 3.13. Python 3.14 może działać, ale przy bibliotekach binarnych może być potrzebna nowsza wersja pakietu.

W terminalu IntelliJ:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Jeżeli IntelliJ używa `.venv`, upewnij się, że terminal i Run Configuration używają tego samego interpretera.

## 2. Załóż projekt Supabase

1. Wejdź na https://supabase.com/
2. Utwórz darmowy projekt.
3. Otwórz **SQL Editor**.
4. Otwórz plik `supabase_setup.sql` z tego projektu.
5. Wklej całość do SQL Editor i kliknij **Run**.

SQL tworzy:

- `launcher_catalog` — jeden publiczny rekord z katalogiem gier,
- `launcher_admins` — lista użytkowników, którzy mogą publikować katalog,
- `is_launcher_admin()` — bezpieczny check po stronie bazy,
- polityki RLS dla odczytu i zapisu.

Supabase opisuje RLS jako mechanizm, który określa, które role mogą odczytywać i modyfikować rekordy; `anon` może dostać SELECT, a `authenticated` może dostać operacje zapisu tylko według polityk. citehttps://supabase.com/docs/guides/database/postgres/row-level-security

## 3. Utwórz konto developera

W Supabase:

**Authentication -> Users -> Add user**

Utwórz własny email i mocne hasło.

Skopiuj **User UID** tego konta.

Następnie w SQL Editor uruchom:

```sql
insert into public.launcher_admins (user_id)
values ('TU_WKLEJ_USER_UID');
```

To jest kluczowy etap. Samo posiadanie konta Supabase nie daje prawa do publikowania — UID musi znajdować się w `launcher_admins`.

Supabase Auth używa tokenów JWT, a te tokeny mogą być używane przez RLS do autoryzacji operacji w Data API. citehttps://supabase.com/docs/guides/auth

## 4. Pobierz dane do launchera

W Supabase znajdź:

**Settings -> API Keys**

Potrzebujesz:

### Project URL

Np.

```text
https://abcxyz.supabase.co
```

### Publishable key

Np.

```text
sb_publishable_...
```

W starszych projektach możesz zobaczyć też legacy `anon` key. Jest to klucz publiczny o niskich uprawnieniach, którego użycie wymaga prawidłowych RLS policies.

**NIGDY nie wpisuj do launchera:**

```text
service_role
sb_secret_...
Master Key
```

Supabase wyraźnie rozróżnia publishable/anon keys od secret/service_role keys i zabrania ujawniania tych drugich w aplikacji klienckiej. citehttps://supabase.com/docs/guides/getting-started/api-keys

## 5. Skonfiguruj MizuLauncher

Uruchom:

```powershell
python main.py
```

Otwórz:

**Ustawienia -> Supabase**

Wpisz:

```text
Project URL:
https://abcxyz.supabase.co

Publishable key:
sb_publishable_...

ID katalogu:
1

Folder gier:
C:\Users\TwojaNazwa\MizuLauncherGames
```

Kliknij **Zapisz ustawienia**.

Launcher powinien pobrać pusty katalog.

## 6. Developer Mode

W Ustawieniach wpisz:

```text
x10x
```

Kliknij **Odblokuj Developer Mode**.

Pojawi się **Developer Center**.

Kliknij **Zaloguj developera** i podaj email/hasło konta utworzonego w Supabase.

Jeżeli UID konta znajduje się w `launcher_admins`, backend pozwoli na UPDATE katalogu. Jeżeli nie — Supabase zwróci odmowę z RLS.

## 7. Dodawanie gry

Kliknij `Dodaj grę`.

Najważniejsze pola:

- Nazwa — nazwa widoczna w launcherze.
- Wersja — np. `1.0.0`.
- Autor / studio.
- Kategoria.
- Tagi.
- Opis.
- Link do ZIP-a — bezpośredni link, który odpowiada na pobranie ZIP-a.
- EXE — opcjonalnie. Jeżeli puste, launcher spróbuje znaleźć EXE automatycznie.
- Argumenty — np. `-fullscreen`.
- Rozmiar w MB.
- Icon URL / Banner URL — na ten moment są metadanymi katalogu; można je później wykorzystać do graficznego UI.
- Homepage URL.
- Notatki developera.
- Wyróżniona gra.
- Dostępna dla użytkowników.

Przykładowe archiwum:

```text
MyGame.zip
└── MyGame/
    ├── MyGame.exe
    ├── MyGame_Data/
    └── ...
```

## 8. Publikowanie

Po dodaniu/edycji gier kliknij:

**Publikuj katalog**

Launcher wyśle nowy JSON do `launcher_catalog` jako zalogowany developer.

Inne osoby nie potrzebują konta Supabase. Mają tylko publiczny odczyt katalogu.

Supabase wystawia Data API przez REST i pozwala zabezpieczyć operacje grantami oraz RLS. citehttps://supabase.com/docs/guides/apihttps://supabase.com/docs/guides/api/securing-your-api

## 9. Gofile

Do ZIP-ów możesz nadal używać Gofile. W formularzu podajesz URL pobierania ZIP-a.

Ważne: link powinien rzeczywiście zwracać plik ZIP. Nie każdy link z panelu strony jest bezpośrednim linkiem do pliku.

## 10. Budowanie EXE

W IntelliJ kliknij prawym na `build_exe.bat` i uruchom, albo w terminalu:

```powershell
python -m PyInstaller --noconfirm --clean --windowed --name MizuLauncher main.py
```

EXE będzie w:

```text
dist\MizuLauncher.exe
```

Przed zbudowaniem publicznej wersji ustaw Supabase URL i Publishable Key w ustawieniach launchera albo wprowadź je do konfiguracji instalacyjnej, którą planujesz dystrybuować.

## 11. Co jest faktycznie chronione

Publiczny użytkownik może:

- pobrać katalog,
- odczytać dane gier,
- pobrać ZIP-y z Gofile,
- instalować i uruchamiać gry.

Nie może przez sam launcher:

- publikować katalogu,
- edytować gier w backendzie,
- usuwać gier w backendzie,
- wykorzystać service_role/secret key, bo nie ma go w aplikacji.

Developer musi przejść dwie warstwy:

```text
x10x
  ↓
Developer Mode w UI
  ↓
Supabase Auth email + hasło
  ↓
JWT
  ↓
RLS
  ↓
launcher_admins
  ↓
UPDATE launcher_catalog
```

## 12. Gdzie trzyma się lokalny cache

Launcher zapisuje lokalny katalog w:

```text
data/games_cache.json
```

Dzięki temu chwilowa awaria internetu nie powoduje pustej biblioteki.

## 13. Najczęstsze błędy

### `401 Invalid JWT`
Najczęściej zły publishable/anon key lub zły Project URL.

### `403` / `42501` przy publikowaniu
Konto jest zalogowane, ale jego UID nie znajduje się w `launcher_admins` albo brakuje właściwego grantu/policy.

### Katalog pobiera się, ale jest pusty
Sprawdź, czy istnieje rekord `launcher_catalog` z `id = 1`.

### Gra pobiera się, ale nie startuje
Ustaw poprawne pole `EXE względem folderu instalacji`, np.:

```text
MyGame.exe
```

lub:

```text
Build\MyGame.exe
```

Jeżeli pole pozostawisz puste, launcher wyszuka `.exe` automatycznie.
