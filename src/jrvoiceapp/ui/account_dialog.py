"""Account configuration dialog with clear transport and WebRTC engine choices."""

from __future__ import annotations

from uuid import uuid4

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from jrvoiceapp.models import (
    AccountConfig,
    ConnectionKind,
    EmergencyConfig,
    SignalingTemplates,
    UserEmergencySettings,
    WebRtcEngine,
)
from jrvoiceapp.ui.emergency_dialog import EmergencySettingsDialog
from jrvoiceapp.ui.signaling_dialog import SignalingDialog


class AccountDialog(QDialog):
    def __init__(
        self,
        account: AccountConfig | None = None,
        user_emergency_settings: UserEmergencySettings | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.account = account
        self.signaling = account.signaling if account else None
        self.emergency = account.emergency if account else EmergencyConfig()
        self.user_emergency_settings = user_emergency_settings or UserEmergencySettings()
        self.setWindowTitle("Add account" if account is None else "Edit account")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Passwords are stored in your operating system’s secure keychain, not in this app’s settings file."
        )
        intro.setWordWrap(True)
        intro.setObjectName("subtle")
        layout.addWidget(intro)
        form = QFormLayout()
        self.label_input = QLineEdit(account.label if account else "")
        self.username_input = QLineEdit(account.username if account else "")
        self.server_input = QLineEdit(account.server if account else "")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Leave empty to keep existing password")
        self.voicemail_input = QLineEdit(account.voicemail_number if account else "*97")
        self.kind_select = QComboBox()
        self.kind_select.addItems([kind.value for kind in ConnectionKind])
        self.engine_select = QComboBox()
        self.engine_select.addItems([engine.value for engine in WebRtcEngine])
        if account:
            self.kind_select.setCurrentText(account.connection_kind.value)
            self.engine_select.setCurrentText(account.web_rtc_engine.value)
        for title, control in (
            ("Account name", self.label_input),
            ("Extension / username", self.username_input),
            ("SIP server or WSS URL", self.server_input),
            ("Password", self.password_input),
            ("Connection", self.kind_select),
            ("WebRTC engine", self.engine_select),
            ("Voicemail number", self.voicemail_input),
        ):
            form.addRow(title, control)
        layout.addLayout(form)
        signaling_row = QHBoxLayout()
        signaling_row.addWidget(QLabel("Message and custom-header settings"))
        signaling_button = QPushButton("Edit signaling templates…")
        signaling_button.clicked.connect(self.open_signaling_dialog)
        signaling_row.addWidget(signaling_button)
        signaling_row.addStretch()
        layout.addLayout(signaling_row)
        emergency_button = QPushButton("Emergency dialing and location…")
        emergency_button.clicked.connect(self.open_emergency_dialog)
        layout.addWidget(emergency_button)
        self.engine_select.setToolTip(
            "SIP.js is recommended. JsSIP is an alternate engine. aiortc is experimental."
        )
        self.kind_select.currentTextChanged.connect(self._sync_engine_availability)
        self._sync_engine_availability()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _sync_engine_availability(self) -> None:
        self.engine_select.setEnabled(self.kind_select.currentText() == ConnectionKind.WEBRTC.value)

    def _accept_if_valid(self) -> None:
        try:
            self.result_account().validate()
        except ValueError as error:
            QMessageBox.warning(self, "Check account settings", str(error))
            return
        self.accept()

    def result_account(self) -> AccountConfig:
        return AccountConfig(
            identifier=self.account.identifier if self.account else str(uuid4()),
            label=self.label_input.text().strip(),
            username=self.username_input.text().strip(),
            server=self.server_input.text().strip(),
            connection_kind=ConnectionKind(self.kind_select.currentText()),
            web_rtc_engine=WebRtcEngine(self.engine_select.currentText()),
            voicemail_number=self.voicemail_input.text().strip() or "*97",
            signaling=self.signaling or SignalingTemplates(),
            emergency=self.emergency,
        )

    def open_signaling_dialog(self) -> None:
        dialog = SignalingDialog(self.signaling or SignalingTemplates(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.signaling = dialog.result_templates()

    def open_emergency_dialog(self) -> None:
        dialog = EmergencySettingsDialog(self.emergency, self.user_emergency_settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.emergency, self.user_emergency_settings = dialog.result_values()
