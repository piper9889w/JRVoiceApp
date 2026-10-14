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
    # Handles menu exits and OS/application-level quit paths in addition to
    # the main window's close button.
    app.aboutToQuit.connect(window._shutdown)
    window.show()
    try:
        return app.exec()
    finally:
        window._shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
