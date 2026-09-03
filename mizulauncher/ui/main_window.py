









from __future__ import annotations

import sys

import threading
import time
import webbrowser
import tkinter
from tkinter import filedialog

import customtkinter as ctk

from ..api import ApiError, SupabaseClient
from config import clear_session, load_cache, load_config, load_session, save_cache, save_config, save_session
from ..game_manager import GameManager
from ..models import Catalog, Game, utc_now
from ..deployment import SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, UPDATE_DOWNLOAD_URL, UPDATE_MANIFEST_URL, UPDATE_ID, UPDATE_CHECK_ENABLED
from mizulauncher.update_check import UpdateInfo, fetch_update_info, fetch_update_info_from_supabase
from pathlib import Path
from .dialogs import confirm, error, info
from .game_editor import GameEditor
from .image_loader import ImageLoader
from .theme import COLORS, FONTS, set_palette


TRANSLATIONS = {
    "pl": {"home":"Home","library":"Biblioteka","settings":"Ustawienia","developer":"Developer","account":"Konto","guest":"Gość","login":"Zaloguj","register":"Zarejestruj","skip":"pomiń • przejdź jako gość","language":"Język","theme":"Motyw","dark":"Ciemny","light":"Jasny","appearance":"Wygląd","save":"Zapisz","logout":"Wyloguj","featured":"WYRÓŻNIONA GRA","available":"Dostępne teraz","view_all":"Zobacz wszystkie →","refresh":"↻  Odśwież","no_games":"Katalog jest pusty","details_back":"‹  Biblioteka"},
    "en": {"home":"Home","library":"Library","settings":"Settings","developer":"Developer","account":"Account","guest":"Guest","login":"Log in","register":"Register","skip":"skip • continue as guest","language":"Language","theme":"Theme","dark":"Dark","light":"Light","appearance":"Appearance","save":"Save","logout":"Log out","featured":"FEATURED GAME","available":"Available now","view_all":"View all →","refresh":"↻  Refresh","no_games":"Catalog is empty","details_back":"‹  Library"},
    "es": {"home":"Inicio","library":"Biblioteca","settings":"Ajustes","developer":"Desarrollador","account":"Cuenta","guest":"Invitado","login":"Iniciar sesión","register":"Registrarse","skip":"omitir • continuar como invitado","language":"Idioma","theme":"Tema","dark":"Oscuro","light":"Claro","appearance":"Apariencia","save":"Guardar","logout":"Cerrar sesión","featured":"JUEGO DESTACADO","available":"Disponible ahora","view_all":"Ver todo →","refresh":"↻  Actualizar","no_games":"El catálogo está vacío","details_back":"‹  Biblioteca"},
}


class MizuLauncher(ctk.CTk):
    """MizuLauncher UI - dark graphite/black Steam-like game hub."""

    def __init__(self):
        super().__init__()
        self.title("MizuLauncher")
        self.geometry("1540x940")
        self.minsize(1200, 760)
        self.configure(fg_color=COLORS["bg"])

        self.config = load_config()
        set_palette(self.config.get("theme", "dark"))
        ctk.set_appearance_mode("dark" if self.config.get("theme", "dark") == "dark" else "light")
        self.games: list[Game] = [Game.from_dict(x) for x in load_cache()]
        self.current_view = "home"
        self.selected_game: Game | None = None
        self.guest_mode = bool(self.config.get("guest_mode", False))
        self.manager = GameManager(self.config["download_directory"], self.config.get("game_install_overrides", {}))
        self.api = self._make_api()
        self._restore_saved_session()
        self.image_loader = ImageLoader(self)
        self.settings_entries = {}
        self.developer_entries = {}
        self.account_tab: str = "account"
        self._initial_auth_done = False
        self._ui_generation = 0
        self._update_check_in_progress = False
        self._update_required = False
        self._update_info: UpdateInfo = UpdateInfo()
        self._app_version = self._load_app_version()
        self._build_shell()
        self.after(70, self._startup)

    def t(self, key):
        lang=self.config.get("language","pl")
        return TRANSLATIONS.get(lang, TRANSLATIONS["pl"]).get(key,key)

    def _restore_saved_session(self):
        session=load_session()
        if session.get("refresh_token") and self.api.configured:
            ok=self.api.restore_session(session.get("access_token", ""), session.get("refresh_token", ""))
            if ok:
                self.guest_mode=False
                self.config["guest_mode"]=False
                save_config(self.config)
                save_session(self.api.save_session_state())

    def _persist_session(self):
        if self.api.authenticated:
            save_session(self.api.save_session_state())
        else:
            clear_session()

    def _rebuild_ui(self):
        for widget in (getattr(self,"sidebar",None), getattr(self,"content",None)):
            if widget is not None and widget.winfo_exists(): widget.destroy()
        self.configure(fg_color=COLORS["bg"])
        self._build_shell()
        if self.api.developer_authenticated:
            self._set_developer_visibility(True)
        self.show_view(self.current_view if self.current_view in {"home","library","settings","developer"} else "home")

    # ---------------- Backend ----------------
    def _make_api(self):
        return SupabaseClient(
            self.config.get("supabase_url", ""),
            self.config.get("supabase_publishable_key", ""),
            self.config.get("catalog_id", 1),
        )

    def _startup(self):
        # Mandatory version gate is handled in main.py before the GUI starts.
        self._continue_startup(None)

    def _load_app_version(self) -> str:
        try:
            if getattr(sys, "frozen", False):
                root = Path(sys.executable).resolve().parent
            else:
                root = Path(__file__).resolve().parent.parent.parent
            return (root / "VERSION.txt").read_text(encoding="utf-8").strip() or "0.0.0"
        except OSError:
            return "0.0.0"

    def _show_update_overlay(self, text="Sprawdzanie aktualizacji…"):
        if getattr(self, "_update_overlay", None) is not None and self._update_overlay.winfo_exists():
            self._update_overlay_label.configure(text=text)
            return
        overlay = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0, border_width=0)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._update_overlay = overlay
        ctk.CTkLabel(overlay, text="MizuLauncher", font=ctk.CTkFont(size=30, weight="bold"), text_color=COLORS["text"]).pack(pady=(250, 10))
        self._update_overlay_label = ctk.CTkLabel(overlay, text=text, text_color=COLORS["muted"])
        self._update_overlay_label.pack()
        self.update_idletasks()

    def _hide_update_overlay(self):
        overlay = getattr(self, "_update_overlay", None)
        if overlay is not None and overlay.winfo_exists():
            overlay.destroy()
        self._update_overlay = None

    def _check_for_updates_async(self, callback):
        if self._update_check_in_progress:
            return
        if not UPDATE_CHECK_ENABLED:
            callback(UpdateInfo(checked=True))
            return

        self._update_check_in_progress = True
        self._show_update_overlay("Sprawdzanie aktualizacji…")

        project_url = (SUPABASE_URL or "").strip()
        publishable_key = (SUPABASE_PUBLISHABLE_KEY or "").strip()
        update_id = int(self.config.get("update_id", UPDATE_ID))

        def worker():
            try:
                # Supabase is the primary update source.
                info_result = fetch_update_info_from_supabase(
                    project_url,
                    publishable_key,
                    self._app_version,
                    update_id=update_id,
                )

                # Optional legacy manifest fallback only when Supabase cannot be checked.
                if not info_result.checked:
                    manifest_url = (self.config.get("update_manifest_url") or UPDATE_MANIFEST_URL or "").strip()
                    if manifest_url:
                        info_result = fetch_update_info(manifest_url, self._app_version)
            except Exception as exc:
                info_result = UpdateInfo(checked=True, error=f"Błąd sprawdzania aktualizacji: {exc}")

            self.after(0, lambda r=info_result: self._finish_update_check(r, callback))

        threading.Thread(target=worker, name="MizuUpdateCheck", daemon=True).start()

    def _finish_update_check(self, info_result: UpdateInfo, callback):
        self._update_check_in_progress = False
        self._update_info = info_result
        self._update_required = bool(info_result.available)
        if info_result.error:
            print(f"[MizuLauncher] Update check: {info_result.error}")
            # Do not silently bypass the mandatory update gate when the authoritative
            # Supabase check could not be completed. The user gets an actionable error.
            self._hide_update_overlay()
            error(self, "Nie można zweryfikować wersji", f"MizuLauncher nie może sprawdzić aktualizacji.\n\n{info_result.error}\n\nSprawdź internet i konfigurację Supabase.")
            self.after(50, self.destroy)
            return
        if info_result.available:
            self._hide_update_overlay()
            self._handle_required_update(info_result)
            return
        self._hide_update_overlay()
        callback(info_result)

    def _handle_required_update(self, info_result: UpdateInfo):
        import webbrowser
        title = "Wymagana aktualizacja"
        message = (
            f"Ta wersja MizuLaunchera ({self._app_version}) nie jest już aktualna.\n\n"
            f"Najnowsza wersja: {info_result.latest_version}\n\n"
            + (info_result.message + "\n\n" if info_result.message else "")
            + "Launcher zostanie zamknięty. Zaktualizuj aplikację, aby kontynuować."
        )
        info(self, title, message)
        page_url = info_result.page_url or (self.config.get("update_download_url") or UPDATE_DOWNLOAD_URL or "").strip()
        if page_url:
            try:
                webbrowser.open(page_url)
            except Exception:
                pass
        self.after(120, self.destroy)

    def _continue_startup(self, _info_result=None):
        if not self.guest_mode and not self.api.configured:
            self.show_auth_gate()
        elif not self.guest_mode and not self.api.authenticated:
            self.show_auth_gate()
        else:
            self.refresh_games(initial=True)

    def _update_allows_action(self, game: Game | None = None) -> bool:
        if self._update_required:
            self._handle_required_update(self._update_info)
            return False
        return True

    # ---------------- Shell ----------------
    def _build_shell(self):
        self.sidebar = ctk.CTkFrame(self, width=255, fg_color=COLORS["panel"], corner_radius=0,
                                    border_width=1, border_color=COLORS["black"])
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Hard black separator between sidebar/content.
        ctk.CTkFrame(self, width=4, fg_color=COLORS["black"], corner_radius=0).pack(side="left", fill="y")

        self.content = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        self.content.pack(side="right", fill="both", expand=True)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=22, pady=(24, 18))
        if getattr(sys, "frozen", False):
            logo_root = Path(sys.executable).resolve().parent / "assets"
        else:
            logo_root = Path(__file__).resolve().parent.parent.parent / "assets"
        try:
            from PIL import Image
            dark_logo = Image.open(logo_root / "mizu_logo.png")
            light_logo = Image.open(logo_root / "mizu_logo_black.png")
            logo_img = ctk.CTkImage(light_image=light_logo, dark_image=dark_logo, size=(54,54))
            ctk.CTkLabel(brand, image=logo_img, text="").pack(anchor="w", pady=(0,8))
        except Exception:
            pass
        ctk.CTkLabel(brand, text="MIZU", font=ctk.CTkFont(size=28, weight="bold"), text_color=COLORS["text"]).pack(anchor="w")
        ctk.CTkLabel(brand, text="GAME LAUNCHER", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLORS["muted"]).pack(anchor="w", pady=(2, 0))
        ctk.CTkFrame(brand, width=50, height=3, fg_color=COLORS["text"], corner_radius=2).pack(anchor="w", pady=(10, 0))

        self.nav_buttons = {}
        self._nav("home", "⌂", self.t("home"))
        self._nav("library", "▦", self.t("library"))
        self._nav("settings", "⚙", self.t("settings"))
        self.dev_button = self._nav("developer", "◆", self.t("developer"), visible=False)

        ctk.CTkFrame(self.sidebar, height=2, fg_color=COLORS["black"], corner_radius=0).pack(fill="x", padx=14, pady=(16, 12))

        spacer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        self.status_pill = ctk.CTkFrame(self.sidebar, fg_color=COLORS["panel2"], corner_radius=13,
                                        border_width=1, border_color=COLORS["black"])
        self.status_pill.pack(fill="x", padx=14, pady=(0, 10))
        self.status_dot = ctk.CTkLabel(self.status_pill, text="●", text_color=COLORS["orange"], font=ctk.CTkFont(size=11))
        self.status_dot.pack(side="left", padx=(12, 5), pady=10)
        self.status_label = ctk.CTkLabel(self.status_pill, text="Offline / cache", text_color=COLORS["muted"], anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True, pady=10)

        self.account_card = ctk.CTkButton(
            self.sidebar,
            text="",
            anchor="w",
            height=76,
            corner_radius=16,
            fg_color=COLORS["panel2"],
            hover_color=COLORS["card_hover"],
            border_width=1,
            border_color=COLORS["black"],
            command=self.open_account_manager,
        )
        self.account_card.pack(fill="x", padx=14, pady=(0, 16))
        self._refresh_account_card()

    def _nav(self, key, icon, text, visible=True):
        btn = ctk.CTkButton(
            self.sidebar,
            text=f"{icon}   {text}",
            anchor="w",
            height=46,
            corner_radius=11,
            fg_color="transparent",
            hover_color=COLORS["card_hover"],
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda k=key: self.show_view(k),
        )
        if visible:
            btn.pack(fill="x", padx=14, pady=3)
        self.nav_buttons[key] = btn
        return btn

    def _refresh_account_card(self):
        if self.api.authenticated:
            role = "DEVELOPER" if self.api.developer_authenticated else "PLAYER"
            text = f"  ●  {self.api.user_email or 'Konto'}\n       {role}"
            self.account_card.configure(text=text, text_color=COLORS["text"])
        elif self.guest_mode:
            self.account_card.configure(text="  ○  Gość\n       Zaloguj się ↗", text_color=COLORS["muted"])
        else:
            self.account_card.configure(text="  ○  Konto\n       Zaloguj / zarejestruj", text_color=COLORS["muted"])

    def _set_developer_visibility(self, visible: bool):
        btn = self.dev_button
        if visible:
            if not btn.winfo_ismapped():
                btn.pack(fill="x", padx=14, pady=3)
        elif btn.winfo_ismapped():
            btn.pack_forget()

    # ---------------- Navigation / animation ----------------
    def _clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def show_view(self, view: str):
        if view == "developer" and not self.api.developer_authenticated:
            return
        self.current_view = view
        for key, btn in self.nav_buttons.items():
            active = key == view
            btn.configure(
                fg_color=COLORS["panel3"] if active else "transparent",
                text_color=COLORS["text"] if active else COLORS["muted"],
            )
        self._clear_content()
        getattr(self, f"build_{view}")()
        self._animate_content_in()

    def _animate_content_in(self):
        """Navigation animation intentionally disabled.

        Full-page navigation should be immediate; animations are reserved for
        small, local UI elements so returning from Settings/Developer never
        causes the Home screen to visibly slide or stutter.
        """
        return

    def _topbar(self, title: str, subtitle: str = "", show_refresh=True, back=None):
        row = ctk.CTkFrame(self.content, fg_color="transparent")
        row.pack(fill="x", padx=30, pady=(24, 10))
        if back:
            ctk.CTkButton(row, text="‹", width=40, height=40, corner_radius=11,
                          fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"],
                          border_width=1, border_color=COLORS["black"], command=back).pack(side="left", padx=(0, 12))
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text=title, font=ctk.CTkFont(size=FONTS["title"], weight="bold"), text_color=COLORS["text"]).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(left, text=subtitle, font=ctk.CTkFont(size=12), text_color=COLORS["muted"]).pack(anchor="w", pady=(3, 0))
        if show_refresh:
            ctk.CTkButton(row, text=self.t("refresh"), width=118, height=38, corner_radius=10,
                          fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"],
                          border_width=1, border_color=COLORS["black"], command=self.refresh_games).pack(side="right")

    # ---------------- Auth ----------------
    def show_auth_gate(self):
        self._clear_content()
        # Full application auth landing page.
        wrapper = ctk.CTkFrame(self.content, fg_color="transparent")
        wrapper.pack(fill="both", expand=True, padx=36, pady=28)

        art = ctk.CTkFrame(wrapper, fg_color=COLORS["panel"], corner_radius=30,
                           border_width=2, border_color=COLORS["black"])
        art.pack(fill="both", expand=True)

        left = ctk.CTkFrame(art, fg_color="#101010", corner_radius=26)
        left.pack(side="left", fill="both", expand=True, padx=3, pady=3)
        ctk.CTkFrame(art, width=3, fg_color=COLORS["black"], corner_radius=0).place(relx=0.56, rely=0.04, relheight=0.92)

        ctk.CTkLabel(left, text="MIZU", font=ctk.CTkFont(size=58, weight="bold"), text_color=COLORS["text"]).pack(anchor="w", padx=58, pady=(110, 0))
        ctk.CTkLabel(left, text="YOUR GAMES.\nONE PLACE.", font=ctk.CTkFont(size=28, weight="bold"), justify="left", text_color=COLORS["text"]).pack(anchor="w", padx=58, pady=(5, 12))
        ctk.CTkLabel(left, text="Pobieraj, aktualizuj i uruchamiaj swoje gry\nz jednego miejsca.", text_color=COLORS["muted"], justify="left", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=58)
        ctk.CTkFrame(left, width=90, height=4, fg_color=COLORS["text"], corner_radius=2).pack(anchor="w", padx=58, pady=(24, 0))
        ctk.CTkLabel(left, text="MIZULAUNCHER • 2026", text_color=COLORS["subtle"], font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=58, pady=(170, 0))

        right = ctk.CTkFrame(art, fg_color="transparent", width=455)
        right.pack(side="right", fill="y", padx=(18, 42), pady=42)
        right.pack_propagate(False)

        ctk.CTkLabel(right, text="Witaj", font=ctk.CTkFont(size=30, weight="bold"), text_color=COLORS["text"]).pack(anchor="w", pady=(55, 3))
        ctk.CTkLabel(right, text="Zaloguj się albo utwórz konto. Możesz też przejść dalej jako gość.", text_color=COLORS["muted"], wraplength=380, justify="left").pack(anchor="w", pady=(0, 24))

        self.auth_email = ctk.CTkEntry(right, height=46, placeholder_text="Email", fg_color=COLORS["panel2"], border_color=COLORS["black"], border_width=2)
        self.auth_email.pack(fill="x", pady=5)
        self.auth_password = ctk.CTkEntry(right, height=46, placeholder_text="Hasło", show="•", fg_color=COLORS["panel2"], border_color=COLORS["black"], border_width=2)
        self.auth_password.pack(fill="x", pady=5)

        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(fill="x", pady=(14, 8))
        ctk.CTkButton(row, text="ZALOGUJ", height=44, fg_color=COLORS["text"], hover_color=COLORS["white"], text_color=COLORS["black"], command=self._auth_login).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(row, text="REJESTRUJ", height=44, fg_color=COLORS["panel3"], hover_color=COLORS["card_hover"], border_width=1, border_color=COLORS["black"], command=self._auth_register).pack(side="left", fill="x", expand=True, padx=(5, 0))

        ctk.CTkButton(right, text="pomiń  •  przejdź jako gość", height=36, fg_color="transparent", hover_color=COLORS["panel2"], text_color=COLORS["subtle"], command=self._continue_as_guest).pack(pady=(18, 8))
        ctk.CTkButton(right, text="konfiguracja backendu / developer", height=30, fg_color="transparent", hover_color=COLORS["panel2"], text_color=COLORS["subtle"], command=self.open_backend_setup).pack(pady=(4, 0))

    @staticmethod
    def _normalize_auth_error(exc: Exception, action: str = "auth") -> tuple[str, str]:
        """Return user-friendly auth title/message instead of raw HTTP errors."""
        text = str(exc or "").strip()
        lower = text.lower()
        if "email_not_confirmed" in lower or "email not confirmed" in lower:
            return ("Potwierdź adres email", "Ten adres email nie został jeszcze potwierdzony. Sprawdź skrzynkę pocztową i kliknij link potwierdzający.")
        if "invalid_credentials" in lower or "invalid login credentials" in lower or "invalid_grant" in lower:
            return ("Nieprawidłowe dane", "Nieprawidłowy email lub hasło.")
        if "user_already_exists" in lower or "email_exists" in lower or "user already registered" in lower:
            return ("Email jest już zajęty", "Konto z tym adresem email już istnieje. Spróbuj się zalogować.")
        if "weak_password" in lower or "password should be at least" in lower:
            return ("Hasło jest za słabe", "Hasło nie spełnia wymagań Supabase. Użyj silniejszego hasła.")
        if "email_address" in lower and ("invalid" in lower or "valid" in lower):
            return ("Nieprawidłowy email", "Wpisz poprawny adres email, np. osoba@example.com.")
        if "signup is disabled" in lower or "email_provider_disabled" in lower:
            return ("Rejestracja wyłączona", "Rejestracja przez email jest wyłączona w ustawieniach Supabase.")
        if "rate limit" in lower or "too many" in lower or "over_email_send_rate_limit" in lower:
            return ("Za dużo prób", "Supabase chwilowo ograniczył liczbę prób. Odczekaj chwilę i spróbuj ponownie.")
        if "401" in lower and action == "login":
            return ("Logowanie nieudane", "Nieprawidłowy email lub hasło, albo sesja Supabase jest nieprawidłowa.")
        if "400" in lower:
            return ("Nieprawidłowe dane", "Supabase odrzucił dane logowania/rejestracji. Sprawdź email, hasło oraz konfigurację Auth.")
        if "403" in lower:
            return ("Brak dostępu", "Supabase odmówił dostępu. Sprawdź klucz Publishable oraz konfigurację projektu.")
        if "404" in lower or "not found" in lower:
            return ("Nie znaleziono projektu", "Sprawdź Supabase Project URL w Developer Settings.")
        if "connect" in lower or "timeout" in lower or "name or service" in lower:
            return ("Brak połączenia", "Nie można połączyć się z Supabase. Sprawdź internet i Project URL.")
        return (("Logowanie nieudane" if action == "login" else "Rejestracja nieudana"), text or "Wystąpił nieznany błąd Supabase.")

    @staticmethod
    def _validate_auth_input(email: str, password: str) -> str | None:
        import re
        email = email.strip()
        if not email:
            return "Wpisz adres email."
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return "Wpisz poprawny adres email, np. osoba@example.com."
        if not password:
            return "Wpisz hasło."
        if len(password) < 6:
            return "Hasło powinno mieć co najmniej 6 znaków."
        return None

    def _auth_login(self):
        email = self.auth_email.get().strip()
        password = self.auth_password.get()
        validation = self._validate_auth_input(email, password)
        if validation:
            error(self, "Nieprawidłowe dane", validation)
            return
        self._auth_busy(True)
        def worker():
            try:
                self.api.sign_in(email, password)
                self.config["guest_mode"] = False
                self.config["developer_email"] = email
                save_config(self.config)
                self._persist_session()
                self.after(0, self._login_complete)
            except Exception as exc:
                title, message = self._normalize_auth_error(exc, "login")
                self.after(0, lambda t=title, m=message: (self._auth_busy(False), error(self, t, m)))
        threading.Thread(target=worker, daemon=True).start()

    def _auth_register(self):
        email = self.auth_email.get().strip()
        password = self.auth_password.get()
        validation = self._validate_auth_input(email, password)
        if validation:
            error(self, "Nieprawidłowe dane", validation)
            return
        self._auth_busy(True)
        def worker():
            try:
                data = self.api.sign_up(email, password)
                if self.api.authenticated:
                    self.config["guest_mode"] = False
                    self.config["developer_email"] = email
                    save_config(self.config)
                    self._persist_session()
                    self.after(0, self._login_complete)
                else:
                    self.after(0, lambda: (self._auth_busy(False), info(self, "Konto utworzone", "Sprawdź email i potwierdź konto, następnie zaloguj się.")))
            except Exception as exc:
                title, message = self._normalize_auth_error(exc, "register")
                self.after(0, lambda t=title, m=message: (self._auth_busy(False), error(self, t, m)))
        threading.Thread(target=worker, daemon=True).start()

    def _auth_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.auth_email.configure(state=state)
        self.auth_password.configure(state=state)

    def _login_complete(self):
        self._auth_busy(False)
        self._set_developer_visibility(self.api.developer_authenticated)
        self.guest_mode = False
        self._refresh_account_card()
        self.refresh_games(initial=True)

    def _continue_as_guest(self):
        self.guest_mode = True
        self.config["guest_mode"] = True
        save_config(self.config)
        self._refresh_account_card()
        self.refresh_games(initial=True)

    def open_backend_setup(self):
        win = ctk.CTkToplevel(self)
        win.title("MizuLauncher • Backend Setup")
        win.geometry("660x520")
        win.transient(self)
        win.grab_set()
        box = ctk.CTkScrollableFrame(win, fg_color=COLORS["bg"])
        box.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(box, text="Developer backend", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", pady=(4, 3))
        ctk.CTkLabel(box, text="Tylko konfiguracja połączenia. Uprawnienia zapisu nadal kontroluje Supabase RLS.", text_color=COLORS["muted"], wraplength=580).pack(anchor="w", pady=(0, 18))
        entries = {}
        for key, label, placeholder in [
            ("supabase_url", "Supabase Project URL", "https://xxxx.supabase.co"),
            ("supabase_publishable_key", "Supabase Publishable Key", "sb_publishable_..."),
            ("catalog_id", "Catalog ID", "1"),
        ]:
            ctk.CTkLabel(box, text=label, text_color=COLORS["muted"]).pack(anchor="w", pady=(8, 4))
            e = ctk.CTkEntry(box, height=44, placeholder_text=placeholder, fg_color=COLORS["panel2"], border_width=2, border_color=COLORS["black"])
            e.pack(fill="x")
            value = str(self.config.get(key, ""))
            if value:
                e.insert(0, value)
            entries[key] = e
        def save_backend():
            try:
                self.config["supabase_url"] = entries["supabase_url"].get().strip()
                self.config["supabase_publishable_key"] = entries["supabase_publishable_key"].get().strip()
                self.config["catalog_id"] = int(entries["catalog_id"].get().strip() or 1)
                save_config(self.config)
                self.api = self._make_api()
                win.destroy()
                self._refresh_account_card()
                self.show_auth_gate()
            except Exception as exc:
                error(win, "Błąd konfiguracji", str(exc))
        ctk.CTkButton(box, text="Zapisz konfigurację", height=46, fg_color=COLORS["text"], text_color=COLORS["black"], hover_color=COLORS["white"], command=save_backend).pack(fill="x", pady=(24, 8))
        ctk.CTkButton(box, text="Anuluj", height=40, fg_color=COLORS["panel2"], command=win.destroy).pack(fill="x")

    # ---------------- Home / Library ----------------
    def build_home(self):
        featured = [g for g in self.games if g.enabled and g.featured] or [g for g in self.games if g.enabled][:1]
        if featured:
            self._build_hero(featured[0])
        else:
            self._topbar("Witaj w MizuLauncher", "Twoje centrum gier.")
            self._empty_state("Katalog jest pusty", "Zaloguj się i odśwież katalog albo dodaj gry w Developer Center.")
            return

        section = ctk.CTkFrame(self.content, fg_color="transparent")
        section.pack(fill="x", padx=30, pady=(6, 7))
        ctk.CTkLabel(section, text="Dostępne teraz", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(section, text="Zobacz wszystkie →", width=150, height=32, fg_color="transparent", hover_color=COLORS["panel2"], command=lambda: self.show_view("library")).pack(side="right")

        grid = ctk.CTkScrollableFrame(self.content, fg_color="transparent", orientation="horizontal", height=264)
        grid.pack(fill="x", padx=22, pady=(0, 14))
        for game in [g for g in self.games if g.enabled][:10]:
            self._game_card(grid, game, compact=True)

    def _build_hero(self, game: Game):
        hero=ctk.CTkFrame(self.content, fg_color=COLORS["panel"], corner_radius=28, border_width=2, border_color=COLORS["black"], height=400)
        hero.pack(fill="x", padx=28, pady=(24,14)); hero.pack_propagate(False)
        image=ctk.CTkLabel(hero,text="",fg_color=COLORS["panel2"],corner_radius=26)
        image.pack(fill="both",expand=True,padx=2,pady=2)
        content=ctk.CTkFrame(hero,fg_color="transparent")
        content.place(relx=0.035,rely=0.05,relwidth=0.52,relheight=0.90)
        ctk.CTkLabel(content,text=self.t("featured"),text_color="#D0D0D0",font=ctk.CTkFont(size=10,weight="bold")).pack(anchor="w",pady=(24,0))
        ctk.CTkFrame(content,width=70,height=4,fg_color=COLORS["text"],corner_radius=2).pack(anchor="w",pady=(11,14))
        ctk.CTkLabel(content,text=game.name,font=ctk.CTkFont(size=38,weight="bold"),wraplength=650,justify="left").pack(anchor="w")
        ctk.CTkLabel(content,text=f"v{game.version}   •   {game.category}   •   {game.developer}",text_color="#D0D0D0").pack(anchor="w",pady=(5,0))
        ctk.CTkLabel(content,text=game.description or "Brak opisu.",text_color="#E4E4E4",wraplength=610,justify="left",font=ctk.CTkFont(size=13)).pack(anchor="w",pady=(16,20))
        ctk.CTkButton(content,text="Otwórz grę  →",width=175,height=45,corner_radius=12,fg_color=COLORS["text"],text_color=COLORS["black"],hover_color=COLORS["white"],command=lambda g=game:self.open_game_details(g)).pack(anchor="w")
        self.image_loader.request(game.banner_url,game.name,(1080,396),"hero",lambda img:image.configure(image=img,text=""))

    def build_library(self):
        self._topbar("Biblioteka", f"{len(self.games)} gier w katalogu")
        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=22, pady=(0, 20))
        visible = [g for g in self.games if g.enabled]
        if not visible:
            self._empty_state("Brak gier", "Gdy katalog zostanie opublikowany, pojawią się tutaj.")
            return
        # 3-column style made with rows; actual frames are clickable and therefore images work correctly.
        columns = 3
        row = None
        for index, game in enumerate(visible):
            if index % columns == 0:
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=5)
            self._game_card(row, game, compact=False)

    def _game_card(self, parent, game: Game, compact=False):
        width = 280 if not compact else 240
        height = 284 if not compact else 242
        card = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=17,
                            border_width=2, border_color=COLORS["black"], width=width, height=height)
        card.pack(side="left", fill="y", expand=not compact, padx=6, pady=6)
        card.pack_propagate(False)
        image = ctk.CTkLabel(card, text="", fg_color=COLORS["panel2"], corner_radius=13)
        image.pack(fill="x", padx=5, pady=5, ipady=48 if compact else 58)
        self.image_loader.request(game.banner_url, game.name, (width - 10, 128 if compact else 150), "banner", lambda img, w=image: w.configure(image=img, text=""))
        ctk.CTkLabel(card, text=game.name, font=ctk.CTkFont(size=15 if compact else 16, weight="bold"), anchor="w").pack(fill="x", padx=14, pady=(4, 0))
        ctk.CTkLabel(card, text=f"v{game.version}  •  {game.category}", text_color=COLORS["muted"], anchor="w").pack(fill="x", padx=14, pady=(2, 0))
        if not compact:
            ctk.CTkLabel(card, text=(game.description or "Brak opisu.")[:115], text_color=COLORS["muted"], anchor="w", justify="left", wraplength=240).pack(fill="x", padx=14, pady=(6, 0))
        button = ctk.CTkButton(card, text="Szczegóły  →", height=34, fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"], command=lambda g=game: self.open_game_details(g))
        button.pack(fill="x", padx=12, pady=10)

        # Make the whole visual card clickable, too.
        for widget in (card, image):
            widget.bind("<Button-1>", lambda _e, g=game: self.open_game_details(g))

    def _empty_state(self, title, subtitle):
        box = ctk.CTkFrame(self.content, fg_color=COLORS["panel"], corner_radius=24,
                           border_width=2, border_color=COLORS["black"])
        box.pack(fill="both", expand=True, padx=30, pady=12)
        ctk.CTkLabel(box, text="◇", font=ctk.CTkFont(size=56, weight="bold"), text_color=COLORS["muted"]).pack(pady=(100, 12))
        ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=28, weight="bold")).pack()
        ctk.CTkLabel(box, text=subtitle, text_color=COLORS["muted"], wraplength=620, justify="center").pack(pady=(8, 18))

    # ---------------- Full game page ----------------
    def open_game_details(self, game: Game):
        self.selected_game = game
        self.current_view = "game_details"
        self._clear_content()

        outer = ctk.CTkFrame(self.content, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=24, pady=18)
        self._animate_frame_in(outer)

        back = ctk.CTkButton(outer, text="‹  Biblioteka", width=125, height=38, corner_radius=11,
                             fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"],
                             border_width=1, border_color=COLORS["black"], command=lambda: self.show_view("library"))
        back.pack(anchor="w", pady=(0, 10))

        hero = ctk.CTkFrame(outer, fg_color=COLORS["panel"], corner_radius=24, height=330,
                            border_width=2, border_color=COLORS["black"])
        hero.pack(fill="x")
        hero.pack_propagate(False)
        banner = ctk.CTkLabel(hero, text="", fg_color=COLORS["panel2"], corner_radius=22)
        banner.pack(fill="both", expand=True, padx=2, pady=2)
        self.image_loader.request(game.banner_url or game.icon_url, game.name, (1160, 326), "banner", lambda img: banner.configure(image=img, text=""))

        body = ctk.CTkFrame(outer, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(12, 0))
        left = ctk.CTkFrame(body, fg_color=COLORS["panel"], corner_radius=20, border_width=2, border_color=COLORS["black"])
        left.pack(side="left", fill="both", expand=True)
        right = ctk.CTkFrame(body, fg_color=COLORS["panel"], corner_radius=20, width=300, border_width=2, border_color=COLORS["black"])
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        head = ctk.CTkFrame(left, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(20, 12))
        icon = ctk.CTkLabel(head, text="", width=92, height=92, corner_radius=18, fg_color=COLORS["panel2"], border_width=2, border_color=COLORS["black"])
        icon.pack(side="left")
        self.image_loader.request(game.icon_url, game.name, (92, 92), "icon", lambda img: icon.configure(image=img, text=""))
        meta = ctk.CTkFrame(head, fg_color="transparent")
        meta.pack(side="left", fill="both", expand=True, padx=(16, 0))
        ctk.CTkLabel(meta, text=game.name, font=ctk.CTkFont(size=30, weight="bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(meta, text=f"v{game.version}   •   {game.developer}   •   {game.category}", text_color=COLORS["muted"], anchor="w").pack(anchor="w", pady=(3, 0))
        if game.tags:
            ctk.CTkLabel(meta, text="  ".join(f"#{x}" for x in game.tags), text_color=COLORS["subtle"], anchor="w").pack(anchor="w", pady=(7, 0))

        textbox = ctk.CTkTextbox(left, height=155, fg_color=COLORS["bg2"], border_width=2, border_color=COLORS["black"], corner_radius=15)
        textbox.pack(fill="x", padx=20, pady=(0, 10))
        textbox.insert("1.0", game.description or "Brak opisu.")
        textbox.configure(state="disabled")

        if game.notes.strip():
            note = ctk.CTkFrame(left, fg_color=COLORS["panel2"], corner_radius=15, border_width=2, border_color=COLORS["black"])
            note.pack(fill="x", padx=20, pady=(0, 18))
            ctk.CTkLabel(note, text="NOTATKA DEVELOPERA", font=ctk.CTkFont(size=10, weight="bold"), text_color=COLORS["muted"]).pack(anchor="w", padx=15, pady=(12, 5))
            ctk.CTkLabel(note, text=game.notes, text_color=COLORS["text"], wraplength=760, justify="left").pack(anchor="w", padx=15, pady=(0, 12))

        ctk.CTkLabel(right, text="Działania", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=18, pady=(18, 12))
        installed = self.manager.is_installed(game)
        ctk.CTkButton(right, text="▶  Uruchom" if installed else "↓  Pobierz grę", height=46, corner_radius=12,
                      fg_color=COLORS["text"] if not installed else COLORS["green"],
                      hover_color=COLORS["white"] if not installed else "#A0ECA0",
                      text_color=COLORS["black"], command=lambda: self.install_or_launch(game, return_to_details=True)).pack(fill="x", padx=18, pady=5)
        if installed:
            ctk.CTkButton(right, text="Odinstaluj", height=38, fg_color="transparent", border_width=1, border_color=COLORS["border_soft"], hover_color=COLORS["panel2"], command=lambda: self._detail_uninstall(game)).pack(fill="x", padx=18, pady=5)
        if game.homepage_url:
            ctk.CTkButton(right, text="↗  Strona projektu", height=38, fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"], command=lambda: webbrowser.open(game.homepage_url)).pack(fill="x", padx=18, pady=5)
        ctk.CTkFrame(right, height=2, fg_color=COLORS["black"]).pack(fill="x", padx=18, pady=14)
        ctk.CTkLabel(right, text=f"Rozmiar\n{game.size_mb:g} MB", text_color=COLORS["muted"], anchor="w", justify="left").pack(fill="x", padx=18, pady=4)
        ctk.CTkLabel(right, text=f"Wydano\n{self._format_date(game.release_date)}", text_color=COLORS["muted"], anchor="w", justify="left").pack(fill="x", padx=18, pady=4)
        ctk.CTkLabel(right, text=f"Aktualizacja\n{self._format_date(game.updated_at)}", text_color=COLORS["muted"], anchor="w", justify="left").pack(fill="x", padx=18, pady=4)
        source = "Gofile" if "gofile.io" in game.download_url.lower() else "Direct download"
        ctk.CTkLabel(right, text=f"Źródło\n{source}", text_color=COLORS["muted"], anchor="w", justify="left").pack(fill="x", padx=18, pady=4)

    def _animate_frame_in(self, frame):
        try:
            frame.place_forget()
        except Exception:
            pass
        # Lightweight vertical slide inside parent.
        frame.pack_forget()
        frame.place(relx=0, rely=0.025, relwidth=1, relheight=0.975)
        def step(n=0):
            if not frame.winfo_exists():
                return
            y = max(0.0, 0.025 - (0.025 * min(n, 7) / 7))
            frame.place_configure(rely=y, relheight=1-y)
            if n < 7:
                self.after(22, lambda: step(n + 1))
            else:
                frame.place_forget()
                frame.pack(fill="both", expand=True, padx=24, pady=18)
        step()

    def _detail_uninstall(self, game):
        # uninstall_game() sam zajmuje się potwierdzeniem, czyszczeniem
        # instalacji i przejściem do Biblioteki. Nie otwieramy ponownie
        # szczegółów usuniętej gry.
        self.uninstall_game(game)

    @staticmethod
    def _format_date(value: str) -> str:
        try:
            return value.replace("T", " ").split(".")[0].replace("+00:00", "")
        except Exception:
            return value or "—"

    # ---------------- Settings ----------------
    def build_settings(self):
        self._topbar(self.t("settings"), "MizuLauncher")
        parent=ctk.CTkScrollableFrame(self.content,fg_color="transparent")
        parent.pack(fill="both",expand=True,padx=24,pady=(0,20))
        card=ctk.CTkFrame(parent,fg_color=COLORS["panel"],corner_radius=22,border_width=2,border_color=COLORS["black"])
        card.pack(fill="x",pady=8)
        ctk.CTkLabel(card,text="Launcher",font=ctk.CTkFont(size=22,weight="bold")).pack(anchor="w",padx=22,pady=(20,5))
        ctk.CTkLabel(card,text="Folder instalacji gier",text_color=COLORS["muted"]).pack(anchor="w",padx=22,pady=(6,4))
        row=ctk.CTkFrame(card,fg_color="transparent"); row.pack(fill="x",padx=22,pady=(0,18))
        e=ctk.CTkEntry(row,height=44,fg_color=COLORS["panel2"],border_width=2,border_color=COLORS["black"]); e.pack(side="left",fill="x",expand=True); e.insert(0,self.config["download_directory"]); self.settings_entries={"download_directory":e}
        ctk.CTkButton(row,text="⚙",width=48,height=44,fg_color=COLORS["panel2"],hover_color=COLORS["card_hover"],command=lambda: self._choose_folder_for_settings(e)).pack(side="left",padx=(8,0)); ctk.CTkButton(row,text=self.t("save"),width=78,height=44,fg_color=COLORS["text"],text_color=COLORS["black"],hover_color=COLORS["white"],command=self.save_settings).pack(side="left",padx=(8,0))

        section=ctk.CTkFrame(parent,fg_color=COLORS["panel"],corner_radius=22,border_width=2,border_color=COLORS["black"]); section.pack(fill="x",pady=8)
        ctk.CTkLabel(section,text=self.t("appearance"),font=ctk.CTkFont(size=22,weight="bold")).pack(anchor="w",padx=22,pady=(20,4))
        ctk.CTkLabel(section,text="Motyw zapisuje się lokalnie na tym komputerze.",text_color=COLORS["muted"]).pack(anchor="w",padx=22,pady=(0,14))
        theme_row=ctk.CTkFrame(section,fg_color="transparent"); theme_row.pack(fill="x",padx=22,pady=(0,14))
        ctk.CTkLabel(theme_row,text=self.t("theme"),font=ctk.CTkFont(size=14,weight="bold")).pack(side="left")
        theme_var=ctk.StringVar(value="dark" if self.config.get("theme","dark")=="dark" else "light")
        ctk.CTkLabel(theme_row,text=self.t("dark"),text_color=COLORS["subtle"]).pack(side="right",padx=(0,12))
        switch=ctk.CTkSwitch(theme_row,text="",variable=theme_var,onvalue="dark",offvalue="light",width=52,height=28,button_color=COLORS["black"],button_hover_color=COLORS["text"],progress_color=COLORS["panel3"])
        switch.pack(side="right")
        def change_theme():
            mode=theme_var.get(); self.config["theme"]=mode; save_config(self.config); set_palette(mode); ctk.set_appearance_mode("dark" if mode=="dark" else "light"); self._rebuild_ui()
        switch.configure(command=change_theme)
        lang_row=ctk.CTkFrame(section,fg_color="transparent"); lang_row.pack(fill="x",padx=22,pady=(0,20))
        ctk.CTkLabel(lang_row,text=self.t("language"),font=ctk.CTkFont(size=14,weight="bold")).pack(side="left")
        lang_map={"Polski":"pl","English":"en","Español":"es"}
        reverse={v:k for k,v in lang_map.items()}; lang_var=ctk.StringVar(value=reverse[self.config.get("language","pl")])
        lang_combo=ctk.CTkComboBox(lang_row,values=list(lang_map.keys()),variable=lang_var,width=180,height=40)
        lang_combo.pack(side="right")
        def change_lang(value):
            self.config["language"]=lang_map[value]; save_config(self.config); self._rebuild_ui()
        lang_combo.configure(command=change_lang)

        account=ctk.CTkFrame(parent,fg_color=COLORS["panel"],corner_radius=22,border_width=2,border_color=COLORS["black"]); account.pack(fill="x",pady=8)
        ctk.CTkLabel(account,text=self.t("account"),font=ctk.CTkFont(size=22,weight="bold")).pack(anchor="w",padx=22,pady=(20,5))
        ctk.CTkLabel(account,text=self.api.user_email if self.api.authenticated else self.t("guest"),text_color=COLORS["muted"]).pack(anchor="w",padx=22)
        ctk.CTkButton(account,text="Otwórz Account Manager",height=42,fg_color=COLORS["panel2"],hover_color=COLORS["card_hover"],command=self.open_account_manager).pack(anchor="w",padx=22,pady=18)

    def _choose_folder_for_settings(self, entry):
        path=filedialog.askdirectory(title="Wybierz folder instalacji gier")
        if path:
            entry.delete(0,"end"); entry.insert(0,path)

    def save_settings(self):
        self.config["download_directory"] = self.settings_entries["download_directory"].get().strip() or self.config["download_directory"]
        save_config(self.config)
        self.manager = GameManager(self.config["download_directory"], self.config.get("game_install_overrides", {}))
        info(self, "Zapisano", "Ustawienia zostały zapisane.")

    # ---------------- Account Manager ----------------
    def open_account_manager(self):
        win = ctk.CTkToplevel(self)
        win.title("MizuLauncher • Account Manager")
        win.geometry("1040x720")
        win.minsize(840, 620)
        win.transient(self)

        sidebar = ctk.CTkFrame(win, width=240, fg_color=COLORS["panel"], corner_radius=0, border_width=1, border_color=COLORS["black"])
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ctk.CTkLabel(sidebar, text="ACCOUNT", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=22, pady=(30, 3))
        ctk.CTkLabel(sidebar, text="MizuLauncher", text_color=COLORS["muted"]).pack(anchor="w", padx=22, pady=(0, 24))

        tabs = {}
        body = ctk.CTkFrame(win, fg_color=COLORS["bg"], corner_radius=0)
        body.pack(side="right", fill="both", expand=True)

        tabs_data = [("account", "Konto")]
        if self.api.developer_authenticated:
            tabs_data.append(("developer", "Developer"))
        for key, label in tabs_data:
            b = ctk.CTkButton(sidebar, text=label, height=44, anchor="w", fg_color="transparent", hover_color=COLORS["card_hover"], text_color=COLORS["muted"], command=lambda k=key: draw_tab(k))
            b.pack(fill="x", padx=14, pady=4)
            tabs[key] = b

        def draw_tab(key):
            for child in body.winfo_children(): child.destroy()
            for k, b in tabs.items():
                b.configure(fg_color=COLORS["panel2"] if k == key else "transparent", text_color=COLORS["text"] if k == key else COLORS["muted"])
            if key == "account":
                self._account_tab(body, win)
            else:
                self._developer_settings_tab(body, win)

        draw_tab("account")

    def _account_tab(self, parent, win):
        ctk.CTkLabel(parent, text="Twoje konto", font=ctk.CTkFont(size=30, weight="bold")).pack(anchor="w", padx=28, pady=(28, 3))
        ctk.CTkLabel(parent, text="Logowanie, profil i dostęp do strefy developera.", text_color=COLORS["muted"]).pack(anchor="w", padx=28)
        card = ctk.CTkFrame(parent, fg_color=COLORS["panel"], corner_radius=22, border_width=2, border_color=COLORS["black"])
        card.pack(fill="x", padx=28, pady=24)
        if self.api.authenticated:
            ctk.CTkLabel(card, text="●", font=ctk.CTkFont(size=28), text_color=COLORS["green"]).pack(anchor="w", padx=22, pady=(22, 6))
            ctk.CTkLabel(card, text=self.api.user_email or "Konto", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=22)
            role = "Developer" if self.api.developer_authenticated else "Player"
            ctk.CTkLabel(card, text=role, text_color=COLORS["muted"]).pack(anchor="w", padx=22, pady=(4, 18))
            ctk.CTkButton(card, text="Wyloguj", height=42, fg_color=COLORS["red_soft"], hover_color=COLORS["red"], command=lambda: self._logout_and_close(win)).pack(anchor="w", padx=22, pady=(0, 22))
        else:
            ctk.CTkLabel(card, text="○", font=ctk.CTkFont(size=28), text_color=COLORS["muted"]).pack(anchor="w", padx=22, pady=(22, 6))
            ctk.CTkLabel(card, text="Tryb gościa", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=22)
            ctk.CTkLabel(card, text="Zaloguj się, aby mieć własne konto.", text_color=COLORS["muted"]).pack(anchor="w", padx=22, pady=(4, 15))
            ctk.CTkButton(card, text="Zaloguj / zarejestruj", height=42, fg_color=COLORS["text"], text_color=COLORS["black"], hover_color=COLORS["white"], command=lambda: (win.destroy(), self.show_auth_gate())).pack(anchor="w", padx=22, pady=(0, 22))

    def _developer_settings_tab(self, parent, win):
        ctk.CTkLabel(parent, text="Developer Settings", font=ctk.CTkFont(size=30, weight="bold")).pack(anchor="w", padx=28, pady=(28, 3))
        ctk.CTkLabel(parent, text="Backend i publikowanie katalogu są dostępne tylko dla konta developera.", text_color=COLORS["muted"]).pack(anchor="w", padx=28, pady=(0, 20))
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=0)
        self.developer_entries = {}
        for key, label in [("supabase_url", "Supabase Project URL"), ("supabase_publishable_key", "Supabase Publishable Key"), ("catalog_id", "Catalog ID")]:
            ctk.CTkLabel(scroll, text=label, text_color=COLORS["muted"]).pack(anchor="w", padx=10, pady=(8, 4))
            e = ctk.CTkEntry(scroll, height=44, fg_color=COLORS["panel2"], border_width=2, border_color=COLORS["black"])
            e.pack(fill="x", padx=10)
            e.insert(0, str(self.config.get(key, "")))
            self.developer_entries[key] = e
        ctk.CTkButton(scroll, text="Zapisz backend", height=44, fg_color=COLORS["text"], text_color=COLORS["black"], hover_color=COLORS["white"], command=self.save_developer_settings).pack(fill="x", padx=10, pady=(20, 8))
        ctk.CTkButton(scroll, text="Otwórz Developer Center", height=40, fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"], command=lambda: (win.destroy(), self.show_view("developer"))).pack(fill="x", padx=10, pady=5)

    def save_developer_settings(self):
        try:
            self.config["supabase_url"] = self.developer_entries["supabase_url"].get().strip()
            self.config["supabase_publishable_key"] = self.developer_entries["supabase_publishable_key"].get().strip()
            self.config["catalog_id"] = int(self.developer_entries["catalog_id"].get().strip() or 1)
            save_config(self.config)
            old_session = self.api.save_session_state()
            self.api = self._make_api()
            if old_session.get("refresh_token"):
                self.api.restore_session(old_session.get("access_token", ""), old_session.get("refresh_token", ""))
                self._persist_session()
            self._refresh_account_card()
            info(self, "Zapisano", "Konfiguracja backendu została zapisana.")
        except Exception as exc:
            error(self, "Błąd", str(exc))

    def _logout_and_close(self, win):
        self.api.sign_out()
        clear_session()
        self.guest_mode = True
        self.config["guest_mode"] = True
        save_config(self.config)
        self._set_developer_visibility(False)
        self._refresh_account_card()
        win.destroy()
        self.show_auth_gate()

    # ---------------- Developer ----------------
    def build_developer(self):
        if not self.api.developer_authenticated:
            self.show_view("home")
            return
        self._topbar("Developer Center", "Publikuj i zarządzaj katalogiem MizuLauncher")
        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=22, pady=(0, 20))

        hero = ctk.CTkFrame(scroll, fg_color=COLORS["panel"], corner_radius=22, border_width=2, border_color=COLORS["black"])
        hero.pack(fill="x", pady=5)
        ctk.CTkLabel(hero, text="DEVELOPER", text_color=COLORS["muted"], font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(hero, text=self.api.user_email or "Developer", font=ctk.CTkFont(size=20, weight="bold")).pack(anchor="w", padx=20)
        ctk.CTkButton(hero, text="Publikuj katalog", height=42, width=155, fg_color=COLORS["text"], text_color=COLORS["black"], hover_color=COLORS["white"], command=self.publish_catalog).pack(side="right", padx=20, pady=18)
        ctk.CTkButton(hero, text="Account Manager", height=42, width=150, fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"], command=self.open_account_manager).pack(side="right", padx=(0, 8), pady=18)

        actions = ctk.CTkFrame(scroll, fg_color="transparent")
        actions.pack(fill="x", pady=10)
        for text, command in (("＋ Dodaj grę", self.add_game), ("✎ Edytuj wybraną", self.edit_selected_game)):
            ctk.CTkButton(actions, text=text, height=42, fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"], command=command).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(scroll, text="Katalog gier", font=ctk.CTkFont(size=19, weight="bold")).pack(anchor="w", pady=(8, 8))
        for game in self.games:
            self._developer_row(scroll, game)

    def _developer_row(self, parent, game: Game):
        row = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=15, height=78, border_width=2, border_color=COLORS["black"])
        row.pack(fill="x", pady=4)
        row.pack_propagate(False)
        icon = ctk.CTkLabel(row, text="", width=54, height=54, fg_color=COLORS["panel2"], corner_radius=12)
        icon.pack(side="left", padx=10, pady=10)
        self.image_loader.request(game.icon_url, game.name, (54, 54), "icon", lambda img, w=icon: w.configure(image=img, text=""))
        meta = ctk.CTkFrame(row, fg_color="transparent")
        meta.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(meta, text=game.name, font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(anchor="w", pady=(12, 0))
        ctk.CTkLabel(meta, text=f"v{game.version} • {game.category} • {'ON' if game.enabled else 'OFF'}", text_color=COLORS["muted"], anchor="w").pack(anchor="w")
        ctk.CTkButton(row, text="Usuń", width=72, height=32, fg_color=COLORS["red_soft"], hover_color=COLORS["red"], command=lambda g=game: self.delete_game(g)).pack(side="right", padx=5)
        ctk.CTkButton(row, text="Edytuj", width=72, height=32, fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"], command=lambda g=game: self.edit_game(g)).pack(side="right", padx=5)
        ctk.CTkButton(row, text="Podgląd", width=78, height=32, fg_color="transparent", border_width=1, border_color=COLORS["border_soft"], command=lambda g=game: self.open_game_details(g)).pack(side="right", padx=5)

    # ---------------- Developer actions ----------------
    def add_game(self):
        dlg = GameEditor(self)
        self.wait_window(dlg)
        if dlg.result:
            self.games.append(dlg.result)
            self._save_local_games()
            self.show_view("developer")

    def edit_selected_game(self):
        if self.selected_game:
            self.edit_game(self.selected_game)
        else:
            info(self, "Brak wyboru", "Najpierw otwórz grę albo użyj przycisku Edytuj przy grze.")

    def edit_game(self, game: Game):
        dlg = GameEditor(self, game)
        self.wait_window(dlg)
        if dlg.result:
            for i, existing in enumerate(self.games):
                if existing.id == game.id:
                    self.games[i] = dlg.result
                    break
            self._save_local_games()
            if getattr(dlg, "release_update", False):
                self._release_game_update(dlg.result)
            else:
                info(self, "Zapisano", f"Zmiany dla '{dlg.result.name}' zapisano lokalnie. Kliknij 'Publikuj katalog + UI', aby udostępnić je użytkownikom, lub użyj 'Zapisz i wypuść aktualizację' przy zmianie wersji/linku.")
                self.show_view("developer")

    def _release_game_update(self, game: Game):
        if not self.api.configured or not self.api.developer_authenticated:
            error(self, "Brak uprawnień", "Wypuszczenie aktualizacji wymaga zalogowanego developera i skonfigurowanego Supabase.")
            return
        original = next((g for g in self.games if g.id == game.id), None)
        if not game.version.strip() or not game.download_url.strip():
            error(self, "Brak danych aktualizacji", "Aktualizacja musi mieć wersję i link do nowego ZIP-a.")
            return
        if original and not is_version_newer(game.version, original.version):
            error(self, "Nieprawidłowa wersja", f"Wypuszczana wersja {game.version} musi być większa od poprzedniej wersji {original.version}.")
            return
        catalog = Catalog(games=[g.to_dict() for g in self.games], updated_at=utc_now()).to_dict()
        try:
            self.api.publish_catalog(catalog)
            self.refresh_games()
            info(self, "Aktualizacja wypuszczona", f"Wersja {game.version} gry '{game.name}' została opublikowana. Użytkownicy z wcześniejszą wersją zobaczą przycisk 'Aktualizuj'.")
        except Exception as exc:
            error(self, "Publikacja aktualizacji nieudana", str(exc))

    def delete_game(self, game: Game):
        if not confirm(self, "Usuń grę", f"Usunąć '{game.name}' z katalogu? Zmiana będzie publiczna dopiero po publikacji."):
            return
        self.games = [g for g in self.games if g.id != game.id]
        self._save_local_games()
        self.show_view("developer")

    def _save_local_games(self):
        save_cache([g.to_dict() for g in self.games])

    def publish_catalog(self):
        if not self.api.configured:
            error(self, "Brak Supabase", "Skonfiguruj backend w Account Manager → Developer Settings.")
            return
        if not self.api.developer_authenticated:
            error(self, "Brak uprawnień", "Zalogowane konto nie jest administratorem MizuLaunchera.")
            return
        catalog = Catalog(games=[g.to_dict() for g in self.games], updated_at=utc_now()).to_dict()
        try:
            self.api.publish_catalog(catalog)
            info(self, "Opublikowano", "Katalog został zapisany w Supabase.")
            self.refresh_games()
        except Exception as exc:
            error(self, "Publikacja nieudana", str(exc))

    # ---------------- Sync ----------------
    def refresh_games(self, initial=False):
        if not self.api.configured:
            self.status_dot.configure(text_color=COLORS["orange"])
            self.status_label.configure(text="Brak backendu\nLokalny cache")
            if initial:
                self.show_view("home")
            return
        self.status_dot.configure(text_color=COLORS["orange"])
        self.status_label.configure(text="Synchronizacja…")
        def worker():
            try:
                payload = self.api.fetch_catalog()
                catalog = Catalog.from_dict(payload)
                games = catalog.normalized_games()
                self.after(0, lambda: self._apply_remote_games(games, catalog.updated_at))
            except Exception as exc:
                self.after(0, lambda e=exc: self._remote_failed(e))
        threading.Thread(target=worker, daemon=True).start()

    def _apply_remote_games(self, games: list[Game], updated_at: str):
        self.games = games
        self._save_local_games()
        self.status_dot.configure(text_color=COLORS["green"])
        self.status_label.configure(text="Online • katalog aktualny")
        if self.current_view in {"home", "library", "developer"}:
            self.show_view(self.current_view)
        else:
            self.show_view("home")

    def _remote_failed(self, exc):
        self.status_dot.configure(text_color=COLORS["orange"])
        self.status_label.configure(text="Offline • lokalny cache")
        if self.current_view in {"home", "library", "developer"}:
            self.show_view(self.current_view)

    # ---------------- Game location ----------------
    def open_game_location_settings(self, game: Game):
        win = ctk.CTkToplevel(self)
        win.title(f"⚙  {game.name} • Lokalizacja")
        win.geometry("720x520")
        win.minsize(640, 460)
        win.transient(self)
        win.grab_set()

        current = str(self.manager.game_root(game))
        ctk.CTkLabel(win, text="Lokalizacja gry", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=24, pady=(24,4))
        ctk.CTkLabel(win, text="Możesz wskazać folder gry ręcznie. Jeżeli nie ustawisz pliku EXE w edycji gry, launcher sam przeszuka ten folder.", text_color=COLORS["muted"], wraplength=640, justify="left").pack(anchor="w", padx=24, pady=(0,18))

        path_row = ctk.CTkFrame(win, fg_color=COLORS["panel"], corner_radius=16, border_width=2, border_color=COLORS["black"])
        path_row.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(path_row, text="Folder gry", text_color=COLORS["muted"]).pack(anchor="w", padx=16, pady=(12,4))
        path_entry = ctk.CTkEntry(path_row, height=42)
        path_entry.pack(side="left", fill="x", expand=True, padx=(16,8), pady=(0,14))
        path_entry.insert(0, current)
        ctk.CTkButton(path_row, text="⚙", width=48, height=42, fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"], command=lambda: self._choose_game_folder(path_entry)).pack(side="left", padx=(0,16), pady=(0,14))

        exe_row = ctk.CTkFrame(win, fg_color=COLORS["panel"], corner_radius=16, border_width=2, border_color=COLORS["black"])
        exe_row.pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(exe_row, text="Plik wykonywalny", text_color=COLORS["muted"]).pack(anchor="w", padx=16, pady=(12,4))
        exe_var = ctk.StringVar(value=game.executable or "Automatyczne wyszukiwanie EXE")
        ctk.CTkLabel(exe_row, textvariable=exe_var, anchor="w").pack(side="left", fill="x", expand=True, padx=16, pady=(0,14))
        def scan():
            try:
                root=Path(path_entry.get().strip())
                found=self.manager._find_executable(root) if hasattr(self.manager,'_find_executable') else None
            except Exception:
                found=None
            if found:
                rel=found.relative_to(Path(path_entry.get().strip())).as_posix()
                exe_var.set(rel)
                info(win,"Znaleziono EXE",f"Launcher znalazł:\n{rel}")
            else:
                info(win,"Nie znaleziono EXE","Nie znaleziono pliku .exe w wybranym folderze. Launcher spróbuje ponownie przy uruchamianiu.")
        ctk.CTkButton(exe_row, text="Skanuj", width=90, height=38, fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"], command=scan).pack(side="right", padx=16, pady=(0,14))

        actions=ctk.CTkFrame(win, fg_color="transparent"); actions.pack(fill="x", padx=24, pady=18)
        def save():
            folder=path_entry.get().strip()
            if not folder:
                error(win,"Brak folderu","Wybierz folder gry."); return
            self.manager.set_install_location(game, folder)
            self.config.setdefault("game_install_overrides", {})[game.id]=str(self.manager.game_root(game))
            save_config(self.config)
            win.destroy()
            self.show_view("details" if self.selected_game and self.selected_game.id==game.id else self.current_view)
        ctk.CTkButton(actions,text="Zapisz lokalizację",height=44,fg_color=COLORS["text"],text_color=COLORS["black"],hover_color=COLORS["white"],command=save).pack(side="left",fill="x",expand=True,padx=(0,6))
        ctk.CTkButton(actions,text="Otwórz folder",height=44,fg_color=COLORS["panel2"],hover_color=COLORS["card_hover"],command=lambda: webbrowser.open(Path(path_entry.get().strip()).as_uri()) if Path(path_entry.get().strip()).exists() else info(win,"Folder nie istnieje","Najpierw wybierz lub utwórz folder.")).pack(side="left",fill="x",expand=True,padx=6)
        ctk.CTkButton(actions,text="Anuluj",height=44,fg_color=COLORS["panel2"],command=win.destroy).pack(side="left",fill="x",expand=True,padx=(6,0))

    def _choose_game_folder(self, entry):
        path=filedialog.askdirectory(title="Wybierz folder gry")
        if path:
            entry.delete(0,"end"); entry.insert(0,path)

    # ---------------- Install / uninstall ----------------
    def install_or_launch(self, game: Game, return_to_details=False):
        if not self._update_allows_action(game):
            return

        # Recheck immediately before a game action. If the server reports a newer
        # launcher version, this action is never started.
        self._show_update_overlay("Sprawdzanie aktualizacji przed uruchomieniem…")
        project_url = (SUPABASE_URL or "").strip()
        publishable_key = (SUPABASE_PUBLISHABLE_KEY or "").strip()
        update_id = int(self.config.get("update_id", UPDATE_ID))

        def worker():
            try:
                result = fetch_update_info_from_supabase(
                    project_url,
                    publishable_key,
                    self._app_version,
                    update_id=update_id,
                )
                if not result.checked:
                    manifest_url = (self.config.get("update_manifest_url") or UPDATE_MANIFEST_URL or "").strip()
                    result = fetch_update_info(manifest_url, self._app_version) if manifest_url else result
            except Exception as exc:
                result = UpdateInfo(checked=True, error=f"Błąd sprawdzania aktualizacji: {exc}")
            self.after(0, lambda r=result: self._finish_action_update_check(r, game, return_to_details))
        threading.Thread(target=worker, name="MizuActionUpdateCheck", daemon=True).start()

    def _finish_action_update_check(self, result: UpdateInfo, game: Game, return_to_details=False):
        self._hide_update_overlay()
        self._update_info = result
        self._update_required = bool(result.available)
        if result.error:
            print(f"[MizuLauncher] Update check before game action: {result.error}")
        if result.available:
            self._handle_required_update(result)
            return
        self._perform_install_or_launch(game, return_to_details)

    def _perform_install_or_launch(self, game: Game, return_to_details=False):
        if self.manager.is_installed(game):
            try:
                self.manager.launch(game)
            except Exception as exc:
                error(self, "Nie można uruchomić", str(exc))
            return
        self._download_game(game, return_to_details)

    def _download_game(self, game: Game, return_to_details=False):
        popup = ctk.CTkToplevel(self)
        popup.title(f"Pobieranie — {game.name}")
        popup.geometry("520x250")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()
        ctk.CTkLabel(popup, text=game.name, font=ctk.CTkFont(size=19, weight="bold")).pack(pady=(25, 7))
        ctk.CTkLabel(popup, text="Pobieranie i instalacja gry…", text_color=COLORS["muted"]).pack()
        progress = ctk.CTkProgressBar(popup, width=430)
        progress.pack(pady=24)
        progress.set(0)
        status = ctk.CTkLabel(popup, text="Łączenie…", text_color=COLORS["muted"])
        status.pack()
        def worker():
            try:
                def update(p):
                    self.after(0, lambda value=p: (progress.set(value / 100), status.configure(text=f"Pobieranie: {value}%")))
                root = self.manager.install(game, progress=update)
                self.after(0, popup.destroy)
                self.after(0, lambda: info(self, "Gotowe", f"{game.name} została zainstalowana.\n\n{root}"))
                self.after(0, lambda: self.open_game_details(game) if return_to_details else self.show_view(self.current_view))
            except Exception as exc:
                self.after(0, popup.destroy)
                self.after(0, lambda e=exc: error(self, "Pobieranie nieudane", str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def uninstall_game(self, game: Game):
        if not confirm(self, "Odinstaluj", f"Usunąć pliki gry '{game.name}'? Zawartość folderu instalacji zostanie usunięta."):
            return
        try:
            self.manager.uninstall(game)
        except Exception as exc:
            error(self, "Nie można odinstalować", str(exc))
            return
        self.show_view("library")

# -----------------------------------------------------------------------------
# Visual GUI editor + layout runtime integration
# -----------------------------------------------------------------------------
from ..layout_engine import load_layout, save_layout, DEFAULT_LAYOUT
from .gui_editor import GuiEditor
from .layout_runtime import render_element
import os as _os
import webbrowser as _webbrowser

_OLD_BUILD_SHELL = MizuLauncher._build_shell
_OLD_REBUILD_UI = MizuLauncher._rebuild_ui
_OLD_INIT = MizuLauncher.__init__
_OLD_REFRESH_GAMES = MizuLauncher.refresh_games


def _new_init(self, *args, **kwargs):
    self.layout = load_layout()
    _OLD_INIT(self, *args, **kwargs)
    self._install_custom_nav_pages()


def _install_custom_nav_pages(self):
    self.custom_nav_buttons = getattr(self, 'custom_nav_buttons', {})
    for btn in list(self.custom_nav_buttons.values()):
        try: btn.destroy()
        except Exception: pass
    self.custom_nav_buttons = {}
    pages = self.layout.get('pages', {})
    fixed = {'home', 'library', 'settings', 'developer', 'details'}
    # Insert custom pages above the settings entry so the expanding spacer remains below navigation.
    before = self.nav_buttons.get('settings')
    for key, page in pages.items():
        if key in fixed: continue
        if not isinstance(page, dict): continue
        label = page.get('label') or key.replace('_',' ').title()
        btn = ctk.CTkButton(self.sidebar, text=f'▸   {label}', anchor='w', height=46, corner_radius=11,
                            fg_color='transparent', hover_color=COLORS['card_hover'], text_color=COLORS['muted'],
                            font=ctk.CTkFont(size=13, weight='bold'), command=lambda k=key: self.show_view(k))
        if before and before.winfo_exists():
            btn.pack(fill='x', padx=14, pady=3, before=before)
        else:
            btn.pack(fill='x', padx=14, pady=3)
        self.custom_nav_buttons[key] = btn

def _animate_pack_in(self, widget, base_padx, steps=7, step=0, generation=None):
    """Animate only the packed horizontal padding. Safe for Tkinter/CustomTkinter."""
    try:
        if not widget.winfo_exists():
            return
        if generation is not None and generation != getattr(self, "_ui_generation", generation):
            return
        t = min(1.0, step / float(max(1, steps)))
        eased = t * t * (3.0 - 2.0 * t)
        current = int(round(base_padx + (18 * (1.0 - eased))))
        widget.pack_configure(padx=current)
        if step < steps:
            self.after(16, lambda: _animate_pack_in(self, widget, base_padx, steps, step + 1, generation))
        else:
            widget.pack_configure(padx=base_padx)
    except (tkinter.TclError, RuntimeError, AttributeError):
        return


def _ease_widget(self, widget, start_y, target_y, steps=8, step=0):
    """Backward-compatible no-op wrapper kept for old callbacks."""
    try:
        if widget.winfo_exists():
            _animate_pack_in(self, widget, int(widget.pack_info().get("padx", 0) or 0), steps=max(1, steps), step=min(step, steps))
    except Exception:
        return


def _rebuild_ui_layout(self):
    # Cancel pending animation callbacks by generation token.
    self._ui_generation = getattr(self, "_ui_generation", 0) + 1
    _OLD_REBUILD_UI(self)
    self._install_custom_nav_pages()
    target = self.current_view if self.current_view in ({"home", "library", "settings", "developer"} | set(self.layout.get("pages", {}))) else "home"
    self.show_view(target)


def _render_layout_page(self, page_name: str):
    page = self.layout.get('pages', {}).get(page_name) or self.layout.get('pages', {}).get('home', {})

    # Use a real vertical scroll container for every layout page. The previous
    # implementation used a plain Frame, so elements placed below the viewport
    # were simply clipped and the Home page could not actually scroll.
    scroll = ctk.CTkScrollableFrame(
        self.content,
        fg_color='transparent',
        orientation='vertical',
        corner_radius=0,
    )
    scroll.pack(fill='both', expand=True, padx=14, pady=(8, 14))

    elements = page.get('elements', []) or []
    # Work out the required virtual canvas height from percentage positions.
    max_bottom = 100.0
    for el in elements:
        try:
            max_bottom = max(max_bottom, float(el.get('y', 0)) + float(el.get('h', 0)))
        except Exception:
            pass
    # A percentage-based layout needs a taller virtual surface to make scrolling
    # possible. 100% is the viewport; values above 100% extend it.
    virtual_height = max(900, int(max_bottom * 9))
    canvas = ctk.CTkFrame(scroll, fg_color=COLORS['bg'], corner_radius=0, height=virtual_height)
    canvas.pack(fill='x', expand=True)
    canvas.pack_propagate(False)

    for el in elements:
        try:
            render_element(self, canvas, el, page_name)
        except Exception:
            # Keep one broken custom widget from breaking the whole page.
            pass
    self._animate_content_in()


def _build_home_layout(self):
    self._render_layout_page('home')


def _build_library_layout(self):
    self._render_layout_page('library')


def _open_game_details_layout(self, game: Game):
    self.selected_game = game
    self.current_view = 'details'
    for key, btn in self.nav_buttons.items():
        active = key == 'library'
        btn.configure(fg_color=COLORS['panel3'] if active else 'transparent', text_color=COLORS['text'] if active else COLORS['muted'])
    self._clear_content()
    top = ctk.CTkFrame(self.content, fg_color='transparent')
    top.pack(fill='x', padx=28, pady=(18, 6))
    ctk.CTkButton(top, text='‹  Biblioteka', width=130, height=38, fg_color=COLORS['panel2'], hover_color=COLORS['card_hover'], border_width=1, border_color=COLORS['black'], command=lambda: self.show_view('library')).pack(side='left')
    ctk.CTkLabel(top, text='  ' + game.name, font=ctk.CTkFont(size=16, weight='bold'), text_color=COLORS['muted']).pack(side='left')
    page = self.layout.get('pages', {}).get('details', {})
    wrapper = ctk.CTkFrame(self.content, fg_color='transparent')
    wrapper.pack(fill='both', expand=True, padx=14, pady=(0, 12))
    for el in page.get('elements', []):
        try:
            render_element(self, wrapper, el, 'details')
        except Exception:
            pass
    self._animate_content_in()


def _open_gui_editor(self):
    if not self.api.developer_authenticated:
        error(self, 'Brak uprawnień', 'GUI Editor jest dostępny tylko dla konta developera.')
        return
    win = GuiEditor(self, self.layout, self.games, on_save=self._on_layout_saved, on_publish=self._publish_layout)
    win.grab_set()


def _on_layout_saved(self, layout):
    self.layout = layout
    save_layout(self.layout)
    self._install_custom_nav_pages()
    if self.current_view in {'home', 'library', 'details'}:
        self.show_view(self.current_view)


def _publish_layout(self, layout):
    if not self.api.developer_authenticated:
        error(self, 'Brak uprawnień', 'Zaloguj się jako developer.')
        return
    catalog = {
        'schema_version': 2,
        'updated_at': utc_now(),
        'games': [g.to_dict() for g in self.games],
        'layout': layout,
    }
    try:
        self.api.publish_catalog(catalog)
        self.layout = layout
        save_layout(layout)
        info(self, 'Opublikowano', 'Gry i layout interfejsu zostały opublikowane w Supabase. Każdy launcher pobierze je przy synchronizacji.')
    except Exception as exc:
        error(self, 'Publikacja nieudana', str(exc))


def _build_developer_layout(self):
    if not self.api.developer_authenticated:
        self.show_view('home')
        return
    self._topbar('Developer Center', 'Katalog, GUI Editor i publikowanie')
    scroll = ctk.CTkScrollableFrame(self.content, fg_color='transparent')
    scroll.pack(fill='both', expand=True, padx=22, pady=(0, 20))
    hero = ctk.CTkFrame(scroll, fg_color=COLORS['panel'], corner_radius=22, border_width=2, border_color=COLORS['black'])
    hero.pack(fill='x', pady=5)
    ctk.CTkLabel(hero, text='DEVELOPER', text_color=COLORS['muted'], font=ctk.CTkFont(size=10, weight='bold')).pack(anchor='w', padx=20, pady=(18, 2))
    ctk.CTkLabel(hero, text=self.api.user_email or 'Developer', font=ctk.CTkFont(size=20, weight='bold')).pack(anchor='w', padx=20)
    ctk.CTkButton(hero, text='Publikuj katalog + UI', height=42, width=185, fg_color=COLORS['text'], text_color=COLORS['black'], hover_color=COLORS['white'], command=lambda: self._publish_layout(self.layout)).pack(side='right', padx=8, pady=18)
    ctk.CTkButton(hero, text='GUI Editor', height=42, width=130, fg_color=COLORS['panel2'], hover_color=COLORS['card_hover'], command=self._open_gui_editor).pack(side='right', padx=(0, 8), pady=18)
    ctk.CTkButton(hero, text='Account Manager', height=42, width=150, fg_color=COLORS['panel2'], hover_color=COLORS['card_hover'], command=self.open_account_manager).pack(side='right', padx=(0, 8), pady=18)

    actions = ctk.CTkFrame(scroll, fg_color='transparent')
    actions.pack(fill='x', pady=10)
    for text, command in (('＋ Dodaj grę', self.add_game), ('✎ Edytuj wybraną', self.edit_selected_game)):
        ctk.CTkButton(actions, text=text, height=42, fg_color=COLORS['panel2'], hover_color=COLORS['card_hover'], command=command).pack(side='left', padx=(0, 8))
    ctk.CTkLabel(scroll, text='Katalog gier', font=ctk.CTkFont(size=19, weight='bold')).pack(anchor='w', pady=(8, 8))
    for game in self.games:
        self._developer_row(scroll, game)


def _show_view_layout(self, view: str):
    # Never silently redirect Settings/Developer to Home.
    # Settings is a fixed application page and must be handled explicitly.
    if view == 'developer' and not self.api.developer_authenticated:
        # This state should normally be unreachable because the Developer
        # button is hidden for non-developers. If auth state changed in the
        # background, open the account manager instead of unexpectedly
        # navigating to Home.
        self.open_account_manager()
        return

    valid_fixed = {'home', 'library', 'settings', 'developer', 'details'}
    custom_pages = set(self.layout.get('pages', {}).keys())
    if view not in valid_fixed and view not in custom_pages:
        view = 'home'

    self.current_view = view
    all_nav = dict(self.nav_buttons)
    all_nav.update(getattr(self, 'custom_nav_buttons', {}))
    for key, btn in all_nav.items():
        active = key == view or (view == 'details' and key == 'library')
        try:
            btn.configure(
                fg_color=COLORS['panel3'] if active else 'transparent',
                text_color=COLORS['text'] if active else COLORS['muted'],
            )
        except Exception:
            pass

    self._clear_content()

    if view == 'home':
        _build_home_layout(self)
    elif view == 'library':
        _build_library_layout(self)
    elif view == 'settings':
        # This branch was missing in the previous build and caused the
        # fallback below to send Settings straight back to Home.
        self.build_settings()
    elif view == 'developer':
        _build_developer_layout(self)
    elif view == 'details':
        if self.selected_game:
            _open_game_details_layout(self, self.selected_game)
        else:
            self.current_view = 'library'
            _build_library_layout(self)
    elif view in custom_pages:
        self._render_layout_page(view)

    # Full-page navigation has no animation. Individual widgets may still
    # animate locally where appropriate.
    self._animate_content_in()


def _apply_remote_games_layout(self, games: list[Game], updated_at: str, layout=None):
    self.games = games
    if isinstance(layout, dict) and layout.get('pages'):
        self.layout = layout
        save_layout(self.layout)
        self._install_custom_nav_pages()
    self._save_local_games()
    self.status_dot.configure(text_color=COLORS['green'])
    self.status_label.configure(text='Online • katalog aktualny')
    if self.current_view in {'home', 'library', 'developer', 'details'}:
        self.show_view(self.current_view)
    else:
        self.show_view('home')


def _refresh_games_layout(self, initial=False):
    if not self.api.configured:
        self.status_dot.configure(text_color=COLORS['orange'])
        self.status_label.configure(text='Brak backendu\nLokalny cache')
        if initial:
            self.show_view('home')
        return
    self.status_dot.configure(text_color=COLORS['orange'])
    self.status_label.configure(text='Synchronizacja…')
    def worker():
        try:
            payload = self.api.fetch_catalog()
            catalog = Catalog.from_dict(payload)
            games = catalog.normalized_games()
            layout = payload.get('layout') if isinstance(payload, dict) else None
            self.after(0, lambda: _apply_remote_games_layout(self, games, catalog.updated_at, layout))
        except Exception as exc:
            self.after(0, lambda e=exc: self._remote_failed(e))
    threading.Thread(target=worker, daemon=True).start()


def _publish_catalog_layout(self):
    _publish_layout(self, self.layout)


def _open_game_location(self, game: Game):
    root = self.manager.game_root(game)
    if not root.exists():
        error(self, 'Brak instalacji', 'Ta gra nie jest jeszcze zainstalowana.')
        return
    try:
        if _os.name == 'nt':
            _os.startfile(str(root))
        else:
            _webbrowser.open(root.as_uri())
    except Exception as exc:
        error(self, 'Nie można otworzyć folderu', str(exc))


def _open_game_homepage(self, game: Game):
    if not game.homepage_url:
        return
    _webbrowser.open(game.homepage_url)


MizuLauncher.__init__ = _new_init
MizuLauncher._rebuild_ui = _rebuild_ui_layout
MizuLauncher.show_view = _show_view_layout
MizuLauncher.refresh_games = _refresh_games_layout
MizuLauncher._apply_remote_games = _apply_remote_games_layout
MizuLauncher.build_home = _build_home_layout
MizuLauncher.build_library = _build_library_layout
MizuLauncher.build_developer = _build_developer_layout
MizuLauncher.open_game_details = _open_game_details_layout
MizuLauncher.open_gui_editor = _open_gui_editor
MizuLauncher._open_gui_editor = _open_gui_editor
MizuLauncher._on_layout_saved = _on_layout_saved
MizuLauncher._publish_layout = _publish_layout
MizuLauncher._publish_catalog_layout = _publish_catalog_layout
MizuLauncher.open_game_location = _open_game_location
MizuLauncher.open_game_homepage = _open_game_homepage
MizuLauncher._install_custom_nav_pages = _install_custom_nav_pages
MizuLauncher._ease_widget = _ease_widget
MizuLauncher._render_layout_page = _render_layout_page

# =============================================================================
# Secure launcher integration (MizuLauncher security v1)
# =============================================================================
import os as _secure_os
import sys as _secure_sys
import webbrowser as _secure_webbrowser
from pathlib import Path as _SecurePath

from ..deployment import SUPABASE_URL as _DEP_SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY as _DEP_SUPABASE_KEY, CATALOG_ID as _DEP_CATALOG_ID, ADMIN_PANEL_URL as _DEP_ADMIN_PANEL_URL, DRM_MASTER_SECRET as _DEP_DRM_SECRET
from ..security.device import collect_device_snapshot
from ..security.drm import DrmGrant, delete_mizuapi, write_mizuapi
from ..security.integrity import IntegrityError, verify_manifest
from ..security.monitor import GameSecurityMonitor

_ORIGINAL_STARTUP = getattr(MizuLauncher, "_startup", None)
_ORIGINAL_INSTALL_OR_LAUNCH = MizuLauncher.install_or_launch
_ORIGINAL_OPEN_BACKEND_SETUP = MizuLauncher.open_backend_setup


def _secure_make_api(self):
    # Production backend is build-time configuration. User-editable local
    # values cannot redirect the launcher to another backend.
    return SupabaseClient(_DEP_SUPABASE_URL, _DEP_SUPABASE_KEY, _DEP_CATALOG_ID)


def _handle_security_shutdown(self, reason: str):
    try:
        for marker in self.manager.installs.glob("*/mizuapi.dat"):
            try:
                marker.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception:
        pass
    try:
        error(self, "MizuLauncher został zablokowany", reason)
    except Exception:
        pass
    try:
        self.destroy()
    except Exception:
        _secure_sys.exit(1)


def _send_telemetry_async(self, event: str):
    if not self.config.get("telemetry_enabled", True) or not self.api.authenticated:
        return
    snapshot = collect_device_snapshot()
    def worker():
        try:
            self.api.send_telemetry(snapshot["windows_username"], snapshot["hwid_hash"], event=event, local_ip=snapshot.get("local_ip", ""))
        except Exception:
            # Telemetry failure is non-fatal. It must never block launcher UI.
            pass
    threading.Thread(target=worker, name="MizuTelemetry", daemon=True).start()


def _secure_refresh_and_enforce(self):
    if not self.api.authenticated:
        return
    def worker():
        try:
            state = self.api.refresh_player_security()
        except Exception:
            return
        def apply():
            if not self.winfo_exists():
                return
            if state.get("kill_switch", False):
                self._security_shutdown("Administrator włączył zdalny Kill-Switch dla tego konta.")
                return
            if self.api.developer_authenticated:
                self._set_developer_visibility(True)
            else:
                self._set_developer_visibility(False)
        self.after(0, apply)
    threading.Thread(target=worker, name="MizuSecurityPoll", daemon=True).start()
    self.after(10000, self._security_poll_once)


def _security_poll_once(self):
    if not self.winfo_exists():
        return
    if self.api.authenticated:
        self._secure_refresh_and_enforce()


def _secure_startup(self):
    try:
        verify_manifest()
    except IntegrityError as exc:
        # Determine developer state from the server before allowing a local
        # modified build to continue. Source/IDE runs are not enforced.
        session = load_session()
        if self.api.configured and session.get("refresh_token"):
            try:
                self.api.restore_session(session.get("access_token", ""), session.get("refresh_token", ""))
            except Exception:
                pass
        if not self.api.developer_authenticated:
            self._security_shutdown(f"{exc}\n\nWykryto zmianę plików zabezpieczonych i konto nie ma uprawnień developera.")
            return

    if not self.guest_mode and not self.api.configured:
        self.show_auth_gate()
        return
    if not self.guest_mode and not self.api.authenticated:
        self.show_auth_gate()
        return

    if self.api.authenticated:
        try:
            self.api.refresh_player_security()
        except Exception:
            pass
        self._set_developer_visibility(self.api.developer_authenticated)
        self._send_telemetry_async("launcher_start")
        if self.api.player_control.get("kill_switch", False):
            self._security_shutdown("Twoje konto zostało zdalnie zablokowane przez administratora.")
            return
    self.refresh_games(initial=True)
    if self.api.authenticated:
        self.after(5000, self._security_poll_once)


def _secure_login_complete(self):
    self._auth_busy(False)
    self._set_developer_visibility(self.api.developer_authenticated)
    self.guest_mode = False
    self._refresh_account_card()
    self._persist_session()
    self._send_telemetry_async("login")
    self.refresh_games(initial=True)


def _secure_open_backend_setup(self):
    if not self.api.developer_authenticated:
        error(self, "Brak dostępu", "Konfiguracja backendu jest dostępna wyłącznie dla zweryfikowanego konta developera.")
        return
    return _ORIGINAL_OPEN_BACKEND_SETUP(self)


def _open_admin_panel(self):
    if not self.api.developer_authenticated:
        error(self, "Brak dostępu", "Panel administratora jest dostępny wyłącznie dla zweryfikowanego developera.")
        return
    url = _DEP_ADMIN_PANEL_URL.strip() or self.config.get("admin_panel_url", "").strip()
    if not url:
        error(self, "Brak URL panelu", "Ustaw ADMIN_PANEL_URL w mizulauncher/deployment.py przed zbudowaniem launchera.")
        return
    _secure_webbrowser.open(url)


def _secure_build_developer(self):
    _build_developer_layout(self)
    if not self.api.developer_authenticated:
        return
    # Add the external admin entry below the existing developer actions.
    button = ctk.CTkButton(
        self.content,
        text="🌐  Otwórz Panel Administratora",
        height=44,
        corner_radius=12,
        fg_color=COLORS["text"],
        text_color=COLORS["black"],
        hover_color=COLORS["white"],
        command=self._open_admin_panel,
    )
    button.pack(anchor="w", padx=22, pady=(0, 14))


def _show_install_note_and_continue(self, game: Game, continue_callback):
    """Show an optional developer note before a fresh install starts."""
    if not getattr(game, "show_install_note", False) or not game.notes.strip():
        continue_callback()
        return

    popup = ctk.CTkToplevel(self)
    popup.title(f"Informacje przed instalacją — {game.name}")
    popup.geometry("720x470")
    popup.minsize(620, 400)
    popup.resizable(True, True)
    popup.transient(self)
    popup.grab_set()

    outer = ctk.CTkFrame(popup, fg_color=COLORS["panel"], corner_radius=20, border_width=2, border_color=COLORS["black"])
    outer.pack(fill="both", expand=True, padx=18, pady=18)

    ctk.CTkLabel(outer, text="INFORMACJA OD DEWELOPERA", font=ctk.CTkFont(size=11, weight="bold"), text_color=COLORS["muted"]).pack(anchor="w", padx=22, pady=(20, 6))
    ctk.CTkLabel(outer, text=game.name, font=ctk.CTkFont(size=26, weight="bold"), text_color=COLORS["text"]).pack(anchor="w", padx=22, pady=(0, 12))

    note = ctk.CTkTextbox(outer, fg_color=COLORS["bg2"], border_width=2, border_color=COLORS["black"], corner_radius=14)
    note.pack(fill="both", expand=True, padx=22, pady=(0, 15))
    note.insert("1.0", game.notes.strip())
    note.configure(state="disabled")

    actions = ctk.CTkFrame(outer, fg_color="transparent")
    actions.pack(fill="x", padx=22, pady=(0, 20))

    def proceed():
        try:
            popup.grab_release()
        except Exception:
            pass
        popup.destroy()
        continue_callback()

    ctk.CTkButton(actions, text="Anuluj", height=42, fg_color=COLORS["panel2"], hover_color=COLORS["card_hover"], command=popup.destroy).pack(side="right", padx=(8, 0))
    ctk.CTkButton(actions, text=(getattr(game, "install_button_label", "Rozpocznij pobieranie") or "Rozpocznij pobieranie"), height=42, fg_color=COLORS["text"], hover_color=COLORS["white"], text_color=COLORS["black"], command=proceed).pack(side="right")


def _secure_install_or_launch(self, game: Game, return_to_details=False):
    if not self.api.authenticated:
        error(self, "Zaloguj się", "Pobieranie i uruchamianie gier wymaga zalogowanego konta.")
        self.open_account_manager()
        return

    try:
        state = self.api.refresh_player_security()
    except Exception as exc:
        error(self, "Brak weryfikacji", f"Nie udało się sprawdzić uprawnień konta.\n\n{exc}")
        return

    if state.get("kill_switch"):
        self._security_shutdown("Administrator włączył Kill-Switch dla tego konta.")
        return
    if not state.get("can_play", True):
        error(self, "Gra zablokowana", "Administrator zablokował możliwość grania na tym koncie.")
        return

    if self.manager.is_installed(game) and self.manager.update_available(game):
        self._download_game_secure(game, return_to_details=return_to_details, update_mode=True)
        return

    if self.manager.is_installed(game):
        def worker():
            try:
                grant = self.api.issue_drm(game.id)
                root = self.manager.game_root(game)
                write_mizuapi(root, DrmGrant(game.id, self.api.user_id, grant["token"], grant["expires_at"], grant.get("status", "authorized")), _DEP_DRM_SECRET)
                process = self.manager.launch(game)
                monitor = GameSecurityMonitor(self.api, game, process, root, on_blocked=lambda s: self.after(0, lambda: info(self, "Gra zatrzymana", "Administrator zablokował grę na tym koncie.")))
                self._active_game_monitor = monitor
                self._active_game_process = process
                monitor.start()
                self._send_telemetry_async("game_launch")
            except Exception as exc:
                self.after(0, lambda e=exc: error(self, "Nie można uruchomić", str(e)))
        threading.Thread(target=worker, name="MizuLaunch", daemon=True).start()
        return

    self._show_install_note_and_continue(
        game,
        lambda: self._download_game_secure(game, return_to_details=return_to_details, update_mode=False),
    )


def _download_game_secure(self, game: Game, return_to_details=False, update_mode=False):
    try:
        state = self.api.refresh_player_security()
    except Exception as exc:
        error(self, "Brak weryfikacji", f"Nie udało się sprawdzić uprawnień pobierania.\n\n{exc}")
        return
    if state.get("kill_switch"):
        self._security_shutdown("Administrator włączył zdalny Kill-Switch dla tego konta.")
        return
    if not state.get("can_download", True):
        error(self, "Pobieranie zablokowane", "Administrator zablokował możliwość pobierania gier dla tego konta.")
        return
    if not state.get("can_play", True):
        error(self, "Gra zablokowana", "To konto nie ma obecnie prawa uruchamiania gier.")
        return

    current_installed = self.manager.installed_version(game)
    title = f"Aktualizacja — {game.name}" if update_mode else f"Pobieranie — {game.name}"
    popup = ctk.CTkToplevel(self)
    popup.title(title)
    popup.geometry("620x390")
    popup.resizable(False, False)
    popup.transient(self)
    popup.grab_set()

    header = ctk.CTkFrame(popup, fg_color=COLORS["panel"], corner_radius=18, border_width=2, border_color=COLORS["black"])
    header.pack(fill="x", padx=18, pady=(18, 10))
    ctk.CTkLabel(header, text=game.name, font=ctk.CTkFont(size=21, weight="bold")).pack(anchor="w", padx=18, pady=(15, 2))
    ctk.CTkLabel(header, text=(f"Aktualizacja {current_installed or '?'} → {game.version}" if update_mode else f"Wersja {game.version}"), text_color=COLORS["muted"]).pack(anchor="w", padx=18, pady=(0, 14))

    progress = ctk.CTkProgressBar(popup, width=560, height=16)
    progress.pack(padx=28, pady=(15, 8))
    progress.set(0)
    pct_label = ctk.CTkLabel(popup, text="0%", font=ctk.CTkFont(size=14, weight="bold"))
    pct_label.pack()
    stats = ctk.CTkFrame(popup, fg_color="transparent")
    stats.pack(fill="x", padx=28, pady=(12, 2))
    downloaded_label = ctk.CTkLabel(stats, text="0 MB / ? MB", text_color=COLORS["muted"])
    downloaded_label.pack(side="left")
    speed_label = ctk.CTkLabel(stats, text="0 MB/s", text_color=COLORS["muted"])
    speed_label.pack(side="right")
    eta_label = ctk.CTkLabel(popup, text="Pozostało: obliczanie…", text_color=COLORS["muted"])
    eta_label.pack(pady=(5, 0))
    status_label = ctk.CTkLabel(popup, text="Łączenie z serwerem…", text_color=COLORS["muted"])
    status_label.pack(pady=(9, 14))

    def fmt_size(v):
        if v is None or v <= 0:
            return "?"
        if v >= 1024 ** 3:
            return f"{v / 1024 ** 3:.2f} GB"
        return f"{v / 1024 ** 2:.1f} MB"

    def fmt_speed(v):
        if not v:
            return "0 MB/s"
        return f"{v / 1024 ** 2:.2f} MB/s"

    def fmt_eta(sec):
        if sec is None:
            return "obliczanie…"
        sec = max(0, int(sec))
        if sec < 60:
            return f"{sec}s"
        if sec < 3600:
            return f"{sec // 60}m {sec % 60}s"
        return f"{sec // 3600}h {(sec % 3600) // 60}m"

    def worker():
        try:
            def on_info(info_data):
                def apply(d=info_data):
                    if not popup.winfo_exists():
                        return
                    pct = float(d.get("percent", 0)) / 100
                    progress.set(pct)
                    pct_label.configure(text=f"{int(d.get('percent', 0))}%")
                    downloaded_label.configure(text=f"{fmt_size(d.get('received'))} / {fmt_size(d.get('total'))}")
                    speed_label.configure(text=fmt_speed(d.get("speed_bps")))
                    eta_label.configure(text=f"Pozostało: {fmt_eta(d.get('eta_seconds'))}")
                    status_label.configure(text="Pobieranie aktualizacji…" if update_mode else "Pobieranie gry…")
                self.after(0, apply)

            def on_extract(p):
                self.after(0, lambda value=p: (progress.set(value / 100), pct_label.configure(text=f"{value}%"), status_label.configure(text="Instalowanie plików…")))

            if update_mode:
                root = self.manager.update(game, progress_info=on_info)
                phase = "Aktualizacja zakończona"
                telemetry_event = "game_update"
            else:
                root = self.manager.install(game, progress_info=on_info)
                phase = "Instalacja zakończona"
                telemetry_event = "game_download"

                # Explicit local installation registry. This is intentionally
                # independent from the selected EXE/location override so that
                # uninstalling a game removes it from Library as well.
                # A fresh install cancels any previous explicit uninstall marker.
                uninstalled_ids = self.config.get("uninstalled_game_ids", [])
                if isinstance(uninstalled_ids, list):
                    self.config["uninstalled_game_ids"] = [x for x in uninstalled_ids if x != game.id]

                installed_ids = self.config.setdefault("installed_game_ids", [])
                if not isinstance(installed_ids, list):
                    installed_ids = []
                    self.config["installed_game_ids"] = installed_ids
                if game.id not in installed_ids:
                    installed_ids.append(game.id)
                save_config(self.config)

            grant = self.api.issue_drm(game.id, purpose="update" if update_mode else "download")
            write_mizuapi(root, DrmGrant(game.id, self.api.user_id, grant["token"], grant["expires_at"], grant.get("status", "authorized")), _DEP_DRM_SECRET)
            self._send_telemetry_async(telemetry_event)
            def finish():
                if popup.winfo_exists():
                    popup.destroy()
                # The manager has already committed a verified marker/state.
                # Re-render immediately from the local state before optionally
                # starting a network catalog refresh.
                info(self, phase, f"{game.name}\nWersja: {game.version}\n\nLokalizacja:\n{root}")
                self.show_view("details" if return_to_details else self.current_view)
                try:
                    self.refresh_games(initial=False)
                except Exception:
                    pass
            self.after(0, finish)
        except Exception as exc:
            def fail(error_value):
                if popup.winfo_exists():
                    popup.destroy()
                error(self, "Aktualizacja nieudana" if update_mode else "Pobieranie nieudane", str(error_value))
            self.after(0, lambda e=exc: fail(e))

    threading.Thread(target=worker, name="MizuUpdate" if update_mode else "MizuDownload", daemon=True).start()


def _secure_uninstall_game(self, game: Game):
    # Stop the owned process first if it is the active game.
    process = getattr(self, "_active_game_process", None)
    if process is not None and process.poll() is None:
        try:
            process.terminate()
        except Exception:
            pass
    monitor = getattr(self, "_active_game_monitor", None)
    if monitor:
        monitor.stop()
    delete_mizuapi(self.manager.game_root(game))
    return MizuLauncher.__dict__["uninstall_game"].__wrapped__(self, game) if hasattr(MizuLauncher.__dict__["uninstall_game"], "__wrapped__") else None


# Bind secure methods. The original uninstall routine remains responsible for UI confirmation;
# mizuapi cleanup is handled by a tiny wrapper below.
MizuLauncher._make_api = _secure_make_api
MizuLauncher._startup = _secure_startup
MizuLauncher._login_complete = _secure_login_complete
MizuLauncher.open_backend_setup = _secure_open_backend_setup
MizuLauncher._open_admin_panel = _open_admin_panel
MizuLauncher.build_developer = _secure_build_developer
MizuLauncher._show_install_note_and_continue = _show_install_note_and_continue
MizuLauncher.install_or_launch = _secure_install_or_launch
MizuLauncher._download_game = _download_game_secure
MizuLauncher._download_game_secure = _download_game_secure
MizuLauncher._security_shutdown = _handle_security_shutdown
MizuLauncher._send_telemetry_async = _send_telemetry_async
MizuLauncher._secure_refresh_and_enforce = _secure_refresh_and_enforce
MizuLauncher._security_poll_once = _security_poll_once
MizuLauncher._secure_uninstall_game = _secure_uninstall_game

# Compatibility aliases for older layout/runtime callbacks.
try:
    if '_download_game_secure' in globals():
        MizuLauncher._download_game = _download_game_secure
        MizuLauncher._download_game_secure = _download_game_secure
except Exception:
    pass


# =============================================================================
# MizuLauncher game executable/location workflow
# =============================================================================
#
# IMPORTANT:
# The launcher deliberately does NOT guess the executable after installation.
# A game is considered downloaded when its installation marker/root exists.
# A game becomes playable only after the user explicitly selects the EXE.
#
# This block is intentionally at the end of the file because the project uses
# runtime method replacement for the GUI/layout/security integrations above.
# =============================================================================

import json as _location_json
from pathlib import Path as _LocationPath


# -----------------------------------------------------------------------------
# Local installation state helpers
# -----------------------------------------------------------------------------

def _game_installation_root(self, game: Game) -> _LocationPath:
    """Return the actual installed content root when known."""
    try:
        record = self.manager._read_install_record(game)
        if record:
            return record[0].resolve()
    except Exception:
        pass

    try:
        return self.manager.game_root(game).resolve()
    except Exception:
        return _LocationPath(str(self.config.get("download_directory", ""))) / "installed" / game.id


def _game_is_downloaded(self, game: Game) -> bool:
    """
    Distinguishes 'downloaded' from 'configured/playable'.

    install() writes .mizu_game.json, therefore this works even when no EXE
    has been selected yet.
    """
    try:
        record = self.manager._read_install_record(game)
        if record:
            root, data = record
            if root.is_dir() and data.get("game_id") in (None, "", game.id):
                return True
    except Exception:
        pass

    try:
        root = self.manager.game_root(game)
        return root.is_dir() and any(root.iterdir())
    except Exception:
        return False


def _game_executable(self, game: Game) -> _LocationPath | None:
    """Return only the EXE explicitly remembered for this game."""
    try:
        getter = getattr(self.manager, "get_saved_executable", None)
        if callable(getter):
            value = getter(game)
            if value:
                path = _LocationPath(value).resolve()
                if path.is_file() and path.suffix.lower() == ".exe":
                    return path
    except Exception:
        pass

    # Compatibility with older GameManager versions.
    try:
        state = getattr(self.manager, "state", {}).get(game.id, {})
        if isinstance(state, dict):
            raw = str(state.get("executable", "") or "").strip()
            if raw:
                path = _LocationPath(os.path.expandvars(os.path.expanduser(raw))).resolve()
                if path.is_file() and path.suffix.lower() == ".exe":
                    return path
    except Exception:
        pass

    return None


def _game_is_configured(self, game: Game) -> bool:
    return self._game_executable(game) is not None


# -----------------------------------------------------------------------------
# Explicit EXE selection
# -----------------------------------------------------------------------------

def _choose_game_executable(self, game: Game, success_callback=None):
    """
    Open Windows file picker directly in the installation directory and let the
    player select the game's EXE.
    """
    if not self._game_is_downloaded(game):
        error(self, "Brak instalacji", "Ta gra nie jest jeszcze zainstalowana.")
        return None

    root = self._game_installation_root(game)
    if not root.exists():
        error(self, "Brak folderu gry", f"Nie znaleziono folderu instalacji:\n\n{root}")
        return None

    current = self._game_executable(game)
    initial_dir = current.parent if current and current.parent.exists() else root

    selected = filedialog.askopenfilename(
        parent=self,
        title=f"Wybierz plik EXE — {game.name}",
        initialdir=str(initial_dir),
        filetypes=[
            ("Pliki wykonywalne (*.exe)", "*.exe"),
            ("Wszystkie pliki", "*.*"),
        ],
    )

    if not selected:
        return None

    selected_path = _LocationPath(selected).resolve()

    # EXE must belong to the installed game. This prevents selecting a random
    # program from Desktop/Program Files by mistake.
    try:
        selected_path.relative_to(root.resolve())
    except ValueError:
        error(
            self,
            "Nieprawidłowy plik",
            "Wybierz plik .exe znajdujący się wewnątrz folderu zainstalowanej gry.",
        )
        return None

    if selected_path.suffix.lower() != ".exe":
        error(self, "Nieprawidłowy plik", "Wybrany plik nie jest plikiem .exe.")
        return None

    try:
        setter = getattr(self.manager, "set_executable", None)
        if callable(setter):
            setter(game, selected_path)
        else:
            # Compatibility fallback for old GameManager builds.
            try:
                relative = str(selected_path.relative_to(root)).replace("\\", "/")
            except ValueError:
                relative = selected_path.name

            self.manager.state[game.id] = {
                "root": str(root),
                "version": str(
                    getattr(self.manager, "state", {}).get(game.id, {}).get(
                        "version", game.version
                    )
                ),
                "executable": str(selected_path),
            }

            if hasattr(self.manager, "_save_state"):
                self.manager._save_state()

            marker = root / ".mizu_game.json"
            marker_data = {}
            try:
                if marker.is_file():
                    marker_data = _location_json.loads(
                        marker.read_text(encoding="utf-8")
                    )
            except Exception:
                marker_data = {}

            marker_data.update({
                "game_id": game.id,
                "version": marker_data.get("version", game.version),
                "updated_at": marker_data.get("updated_at", game.updated_at),
                "executable_rel": relative,
            })

            marker.write_text(
                _location_json.dumps(
                    marker_data,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    except Exception as exc:
        error(
            self,
            "Nie udało się zapisać lokalizacji",
            str(exc),
        )
        return None

    # Keep the normal config object in sync with the GameManager.
    self.config["game_install_overrides"] = {
        str(k): str(v)
        for k, v in getattr(self.manager, "install_overrides", {}).items()
    }

    try:
        save_config(self.config)
    except Exception:
        pass

    if success_callback:
        success_callback(selected_path)

    return selected_path


def _set_game_location(self, game: Game, return_to_details=True):
    """Public action for both the first setup and changing the EXE later."""
    selected = self._choose_game_executable(game)

    if selected:
        if return_to_details:
            self.show_view("details")
        else:
            self.show_view(self.current_view)

    return selected


# -----------------------------------------------------------------------------
# Folder opening
# -----------------------------------------------------------------------------

def _open_game_location_v2(self, game: Game):
    if not self._game_is_downloaded(game):
        error(
            self,
            "Brak instalacji",
            "Ta gra nie jest jeszcze zainstalowana.",
        )
        return

    executable = self._game_executable(game)
    root = executable.parent if executable else self._game_installation_root(game)

    try:
        if _secure_os.name == "nt":
            _secure_os.startfile(str(root))
        else:
            _secure_webbrowser.open(root.as_uri())
    except Exception as exc:
        error(
            self,
            "Nie można otworzyć folderu",
            str(exc),
        )


# -----------------------------------------------------------------------------
# Secure install/play flow
# -----------------------------------------------------------------------------

def _secure_install_or_launch_v2(self, game: Game, return_to_details=False):
    if not self.api.authenticated:
        error(
            self,
            "Zaloguj się",
            "Pobieranie i uruchamianie gier wymaga zalogowanego konta.",
        )
        self.open_account_manager()
        return

    try:
        state = self.api.refresh_player_security()
    except Exception as exc:
        error(
            self,
            "Brak weryfikacji",
            f"Nie udało się sprawdzić uprawnień konta.\n\n{exc}",
        )
        return

    if state.get("kill_switch"):
        self._security_shutdown(
            "Administrator włączył Kill-Switch dla tego konta."
        )
        return

    if not state.get("can_play", True):
        error(
            self,
            "Gra zablokowana",
            "Administrator zablokował możliwość grania na tym koncie.",
        )
        return

    downloaded = self._game_is_downloaded(game)
    executable = self._game_executable(game)

    # ---------------------------------------------------------------
    # Installed but EXE has not been selected yet.
    # NEVER download the game again.
    # ---------------------------------------------------------------
    if downloaded and not executable:
        self._choose_game_executable(
            game,
            success_callback=lambda _p: self.show_view("details")
            if return_to_details
            else self.show_view(self.current_view),
        )
        return

    # ---------------------------------------------------------------
    # Fully configured installation -> update or launch.
    # ---------------------------------------------------------------
    if downloaded and executable:
        try:
            needs_update = bool(
                self.manager.update_available(game)
            )
        except Exception:
            needs_update = False

        if needs_update:
            self._download_game_secure(
                game,
                return_to_details=return_to_details,
                update_mode=True,
            )
            return

        def worker():
            try:
                grant = self.api.issue_drm(game.id)
                root = self._game_installation_root(game)

                write_mizuapi(
                    root,
                    DrmGrant(
                        game.id,
                        self.api.user_id,
                        grant["token"],
                        grant["expires_at"],
                        grant.get("status", "authorized"),
                    ),
                    _DEP_DRM_SECRET,
                )

                process = self.manager.launch(game)

                monitor = GameSecurityMonitor(
                    self.api,
                    game,
                    process,
                    root,
                    on_blocked=lambda s: self.after(
                        0,
                        lambda: info(
                            self,
                            "Gra zatrzymana",
                            "Administrator zablokował grę na tym koncie.",
                        ),
                    ),
                )

                self._active_game_monitor = monitor
                self._active_game_process = process
                monitor.start()
                self._send_telemetry_async("game_launch")

            except Exception as exc:
                self.after(
                    0,
                    lambda e=exc: error(
                        self,
                        "Nie można uruchomić",
                        str(e),
                    ),
                )

        threading.Thread(
            target=worker,
            name="MizuLaunch",
            daemon=True,
        ).start()
        return

    # ---------------------------------------------------------------
    # Nothing installed -> normal download.
    # ---------------------------------------------------------------
    self._show_install_note_and_continue(
        game,
        lambda: self._download_game_secure(
            game,
            return_to_details=return_to_details,
            update_mode=False,
        ),
    )


# -----------------------------------------------------------------------------
# Runtime layout context
# -----------------------------------------------------------------------------

import mizulauncher.ui.layout_runtime as _location_runtime


def _location_game_context(app, game):
    if not game:
        return {}

    downloaded = app._game_is_downloaded(game)
    executable = app._game_executable(game)
    configured = executable is not None

    try:
        update_available = bool(
            configured and app.manager.update_available(game)
        )
    except Exception:
        update_available = False

    if not downloaded:
        primary_label = "Zainstaluj"
        install_label = "Zainstaluj"
    elif not configured:
        primary_label = "Ustaw lokalizację"
        install_label = "Ustaw lokalizację"
    elif update_available:
        primary_label = "Aktualizuj"
        install_label = "Aktualizacja dostępna"
    else:
        primary_label = "Graj"
        install_label = "Zainstalowana"

    path = app._game_installation_root(game)

    try:
        installed_version = app.manager.installed_version(game) if configured else ""
    except Exception:
        installed_version = ""

    return {
        "game.name": game.name,
        "game.version": game.version,
        "game.developer": game.developer,
        "game.description": game.description,
        "game.category": game.category,
        "game.id": game.id,
        "game.path": str(path),
        "game.executable": str(executable) if executable else "",
        "game.primary_label": primary_label,
        "game.install_label": install_label,
        "game.installed": downloaded,
        "game.downloaded": downloaded,
        "game.configured": configured,
        "game.installed_version": installed_version,
        "game.update_available": update_available,
    }


# -----------------------------------------------------------------------------
# Runtime game list
# -----------------------------------------------------------------------------

def _location_build_game_list(app, parent, el, page_name="home"):
    wrapper = ctk.CTkFrame(
        parent,
        fg_color="transparent",
        corner_radius=0,
    )
    wrapper.pack_propagate(False)

    if page_name == "library":
        installed_only = True
        search_enabled = True
    elif page_name == "home":
        installed_only = False
        search_enabled = True
    else:
        installed_only = bool(el.get("installed_only", False))
        search_enabled = bool(el.get("search_enabled", False))

    search_var = ctk.StringVar(value="")

    header = ctk.CTkFrame(
        wrapper,
        fg_color="transparent",
        corner_radius=0,
    )
    header.pack(
        fill="x",
        padx=4,
        pady=(0, 10),
    )

    if search_enabled:
        search_box = ctk.CTkFrame(
            header,
            fg_color=COLORS["panel"],
            corner_radius=16,
            border_width=2,
            border_color=COLORS["black"],
        )
        search_box.pack(fill="x")

        ctk.CTkLabel(
            search_box,
            text="⌕",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(
            side="left",
            padx=(14, 4),
        )

        entry = ctk.CTkEntry(
            search_box,
            textvariable=search_var,
            placeholder_text=el.get(
                "search_placeholder",
                "Szukaj gry...",
            ),
            border_width=0,
            fg_color="transparent",
            height=44,
            font=ctk.CTkFont(size=14),
        )
        entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 12),
            pady=3,
        )

    count_label = ctk.CTkLabel(
        header,
        text="",
        text_color=COLORS["muted"],
    )
    count_label.pack(
        anchor="w",
        padx=4,
        pady=(8, 0),
    )

    holder = ctk.CTkScrollableFrame(
        wrapper,
        fg_color="transparent",
        orientation="vertical",
        corner_radius=0,
    )
    holder.pack(
        fill="both",
        expand=True,
    )

    columns = max(
        1,
        int(_location_runtime._num(el.get("columns"), 3)),
    )

    gap = int(
        _location_runtime._num(
            el.get("gap"),
            1.0,
        )
    )

    primary_template = app.layout.get(
        "templates",
        {},
    ).get(
        el.get(
            "template_primary",
            "game_primary",
        ),
        {},
    )

    uninstall_template = app.layout.get(
        "templates",
        {},
    ).get(
        el.get(
            "template_uninstall",
            "game_uninstall",
        ),
        {},
    )

    path_template = app.layout.get(
        "templates",
        {},
    ).get(
        el.get(
            "template_path",
            "game_path",
        ),
        {},
    )

    def matches(game, query):
        if not query:
            return True

        q = query.lower().strip()
        haystack = (
            f"{game.name} {game.developer}"
            .lower()
        )

        return q in haystack

    def rebuild(*_):
        for child in holder.winfo_children():
            child.destroy()

        query = search_var.get().strip()

        candidates = [
            g
            for g in app.games
            if g.enabled
        ]

        if installed_only:
            candidates = [
                g
                for g in candidates
                if app._game_is_downloaded(g)
            ]

        filtered = [
            g
            for g in candidates
            if matches(g, query)
        ]

        noun = (
            "gra"
            if len(filtered) == 1
            else "gier"
        )

        if installed_only:
            count_label.configure(
                text=(
                    f"{len(filtered)} "
                    f"{noun} zainstalowanych"
                )
            )
        else:
            count_label.configure(
                text=f"{len(filtered)} {noun}",
            )

        if not filtered:
            empty = ctk.CTkFrame(
                holder,
                fg_color=COLORS["panel"],
                corner_radius=18,
                border_width=2,
                border_color=COLORS["black"],
            )

            empty.grid(
                row=0,
                column=0,
                sticky="ew",
                padx=6,
                pady=10,
            )

            holder.grid_columnconfigure(
                0,
                weight=1,
            )

            if installed_only:
                title = "Brak zainstalowanych gier"
                subtitle = (
                    "Pobierz grę z Home, aby pojawiła się "
                    "w Bibliotece."
                )
            elif query:
                title = "Nie znaleziono gry"
                subtitle = "Spróbuj innej nazwy lub autora."
            else:
                title = "Katalog jest pusty"
                subtitle = "Na razie nie ma żadnych gier w katalogu."

            ctk.CTkLabel(
                empty,
                text=title,
                font=ctk.CTkFont(
                    size=21,
                    weight="bold",
                ),
            ).pack(
                anchor="w",
                padx=22,
                pady=(22, 4),
            )

            ctk.CTkLabel(
                empty,
                text=subtitle,
                text_color=COLORS["muted"],
            ).pack(
                anchor="w",
                padx=22,
                pady=(0, 22),
            )

            return

        for idx, game in enumerate(filtered):
            card = ctk.CTkFrame(
                holder,
                fg_color=COLORS["card"],
                corner_radius=20,
                border_width=2,
                border_color=COLORS["black"],
            )

            r, c = divmod(
                idx,
                columns,
            )

            card.grid(
                row=r,
                column=c,
                sticky="nsew",
                padx=gap * 5,
                pady=gap * 5,
            )

            holder.grid_columnconfigure(
                c,
                weight=1,
                uniform="gamecol",
            )

            art = ctk.CTkLabel(
                card,
                text="",
                fg_color=COLORS["panel2"],
                corner_radius=18,
            )

            art.pack(
                fill="x",
                padx=2,
                pady=2,
            )

            app.image_loader.request(
                game.banner_url or game.icon_url,
                game.name,
                (430, 220),
                "banner",
                lambda img, w=art: w.configure(
                    image=img,
                    text="",
                ),
            )

            body = ctk.CTkFrame(
                card,
                fg_color="transparent",
            )

            body.pack(
                fill="both",
                expand=True,
                padx=14,
                pady=(8, 14),
            )

            top = ctk.CTkFrame(
                body,
                fg_color="transparent",
            )

            top.pack(fill="x")

            ctk.CTkLabel(
                top,
                text=game.name,
                font=ctk.CTkFont(
                    size=17,
                    weight="bold",
                ),
                anchor="w",
            ).pack(
                side="left",
                fill="x",
                expand=True,
            )

            if app._game_is_configured(game):
                try:
                    update = bool(
                        app.manager.update_available(game)
                    )
                except Exception:
                    update = False

                if update:
                    ctk.CTkLabel(
                        top,
                        text="UPDATE",
                        text_color="#F0C36B",
                        fg_color="#2E2615",
                        corner_radius=8,
                        font=ctk.CTkFont(
                            size=10,
                            weight="bold",
                        ),
                    ).pack(
                        side="right",
                        padx=(8, 0),
                    )

            ctk.CTkLabel(
                body,
                text=(
                    f"v{game.version}  •  "
                    f"{game.category or 'Gra'}"
                ),
                text_color=COLORS["muted"],
                anchor="w",
            ).pack(
                fill="x",
                pady=(2, 8),
            )

            if game.description:
                ctk.CTkLabel(
                    body,
                    text=game.description,
                    text_color=COLORS["muted"],
                    justify="left",
                    anchor="nw",
                    wraplength=360,
                ).pack(
                    fill="x",
                    pady=(0, 8),
                )

            ctk.CTkButton(
                body,
                text="Szczegóły",
                height=34,
                fg_color="transparent",
                hover_color=COLORS["panel2"],
                border_width=1,
                border_color=COLORS["border_soft"],
                command=lambda g=game: app.open_game_details(g),
            ).pack(
                fill="x",
                pady=(0, 6),
            )

            context = _location_game_context(
                app,
                game,
            )

            primary_text = _location_runtime._substitute(
                primary_template.get(
                    "text",
                    "{{game.primary_label}}",
                ),
                context,
            )

            ctk.CTkButton(
                body,
                text=primary_text,
                height=38,
                command=lambda g=game, d=primary_template: _location_runtime.perform_action(
                    app,
                    d.get(
                        "action",
                        "game.primary",
                    ),
                    g,
                    d,
                ),
                **_location_runtime._button_style(
                    primary_template
                ),
            ).pack(
                fill="x",
                pady=2,
            )

            if app._game_is_downloaded(game):
                ctk.CTkButton(
                    body,
                    text=uninstall_template.get(
                        "text",
                        "Odinstaluj",
                    ),
                    height=34,
                    command=lambda g=game: app.uninstall_game(g),
                    **_location_runtime._button_style(
                        uninstall_template
                    ),
                ).pack(
                    fill="x",
                    pady=2,
                )

                ctk.CTkButton(
                    body,
                    text=path_template.get(
                        "text",
                        "Lokalizacja",
                    ),
                    height=34,
                    command=lambda g=game, d=path_template: _location_runtime.perform_action(
                        app,
                        d.get(
                            "action",
                            "game.path",
                        ),
                        g,
                        d,
                    ),
                    **_location_runtime._button_style(
                        path_template
                    ),
                ).pack(
                    fill="x",
                    pady=2,
                )

                ctk.CTkButton(
                    body,
                    text="Ustaw nową lokalizację",
                    height=34,
                    fg_color=COLORS["panel2"],
                    hover_color=COLORS["card_hover"],
                    border_width=1,
                    border_color=COLORS["border_soft"],
                    command=lambda g=game: app._set_game_location(
                        g,
                        return_to_details=False,
                    ),
                ).pack(
                    fill="x",
                    pady=2,
                )

    if search_enabled:
        search_var.trace_add(
            "write",
            rebuild,
        )
        entry.bind(
            "<Escape>",
            lambda _e: search_var.set(""),
        )
        entry.bind(
            "<Return>",
            lambda _e: None,
        )

    rebuild()
    return wrapper


# -----------------------------------------------------------------------------
# Runtime game details
# -----------------------------------------------------------------------------

def _location_build_game_detail(app, parent, el):
    game = app.selected_game

    outer = ctk.CTkFrame(
        parent,
        fg_color="transparent",
    )

    if not game:
        ctk.CTkLabel(
            outer,
            text="Nie wybrano gry",
            font=ctk.CTkFont(
                size=28,
                weight="bold",
            ),
        ).pack(
            anchor="w",
            padx=20,
            pady=20,
        )
        return outer

    hero = ctk.CTkFrame(
        outer,
        fg_color=COLORS["panel"],
        corner_radius=24,
        border_width=2,
        border_color=COLORS["black"],
    )
    hero.pack(
        fill="x",
        pady=3,
    )

    art = ctk.CTkLabel(
        hero,
        text="",
        fg_color=COLORS["panel2"],
        corner_radius=22,
    )
    art.pack(
        fill="x",
        padx=2,
        pady=2,
    )

    app.image_loader.request(
        game.banner_url or game.icon_url,
        game.name,
        (1000, 320),
        "hero",
        lambda img, w=art: w.configure(
            image=img,
            text="",
        ),
    )

    box = ctk.CTkFrame(
        hero,
        fg_color="transparent",
    )

    box.place(
        relx=0.035,
        rely=0.08,
        relwidth=0.9,
        relheight=0.82,
    )

    ctk.CTkLabel(
        box,
        text=game.name,
        font=ctk.CTkFont(
            size=34,
            weight="bold",
        ),
        text_color="#FFF",
        anchor="w",
    ).pack(
        anchor="w",
    )

    ctk.CTkLabel(
        box,
        text=(
            f"v{game.version} • "
            f"{game.developer} • "
            f"{game.category}"
        ),
        text_color="#D0D0D0",
    ).pack(
        anchor="w",
        pady=(5, 8),
    )

    ctk.CTkLabel(
        box,
        text=game.description or "",
        wraplength=850,
        justify="left",
        text_color="#D6D6D6",
    ).pack(anchor="w")

    actions = ctk.CTkFrame(
        outer,
        fg_color=COLORS["panel"],
        corner_radius=18,
        border_width=2,
        border_color=COLORS["black"],
    )

    actions.pack(
        fill="x",
        pady=8,
    )

    primary = app.layout.get(
        "templates",
        {},
    ).get(
        el.get(
            "template_primary",
            "game_primary",
        ),
        {},
    )

    uninstall = app.layout.get(
        "templates",
        {},
    ).get(
        el.get(
            "template_uninstall",
            "game_uninstall",
        ),
        {},
    )

    path_t = app.layout.get(
        "templates",
        {},
    ).get(
        el.get(
            "template_path",
            "game_path",
        ),
        {},
    )

    context = _location_game_context(
        app,
        game,
    )

    ctk.CTkButton(
        actions,
        text=_location_runtime._substitute(
            primary.get(
                "text",
                "{{game.primary_label}}",
            ),
            context,
        ),
        height=44,
        command=lambda d=primary: _location_runtime.perform_action(
            app,
            d.get(
                "action",
                "game.primary",
            ),
            game,
            d,
        ),
        **_location_runtime._button_style(
            primary
        ),
    ).pack(
        side="left",
        fill="x",
        expand=True,
        padx=(14, 5),
        pady=14,
    )

    # Once the archive exists, keep the standard management buttons available.
    if app._game_is_downloaded(game):
        ctk.CTkButton(
            actions,
            text=uninstall.get(
                "text",
                "Odinstaluj",
            ),
            height=44,
            command=lambda g=game: app.uninstall_game(g),
            **_location_runtime._button_style(
                uninstall
            ),
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=5,
            pady=14,
        )

        ctk.CTkButton(
            actions,
            text=path_t.get(
                "text",
                "Lokalizacja",
            ),
            height=44,
            command=lambda d=path_t: _location_runtime.perform_action(
                app,
                d.get(
                    "action",
                    "game.path",
                ),
                game,
                d,
            ),
            **_location_runtime._button_style(
                path_t
            ),
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=5,
            pady=14,
        )

        ctk.CTkButton(
            actions,
            text="Ustaw nową lokalizację",
            height=44,
            fg_color=COLORS["panel2"],
            hover_color=COLORS["card_hover"],
            border_width=1,
            border_color=COLORS["border_soft"],
            command=lambda: app._set_game_location(
                game,
                return_to_details=True,
            ),
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=(5, 14),
            pady=14,
        )

    elif game.homepage_url:
        ctk.CTkButton(
            actions,
            text="Strona projektu",
            height=44,
            command=lambda: _location_runtime.perform_action(
                app,
                "game.homepage",
                game,
            ),
            fg_color=COLORS["panel2"],
            hover_color=COLORS["card_hover"],
            border_width=1,
            border_color=COLORS["black"],
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=(5, 14),
            pady=14,
        )

    body = ctk.CTkScrollableFrame(
        outer,
        fg_color="transparent",
    )

    body.pack(
        fill="both",
        expand=True,
        pady=4,
    )

    if game.notes:
        note_card = ctk.CTkFrame(
            body,
            fg_color=COLORS["panel"],
            corner_radius=18,
            border_width=2,
            border_color=COLORS["black"],
        )

        note_card.pack(
            fill="x",
            pady=6,
        )

        ctk.CTkLabel(
            note_card,
            text="NOTATKA DEWELOPERA",
            font=ctk.CTkFont(
                size=10,
                weight="bold",
            ),
            text_color=COLORS["muted"],
        ).pack(
            anchor="w",
            padx=18,
            pady=(16, 4),
        )

        ctk.CTkLabel(
            note_card,
            text=game.notes,
            justify="left",
            wraplength=900,
        ).pack(
            anchor="w",
            padx=18,
            pady=(0, 16),
        )

    info_card = ctk.CTkFrame(
        body,
        fg_color=COLORS["panel"],
        corner_radius=18,
        border_width=2,
        border_color=COLORS["black"],
    )

    info_card.pack(
        fill="x",
        pady=6,
    )

    exe = app._game_executable(game)
    exe_text = str(exe) if exe else "Nie ustawiono — wybierz lokalizację EXE."

    ctk.CTkLabel(
        info_card,
        text=f"Instalacja: {app._game_installation_root(game)}",
        text_color=COLORS["muted"],
        justify="left",
        anchor="w",
    ).pack(
        anchor="w",
        padx=18,
        pady=(16, 4),
    )

    ctk.CTkLabel(
        info_card,
        text=f"EXE: {exe_text}",
        text_color=(
            COLORS["text"]
            if exe
            else COLORS["orange"]
        ),
        justify="left",
        anchor="w",
        wraplength=900,
    ).pack(
        anchor="w",
        padx=18,
        pady=(0, 16),
    )

    return outer


# -----------------------------------------------------------------------------
# Use the new functions from the whole application.
# -----------------------------------------------------------------------------

MizuLauncher._game_installation_root = _game_installation_root
MizuLauncher._game_is_downloaded = _game_is_downloaded
MizuLauncher._game_executable = _game_executable
MizuLauncher._game_is_configured = _game_is_configured
MizuLauncher._choose_game_executable = _choose_game_executable
MizuLauncher._set_game_location = _set_game_location
MizuLauncher.open_game_location = _open_game_location_v2
MizuLauncher.install_or_launch = _secure_install_or_launch_v2

# The visual layout runtime is imported as a module by render_element(), so
# replacing its globals updates every layout-rendered Home/Library/Details page.
_location_runtime._game_context = _location_game_context
_location_runtime.build_game_list = _location_build_game_list
_location_runtime.build_game_detail = _location_build_game_detail


# =============================================================================
# FINAL FIX: REAL GAME UNINSTALL + CLEAN LOCAL INSTALL STATE
# =============================================================================
import shutil as _uninstall_shutil
import os as _uninstall_os
import subprocess as _uninstall_subprocess
import base64 as _uninstall_base64
import stat as _uninstall_stat


def _force_remove_tree(path):
    """Remove a game directory on Windows even when files are read-only."""
    path = _LocationPath(path)
    if not path.exists():
        return

    def _onerror(func, name, exc_info):
        try:
            _os.chmod(name, _uninstall_stat.S_IRUSR | _uninstall_stat.S_IWUSR | _uninstall_stat.S_IXUSR)
        except Exception:
            pass
        try:
            func(name)
        except PermissionError:
            try:
                _os.system(f"attrib -R -S -H \"{name}\" /S /D >nul 2>&1")
                _os.chmod(name, _uninstall_stat.S_IRUSR | _uninstall_stat.S_IWUSR | _uninstall_stat.S_IXUSR)
                func(name)
            except Exception:
                raise

    _uninstall_shutil.rmtree(path, onerror=_onerror)


def _game_is_downloaded_v2(self, game: Game) -> bool:
    """
    Return True only when this game has a local installation record.

    A plain folder, an old location override, or a saved EXE is not enough.
    The explicit installed_game_ids registry is checked first so uninstalling
    immediately removes the game from Library even with an older GameManager.
    """
    try:
        uninstalled_ids = self.config.get("uninstalled_game_ids", [])
        if isinstance(uninstalled_ids, list) and game.id in uninstalled_ids:
            return False
    except Exception:
        pass

    try:
        installed_ids = self.config.get("installed_game_ids", [])
        if isinstance(installed_ids, list) and game.id in installed_ids:
            # Also verify that the installation still exists. If the user
            # manually deleted it, clean the stale registry entry.
            root = self._game_installation_root(game)
            if root and root.is_dir():
                return True
            installed_ids[:] = [x for x in installed_ids if x != game.id]
            self.config["installed_game_ids"] = installed_ids
            try:
                save_config(self.config)
            except Exception:
                pass
    except Exception:
        pass

    try:
        record = self.manager._read_install_record(game)
        if record:
            root, data = record
            if root.is_dir() and isinstance(data, dict):
                game_id = data.get("game_id")
                if game_id in (None, "", game.id):
                    return True
    except Exception:
        pass

    return False



def _uninstall_game_v2(self, game: Game):
    """Remove the game from local state and reliably delete its installation on Windows."""
    if not confirm(self, "Odinstaluj", f"Usunąć pliki gry '{game.name}'? Zawartość folderu instalacji zostanie usunięta."):
        return

    # Capture the actual installation root before the manager changes anything.
    root = None
    try:
        root = _LocationPath(str(self._game_installation_root(game))).resolve()
    except Exception:
        try:
            root = _LocationPath(str(self.manager.game_root(game))).resolve()
        except Exception:
            pass

    # The game is considered uninstalled immediately. This is independent from
    # whether Windows needs a moment to release a locked EXE/DLL.
    try:
        installed_ids = self.config.get("installed_game_ids", [])
        if isinstance(installed_ids, list):
            self.config["installed_game_ids"] = [x for x in installed_ids if x != game.id]
        uninstalled_ids = self.config.get("uninstalled_game_ids", [])
        if not isinstance(uninstalled_ids, list):
            uninstalled_ids = []
        if game.id not in uninstalled_ids:
            uninstalled_ids.append(game.id)
        self.config["uninstalled_game_ids"] = uninstalled_ids
        overrides = self.config.get("game_install_overrides", {})
        if isinstance(overrides, dict):
            overrides.pop(game.id, None)
            overrides.pop(str(game.id), None)
        self.config["game_install_overrides"] = overrides
        save_config(self.config)
    except Exception as exc:
        print(f"[MizuLauncher] uninstall state warning: {exc}")

    # Stop the tracked game and its CHILD PROCESSES. A game can spawn a launcher,
    # updater, crash reporter, etc. that keeps a DLL/EXE locked.
    process = getattr(self, "_active_game_process", None)
    try:
        pid = int(process.pid) if process is not None else None
    except Exception:
        pid = None

    if pid and _uninstall_os.name == "nt":
        try:
            _uninstall_subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=_uninstall_subprocess.DEVNULL,
                stderr=_uninstall_subprocess.DEVNULL,
                check=False,
                timeout=15,
            )
        except Exception as exc:
            print(f"[MizuLauncher] taskkill warning: {exc}")
    elif process is not None:
        try:
            process.terminate()
        except Exception:
            pass

    monitor = getattr(self, "_active_game_monitor", None)
    if monitor:
        try:
            monitor.stop()
        except Exception:
            pass
    self._active_game_process = None
    self._active_game_monitor = None

    # Best effort DRM cleanup.
    if root is not None:
        try:
            delete_mizuapi(root)
        except Exception:
            pass

    # Clear manager state/overrides even when an older GameManager implementation
    # itself fails during filesystem deletion.
    state = getattr(self.manager, "state", None)
    if isinstance(state, dict):
        state.pop(game.id, None)
        try:
            saver = getattr(self.manager, "_save_state", None)
            if callable(saver):
                saver()
        except Exception:
            pass
    manager_overrides = getattr(self.manager, "install_overrides", None)
    if isinstance(manager_overrides, dict):
        manager_overrides.pop(game.id, None)
        manager_overrides.pop(str(game.id), None)

    try:
        self.manager.uninstall(game)
    except Exception as exc:
        print(f"[MizuLauncher] manager.uninstall warning: {exc}")

    def remove_now(path):
        if path is None or not path.exists():
            return True
        def fix_permissions(func, target, exc_info):
            try:
                _uninstall_os.chmod(target, 0o777)
                func(target)
            except Exception:
                pass
        for _ in range(8):
            try:
                for current, dirs, files in _uninstall_os.walk(path, topdown=False):
                    for name in files + dirs:
                        target = _LocationPath(current) / name
                        try:
                            _uninstall_os.chmod(target, 0o777)
                        except Exception:
                            pass
                _uninstall_shutil.rmtree(path, onerror=fix_permissions)
                return not path.exists()
            except (PermissionError, OSError) as exc:
                print(f"[MizuLauncher] delete retry: {exc}")
                time.sleep(0.5)
        return not path.exists()

    removed = remove_now(root)

    # If another process still owns a handle, hand deletion to a completely
    # independent Windows process. It retries for up to 90 seconds, so after the
    # launcher/game releases its last handle the actual files disappear too.
    if not removed and root is not None and root.exists() and _uninstall_os.name == "nt":
        try:
            encoded = _uninstall_base64.b64encode(str(root).encode("utf-16le")).decode("ascii")
            ps = (
                "$p=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('" + encoded + "'));"
                "for($i=0;$i -lt 90;$i++){"
                "if(-not(Test-Path -LiteralPath $p)){break};"
                "try{"
                "Get-ChildItem -LiteralPath $p -Force -Recurse -ErrorAction SilentlyContinue | "
                "ForEach-Object{try{$_.IsReadOnly=$false}catch{}};"
                "Remove-Item -LiteralPath $p -Force -Recurse -ErrorAction Stop;break"
                "}catch{Start-Sleep -Seconds 1}}"
            )
            _uninstall_subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps],
                stdin=_uninstall_subprocess.DEVNULL,
                stdout=_uninstall_subprocess.DEVNULL,
                stderr=_uninstall_subprocess.DEVNULL,
                creationflags=getattr(_uninstall_subprocess, "CREATE_NO_WINDOW", 0),
            )
            print(f"[MizuLauncher] deferred Windows delete scheduled: {root}")
            removed = True
        except Exception as exc:
            print(f"[MizuLauncher] deferred delete warning: {exc}")

    try:
        save_config(self.config)
    except Exception:
        pass
    self.selected_game = None
    self.show_view("library")

MizuLauncher._game_is_downloaded = _game_is_downloaded_v2
MizuLauncher.uninstall_game = _uninstall_game_v2

# Keep the location-aware runtime bound to the corrected installation check.
_location_runtime._game_context = _location_game_context
_location_runtime.build_game_list = _location_build_game_list
_location_runtime.build_game_detail = _location_build_game_detail
