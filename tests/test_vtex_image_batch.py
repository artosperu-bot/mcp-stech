from __future__ import annotations

from pathlib import Path

from stech_mcp.services.vtex_image_batch import VtexImageBatchService


class FakeLocalService:
    def __init__(self, rows):
        self.rows = rows
        self.sync_calls = []
        self.validate_calls = []

    def sync(self, partnumber: str):
        self.sync_calls.append(partnumber)
        return dict(self.rows[partnumber]["local"])

    def validate(self, partnumber: str):
        self.validate_calls.append(partnumber)
        return dict(self.rows[partnumber]["local"])


class FakeSyncService:
    def __init__(self, rows):
        self.rows = rows
        self.local_service = FakeLocalService(rows)
        self.status_calls = []
        self.sync_calls = []

    def status(self, partnumber: str, *, account_code: str = "VTEX_STECH"):
        self.status_calls.append((partnumber, account_code))
        return dict(self.rows[partnumber]["status"])

    def sync(self, partnumber: str, *, account_code: str = "VTEX_STECH"):
        self.sync_calls.append((partnumber, account_code))
        return dict(self.rows[partnumber]["sync"])


def _local(partnumber: str, count: int = 2, state: str = "READY", reason=None):
    return {
        "found": True,
        "partnumber": partnumber,
        "state": state,
        "reason": reason,
        "image_count": count,
        "images": [
            {
                "product_image_id": position,
                "partnumber": partnumber,
                "storage_path": str(Path(partnumber) / f"{partnumber}_{position:02d}.jpg"),
                "position": position,
                "is_main": position == 1,
            }
            for position in range(1, count + 1)
        ],
    }


def _status(partnumber: str, state: str, remote_files=None, *, reason=None, write_blocked=False):
    remote_files = list(remote_files or [])
    return {
        "found": True,
        "partnumber": partnumber,
        "transport": "catalog_seller_portal",
        "local_state": "READY",
        "local_image_count": 2,
        "remote_image_count": len(remote_files),
        "remote_files": remote_files,
        "state": state,
        "reason": reason,
        "write_blocked": write_blocked,
    }


def test_discover_partnumbers_uses_exact_local_image_folders(tmp_path):
    good_b = tmp_path / "LENOVO" / "LAPTOP" / "B-PN"
    good_b.mkdir(parents=True)
    (good_b / "B-PN_01.jpg").write_bytes(b"1")
    (good_b / "B-PN_02.jpg").write_bytes(b"2")

    good_a = tmp_path / "EPSON" / "PROYECTOR" / "A-PN"
    good_a.mkdir(parents=True)
    (good_a / "A-PN_03.png").write_bytes(b"3")

    bad = tmp_path / "LENOVO" / "LAPTOP" / "WRONG"
    bad.mkdir(parents=True)
    (bad / "OTHER_01.jpg").write_bytes(b"x")
    (bad / "notes.txt").write_text("ignore", encoding="utf-8")

    service = VtexImageBatchService(root=tmp_path, sync_service=object())

    assert service.discover_partnumbers() == ["A-PN", "B-PN"]


def test_missing_list_returns_only_unsynced_and_marks_actionable(tmp_path):
    for partnumber in ("A-PN", "B-PN", "C-PN"):
        folder = tmp_path / partnumber
        folder.mkdir()
        (folder / f"{partnumber}_01.jpg").write_bytes(b"1")

    rows = {
        "A-PN": {
            "local": _local("A-PN"),
            "status": _status(
                "A-PN",
                "SYNCED",
                [
                    {"name": "A-PN_01.jpg", "is_main": True},
                    {"name": "A-PN_02.jpg", "is_main": False},
                ],
            ),
            "sync": {"state": "SYNCED"},
        },
        "B-PN": {
            "local": _local("B-PN"),
            "status": _status("B-PN", "READY", [{"name": "B-PN_01.jpg", "is_main": True}]),
            "sync": {"state": "SYNCED"},
        },
        "C-PN": {
            "local": _local("C-PN", state="REVIEW", reason="main_image_01_missing"),
            "status": {
                **_status("C-PN", "REVIEW", []),
                "local_state": "REVIEW",
                "reason": "main_image_01_missing",
                "write_blocked": False,
            },
            "sync": {"state": "REVIEW", "reason": "main_image_01_missing"},
        },
    }
    sync_service = FakeSyncService(rows)
    service = VtexImageBatchService(root=tmp_path, sync_service=sync_service)

    result = service.missing_list(limit=10, include_blocked=True)

    assert [row["partnumber"] for row in result["items"]] == ["B-PN", "C-PN"]
    assert result["items"][0]["actionable"] is True
    assert result["items"][0]["pending_files"] == ["B-PN_02.jpg"]
    assert result["items"][1]["actionable"] is False
    assert result["items"][1]["reason"] == "main_image_01_missing"
    assert sync_service.local_service.sync_calls == ["A-PN", "B-PN", "C-PN"]


def test_missing_list_paginates_by_partnumber_cursor(tmp_path):
    rows = {}
    for partnumber in ("A-PN", "B-PN", "C-PN"):
        folder = tmp_path / partnumber
        folder.mkdir()
        (folder / f"{partnumber}_01.jpg").write_bytes(b"1")
        rows[partnumber] = {
            "local": _local(partnumber),
            "status": _status(partnumber, "READY", []),
            "sync": {"state": "SYNCED"},
        }
    service = VtexImageBatchService(root=tmp_path, sync_service=FakeSyncService(rows))

    first = service.missing_list(limit=2)
    second = service.missing_list(after_partnumber=first["next_after_partnumber"], limit=2)

    assert [row["partnumber"] for row in first["items"]] == ["A-PN", "B-PN"]
    assert first["has_more"] is True
    assert first["next_after_partnumber"] == "B-PN"
    assert [row["partnumber"] for row in second["items"]] == ["C-PN"]
    assert second["has_more"] is False


def test_sync_batch_auto_processes_only_actionable_pending_and_continues_after_error(tmp_path):
    rows = {}
    states = {
        "A-PN": ("SYNCED", False),
        "B-PN": ("READY", False),
        "C-PN": ("READY", False),
        "D-PN": ("BLOCKED", True),
    }
    for partnumber, (state, blocked) in states.items():
        folder = tmp_path / partnumber
        folder.mkdir()
        (folder / f"{partnumber}_01.jpg").write_bytes(b"1")
        rows[partnumber] = {
            "local": _local(partnumber),
            "status": _status(partnumber, state, [], write_blocked=blocked),
            "sync": {
                "found": True,
                "partnumber": partnumber,
                "state": "ERROR" if partnumber == "B-PN" else "SYNCED",
                "reason": "forced_error" if partnumber == "B-PN" else None,
                "uploaded_count": 0 if partnumber == "B-PN" else 2,
                "verified_count": 0 if partnumber == "B-PN" else 2,
                "errors": [{"error": "forced"}] if partnumber == "B-PN" else [],
            },
        }
    sync_service = FakeSyncService(rows)
    service = VtexImageBatchService(root=tmp_path, sync_service=sync_service)

    result = service.sync_batch(limit=10, stop_on_error=False)

    assert [row[0] for row in sync_service.sync_calls] == ["B-PN", "C-PN"]
    assert result["processed_count"] == 2
    assert result["synced_count"] == 1
    assert result["error_count"] == 1
    assert result["blocked_count"] == 1
    assert result["states"] == {"ERROR": 1, "SYNCED": 1}


def test_sync_batch_explicit_partnumbers_normalizes_and_deduplicates(tmp_path):
    rows = {
        "A-PN": {
            "local": _local("A-PN"),
            "status": _status("A-PN", "READY", []),
            "sync": {"found": True, "partnumber": "A-PN", "state": "SYNCED", "errors": []},
        },
        "B-PN": {
            "local": _local("B-PN"),
            "status": _status("B-PN", "READY", []),
            "sync": {"found": True, "partnumber": "B-PN", "state": "SYNCED", "errors": []},
        },
    }
    sync_service = FakeSyncService(rows)
    service = VtexImageBatchService(root=tmp_path, sync_service=sync_service)

    result = service.sync_batch(partnumbers=[" a-pn ", "A-PN", "b-pn"], limit=10)

    assert [row[0] for row in sync_service.sync_calls] == ["A-PN", "B-PN"]
    assert result["processed_count"] == 2
    assert result["synced_count"] == 2

def test_server_exposes_batch_tools():
    source = (Path(__file__).resolve().parents[1] / "src" / "stech_mcp" / "server.py").read_text(
        encoding="utf-8"
    )

    assert "def vtex_images_missing_list(" in source
    assert "def vtex_images_sync_batch(" in source
