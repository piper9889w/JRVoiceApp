"""Application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from jrvoiceapp.theme import APP_STYLE
from jrvoiceapp.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("JRVoiceApp")
    app.setOrganizationName("Global Voice")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
