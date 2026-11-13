"""Spend ledger and budget guard for every Meta Model API call, shared by every API and worker process.

Each call reserves its expected cost first with one conditional UPDATE, so parallel calls cannot spend past
BUDGET_USD between a check and a record. The actual cost is recorded after the call and the reservation released.
Calls go to the model_calls table; a one-row budget table keeps running totals so status reads stay cheap.
The JSONL ledger of earlier releases is imported once.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

import sqlalchemy as sa

from .. import db
from ..config import BUDGET_USD, PRICE, VAR

LEDGER = VAR / "ledger.jsonl"   # legacy file, imported once
TARGET: str | Path | None = None   # database override for tests; None means DATABASE_URL or the local SQLite file
_listeners: list[Callable[[dict], None]] = []
_imported: set[str] = set()
_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    pass


def _engine() -> sa.Engine:
    engine = db.engine(TARGET)
    key = f'{engine.url}|{LEDGER}'
    if key not in _imported:
        with _lock:
            if key not in _imported:
                _import_legacy(engine)
                _imported.add(key)
    return engine


def _legacy_rows(path: Path) -> list[dict]:
    """Readable records only. The eval and the server could append at once, so a line can be torn; skip it."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and "model" in row:
            rows.append(row)
    return rows


def _import_legacy(engine: sa.Engine) -> None:
    budget = db.budget
    with engine.begin() as c:
        query = sa.select(budget.c.imported_ledger).where(budget.c.id == 1)
        if c.dialect.name == 'postgresql':
            query = query.with_for_update()
        if c.execute(query).scalar():
            return
        rows = _legacy_rows(LEDGER)
        if rows:
            c.execute(db.model_calls.insert(), [_row(r) for r in rows])
        c.execute(budget.update().where(budget.c.id == 1).values(imported_ledger=True, **_totals(rows, budget)))


def _row(r: dict) -> dict:
    known = {"t", "model", "op", "ms", "status", "cost_usd", "run_id", "prompt_tokens", "cached_tokens", "completion_tokens"}
    return {"t": float(r.get("t") or time.time()), "model": str(r["model"])[:48], "op": str(r.get("op", ""))[:48],
            "ms": int(r.get("ms") or 0), "status": str(r.get("status", ""))[:24], "cost_usd": float(r.get("cost_usd") or 0),
            "run_id": r.get("run_id"), "prompt_tokens": r.get("prompt_tokens"), "cached_tokens": r.get("cached_tokens"),
            "completion_tokens": r.get("completion_tokens"), "extra": {k: v for k, v in r.items() if k not in known} or None}


def _saving(r: dict) -> float:
    price = PRICE.get(r["model"], PRICE["muse-spark-1.3"])
    reused = r.get("cached_tokens") or 0
    return reused * (price.get("in", 0) - price.get("cached", 0)) if r.get("prompt_tokens") else 0.0


def _totals(rows: list[dict], budget: sa.Table) -> dict:
    """Column increments for a set of calls."""
    return {"spent_usd": budget.c.spent_usd + sum(float(r.get("cost_usd") or 0) for r in rows),
            "prompt_tokens": budget.c.prompt_tokens + sum(int(r.get("prompt_tokens") or 0) for r in rows),
            "cached_tokens": budget.c.cached_tokens + sum(int(r.get("cached_tokens") or 0) for r in rows if r.get("prompt_tokens")),
            "saved_usd": budget.c.saved_usd + sum(_saving(r) for r in rows)}


def on_call(fn: Callable[[dict], None]) -> None:
    _listeners.append(fn)


def _budget_row() -> sa.Row:
    with _engine().connect() as c:
        return c.execute(sa.select(db.budget).where(db.budget.c.id == 1)).one()


def spent() -> float:
    return round(_budget_row().spent_usd, 4)


def reserved() -> float:
    return round(_budget_row().reserved_usd, 6)


@contextmanager
def reserve(amount: float):
    """Hold `amount` of the budget for one call. Raises BudgetExceeded if the hold would pass BUDGET_USD."""
    budget = db.budget
    engine = _engine()
    with engine.begin() as c:
        held = c.execute(budget.update().where(
            budget.c.id == 1, budget.c.spent_usd + budget.c.reserved_usd + amount <= BUDGET_USD,
        ).values(reserved_usd=budget.c.reserved_usd + amount))
    if held.rowcount != 1:
        raise BudgetExceeded(f"Meta API budget guard: spent ${spent():.2f} of ${BUDGET_USD:.2f}")
    try:
        yield
    finally:
        with engine.begin() as c:
            left = budget.c.reserved_usd - amount
            c.execute(budget.update().where(budget.c.id == 1).values(
                reserved_usd=sa.case((left < 0, 0.0), else_=left)))


def check_budget(expected: float = 0.0) -> None:
    """A check without a hold, for callers that only need to refuse work up front."""
    row = _budget_row()
    if row.spent_usd + row.reserved_usd + expected > BUDGET_USD:
        raise BudgetExceeded(f"Meta API budget guard: spent ${row.spent_usd:.2f} of ${BUDGET_USD:.2f}")


def spark_cost(model: str, prompt_tokens: int, completion_tokens: int, cached: int) -> float:
    p = PRICE.get(model, PRICE["muse-spark-1.3"])
    return (prompt_tokens - cached) * p["in"] + cached * p["cached"] + completion_tokens * p["out"]


def spark_estimate(model: str, max_tokens: int, prompt_tokens: int = 8000) -> float:
    """An upper bound for a reservation: every prompt token uncached and the full output budget used."""
    p = PRICE.get(model, PRICE["muse-spark-1.3"])
    return prompt_tokens * p["in"] + max_tokens * p["out"]


def cache_stats() -> dict:
    """Input tokens served from the Model API prefix cache, and what that saved against the full input price."""
    row = _budget_row()
    return {"prompt_tokens": int(row.prompt_tokens), "cached_tokens": int(row.cached_tokens),
            "hit_rate": round(row.cached_tokens / row.prompt_tokens, 4) if row.prompt_tokens else 0.0,
            "saved_usd": round(row.saved_usd, 6)}


def record(model: str, op: str, ms: float, status, cost_usd: float, run_id: str | None = None, **extra) -> dict:
    rec = {"t": round(time.time(), 3), "model": model, "op": op, "ms": round(ms), "status": status,
           "cost_usd": round(cost_usd, 6), "run_id": run_id, **extra}
    with _engine().begin() as c:
        c.execute(db.model_calls.insert().values(**_row(rec)))
        c.execute(db.budget.update().where(db.budget.c.id == 1).values(**_totals([rec], db.budget)))
    for fn in _listeners:
        try:
            fn(rec)
        except Exception:
            pass
    return rec


def _as_dict(row: sa.Row) -> dict:
    data = {k: v for k, v in row._mapping.items() if k not in ("id", "extra") and v is not None}
    return {**data, **(row.extra or {})}


def recent(limit: int = 200) -> list[dict]:
    calls = db.model_calls
    with _engine().connect() as c:
        rows = c.execute(sa.select(calls).order_by(calls.c.id.desc()).limit(limit)).all()
    return [_as_dict(r) for r in reversed(rows)]


def run_cost(run_id: str) -> float:
    calls = db.model_calls
    with _engine().connect() as c:
        return float(c.execute(sa.select(sa.func.coalesce(sa.func.sum(calls.c.cost_usd), 0.0))
                               .where(calls.c.run_id == run_id)).scalar_one())


def by_model() -> dict:
    calls = db.model_calls
    with _engine().connect() as c:
        rows = c.execute(sa.select(calls.c.model, sa.func.count(), sa.func.sum(calls.c.cost_usd))
                         .group_by(calls.c.model)).all()
    return {model: {"calls": count, "cost_usd": round(cost or 0, 4)} for model, count, cost in rows}


def daily(since: float) -> list[dict]:
    """Cost and cache use per UTC day since a timestamp, for the dashboard."""
    calls = db.model_calls
    engine = _engine()
    if engine.dialect.name == "postgresql":
        day = sa.func.to_char(sa.func.timezone("UTC", sa.func.to_timestamp(calls.c.t)), "YYYY-MM-DD")
    else:
        day = sa.func.strftime("%Y-%m-%d", calls.c.t, "unixepoch")
    query = (sa.select(day.label("day"), sa.func.count(), sa.func.sum(calls.c.cost_usd),
                       sa.func.sum(calls.c.prompt_tokens), sa.func.sum(calls.c.cached_tokens))
             .where(calls.c.t >= since).group_by(day).order_by(day))
    with engine.connect() as c:
        rows = c.execute(query).all()
    return [{"day": d, "calls": n, "cost_usd": round(cost or 0, 6), "prompt_tokens": int(prompt or 0),
             "cached_tokens": int(cached or 0)} for d, n, cost, prompt, cached in rows]
