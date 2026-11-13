"""Deterministic core: compositor, severity ladder, curves, validators, COCO RLE, cost maths."""
import cv2
import numpy as np
import pytest

from app.export.coco import rle
from app.forge import severity as sev
from app.forge.composite import composite, dhash, hamming, iou
from app.forge.validators import accepted, run_validators
from app.meta.ledger import spark_cost


def textured(seed=0, size=256):
    rng = np.random.default_rng(seed)
    base = np.zeros((size, size, 3), np.float32)
    base[..., 0], base[..., 1], base[..., 2] = 150, 80, 40
    noise = cv2.GaussianBlur(rng.normal(0, 25, (size, size)).astype(np.float32), (0, 0), 3)
    stripes = 20 * np.sin(np.linspace(0, 12 * np.pi, size))[None, :]
    img = base + (noise + stripes)[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


def fake_edit(orig, shift=2, drift=4, radius=14):
    """Simulates Muse Image: upscaled, shifted a few px, slight global colour drift, a dark hole at the centre."""
    h, w = orig.shape[:2]
    ed = orig.astype(np.int16) + drift
    cv2.circle(ed, (w // 2, h // 2), radius, (20, 10, 5), -1)
    ed = np.clip(ed, 0, 255).astype(np.uint8)
    M = np.float32([[1, 0, shift], [0, 1, -shift]])
    ed = cv2.warpAffine(ed, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    return cv2.resize(ed, (int(w * 1.5625), int(h * 1.5625)), interpolation=cv2.INTER_CUBIC)


def test_composite_isolates_the_defect_and_keeps_everything_else_identical():
    orig = textured()
    out = composite(orig, fake_edit(orig))
    truth = np.zeros(orig.shape[:2], np.uint8)
    cv2.circle(truth, (128, 128), 14, 1, -1)
    assert out["identical_outside"]
    assert iou(out["mask"], truth > 0) > 0.6
    assert out["components"] >= 1
    assert out["shift_px"] < 8          # true shift is ~2.8 px; ECC also absorbs some of the edit
    outside = out["alpha"] == 0
    assert (out["composite"][outside] == orig[outside]).all()


def test_composite_with_no_change_yields_empty_or_tiny_mask():
    orig = textured(1)
    out = composite(orig, cv2.resize(orig, (400, 400)))
    assert out["mask"].sum() < 0.01 * orig.shape[0] * orig.shape[1]


def test_severity_opacity_and_size_ladders():
    orig = textured(2)
    comp = orig.copy()
    mask = np.zeros(orig.shape[:2], bool)
    mask[110:146, 110:146] = True
    comp[mask] = (10, 10, 10)
    full, m_full = sev.variant(orig, comp, mask, "opacity", 1.0)
    assert (full[mask] == comp[mask]).all() and (m_full == mask).all()
    faint, _ = sev.variant(orig, comp, mask, "opacity", 0.12)
    assert np.abs(faint.astype(int) - orig.astype(int)).max() < np.abs(comp.astype(int) - orig.astype(int)).max()
    small, m_small = sev.variant(orig, comp, mask, "size", 0.35)
    assert 0.05 < m_small.sum() / mask.sum() < 0.25          # area scales ~ level^2
    assert (small[~m_small] == orig[~m_small]).all()


def test_wilson_and_curves_and_threshold_note():
    lo, hi = sev.wilson(5, 5)
    assert 0.5 < lo < 0.6 and hi == 1.0
    assert sev.wilson(0, 0) == (0.0, 0.0)
    pts = []
    rates = {("opacity", 1.0): 5, ("opacity", 0.5): 5, ("opacity", 0.25): 3, ("opacity", 0.12): 0,
             ("size", 0.6): 5, ("size", 0.35): 4, ("size", 0.2): 1}
    for (k, l), det in rates.items():
        for i in range(5):
            pts.append({"defect_type": "hole", "kind": k, "level": l, "detected": i < det, "size_mm": 2.0 * (l if k == "size" else 1)})
    (c,) = sev.curves(pts)
    assert [x["n"] for x in c["cells"]] == [5] * 7
    assert "missed at 0.12x" in c["threshold_note"] and "missed at 0.2x" in c["threshold_note"]


def test_equivalent_diameter():
    assert sev.equiv_diameter_mm(np.pi * 25, 200, 20) == pytest.approx(1.0, abs=0.01)
    assert sev.equiv_diameter_mm(100, 0, 20) is None


def _comp(identical=True, components=1, changed=0.01):
    return {"identical_outside": identical, "components": components, "changed_frac": changed}


def test_validators_accept_a_clean_sample_and_reject_bad_ones():
    m = np.zeros((100, 100), bool)
    m[40:50, 40:50] = True
    part = np.ones((100, 100), bool)
    crit = {"verdict": "accept", "realism": 5, "matches_type": True}
    prov = {"prompt": "p", "prompt_sha256": "x", "models": {"a": 1}, "source_image": "s", "crop_box": [0, 0, 1, 1]}
    good = run_validators(comp=_comp(), defect_mask_full=m, part_mask=part, crop_area=10000, sam_iou=0.8,
                          defect_type="hole", critic=crit, dhash_val=0, accepted_hashes=[2 ** 63 - 1], provenance=prov)
    assert len(good) == 8 and accepted(good)
    off_part = run_validators(comp=_comp(), defect_mask_full=m, part_mask=np.zeros((100, 100), bool), crop_area=10000,
                              sam_iou=0.8, defect_type="hole", critic=crit, dhash_val=0, accepted_hashes=[], provenance=prov)
    assert not accepted(off_part)
    bad_critic = run_validators(comp=_comp(), defect_mask_full=m, part_mask=part, crop_area=10000, sam_iou=0.8,
                                defect_type="hole", critic={**crit, "verdict": "reject", "realism": 2}, dhash_val=0,
                                accepted_hashes=[], provenance=prov)
    assert not accepted(bad_critic)
    soft_sam = run_validators(comp=_comp(), defect_mask_full=m, part_mask=part, crop_area=10000, sam_iou=0.05,
                              defect_type="hole", critic=crit, dhash_val=0, accepted_hashes=[], provenance=prov)
    assert accepted(soft_sam) and not next(v for v in soft_sam if v["id"] == "V4")["passed"]   # V4 is advisory


def test_dhash_duplicates():
    a = textured(3)
    assert hamming(dhash(a), dhash(a)) == 0
    assert hamming(dhash(a), dhash(np.ascontiguousarray(np.rot90(a)))) > 4


def test_coco_rle_round_trip():
    m = np.zeros((7, 5), bool)
    m[2:5, 1:3] = True
    r = rle(m)
    flat = np.zeros(35, np.uint8)
    pos, val = 0, 0
    for c in r["counts"]:
        flat[pos:pos + c] = val
        pos += c
        val = 1 - val
    assert (flat.reshape((5, 7)).T.astype(bool) == m).all()
    assert r["size"] == [7, 5]


def test_spark_cost_uses_cached_price():
    full = spark_cost("muse-spark-1.3", 1_000_000, 0, 0)
    cached = spark_cost("muse-spark-1.3", 1_000_000, 0, 1_000_000)
    assert full == pytest.approx(1.25) and cached == pytest.approx(0.15)


def test_otsu_finds_a_dark_part_on_a_light_desk_and_a_bright_part_on_black():
    from PIL import Image
    from app.forge.locate import otsu_mask
    for bg, fg in (((205, 195, 180), (110, 60, 30)), ((12, 12, 14), (170, 100, 50))):
        a = np.full((300, 400, 3), bg, np.uint8)
        cv2.circle(a, (200, 150), 80, fg, -1)
        cv2.circle(a, (180, 130), 12, (235, 225, 210), -1)      # specular highlight inside the part
        m = otsu_mask(Image.fromarray(a))
        assert m[150, 200] and m[130, 180] and not m[5, 5]
        assert 0.14 < m.mean() < 0.18


def test_box_hits_needs_overlap_with_the_defect():
    m = np.zeros((100, 100), bool)
    m[40:50, 40:50] = True
    assert sev.box_hits([35, 35, 45, 45], m)
    assert not sev.box_hits([60, 60, 90, 90], m)
    assert not sev.box_hits(None, m)


def test_legacy_ledger_import_skips_a_torn_line(tmp_path, monkeypatch):
    from app.meta import ledger
    f = tmp_path / "ledger.jsonl"
    f.write_text('{"model": "m", "cost_usd": 1.5, "run_id": "r"}\non_tokens": 545}\n{"model": "m", "cost_usd": 0.5, "run_id": "x"}\n')
    monkeypatch.setattr(ledger, "LEDGER", f)
    monkeypatch.setattr(ledger, "TARGET", tmp_path / "ledger.sqlite3")
    assert len(ledger.recent(10)) == 2
    assert ledger.run_cost("r") == 1.5
    assert ledger.by_model()["m"]["calls"] == 2
    assert ledger.spent() == 2.0
    ledger._imported.clear()
    assert ledger.spent() == 2.0, "the legacy file is imported only once"
