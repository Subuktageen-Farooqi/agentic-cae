"""Durable, fail-closed quota guard for the single opt-in live smoke run.

The ledger contains counts, role names, status and numeric usage only. Reserve
before transport, including uncertain outcomes; never retry or reset a ledger.
"""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3

from providers.vertex import ProviderUnavailable


ROLES = ("advisor", "design_specification", "cad_code", "analysis_specification", "report_explanation")


def safe_usage(provider):
    usage = getattr(provider, "last_usage", None)
    safe = {k: v for k, v in (usage or {}).items() if k in (
        "prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count")
        and (v is None or type(v) is int)}
    code = getattr(provider, "last_http_status", None)
    if type(code) is int and 400 <= code <= 599:
        safe["http_status_code"] = code
    return safe


class LiveBudget:
    def __init__(self, path):
        self.path = Path(path)

    @classmethod
    def create(cls, path, *, max_requests=5):
        if not 1 <= max_requests <= 5:
            raise ValueError("Live request allowance must be between one and five")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents a second run from resetting the allowance.
        with path.open("xb"):
            pass
        budget = cls(path)
        with budget.connection() as db:
            db.execute("CREATE TABLE requests (number INTEGER PRIMARY KEY, role TEXT, status TEXT, usage TEXT)")
            db.execute("CREATE TABLE gate (stopped INTEGER NOT NULL, maximum INTEGER NOT NULL)")
            db.execute("INSERT INTO gate VALUES (?,?)", (0, max_requests))
        return budget

    @contextmanager
    def connection(self):
        if not self.path.is_file():
            raise ProviderUnavailable("Live budget ledger is missing; explicit initialization is required")
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            yield db

    def stop(self):
        with self.connection() as db:
            db.execute("UPDATE gate SET stopped=1")

    def snapshot(self):
        with self.connection() as db:
            rows = db.execute("SELECT number,role,status,usage FROM requests ORDER BY number").fetchall()
            gate = db.execute("SELECT * FROM gate").fetchone()
            # The first run's existing ledger has a one-column gate. Read it
            # unchanged; a recovery allowance gets its own separate ledger.
            return {"maximum": gate[1] if len(gate) > 1 else 5,
                    "count": len(rows), "stopped": bool(gate[0]),
                    "requests": [{"number": n, "role": r, "status": s, "usage": json.loads(u) if u else None} for n,r,s,u in rows]}

    def wrap(self, provider):
        budget = self
        class GuardedProvider:
            def availability_issues(self):
                return provider.availability_issues()

            def generate(self, **kwargs):
                with budget.connection() as db:
                    rows = db.execute("SELECT status FROM requests ORDER BY number").fetchall()
                    gate = db.execute("SELECT * FROM gate").fetchone()
                    maximum = gate[1] if len(gate) > 1 else 5
                    if gate[0] or len(rows) >= maximum or any(r[0] != "returned" for r in rows):
                        raise ProviderUnavailable("Live request budget stopped, exhausted or has an uncertain outcome; no request sent")
                    number = len(rows) + 1
                    db.execute("INSERT INTO requests VALUES (?,?,?,NULL)", (number, ROLES[number-1], "reserved"))
                try:
                    response = provider.generate(**kwargs)
                except BaseException:
                    with budget.connection() as db:
                        db.execute("UPDATE requests SET status='failed',usage=? WHERE number=?", (json.dumps(safe_usage(provider)),number))
                        db.execute("UPDATE gate SET stopped=1")
                    raise ProviderUnavailable("Live request failed; budget is stopped. Diagnose offline before requesting another allowance.") from None
                # No arbitrary provider values can enter the secret-free ledger.
                safe = safe_usage(provider)
                with budget.connection() as db:
                    db.execute("UPDATE requests SET status='returned',usage=? WHERE number=?", (json.dumps(safe),number))
                return response
        return GuardedProvider()
