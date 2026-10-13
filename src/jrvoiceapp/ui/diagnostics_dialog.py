"""Safe, periodically refreshed SIP provider diagnostics."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)


class DiagnosticsDialog(QDialog):
    def __init__(self, snapshot: Callable[[], dict[str, object]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Call diagnostics")
        self.resize(720, 620)
        self._snapshot = snapshot
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Passwords, SIP authorization data, and SDES keys are never displayed here."
        )
        notice.setObjectName("subtle")
        layout.addWidget(notice)
        form = QFormLayout()
        self.fields: dict[str, QLabel] = {}
        for key, label in (
            ("provider_state", "Provider state"),
            ("transport", "Signaling transport"),
            ("tls_verification", "TLS certificate verification"),
            ("local_signaling", "Local signaling"),
            ("signaling_destination", "Signaling destination"),
            ("codec", "Codec"),
            ("media_security", "Media security"),
            ("rtp_local", "Local RTP"),
            ("rtp_remote", "Remote RTP"),
            ("rtp_packets", "RTP packets"),
            ("rtp_packet_rate", "RTP packets per second"),
            ("jitter", "Jitter/loss"),
            ("nat", "NAT status"),
            ("audio_error", "Audio issue"),
            ("last_network_error", "Last network error"),
        ):
            value = QLabel("—")
            value.setWordWrap(True)
            self.fields[key] = value
            form.addRow(label, value)
        layout.addLayout(form)
        layout.addWidget(QLabel("Recent safe SIP events"))
        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        layout.addWidget(self.events)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def refresh(self) -> None:
        data = self._snapshot()
        for key, field in self.fields.items():
            field.setText(str(data.get(key) or "—"))
        self.events.setPlainText("\n".join(str(item) for item in data.get("events", [])))

    def closeEvent(self, event) -> None:
        self.timer.stop()
        super().closeEvent(event)
