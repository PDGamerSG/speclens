"""T0: verify the key, list models, and read rate-limit headers (never prints the key)."""
import json, os, time
from pathlib import Path
import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
BASE = os.environ.get("MODEL_API_BASE_URL", "https://api.meta.ai/v1")
H = {"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}"}

r = httpx.get(f"{BASE}/models", headers=H, timeout=30)
print("GET /models ->", r.status_code)
rl = {k: v for k, v in r.headers.items() if "ratelimit" in k.lower() or "retry" in k.lower()}
print("rate-limit headers:", json.dumps(rl, indent=1))
if r.status_code == 200:
    ids = sorted(m.get("id") for m in r.json().get("data", []))
    print("models:", ids)

t = time.time()
r2 = httpx.post(f"{BASE}/chat/completions", headers=H, timeout=60, json={
    "model": "muse-spark-1.3", "max_tokens": 4000, "reasoning_effort": "low",
    "messages": [{"role": "user", "content": "Reply with exactly: ok"}]})
print("spark ping ->", r2.status_code, f"{time.time()-t:.1f}s")
if r2.status_code == 200:
    j = r2.json()
    print("reply:", j["choices"][0]["message"]["content"][:80], "| usage:", j.get("usage"))
    print("spark rate-limit headers:", {k: v for k, v in r2.headers.items() if "ratelimit" in k.lower()})
else:
    print(r2.text[:500])
