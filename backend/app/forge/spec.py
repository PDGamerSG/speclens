"""Spec -> defect taxonomy (Muse Spark), forge prompts, and the Muse Spark realism critic."""
from __future__ import annotations

from ..meta.client import data_url, spark_json, to_jpeg

DEFAULT_SPEC = """HAZELNUT VISUAL QA SPECIFICATION  HZ-QA-07 rev C
Part: whole in-shell hazelnut, nominal width 20 mm, inspected top-down on a dark conveyor by a camera inspector.

3. ACCEPTABLE (do not reject)
3.1 Natural shell colour variation, longitudinal stripes and gloss.
3.2 The rough, fuzzy cap (hilum) area and its natural boundary.
3.3 Small natural specks, dust shadows and lighting gradients.

4. REJECT
4.1 Hole: any drilled, bored or insect hole through the shell, any diameter. Typically 0.5-2 mm, dark inside, with a rough or torn rim.
4.2 Crack: any fracture of the shell, from a thin hairline split to a broken-away piece exposing the kernel.
4.3 Cut: any knife cut, slice or notch in the shell surface, usually straight-edged and 2-8 mm long, showing paler material inside.
4.4 Print: any ink, stamp, printed characters or marking on the shell, any size or colour.

5. Inspection must catch every reject class above at the smallest size listed."""

TAXONOMY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["part_name", "part_width_mm", "defects"],
    "properties": {
        "part_name": {"type": "string"},
        "part_width_mm": {"type": "number"},
        "defects": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["defect_type", "clause", "description", "severity_note"],
            "properties": {
                "defect_type": {"type": "string"},
                "clause": {"type": "string"},
                "description": {"type": "string"},
                "severity_note": {"type": "string"}}}}}}

CRITIC_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["realism", "matches_type", "artifacts", "verdict", "revised_prompt"],
    "properties": {
        "realism": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "matches_type": {"type": "boolean"},
        "artifacts": {"type": "string"},
        "verdict": {"type": "string", "enum": ["accept", "reject"]},
        "revised_prompt": {"type": "string"}}}


def taxonomy(spec_text: str, run_id: str | None = None) -> dict:
    msgs = [
        {"role": "system", "content": (
            "You turn manufacturing visual-inspection specs into a defect taxonomy for a synthetic defect generator. "
            "List every REJECT defect class in the spec, one entry each. defect_type: a short lowercase slug (one word). "
            "clause: the clause number. description: one concrete visual phrase an image editor can paint onto a photo of "
            "a good part, describing appearance, size relative to the part, colour and texture (start with 'a' or 'an'; "
            "no instructions, no camera words). severity_note: the size/limit rule from the spec. part_width_mm: the "
            "nominal part width in mm if stated, else 0.")},
        {"role": "user", "content": spec_text}]
    r = spark_json(msgs, TAXONOMY_SCHEMA, "taxonomy", effort="low", max_tokens=6000, run_id=run_id)
    t = r["data"]
    for d in t["defects"]:
        d["defect_type"] = d["defect_type"].strip().lower().replace(" ", "_")[:24] or "defect"
    return t


def forge_prompt(part_name: str, description: str) -> str:
    return (f"Edit this close-up photo of a {part_name}. Add {description.rstrip('.')} exactly at the center of the image. "
            "The defect must be small and local, covering well under a tenth of this image, with the rest of the part intact. "
            "Keep the same lighting, focus, texture and camera angle. Do not change anything else in the photo.")


def critic(crop_img, part_name: str, defect_type: str, description: str, run_id: str | None = None) -> dict:
    msgs = [
        {"role": "system", "content": (
            "You are a strict reviewer of synthetic defect images for industrial inspection. Judge whether the defect near the "
            "centre looks like a real, physically plausible defect photographed with the same camera and lighting as the rest of "
            "the image. Penalize pasted-looking edges, wrong lighting, painterly or cartoon texture, blur mismatch, and a defect "
            "that does not match the requested type. Accept if realism >= 4 and the type matches. If rejecting, write "
            "revised_prompt: an improved one-sentence edit instruction for the image editor; otherwise an empty string.")},
        {"role": "user", "content": [
            {"type": "text", "text": f"Part: {part_name}. Requested defect type: {defect_type} ({description})."},
            {"type": "image_url", "image_url": {"url": data_url(to_jpeg(crop_img, 90, 512))}}]}]
    r = spark_json(msgs, CRITIC_SCHEMA, "critic", effort="low", run_id=run_id)
    return {**r["data"], "cost_usd": r["cost_usd"], "ms": r["ms"]}
