"""The synthetic labels must describe the exact pixels changed by construction."""
import json
from pathlib import Path

import numpy as np
from PIL import Image


def test_white_print_masks_match_every_changed_pixel():
    root = Path(__file__).resolve().parents[1] / 'fixtures'
    samples = json.loads((root / 'speclens/manifest.json').read_text())
    assert len(samples) == 3
    for item in samples:
        original = np.array(Image.open(root / item['source']).convert('RGB'))
        edited = np.array(Image.open(root / item['image']).convert('RGB'))
        mask = np.array(Image.open(root / item['mask'])) > 0
        assert np.array_equal(mask, np.any(original != edited, axis=2))
        assert np.any(mask)
        assert np.array_equal(edited[~mask], original[~mask])
