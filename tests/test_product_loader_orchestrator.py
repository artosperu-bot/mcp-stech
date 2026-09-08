from __future__ import annotations

from stech_mcp.services.product_loader_orchestrator import ProductLoaderOrchestrator


class FakeRepository:
    def __init__(self, rows):
        self.rows = rows
        self.items = {
            index + 100: {
                "item_id": index + 100,
                "product_loader_job_item_id": index + 100,
                "product_loader_job_id": 1,
                "row_number": row["row_number"],
                "partnumber": row["partnumber"],
                "input": dict(row),
                "status": "PENDING",
                "product_id_vtex": None,
                "sku_id_vtex": None,
            }
            for index, row in enumerate(rows)
        }
        self.job_status = "PENDING"
        self.transitions = []
        self.events = []

    def create_job(self, *, source_name, rows, actor_source, channel):
        return {
            "job_id": 1,
            "status": "PENDING",
            "items": [dict(item) for item in self.items.values()],
            "source_name": source_name,
            "channel": channel,
            "actor_source": actor_source,
        }

    def get_item(self, item_id):
        return dict(self.items[int(item_id)])

    def claim_item(self, item_id, expected_states):
        return self.items[int(item_id)]["status"] in set(expected_states)

    def update_item(self, item_id, **changes):
        item = self.items[int(item_id)]
        item.update({key: value for key, value in changes.items() if key in {
            "status", "current_step", "product_id_vtex", "sku_id_vtex",
            "product_ref_id_vtex", "sku_ref_id_vtex", "last_error_code", "last_error_detail"
        } and value is not None})
        item["status"] = changes["status"]
        self.transitions.append((item["partnumber"], changes["status"]))
        return dict(item)

    def append_event(self, **kwargs):
        self.events.append(dict(kwargs))

    def refresh_job_summary(self, job_id):
        states = [item["status"] for item in self.items.values()]
        return {
            "total_items": len(states),
            "completed_items": states.count("COMPLETED"),
            "review_items": states.count("RESEARCH_REQUIRED") + states.count("REVIEW_REQUIRED"),
            "blocked_items": states.count("BLOCKED"),
            "failed_items": states.count("FAILED"),
        }

    def set_job_status(self, job_id, status):
        self.job_status = status

    def get_job(self, job_id):
        return {
            "job_id": 1,
            "status": self.job_status,
            "items": [dict(item) for item in self.items.values()],
        }

    def reset_item_for_retry(self, item_id):
        self.items[int(item_id)]["status"] = "PENDING"
        return dict(self.items[int(item_id)])

    def list_resumable_items(self):
        return [dict(item) for item in self.items.values() if item["status"] == "PENDING"]


class FakePrepare:
    def __init__(self, fail_for=None):
        self.fail_for = set(fail_for or [])
        self.calls = []

    def prepare(self, partnumber, category="LAPTOP"):
        self.calls.append(partnumber)
        if partnumber in self.fail_for:
            raise RuntimeError("prepare boom")
        return {
            "found": True,
            "partnumber": partnumber,
            "product_master": {
                "partnumber": partnumber,
                "product_name": f"Producto {partnumber}",
                "package_height_cm": 7,
                "package_length_cm": 49,
                "package_width_cm": 31,
                "package_weight_g": 2400,
            },
        }


class FakeLocalImages:
    def __init__(self, states=None):
        self.states = states or {}
        self.calls = []

    def sync(self, partnumber):
        self.calls.append(partnumber)
        state = self.states.get(partnumber, "READY")
        return {"found": True, "partnumber": partnumber, "state": state, "reason": None if state == "READY" else "no_local_images", "image_count": 4 if state == "READY" else 0}


class FakeEnsure:
    def __init__(self, statuses=None):
        self.statuses = statuses or {}
        self.calls = []

    def ensure(self, partnumber, master, *, category_id, brand_id):
        self.calls.append((partnumber, category_id, brand_id))
        status = self.statuses.get(partnumber, "EXISTS")
        if status == "REVIEW_REQUIRED":
            return {"status": status, "blocking_reasons": ["VTEX_CATEGORY_ID_REQUIRED"], "read_back_verified": False}
        return {
            "status": status,
            "product_created": status == "CREATED",
            "sku_created": status == "CREATED",
            "product_id": 400,
            "sku_id": 500,
            "product_ref_id": partnumber,
            "sku_ref_id": f"{partnumber}-S",
            "read_back_verified": True,
        }


class FakeImageSync:
    def __init__(self, states=None):
        self.states = states or {}
        self.calls = []

    def sync(self, partnumber, *, account_code="VTEX_STECH"):
        self.calls.append((partnumber, account_code))
        state = self.states.get(partnumber, "SYNCED")
        return {"found": True, "partnumber": partnumber, "state": state, "reason": None if state == "SYNCED" else "image_sync_failed", "write_blocked": state != "SYNCED"}


def _rows():
    return [
        {"row_number": 2, "partnumber": "82YU00XYLM", "vtex_category_id": 65, "vtex_brand_id": 27},
        {"row_number": 3, "partnumber": "83GW005FLD", "vtex_category_id": 65, "vtex_brand_id": 27},
    ]


def test_run_inline_completes_each_item_in_required_order():
    repo = FakeRepository(_rows())
    orch = ProductLoaderOrchestrator(
        repository=repo,
        prepare_service=FakePrepare(),
        local_image_sync_service=FakeLocalImages(),
        vtex_ensure_service=FakeEnsure(),
        vtex_image_sync_service=FakeImageSync(),
    )

    result = orch.start(_rows(), "carga.xlsx", background=False)

    assert result["status"] == "COMPLETED"
    for pn in ("82YU00XYLM", "83GW005FLD"):
        states = [state for item_pn, state in repo.transitions if item_pn == pn]
        assert states == [
            "VALIDATING", "PREPARING", "IMAGES_LOCAL", "VTEX_CHECK",
            "VTEX_IMAGES", "VERIFYING", "COMPLETED",
        ]


def test_missing_images_is_research_required_and_does_not_touch_vtex():
    rows = [_rows()[0]]
    repo = FakeRepository(rows)
    ensure = FakeEnsure()
    image_sync = FakeImageSync()
    orch = ProductLoaderOrchestrator(
        repository=repo,
        prepare_service=FakePrepare(),
        local_image_sync_service=FakeLocalImages({"82YU00XYLM": "NO_IMAGES"}),
        vtex_ensure_service=ensure,
        vtex_image_sync_service=image_sync,
    )

    result = orch.start(rows, "carga.xlsx", background=False)

    assert result["status"] == "WAITING_REVIEW"
    assert result["items"][0]["status"] == "RESEARCH_REQUIRED"
    assert ensure.calls == []
    assert image_sync.calls == []


def test_missing_vtex_ids_for_new_product_is_review_required_before_image_write():
    rows = [{"row_number": 2, "partnumber": "NEW-001"}]
    repo = FakeRepository(rows)
    image_sync = FakeImageSync()
    orch = ProductLoaderOrchestrator(
        repository=repo,
        prepare_service=FakePrepare(),
        local_image_sync_service=FakeLocalImages(),
        vtex_ensure_service=FakeEnsure({"NEW-001": "REVIEW_REQUIRED"}),
        vtex_image_sync_service=image_sync,
    )

    result = orch.start(rows, "carga.xlsx", background=False)

    assert result["status"] == "WAITING_REVIEW"
    assert result["items"][0]["status"] == "REVIEW_REQUIRED"
    assert image_sync.calls == []


def test_one_failed_item_does_not_stop_following_items():
    repo = FakeRepository(_rows())
    orch = ProductLoaderOrchestrator(
        repository=repo,
        prepare_service=FakePrepare(fail_for={"82YU00XYLM"}),
        local_image_sync_service=FakeLocalImages(),
        vtex_ensure_service=FakeEnsure(),
        vtex_image_sync_service=FakeImageSync(),
    )

    result = orch.start(_rows(), "carga.xlsx", background=False)

    states = {item["partnumber"]: item["status"] for item in result["items"]}
    assert states == {"82YU00XYLM": "FAILED", "83GW005FLD": "COMPLETED"}
    assert result["status"] == "PARTIAL"
