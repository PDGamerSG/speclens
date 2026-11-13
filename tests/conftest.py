"""Tests run fully offline: demo mode, a temp var/ dir, and a fake Meta transport where a test needs one."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DEMO_MODE"] = "1"
os.environ["MODEL_API_KEY"] = ""
os.environ["SPECLENS_HOUSEKEEPING"] = "0"
os.environ.setdefault("SPECLENS_VAR", tempfile.mkdtemp(prefix="speclens-test-"))
sys.path.insert(0, str(ROOT / "backend"))
