"""Platform credential storage for SIP and VoiceAdmin secrets."""

from typing import Optional

try:
    import keyring
    from keyring.errors import KeyringError
except ImportError:  # pragma: no cover - exercised by deployment validation
    keyring = None

    class KeyringError(Exception):
        pass


SERVICE_NAME = "SIPApp"


class CredentialStoreError(RuntimeError):
    pass


class CredentialStore:
    def _require_backend(self) -> None:
        if keyring is None:
            raise CredentialStoreError(
                "Secure credential storage is unavailable. Install requirements.txt and restart SIPApp."
            )

    def set(self, key: str, value: str) -> None:
        self._require_backend()
        try:
            if value:
                keyring.set_password(SERVICE_NAME, key, value)
            else:
                self.delete(key)
        except KeyringError as exc:
            raise CredentialStoreError(
                f"Could not save a credential in the platform keychain: {exc}"
            ) from exc

    def get(self, key: str) -> str:
        self._require_backend()
        try:
            return keyring.get_password(SERVICE_NAME, key) or ""
        except KeyringError as exc:
            raise CredentialStoreError(
                f"Could not read a credential from the platform keychain: {exc}"
            ) from exc

    def delete(self, key: str) -> None:
        self._require_backend()
        try:
            if keyring.get_password(SERVICE_NAME, key) is not None:
                keyring.delete_password(SERVICE_NAME, key)
        except KeyringError as exc:
            raise CredentialStoreError(
                f"Could not remove a credential from the platform keychain: {exc}"
            ) from exc

    @staticmethod
    def sip_password_key(account_id: str) -> str:
        return f"sip-password:{account_id}"

    @staticmethod
    def provisioning_username_key(credential_id: str) -> str:
        return f"provisioning-username:{credential_id}"

    @staticmethod
    def provisioning_password_key(credential_id: str) -> str:
        return f"provisioning-password:{credential_id}"
