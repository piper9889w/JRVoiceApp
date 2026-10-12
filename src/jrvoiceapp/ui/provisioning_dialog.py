"""Small VoiceAdmin enrollment dialog; credentials never enter app configuration."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout

from jrvoiceapp.models import AccountConfig
from jrvoiceapp.provisioning import (
    ProvisionedAccount,
    ProvisioningError,
    VoiceAdminClient,
    map_profile,
)


class ProvisioningDialog(QDialog):
    def __init__(
        self, account: AccountConfig, username: str = "", password: str = "", parent=None
    ) -> None:
        super().__init__(parent)
        self.account = account
        self.provisioned: ProvisionedAccount | None = None
        self.setWindowTitle("Provision from VoiceAdmin")
        layout = QVBoxLayout(self)
        note = QLabel(
            "Downloads a VoiceAdmin profile using HTTPS when available. Credentials are saved only in the system keychain."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.server_input = QLineEdit(account.provisioning_server)
        self.username_input = QLineEdit(username)
        self.password_input = QLineEdit(password)
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Provisioning server", self.server_input)
        form.addRow("Provisioning username", self.username_input)
        form.addRow("Provisioning password", self.password_input)
        layout.addLayout(form)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #cc7777")
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self._download)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _download(self) -> None:
        try:
            candidate = AccountConfig(
                **{**self.account.__dict__, "provisioning_server": self.server_input.text().strip()}
            )
            client = VoiceAdminClient(
                candidate.provisioning_server,
                self.username_input.text(),
                self.password_input.text(),
            )
            self.provisioned = map_profile(client.fetch(), candidate)
        except ProvisioningError as error:
            self.error_label.setText(str(error))
            return
        self.accept()
