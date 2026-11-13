"""Deterministic schematic evidence for demo records; never presented as factory photos."""
import io

from PIL import Image, ImageDraw, ImageFont


def sample_image(shape: str, name: str, part: str, defect: str | None) -> tuple[bytes, list[int] | None]:
    image = Image.new('RGB', (800, 560), '#f5f3ed')
    draw = ImageDraw.Draw(image)
    title = ImageFont.load_default(size=24)
    font = ImageFont.load_default(size=17)
    small = ImageFont.load_default(size=14)
    draw.rounded_rectangle((24, 24, 776, 536), radius=18, fill='#ffffff', outline='#ddd8cb', width=2)
    draw.rounded_rectangle((48, 44, 245, 75), radius=7, fill='#e8eddb')
    draw.text((60, 50), 'SYNTHETIC DEMO', fill='#394b31', font=font)
    draw.text((48, 94), name, fill='#242924', font=title)
    draw.text((48, 128), part, fill='#667060', font=small)
    # The tray/grid is illustrative; it supplies no metrology calibration.
    for x in range(100, 730, 40):
        draw.line((x, 175, x, 445), fill='#f0f1ed')
    for y in range(180, 460, 40):
        draw.line((80, y, 720, y), fill='#f0f1ed')
    if shape == 'hazelnut':
        draw.ellipse((265, 190, 535, 435), fill='#b4834c', outline='#765638', width=5)
        for offset in range(0, 150, 22):
            draw.arc((285 + offset // 3, 205, 510 - offset // 3, 420), 105, 260, fill='#8d653d', width=2)
        draw.polygon([(335, 210), (400, 170), (465, 210)], fill='#9a743e')
    elif shape == 'seal':
        draw.rounded_rectangle((220, 205, 580, 425), radius=24, fill='#dce7e6', outline='#668e8a', width=5)
        draw.rounded_rectangle((242, 225, 558, 403), radius=14, outline='#9ab9b4', width=16)
        draw.ellipse((295, 265, 355, 365), fill='#e2c096', outline='#8f7052', width=2)
        draw.ellipse((375, 265, 435, 365), fill='#e2c096', outline='#8f7052', width=2)
        draw.ellipse((455, 265, 515, 365), fill='#e2c096', outline='#8f7052', width=2)
    elif shape == 'cap':
        draw.ellipse((255, 190, 545, 445), fill='#6385aa', outline='#354e73', width=5)
        draw.ellipse((275, 207, 525, 425), outline='#97b2c8', width=12)
        draw.ellipse((303, 235, 497, 402), outline='#45678d', width=4)
    elif shape == 'washer':
        draw.ellipse((260, 185, 540, 445), fill='#b2bdc5', outline='#546575', width=5)
        draw.ellipse((340, 262, 460, 373), fill='#fff', outline='#657581', width=5)
        draw.arc((280, 202, 520, 428), 190, 330, fill='#e9eef0', width=8)
    elif shape == 'label':
        draw.rounded_rectangle((235, 192, 565, 434), radius=12, fill='#f9f7ee', outline='#6a7268', width=3)
        draw.text((267, 220), 'SPECLENS / SAMPLE', font=font, fill='#324635')
        draw.text((267, 250), 'BATCH DEMO - 250 g', font=small, fill='#596553')
        for i in range(46):
            x = 270 + i * 5
            draw.rectangle((x, 300, x + (1 if i % 3 else 3), 380), fill='#354236')
        draw.text((282, 398), '0000 1234 5678', font=small, fill='#596553')
    elif shape == 'pcb':
        draw.rounded_rectangle((220, 195, 580, 430), radius=12, fill='#416c55', outline='#254d3b', width=5)
        for y in (230, 290, 370):
            draw.line((245, y, 550, y), fill='#a7bb79', width=3)
        for x in (265, 345, 425, 505):
            draw.rectangle((x, 235, x + 40, 265), fill='#b0a88d', outline='#d9d0b3', width=3)
            draw.ellipse((x, 360, x + 24, 384), fill='#c6c5b5')
        draw.rectangle((345, 300, 455, 350), fill='#303937', outline='#abb4a4', width=3)
    else:
        raise ValueError('Unknown demo part illustration.')
    box = None
    if defect:
        box = [415, 265, 500, 330]
        if defect in {'crack', 'scratch', 'cut', 'seal_gap'}:
            draw.line([(420, 280), (442, 296), (452, 280), (480, 316)], fill='#b2342f', width=6)
        elif defect in {'print', 'misprint', 'smudge'}:
            draw.text((421, 280), 'XX', fill='#b2342f', font=title)
        else:
            draw.ellipse((430, 280, 480, 317), fill='#a93c32', outline='#6c2926', width=3)
        draw.text((48, 467), f'Illustrated finding: {defect.replace("_", " ")}', fill='#983c30', font=font)
    else:
        draw.text((48, 467), 'Illustrated condition: nominal appearance', fill='#48633f', font=font)
    draw.text((48, 501), 'Illustrative inspection only. No model was run. Not a measured factory result.',
              fill='#6d7165', font=small)
    output = io.BytesIO()
    image.save(output, 'JPEG', quality=88)
    return output.getvalue(), box
