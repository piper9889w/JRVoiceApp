"""Persist non-secret account data and isolate secrets in the operating-system keychain."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import keyring
from PySide6.QtCore import QStandardPaths

from jrvoiceapp.models import (
    AccountConfig,
    ConnectionKind,
    EmergencyConfig,
    SignalingTemplates,
    UserEmergencySettings,
    WebRtcEngine,
)

KEYRING_SERVICE = "JRVoiceApp"


class AccountStore:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            base = Path(
                QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
            )
            path = base / "accounts.json"
        self.path = path

    def load(self) -> list[AccountConfig]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [
            AccountConfig(
                identifier=item["identifier"],
                label=item["label"],
                username=item["username"],
                server=item["server"],
                connection_kind=ConnectionKind(item["connection_kind"]),
                web_rtc_engine=WebRtcEngine(item.get("web_rtc_engine", WebRtcEngine.SIPJS)),
                voicemail_number=item.get("voicemail_number", "*97"),
                signaling=SignalingTemplates(**item.get("signaling", {})),
                emergency=EmergencyConfig(**item.get("emergency", {})),
            )
            for item in raw
        ]

    def save(self, accounts: list[AccountConfig]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for account in accounts:
            account.validate()
        self.path.write_text(
            json.dumps([asdict(account) for account in accounts], indent=2), encoding="utf-8"
        )

    def save_password(self, account_id: str, password: str) -> None:
        keyring.set_password(KEYRING_SERVICE, account_id, password)

    def password_for(self, account_id: str) -> str:
        """Read a password only when a provider is being started."""
        return keyring.get_password(KEYRING_SERVICE, account_id) or ""

    @property
    def emergency_settings_path(self) -> Path:
        return self.path.with_name("emergency-settings.json")

    def load_user_emergency_settings(self) -> UserEmergencySettings:
        path = self.emergency_settings_path
        if not path.exists():
            return UserEmergencySettings()
        return UserEmergencySettings(**json.loads(path.read_text(encoding="utf-8")))

    def save_user_emergency_settings(self, settings: UserEmergencySettings) -> None:
        settings.validate()
        path = self.emergency_settings_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
