from __future__ import annotations

import customtkinter as ctk

from ..models import Game, utc_now
from .dialogs import error
from .theme import COLORS


class GameEditor(ctk.CTkToplevel):
    def __init__(self, master, game: Game | None = None):
        super().__init__(master)
        self.title("Dodaj grę" if game is None else f"Edytuj: {game.name}")
        self.geometry("820x820")
        self.minsize(760, 720)
        self.transient(master)
        self.grab_set()
        self.result = None
        self.release_update = False
        self.original = game
        self.fields = {}
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=15, pady=15)

        self._section("Podstawowe informacje")
        self._field("name", "Nazwa gry *", getattr(game, "name", ""))
        self._field("version", "Wersja", getattr(game, "version", "1.0.0"))
        self._field("developer", "Autor / studio", getattr(game, "developer", "Mizu"))
        self._field("category", "Kategoria", getattr(game, "category", "Other"))
        self._field("tags", "Tagi (po przecinku)", ", ".join(getattr(game, "tags", [])))
        self._field("description", "Opis", getattr(game, "description", ""), multiline=True, height=120)

        self._section("Pobieranie i uruchamianie")
        self._field("download_url", "Link do ZIP-a * (Gofile: https://gofile.io/d/...), także bezpośredni URL)", getattr(game, "download_url", ""))
        self._field("executable", "EXE względem folderu instalacji", getattr(game, "executable", ""), placeholder=r"np. MyGame.exe albo Build\MyGame.exe")
        self._field("arguments", "Argumenty startowe", getattr(game, "arguments", ""), placeholder="np. -fullscreen")
        self._field("install_folder", "Podfolder instalacji (opcjonalnie)", getattr(game, "install_folder", ""), placeholder="np. stable")
        self._field("size_mb", "Rozmiar w MB", str(getattr(game, "size_mb", 0) or 0))

        extraction = ctk.CTkFrame(self.scroll, fg_color=COLORS["panel2"], corner_radius=12)
        extraction.pack(fill="x", pady=(8, 4))
        self.extract_to_game_folder = ctk.BooleanVar(value=getattr(game, "extract_to_game_folder", True))
        ctk.CTkSwitch(
            extraction,
            text="Rozpakuj do osobnego folderu gry",
            variable=self.extract_to_game_folder,
        ).pack(side="left", padx=15, pady=14)
        ctk.CTkLabel(
            extraction,
            text="Wyłącz tylko, jeśli ZIP ma być rozpakowany bez dodatkowego folderu gry.",
            text_color=COLORS["muted"],
            wraplength=420,
            justify="left",
        ).pack(side="left", padx=(8, 15), pady=8)

        self._section("Wygląd i linki")
        self._field("icon_url", "URL ikony 1:1", getattr(game, "icon_url", ""))
        self._field("banner_url", "URL bannera", getattr(game, "banner_url", ""))
        self._field("homepage_url", "Strona projektu", getattr(game, "homepage_url", ""))
        self._field("notes", "Notatki developera", getattr(game, "notes", ""), multiline=True, height=90)

        note_options = ctk.CTkFrame(self.scroll, fg_color=COLORS["panel2"], corner_radius=12)
        note_options.pack(fill="x", pady=(8, 4))
        self.show_install_note = ctk.BooleanVar(value=getattr(game, "show_install_note", False))
        ctk.CTkSwitch(
            note_options,
            text="Pokaż notatkę po kliknięciu „Zainstaluj”",
            variable=self.show_install_note,
        ).pack(anchor="w", padx=15, pady=(12, 6))
        ctk.CTkLabel(note_options, text="Tekst przycisku po notatce", text_color=COLORS["muted"]).pack(anchor="w", padx=15, pady=(0, 4))
        self.install_button_label = ctk.CTkEntry(note_options, height=40)
        self.install_button_label.pack(fill="x", padx=15, pady=(0, 12))
        self.install_button_label.insert(0, getattr(game, "install_button_label", "Rozpocznij pobieranie"))
        self._field("preserve_paths", "Pliki/foldery zachowywane przy aktualizacji (po przecinku)", ", ".join(getattr(game, "preserve_paths", [])), placeholder="np. Saves, userdata, save")

        switches = ctk.CTkFrame(self.scroll, fg_color=COLORS["panel2"], corner_radius=12)
        switches.pack(fill="x", pady=(8, 4))
        self.featured = ctk.BooleanVar(value=getattr(game, "featured", False))
        self.enabled = ctk.BooleanVar(value=getattr(game, "enabled", True))
        ctk.CTkSwitch(switches, text="Wyróżniona gra", variable=self.featured).pack(side="left", padx=15, pady=14)
        ctk.CTkSwitch(switches, text="Dostępna dla użytkowników", variable=self.enabled).pack(side="left", padx=15, pady=14)

        ctk.CTkButton(self.scroll, text="Zapisz grę", height=46, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], command=lambda: self.save(False)).pack(fill="x", pady=(16, 5))
        if self.original:
            ctk.CTkButton(self.scroll, text="🚀 Zapisz i wypuść aktualizację", height=44, fg_color=COLORS["panel3"], hover_color=COLORS["card_hover"], command=lambda: self.save(True)).pack(fill="x", pady=(0, 5))
        ctk.CTkButton(self.scroll, text="Anuluj", height=40, fg_color=COLORS["panel2"], command=self.destroy).pack(fill="x")

    def _section(self, title: str):
        ctk.CTkLabel(self.scroll, text=title, font=ctk.CTkFont(size=18, weight="bold"), text_color=COLORS["text"]).pack(anchor="w", pady=(13, 8))

    def _field(self, key, label, value="", multiline=False, height=42, placeholder=""):
        frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        frame.pack(fill="x", pady=4)
        ctk.CTkLabel(frame, text=label, text_color=COLORS["muted"]).pack(anchor="w", pady=(0, 4))
        if multiline:
            widget = ctk.CTkTextbox(frame, height=height)
            widget.pack(fill="x")
            widget.insert("1.0", value)
        else:
            widget = ctk.CTkEntry(frame, height=height, placeholder_text=placeholder)
            widget.pack(fill="x")
            widget.insert(0, value)
        self.fields[key] = widget

    def _get(self, key) -> str:
        widget = self.fields[key]
        return widget.get("1.0", "end-1c").strip() if isinstance(widget, ctk.CTkTextbox) else widget.get().strip()

    def save(self, release_update=False):
        name = self._get("name")
        url = self._get("download_url")
        if not name:
            error(self, "Brak nazwy", "Podaj nazwę gry.")
            return
        if not url:
            error(self, "Brak ZIP-a", "Podaj link do ZIP-a z grą.")
            return
        if self.show_install_note.get() and not self._get("notes"):
            error(self, "Brak notatki", "Włączyłeś wyświetlanie notatki przed instalacją, ale pole notatki jest puste. Wpisz treść albo wyłącz przełącznik.")
            return

        try:
            size = float(self._get("size_mb").replace(",", ".") or 0)
        except ValueError:
            error(self, "Błędny rozmiar", "Rozmiar musi być liczbą.")
            return

        now = utc_now()
        game = Game.new(
            id=self.original.id if self.original else None,
            name=name,
            version=self._get("version") or "1.0.0",
            developer=self._get("developer") or "Mizu",
            category=self._get("category") or "Other",
            tags=[x.strip() for x in self._get("tags").split(",") if x.strip()],
            description=self._get("description"),
            download_url=url,
            executable=self._get("executable"),
            arguments=self._get("arguments"),
            install_folder=self._get("install_folder"),
            size_mb=size,
            icon_url=self._get("icon_url"),
            banner_url=self._get("banner_url"),
            homepage_url=self._get("homepage_url"),
            notes=self._get("notes"),
            preserve_paths=[x.strip() for x in self._get("preserve_paths").split(",") if x.strip()],
            extract_to_game_folder=self.extract_to_game_folder.get(),
            show_install_note=self.show_install_note.get(),
            install_button_label=self.install_button_label.get().strip() or "Rozpocznij pobieranie",
            featured=self.featured.get(),
            enabled=self.enabled.get(),
            updated_at=now,
        )
        if self.original:
            game.release_date = self.original.release_date
        self.result = game
        self.release_update = bool(release_update and self.original)
        self.destroy()
