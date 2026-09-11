from stech_mcp.worker import ProductWorkWorker


class Repo:
    def __init__(self):
        self.claim_args = None

    def claim_next(self, worker_id, lease_seconds, allowed_work_types=None):
        self.claim_args = (worker_id, lease_seconds, tuple(allowed_work_types or ()))
        return None

    def release_expired_claims(self):
        return 0


class Dispatcher:
    pass


def test_worker_passes_allowed_work_types_to_claim():
    repo = Repo()
    worker = ProductWorkWorker(
        repo,
        Dispatcher(),
        worker_id="img-1",
        allowed_work_types=("RESEARCH_IMAGES",),
    )
    assert worker.run_once() is False
    assert repo.claim_args[2] == ("RESEARCH_IMAGES",)


def test_unrestricted_worker_keeps_legacy_claim_signature():
    class LegacyRepo:
        def __init__(self): self.called = False
        def claim_next(self, worker_id, lease_seconds):
            self.called = True
            return None
    repo = LegacyRepo()
    worker = ProductWorkWorker(repo, Dispatcher(), worker_id="legacy")
    assert worker.run_once() is False
    assert repo.called is True
