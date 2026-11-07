"""Create reproducible white-print test images and exact changed-pixel masks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'fixtures' / 'speclens'


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    font_paths = [Path('/System/Library/Fonts/Menlo.ttc'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf')]
    font_path = next((p for p in font_paths if p.exists()), None)
    font = ImageFont.truetype(str(font_path), 25) if font_path else ImageFont.load_default(size=25)
    manifest = []
    for index, (source_name, text, xy, opacity, rotation) in enumerate([
        ('hazelnut_gen_01.jpg', 'A7', (492, 480), 165, -8),
        ('hazelnut_gen_02.jpg', 'C4', (505, 515), 140, 5),
        ('hazelnut_gen_03.jpg', 'B2', (485, 500), 190, -4),
    ], 1):
        source = ROOT / 'fixtures' / 'parts' / source_name
        original = Image.open(source).convert('RGB')
        ink = Image.new('RGBA', original.size)
        ImageDraw.Draw(ink).text(xy, text, fill=(247, 245, 231, opacity), font=font, anchor='mm')
        ink = ink.rotate(rotation, Image.Resampling.BICUBIC, center=xy)
        edited = Image.alpha_composite(original.convert('RGBA'), ink).convert('RGB')
        mask = np.any(np.array(original) != np.array(edited), axis=2)
        name = f'white-print-{index:02d}'
        edited.save(OUT / f'{name}.png')
        Image.fromarray(mask.astype('uint8') * 255).save(OUT / f'{name}-mask.png')
        manifest.append({'id': name, 'source': f'parts/{source_name}', 'image': f'speclens/{name}.png',
                         'mask': f'speclens/{name}-mask.png', 'expected_verdict': 'defect', 'defect_type': 'print',
                         'changed_pixels': int(mask.sum()), 'sha256': hashlib.sha256((OUT / f'{name}.png').read_bytes()).hexdigest(),
                         'provenance': 'Generated part photo with a deterministic ink overlay. Synthetic test sample, not a real production defect.'})
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Created {len(manifest)} white-print samples with exact masks.')


if __name__ == '__main__':
    build()
