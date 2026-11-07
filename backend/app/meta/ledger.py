"""Append-only cost ledger for every Meta Model API call, with a hard budget guard and a per-run event hook."""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from typing import Callable

from ..config import BUDGET_USD, PRICE, VAR

LEDGER = VAR / "ledger.jsonl"
_lock = threading.Lock()
_spent = 0.0
_listeners: list[Callable[[dict], None]] = []


class BudgetExceeded(RuntimeError):
    pass


def _rows() -> list[dict]:
    """All readable records. The eval and the server can append at once, so a line can arrive torn; skip it."""
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict) and "model" in r:
            rows.append(r)
    return rows


def _load() -> None:
    global _spent
    _spent += sum(r.get("cost_usd", 0.0) for r in _rows())


_load()


def on_call(fn: Callable[[dict], None]) -> None:
    _listeners.append(fn)


def spent() -> float:
    return round(_spent, 4)


def check_budget(expected: float = 0.0) -> None:
    if _spent + expected > BUDGET_USD:
        raise BudgetExceeded(f"Meta API budget guard: spent ${_spent:.2f} of ${BUDGET_USD:.2f}")


def spark_cost(model: str, prompt_tokens: int, completion_tokens: int, cached: int) -> float:
    p = PRICE.get(model, PRICE["muse-spark-1.3"])
    return (prompt_tokens - cached) * p["in"] + cached * p["cached"] + completion_tokens * p["out"]


def cache_stats() -> dict:
    """Input tokens served from the Model API prefix cache, and what that saved against the full input price."""
    prompt = cached = 0
    saved = 0.0
    for r in _rows():
        tokens = r.get("prompt_tokens") or 0
        if not tokens:
            continue
        reused = r.get("cached_tokens") or 0
        price = PRICE.get(r["model"], PRICE["muse-spark-1.3"])
        prompt += tokens
        cached += reused
        saved += reused * (price["in"] - price["cached"])
    return {"prompt_tokens": prompt, "cached_tokens": cached, "hit_rate": round(cached / prompt, 4) if prompt else 0.0,
            "saved_usd": round(saved, 6)}


def record(model: str, op: str, ms: float, status, cost_usd: float, run_id: str | None = None, **extra) -> dict:
    global _spent
    rec = {"t": round(time.time(), 3), "model": model, "op": op, "ms": round(ms), "status": status,
           "cost_usd": round(cost_usd, 6), "run_id": run_id, **extra}
    with _lock:
        _spent += cost_usd
        fd = os.open(LEDGER, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)   # one write per record
        try:
            os.write(fd, (json.dumps(rec) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    for fn in _listeners:
        try:
            fn(rec)
        except Exception:
            pass
    return rec


def recent(limit: int = 200) -> list[dict]:
    return _rows()[-limit:]


def run_cost(run_id: str) -> float:
    return sum(r.get("cost_usd", 0.0) for r in _rows() if r.get("run_id") == run_id)


def by_model() -> dict:
    agg: dict = defaultdict(lambda: {"calls": 0, "cost_usd": 0.0})
    for r in _rows():
        agg[r["model"]]["calls"] += 1
        agg[r["model"]]["cost_usd"] = round(agg[r["model"]]["cost_usd"] + r.get("cost_usd", 0), 4)
    return dict(agg)
