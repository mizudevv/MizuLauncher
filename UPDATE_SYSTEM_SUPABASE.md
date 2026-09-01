# MizuLauncher — aktualizacje sterowane z Supabase

Ta wersja może sprawdzać aktualną wersję bez osobnego `updates.json`.
Launcher używa `launcher_updates` w Supabase, jeśli `update_manifest_url` jest pusty.

## 1. SQL

W Supabase SQL Editor uruchom cały plik `launcher_updates_supabase.sql`.

## 2. Ustawienie bieżącej wersji

Wersja zainstalowana na komputerze jest w `VERSION.txt`, np.:

```text
1.0.0
```

W Supabase wpis:

```sql
update public.launcher_updates
set
    latest_version = '1.1.0',
    download_url = 'https://twoja-strona.pl/mizulauncher',
    message = 'Wymagana jest aktualizacja MizuLaunchera do wersji 1.1.0.',
    enabled = true,
    updated_at = now()
where id = 1;
```

Od tego momentu każdy launcher starszy niż `1.1.0` zostanie zablokowany.

## 3. Wyłączenie obowiązkowej aktualizacji

Gdy nie chcesz wymuszać aktualizacji:

```sql
update public.launcher_updates
set enabled = false,
    updated_at = now()
where id = 1;
```

## 4. Zmiana linku

`download_url` może być np.:

- GitHub Releases,
- Vercel,
- własna strona,
- bezpośredni link do EXE.

Launcher otwiera ten adres przez domyślną przeglądarkę.

## 5. Ważne

Nie musisz wpisywać `UPDATE_MANIFEST_URL` w `deployment.py`. Zostaw je puste:

```python
UPDATE_MANIFEST_URL = ""
UPDATE_DOWNLOAD_URL = ""
```

Launcher wtedy automatycznie korzysta z Supabase.

Jeżeli `update_manifest_url` jest ustawiony, manifest pozostaje priorytetem.

## 6. Test

Najpierw ustaw w `VERSION.txt`:

```text
1.0.0
```

Następnie w Supabase:

```sql
update public.launcher_updates
set latest_version = '1.1.0', enabled = true
where id = 1;
```

Uruchom launcher. Powinien pokazać wymaganie aktualizacji, otworzyć `download_url` i zamknąć się.

Następnie:

```sql
update public.launcher_updates
set latest_version = '1.0.0', enabled = false
where id = 1;
```

Uruchom ponownie launcher — powinien działać normalnie.
