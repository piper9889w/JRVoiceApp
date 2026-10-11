"""Actionable desktop call alert used by the tray and future protocol providers."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class IncomingCallDialog(QDialog):
    answer_requested = Signal()
    ignore_requested = Signal()
    voicemail_requested = Signal()

    def __init__(self, caller_name: str, caller_number: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Incoming call")
        self.setModal(False)
        layout = QVBoxLayout(self)
        for label, name in (
            (QLabel("Incoming call"), "online"),
            (QLabel(caller_name), "heading"),
            (QLabel(caller_number), "subtle"),
        ):
            label.setObjectName(name)
            layout.addWidget(label)
        actions = QHBoxLayout()
        for label, signal in (
            ("Answer", self.answer_requested),
            ("Ignore", self.ignore_requested),
            ("Send to voicemail", self.voicemail_requested),
        ):
            button = QPushButton(label)
            button.clicked.connect(signal.emit)
            button.clicked.connect(self.close)
            actions.addWidget(button)
        layout.addLayout(actions)
