from __future__ import annotations

import requests


class ApiError(RuntimeError):
    pass


class SupabaseClient:
    """Small REST/Auth client.

    The launcher contains only a public publishable/anon key. Privileged actions are
    protected by Supabase Auth + RLS and by server-side Edge Functions where needed.
    No service_role/secret key belongs in this client.
    """

    def __init__(self, project_url: str, publishable_key: str, catalog_id: int = 1, timeout: int = 20):
        self.project_url = project_url.rstrip("/")
        self.publishable_key = publishable_key.strip()
        self.catalog_id = int(catalog_id)
        self.timeout = timeout
        self.access_token = ""
        self.refresh_token = ""
        self.user_id = ""
        self.user_email = ""
        self.is_developer = False
        self.is_admin = False
        self.player_control: dict = {}

    @property
    def configured(self) -> bool:
        return bool(self.project_url and self.publishable_key)

    @property
    def authenticated(self) -> bool:
        return bool(self.access_token and self.user_id)

    @property
    def developer_authenticated(self) -> bool:
        return self.authenticated and self.is_developer

    @property
    def admin_authenticated(self) -> bool:
        return self.authenticated and self.is_admin

    def _headers(self, authenticated: bool = False, prefer: str | None = None) -> dict:
        if not self.configured:
            raise ApiError("Supabase nie jest skonfigurowany.")
        token = self.access_token if authenticated and self.access_token else self.publishable_key
        headers = {
            "apikey": self.publishable_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _handle(self, response: requests.Response):
        if response.ok:
            if not response.text.strip():
                return {}
            try:
                return response.json()
            except ValueError:
                return {}
        try:
            payload = response.json()
            msg = payload.get("message") or payload.get("error_description") or payload.get("error")
            detail = payload.get("details") or payload.get("hint")
            if detail:
                msg = f"{msg} ({detail})"
        except ValueError:
            msg = response.text[:500]
        raise ApiError(f"Supabase {response.status_code}: {msg}")

    def fetch_catalog(self) -> dict:
        url = f"{self.project_url}/rest/v1/launcher_catalog"
        params = {"id": f"eq.{self.catalog_id}", "select": "data,updated_at", "limit": "1"}
        r = requests.get(url, headers=self._headers(False), params=params, timeout=self.timeout)
        data = self._handle(r)
        if not data:
            return {"schema_version": 1, "updated_at": "", "games": []}
        row = data[0]
        return row.get("data") or {"schema_version": 1, "updated_at": row.get("updated_at", ""), "games": []}

    def save_session_state(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "user_id": self.user_id,
            "user_email": self.user_email,
        }

    def restore_session(self, access_token: str = "", refresh_token: str = "") -> bool:
        if not self.configured or not refresh_token:
            return False
        try:
            r = requests.post(
                f"{self.project_url}/auth/v1/token",
                headers=self._headers(False),
                params={"grant_type": "refresh_token"},
                json={"refresh_token": refresh_token},
                timeout=self.timeout,
            )
            data = self._handle(r)
            self._set_session(data)
            self.refresh_player_security()
            return self.authenticated
        except Exception:
            return False

    def sign_in(self, email: str, password: str) -> dict:
        if not self.configured:
            raise ApiError("Najpierw skonfiguruj Supabase.")
        r = requests.post(
            f"{self.project_url}/auth/v1/token",
            headers=self._headers(False),
            params={"grant_type": "password"},
            json={"email": email.strip(), "password": password},
            timeout=self.timeout,
        )
        data = self._handle(r)
        self._set_session(data)
        self.refresh_player_security()
        return data

    def sign_up(self, email: str, password: str) -> dict:
        if not self.configured:
            raise ApiError("Najpierw skonfiguruj Supabase.")
        r = requests.post(
            f"{self.project_url}/auth/v1/signup",
            headers=self._headers(False),
            json={"email": email.strip(), "password": password},
            timeout=self.timeout,
        )
        data = self._handle(r)
        if data.get("access_token"):
            self._set_session(data)
            self.refresh_player_security()
        return data

    def _set_session(self, data: dict) -> None:
        self.access_token = data.get("access_token", "")
        self.refresh_token = data.get("refresh_token", "")
        user = data.get("user") or {}
        self.user_id = user.get("id", "")
        self.user_email = user.get("email", "")
        if not self.user_id and self.access_token:
            self._load_user()

    def _load_user(self) -> dict:
        r = requests.get(
            f"{self.project_url}/auth/v1/user",
            headers=self._headers(True),
            timeout=self.timeout,
        )
        user = self._handle(r)
        self.user_id = user.get("id", "")
        self.user_email = user.get("email", "")
        return user

    def refresh_player_security(self) -> dict:
        if not self.authenticated:
            self.is_developer = False
            self.is_admin = False
            self.player_control = {}
            return {}
        url = f"{self.project_url}/rest/v1/player_control"
        params = {
            "user_id": f"eq.{self.user_id}",
            "select": "user_id,is_developer,is_admin,can_play,can_download,kill_switch,updated_at",
            "limit": "1",
        }
        r = requests.get(url, headers=self._headers(True), params=params, timeout=self.timeout)
        data = self._handle(r)
        self.player_control = data[0] if data else {}
        self.is_developer = bool(self.player_control.get("is_developer", False))
        self.is_admin = bool(self.player_control.get("is_admin", False))
        return self.player_control

    def fetch_player_control(self) -> dict:
        return self.refresh_player_security()

    def require_developer(self):
        self.refresh_player_security()
        if not self.developer_authenticated:
            raise ApiError("Brak uprawnień developera.")

    def call_function(self, name: str, payload: dict) -> dict:
        if not self.authenticated:
            raise ApiError("Musisz być zalogowany.")
        r = requests.post(
            f"{self.project_url}/functions/v1/{name}",
            headers=self._headers(True),
            json=payload,
            timeout=self.timeout,
        )
        return self._handle(r)

    def send_telemetry(self, windows_username: str, hwid_hash: str, event: str = "launcher_start", local_ip: str = "") -> dict:
        return self.call_function(
            "mizu-telemetry",
            {
                "event": event,
                "windows_username": windows_username,
                "hwid_hash": hwid_hash,
                "local_ip": local_ip,
                "app_version": "security-v1",
            },
        )

    def issue_drm(self, game_id: str, purpose: str = "play") -> dict:
        self.refresh_player_security()
        if not self.player_control.get("can_play", True) or self.player_control.get("kill_switch", False):
            raise ApiError("Gra jest zablokowana dla tego konta.")
        return self.call_function("mizu-drm-issue", {"game_id": game_id, "purpose": purpose})

    def verify_drm(self, game_id: str, user_id: str, token: str) -> dict:
        return self.call_function(
            "mizu-drm-verify",
            {"game_id": game_id, "user_id": user_id, "token": token},
        )

    def sign_out(self) -> None:
        if self.access_token:
            try:
                requests.post(
                    f"{self.project_url}/auth/v1/logout",
                    headers=self._headers(True),
                    timeout=self.timeout,
                )
            except requests.RequestException:
                pass
        self.access_token = ""
        self.refresh_token = ""
        self.user_id = ""
        self.user_email = ""
        self.is_developer = False
        self.is_admin = False
        self.player_control = {}

    def publish_catalog(self, catalog: dict) -> dict:
        self.require_developer()
        r = requests.patch(
            f"{self.project_url}/rest/v1/launcher_catalog",
            headers=self._headers(True, prefer="return=representation"),
            params={"id": f"eq.{self.catalog_id}"},
            json={"data": catalog, "updated_at": catalog.get("updated_at")},
            timeout=self.timeout,
        )
        data = self._handle(r)
        return data[0] if isinstance(data, list) and data else data

    def admin_set_play(self, target_user_id: str, allowed: bool) -> dict:
        if not self.admin_authenticated:
            raise ApiError("Tylko administrator może zmieniać status gracza.")
        return self.call_function("mizu-admin-action", {"action": "play", "target_user_id": target_user_id, "value": bool(allowed)})

    def admin_set_download(self, target_user_id: str, allowed: bool) -> dict:
        if not self.admin_authenticated:
            raise ApiError("Tylko administrator może zmieniać status gracza.")
        return self.call_function("mizu-admin-action", {"action": "download", "target_user_id": target_user_id, "value": bool(allowed)})

    def admin_set_kill_switch(self, target_user_id: str, enabled: bool) -> dict:
        if not self.admin_authenticated:
            raise ApiError("Tylko administrator może zmieniać status gracza.")
        return self.call_function("mizu-admin-action", {"action": "kill_switch", "target_user_id": target_user_id, "value": bool(enabled)})

    def admin_list_players(self) -> list[dict]:
        if not self.admin_authenticated:
            raise ApiError("Tylko administrator może przeglądać listę graczy.")
        r = requests.get(
            f"{self.project_url}/rest/v1/player_control",
            headers=self._headers(True),
            params={
                "select": "user_id,email,windows_username,ip_address,hwid_hash,last_login_at,last_seen_at,is_developer,is_admin,can_play,can_download,kill_switch,updated_at",
                "order": "last_seen_at.desc.nullslast",
            },
            timeout=self.timeout,
        )
        return self._handle(r)

    def ping(self) -> None:
        self.fetch_catalog()
