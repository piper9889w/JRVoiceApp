"""Traditional SIP integration through the cross-platform Baresip runtime."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from jrvoiceapp.models import AccountConfig
from jrvoiceapp.telephony.base import ProviderState, TelephonyProvider


class BaresipProvider(TelephonyProvider):
    def __init__(self, account: AccountConfig, password: str, executable: str = "baresip") -> None:
        super().__init__()
        self.account = account
        self.password = password
        self.executable = executable
        self.process: subprocess.Popen[str] | None = None
        self._runtime_dir: tempfile.TemporaryDirectory[str] | None = None

    def start(self) -> None:
        binary = shutil.which(self.executable)
        if binary is None:
            self.state = ProviderState.ERROR
            raise RuntimeError(
                "Baresip is not installed. Install it before enabling a SIP account."
            )
        self._runtime_dir = tempfile.TemporaryDirectory(prefix="jrvoiceapp-sip-")
        directory = Path(self._runtime_dir.name)
        account_file = directory / "accounts"
        account_file.write_text(self._account_line(), encoding="utf-8")
        account_file.chmod(0o600)
        self.process = subprocess.Popen(
            [binary, "-f", str(directory)], text=True, stdin=subprocess.PIPE
        )
        self.state = ProviderState.READY

    def _account_line(self) -> str:
        return f"<sip:{self.account.username}:{self.password}@{self.account.server};regint=300>\n"

    def dial(self, destination: str) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("SIP provider is not running.")
        self.process.stdin.write(f"/dial {destination}\n")
        self.process.stdin.flush()

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
        if self._runtime_dir:
            self._runtime_dir.cleanup()
        self.process = None
        self._runtime_dir = None
        self.state = ProviderState.IDLE
