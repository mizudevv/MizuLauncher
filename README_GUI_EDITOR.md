# MizuLauncher — Visual GUI Editor

## Co zostało dodane

GUI Editor jest dostępny wyłącznie dla zalogowanego konta developera. Layout jest zapisywany lokalnie w `data/layout.json` i może być publikowany razem z katalogiem gier do Supabase. Oznacza to, że inni użytkownicy pobiorą nie tylko gry, ale również opublikowany układ interfejsu.

### Edytor stron
- Home
- Library
- Game Details
- własne zakładki tworzone przyciskiem `+ Nowa zakładka`
- usuwanie i przełączanie stron
- własne zakładki pojawiają się automatycznie w lewym menu launchera (z wyjątkiem wewnętrznych `details`)

### Elementy
- Tekst
- Tytuł sekcji
- Przycisk
- Obraz
- Separator
- Odstęp
- Featured Game
- Lista gier
- Szczegóły gry

Każdy element ma właściwości pozycji i rozmiaru w procentach ekranu, dzięki czemu layout jest responsywny. Dostępne są m.in. X, Y, szerokość, wysokość, font, radius, obramowanie, opacity, kolory, URL obrazu i tekst.

### Akcje przycisków
- Home / Library / Settings
- własna zakładka
- Account Manager
- odświeżenie katalogu
- szczegóły gry
- Graj / Pobierz
- Graj
- Zainstaluj
- Odinstaluj
- Lokalizacja gry
- Strona projektu
- otwórz URL

### Game binding
Przycisk może być przypięty do:
- `context` — bieżącej gry, np. gry otwartej w szczegółach
- `selected` — gry aktualnie wybranej
- `fixed` — konkretnej gry przez jej ID

Dzięki temu jeden template przycisku może działać dla każdej gry. Przykład: template `game_primary` ma akcję `game.primary`. Jeżeli gra jest zainstalowana, przycisk pokazuje `Graj` i uruchamia EXE. Jeżeli nie jest zainstalowana, pokazuje `Zainstaluj` i uruchamia instalację.

### Button Templates
W `Edytor templatek przycisków` możesz tworzyć własne szablony. Template przechowuje wygląd i akcję. Element `button`, `Featured Game`, `Lista gier` i `Szczegóły gry` mogą wskazywać wybrany template.

Przydatne domyślne template:
- `game_primary` — Graj / Zainstaluj
- `game_uninstall` — Odinstaluj
- `game_path` — Lokalizacja

### Live preview
Przycisk w edytorze jest testowalny. Podgląd używa pierwszej gry z bieżącego katalogu jako gry testowej. Dzięki temu można sprawdzić logikę `game.primary`, `game.path`, `game.uninstall` itp. bez ręcznego budowania layoutu.

### Import / Export
- `Export` zapisuje layout do JSON.
- `Import` wczytuje JSON i scala go z domyślnym schema, więc brakujące ustawienia są uzupełniane.
- `Reset` przywraca domyślny layout.

## Jak wdrożyć

1. Rozpakuj paczkę i otwórz folder w IntelliJ IDEA.
2. Upewnij się, że projekt używa Pythona 3.14.
3. W terminalu IntelliJ uruchom:

```powershell
python -m pip install -r requirements.txt
```

4. Uruchom:

```powershell
python main.py
```

5. Zaloguj się na konto developera z Supabase.
6. Wejdź w `Developer → GUI Editor`.
7. Zapisz layout lokalnie przez `Zapisz`.
8. Aby inni użytkownicy zobaczyli zmiany, kliknij `Publikuj` albo `Publikuj katalog + UI` w Developer Center.

## Ważne

Publiczny launcher zawiera tylko Supabase Publishable/anon key. Nie dodawaj do paczki `service_role` ani `sb_secret`. Uprawnienia zapisu katalogu nadal wynikają z RLS i tabeli `launcher_admins`.

## Wersjonowanie layoutu

Layout jest publikowany w tym samym polu JSON `launcher_catalog.data` jako:

```json
{
  "schema_version": 2,
  "updated_at": "...",
  "games": [],
  "layout": {
    "version": 1,
    "design": {"width": 1280, "height": 760},
    "templates": {},
    "pages": {}
  }
}
```

Nie trzeba zmieniać tabeli Supabase, jeśli `data` jest typu `json/jsonb`.
