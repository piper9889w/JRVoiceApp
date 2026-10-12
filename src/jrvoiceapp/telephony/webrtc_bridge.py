"""Embedded SIP.js/JsSIP browser runtime host.

It emits only summary lifecycle events. WSS/TURN interoperability still needs
deployment testing; credentials are passed directly to the page and never put
in page titles, application events, or diagnostics.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from jrvoiceapp.telephony.webrtc import WebRtcBridgeConfig


def runtime_document() -> str:
    """Return an isolated runtime page that loads the selected maintained JS engine."""
    return """<!doctype html><meta charset=utf-8><script>
const emit = (event, details={}) => { document.title='jrvoice:'+btoa(JSON.stringify({event, details})); };
window.jrvoiceStart = async config => {
  const source = config.engine === 'JsSIP' ? 'https://cdn.jsdelivr.net/npm/jssip@3.10.1/lib/JsSIP.min.js' : 'https://cdn.jsdelivr.net/npm/sip.js@0.21.2/lib/index.js';
  const script = document.createElement('script'); script.src = source;
  script.onload = () => emit('runtime-loaded', {engine: config.engine});
  script.onerror = () => emit('runtime-error', {summary: 'Unable to load the selected WebRTC runtime.'});
  document.head.appendChild(script); emit('runtime-loading', {engine: config.engine});
};
</script>"""


class EmbeddedWebRtcBridge(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.view: QWebEngineView | None = None
        self._callback: Callable[[str, dict[str, str]], None] | None = None

    def start(
        self,
        config: WebRtcBridgeConfig,
        password: str,
        callback: Callable[[str, dict[str, str]], None],
    ) -> None:
        if QApplication.instance() is None:
            raise RuntimeError(
                "The embedded WebRTC bridge requires the desktop application event loop."
            )
        self._callback = callback
        self.view = QWebEngineView()
        self.view.setVisible(False)
        self.view.titleChanged.connect(self._on_title)
        payload = {
            "engine": config.engine.value,
            "username": config.username,
            "websocketUrl": config.websocket_url,
            "password": password,
        }
        encoded = json.dumps(payload).replace("</", "<\\/")
        self.view.loadFinished.connect(lambda ok: self._start_page(ok, encoded))
        self.view.setHtml(runtime_document())

    def _start_page(self, ok: bool, payload: str) -> None:
        if not ok or not self.view:
            self._emit("runtime-error", {"summary": "The embedded WebRTC page could not start."})
            return
        self.view.page().runJavaScript(f"window.jrvoiceStart({payload})")

    def _on_title(self, title: str) -> None:
        if not title.startswith("jrvoice:"):
            return
        try:
            message = json.loads(base64.b64decode(title.removeprefix("jrvoice:")).decode())
            self._emit(message["event"], {str(k): str(v) for k, v in message["details"].items()})
        except (KeyError, ValueError, UnicodeDecodeError):
            self._emit(
                "runtime-error", {"summary": "The embedded WebRTC runtime sent an invalid event."}
            )

    def _emit(self, event: str, details: dict[str, str]) -> None:
        if self._callback:
            self._callback(event, details)

    def stop(self) -> None:
        if self.view:
            self.view.deleteLater()
            self.view = None
