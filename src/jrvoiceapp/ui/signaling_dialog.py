"""Editable, non-secret SIP/WebRTC signaling templates per account."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from jrvoiceapp.models import SignalingTemplates


class SignalingDialog(QDialog):
    """Edit message templates without letting credentials enter the config file."""

    def __init__(self, templates: SignalingTemplates, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Signaling templates and custom headers")
        self.resize(760, 720)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Leave a template blank to use the engine default. Templates are saved with the "
            "account and applied on the next call. Define variables as `name = value`; use "
            "`{name}` in a template, or `{custom_headers}` to insert every defined header line. "
            "Never place passwords, tokens, or CR/LF text here."
        )
        intro.setWordWrap(True)
        intro.setObjectName("subtle")
        layout.addWidget(intro)
        form = QFormLayout()
        self.sip_invite = self._editor(templates.sip_invite)
        self.sip_ok = self._editor(templates.sip_ok)
        self.webrtc_invite = self._editor(templates.webrtc_invite)
        self.webrtc_ok = self._editor(templates.webrtc_ok)
        self.variables = self._editor(
            "\n".join(f"{name} = {value}" for name, value in templates.header_variables.items())
        )
        form.addRow("SIP INVITE template", self.sip_invite)
        form.addRow("SIP 200 OK template", self.sip_ok)
        form.addRow("WebRTC INVITE template", self.webrtc_invite)
        form.addRow("WebRTC 200 OK template", self.webrtc_ok)
        form.addRow("Header variables", self.variables)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _editor(value: str) -> QPlainTextEdit:
        editor = QPlainTextEdit(value)
        editor.setMinimumHeight(82)
        editor.setTabChangesFocus(True)
        return editor

    def result_templates(self) -> SignalingTemplates:
        variables: dict[str, str] = {}
        for line in self.variables.toPlainText().splitlines():
            if not line.strip():
                continue
            if "=" not in line:
                raise ValueError("Header variables use `name = value`, one per line.")
            name, value = line.split("=", 1)
            variables[name.strip()] = value.strip()
        return SignalingTemplates(
            sip_invite=self.sip_invite.toPlainText().strip(),
            sip_ok=self.sip_ok.toPlainText().strip(),
            webrtc_invite=self.webrtc_invite.toPlainText().strip(),
            webrtc_ok=self.webrtc_ok.toPlainText().strip(),
            header_variables=variables,
        )

    def _accept_if_valid(self) -> None:
        try:
            self.result_templates().validate()
        except ValueError as error:
            QMessageBox.warning(self, "Check signaling settings", str(error))
            return
        self.accept()
