"""Emergency dialing and PIDF-LO preference dialogs."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from jrvoiceapp.models import EmergencyConfig, UserEmergencySettings


class EmergencySettingsDialog(QDialog):
    """Edit account locations and the application's emergency dial strings."""

    def __init__(
        self, emergency: EmergencyConfig, user_settings: UserEmergencySettings, parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Emergency dialing and location")
        self.resize(620, 490)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Only enable this after confirming your provider supports PIDF-LO. Saved locations "
            "are shown for confirmation when the account registers. They are not passwords."
        )
        notice.setWordWrap(True)
        notice.setObjectName("subtle")
        layout.addWidget(notice)
        form = QFormLayout()
        self.enabled = QCheckBox("Provider supports PIDF-LO and emergency dialing")
        self.enabled.setChecked(emergency.enabled)
        self.digits = QLineEdit(user_settings.dial_strings)
        self.digits.setPlaceholderText("911, 112, 999")
        self.locations = QPlainTextEdit("\n".join(emergency.locations))
        self.locations.setPlaceholderText(
            "One complete address or location description per line (up to 5)"
        )
        self.locations.textChanged.connect(self._refresh_defaults)
        self.default = QComboBox()
        self._initial_default = emergency.default_location
        self._refresh_defaults()
        form.addRow("PIDF-LO support", self.enabled)
        form.addRow("Emergency dial strings", self.digits)
        form.addRow("Saved locations", self.locations)
        form.addRow("Default location", self.default)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _location_list(self) -> list[str]:
        return [line.strip() for line in self.locations.toPlainText().splitlines() if line.strip()]

    def _refresh_defaults(self) -> None:
        selected = self.default.currentText() if hasattr(self, "default") else self._initial_default
        if not hasattr(self, "default"):
            return
        self.default.clear()
        self.default.addItems(self._location_list())
        index = self.default.findText(selected)
        if index >= 0:
            self.default.setCurrentIndex(index)

    def result_values(self) -> tuple[EmergencyConfig, UserEmergencySettings]:
        emergency = EmergencyConfig(
            enabled=self.enabled.isChecked(),
            locations=self._location_list(),
            default_location=self.default.currentText(),
        )
        user = UserEmergencySettings(self.digits.text().strip())
        emergency.validate()
        user.validate()
        return emergency, user

    def _accept_if_valid(self) -> None:
        try:
            self.result_values()
        except ValueError as error:
            QMessageBox.warning(self, "Check emergency settings", str(error))
            return
        self.accept()


class EmergencyLocationDialog(QDialog):
    """Ask the user to verify or temporarily override the emergency location."""

    def __init__(self, emergency: EmergencyConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Verify emergency location")
        layout = QVBoxLayout(self)
        prompt = QLabel(
            "Before emergency dialing is available, confirm the current location. Select a saved "
            "location or enter a temporary one for this session."
        )
        prompt.setWordWrap(True)
        layout.addWidget(prompt)
        form = QFormLayout()
        self.location = QComboBox()
        self.location.setEditable(True)
        self.location.addItems(emergency.locations)
        if emergency.default_location:
            self.location.setCurrentText(emergency.default_location)
        form.addRow("Current location", self.location)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_location(self) -> str:
        return self.location.currentText().strip()
