"""Budget behavior with a local fake; no live API requests."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from providers.budget import LiveBudget, ROLES
from providers.vertex import ProviderUnavailable


class Double:
    last_usage = {"total_token_count": 7, "secret": "must-not-persist"}
    def generate(self, **kwargs): return "{}"


def test_five_total_across_instances_and_reopen_no_reset(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger = LiveBudget.create(path)
    for i in range(5):
        LiveBudget(path).wrap(Double()).generate(prompt="fixture")
    assert ledger.snapshot()["count"] == 5
    assert [r["role"] for r in ledger.snapshot()["requests"]] == list(ROLES)
    assert all(r["usage"] == {"total_token_count":7} for r in ledger.snapshot()["requests"])
    with pytest.raises(ProviderUnavailable): ledger.wrap(Double()).generate()
    with pytest.raises(FileExistsError): LiveBudget.create(path)


def test_failure_and_uncertain_outcomes_latch_budget(tmp_path):
    class Failure:
        def generate(self, **kwargs): raise RuntimeError("private SDK error")
    ledger = LiveBudget.create(tmp_path / "ledger.sqlite3")
    with pytest.raises(ProviderUnavailable, match="budget is stopped"):
        ledger.wrap(Failure()).generate()
    with pytest.raises(ProviderUnavailable): ledger.wrap(Double()).generate()
    assert ledger.snapshot()["count"] == 1 and ledger.snapshot()["stopped"]
    other = LiveBudget.create(tmp_path / "uncertain.sqlite3")
    with other.connection() as db:
        db.execute("INSERT INTO requests VALUES (1,'advisor','reserved',NULL)")
    with pytest.raises(ProviderUnavailable): other.wrap(Double()).generate()


def test_parallel_requests_cannot_exceed_maximum(tmp_path):
    ledger = LiveBudget.create(tmp_path / "ledger.sqlite3")
    def attempt(_):
        try: ledger.wrap(Double()).generate()
        except ProviderUnavailable: pass
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(attempt, range(12)))
    assert 1 <= ledger.snapshot()["count"] <= 5
