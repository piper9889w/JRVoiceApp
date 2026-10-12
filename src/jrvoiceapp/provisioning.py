"""VoiceAdmin profile retrieval with deliberately safe, narrow error reporting."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from jrvoiceapp.models import AccountConfig, ConnectionKind


class ProvisioningError(RuntimeError):
    """An error suitable for display without exposing credentials or response content."""


def normalize_base_url(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ProvisioningError("Enter a provisioning server URL.")
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    try:
        parsed = urllib.parse.urlsplit(candidate)
        port = parsed.port
    except ValueError as error:
        raise ProvisioningError("The provisioning server URL is invalid.") from error
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ProvisioningError("Provisioning URLs must use HTTP or HTTPS and include a host.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProvisioningError(
            "The provisioning server URL must not include credentials or a query."
        )
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    return urllib.parse.urlunsplit(
        (parsed.scheme, f"{host}:{port}" if port else host, parsed.path.rstrip("/"), "", "")
    )


@dataclass(frozen=True)
class ProvisionedAccount:
    account: AccountConfig
    sip_password: str
    omitted_fields: tuple[str, ...]


class VoiceAdminClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: float = 10.0) -> None:
        if not username.strip() or not password:
            raise ProvisioningError("Enter the provisioning username and password.")
        self.base_url = normalize_base_url(base_url)
        self.username = username.strip()
        self.password = password
        self.timeout = timeout

    @property
    def profile_url(self) -> str:
        return f"{self.base_url}/api/provision/{urllib.parse.quote(self.username, safe='')}"

    def fetch(self, retries: int = 2) -> dict[str, Any]:
        """Fetch version-1 JSON, retrying transient network failures only."""
        for attempt in range(retries + 1):
            try:
                return self._fetch_once()
            except ProvisioningError as error:
                if attempt == retries or not str(error).startswith("Could not reach"):
                    raise
        raise AssertionError("unreachable")  # pragma: no cover

    def _fetch_once(self) -> dict[str, Any]:
        token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        request = urllib.request.Request(
            self.profile_url,
            headers={"Authorization": f"Basic {token}", "Accept": "application/json"},
            method="GET",
        )
        try:
            # urllib's default HTTPS context verifies both certificate and hostname.
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            messages = {
                401: "Provisioning authentication failed.",
                403: "Provisioning access was denied.",
                404: "No provisioning profile was found.",
            }
            raise ProvisioningError(
                messages.get(error.code, "The provisioning server returned an error.")
            ) from error
        except TimeoutError:
            raise ProvisioningError(
                "Could not reach the provisioning server before the timeout."
            ) from None
        except urllib.error.URLError:
            raise ProvisioningError("Could not reach the provisioning server.") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProvisioningError("The provisioning server returned malformed JSON.") from None
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ProvisioningError("The provisioning response must contain version 1.")
        configuration = payload.get("configuration")
        if not isinstance(configuration, dict):
            raise ProvisioningError("The provisioning response is missing configuration.")
        return configuration


def map_profile(configuration: dict[str, Any], existing: AccountConfig) -> ProvisionedAccount:
    required = ("username", "displayName", "server", "transport", "voicemail")
    missing = [name for name in required if not str(configuration.get(name, "")).strip()]
    if missing:
        raise ProvisioningError("The provisioning profile is missing required account fields.")
    transport = str(configuration["transport"]).upper()
    if transport != "TLS":
        raise ProvisioningError(
            "This JRVoiceApp build currently supports only TLS SIP provisioning profiles."
        )
    server = str(configuration["server"]).strip().removeprefix("sip:").rstrip("/")
    if not server or "/" in server:
        raise ProvisioningError("The provisioning profile has an invalid SIP server.")
    sip_password = str(configuration.get("sipPassword", ""))
    omitted = tuple(sorted(name for name in ("sipPassword",) if not configuration.get(name)))
    return ProvisionedAccount(
        account=AccountConfig(
            identifier=existing.identifier,
            label=str(configuration["displayName"]).strip(),
            username=str(configuration["username"]).strip(),
            server=server,
            connection_kind=ConnectionKind.SIP,
            voicemail_number=str(configuration["voicemail"]).strip() or "*97",
            signaling=existing.signaling,
            emergency=existing.emergency,
            provisioning_server=normalize_base_url(existing.provisioning_server),
        ),
        sip_password=sip_password,
        omitted_fields=omitted,
    )
