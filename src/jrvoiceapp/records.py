"""Non-secret local contacts and unified call history."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import QStandardPaths


@dataclass(frozen=True)
class Contact:
    name: str
    address: str


@dataclass(frozen=True)
class CallRecord:
    address: str
    direction: str
    status: str
    occurred_at: str
    account_id: str


class RecordsStore:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            base = Path(
                QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
            )
            path = base / "call-records.json"
        self.path = path

    def load(self) -> tuple[list[Contact], list[CallRecord]]:
        if not self.path.exists():
            return [], []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return (
            [Contact(**item) for item in raw.get("contacts", [])],
            [CallRecord(**item) for item in raw.get("calls", [])],
        )

    def save(self, contacts: list[Contact], calls: list[CallRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "contacts": [asdict(item) for item in contacts],
                    "calls": [asdict(item) for item in calls],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def add_call(
        self, contacts: list[Contact], calls: list[CallRecord], record: CallRecord
    ) -> list[CallRecord]:
        updated = [record, *calls][:200]
        self.save(contacts, updated)
        return updated

    def update_latest(
        self, contacts: list[Contact], calls: list[CallRecord], account_id: str, status: str
    ) -> list[CallRecord]:
        for index, call in enumerate(calls):
            if call.account_id == account_id:
                calls = [*calls]
                calls[index] = CallRecord(
                    call.address, call.direction, status, call.occurred_at, account_id
                )
                self.save(contacts, calls)
                break
        return calls

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()
