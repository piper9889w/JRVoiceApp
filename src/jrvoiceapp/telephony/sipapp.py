"""Adapter boundary for the SIP implementation developed in SIPApp.

This project deliberately continues SIP development from the existing SIPApp source,
which must be brought into JRVoiceApp as maintained project code. Do not substitute
an unrelated SIP application or runtime as the product's SIP implementation.
"""

from jrvoiceapp.models import AccountConfig
from jrvoiceapp.telephony.base import ProviderState, TelephonyProvider


class SipAppProvider(TelephonyProvider):
    """Temporary boundary while the approved SIPApp code is ported in."""

    def __init__(self, account: AccountConfig, password: str) -> None:
        super().__init__()
        self.account = account
        self.password = password

    def start(self) -> None:
        self.state = ProviderState.ERROR
        raise RuntimeError(
            "SIPApp source has not been integrated yet. Continue SIP development from the approved SIPApp implementation."
        )

    def dial(self, destination: str) -> None:
        raise RuntimeError("SIPApp is not registered.")

    def stop(self) -> None:
        self.state = ProviderState.IDLE
