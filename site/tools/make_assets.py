"""Regenerate the site's image assets from docs/media and the bundled fonts.

Writes, under site/:
  stills/<name>.png   a still frame of each GIF (shown when animations are paused or
                      the visitor prefers reduced motion)
  social.png          the 1200x630 Open Graph / Twitter card image
  icon-180.png        the Apple touch icon

Run it again whenever a GIF in docs/media changes:

    uv run --no-project --with pillow --with fonttools --with brotli \
        python site/tools/make_assets.py
"""

from __future__ import annotations

import io
import math
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageSequence

SITE = Path(__file__).resolve().parents[1]
MEDIA = SITE.parent / "docs" / "media"
GIFS = ["hero", "discover", "apply", "chat"]


def oklch(lightness: float, chroma: float, hue: float) -> tuple[int, int, int]:
    """OKLCH (as written in frontend/src/index.css) to an sRGB tuple."""
    a = chroma * math.cos(math.radians(hue))
    b = chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )

    def encode(c: float) -> int:
        c = min(max(c, 0.0), 1.0)
        v = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        return round(v * 255)

    r, g, bl = (encode(c) for c in rgb)
    return (r, g, bl)


PAPER = oklch(0.965, 0.014, 80)
INK = oklch(0.23, 0.014, 55)
INK_2 = oklch(0.36, 0.016, 55)
ESPRESSO = oklch(0.25, 0.014, 55)
ACCENT = oklch(0.52, 0.13, 40)
ACCENT_SOFT = oklch(0.8, 0.1, 50)
CREAM = oklch(0.95, 0.012, 80)


def font(name: str, size: int, weight: int, opsz: int | None = None) -> ImageFont.FreeTypeFont:
    """Load a bundled variable woff2 font at a given weight (Pillow can't read woff2)."""
    tt = TTFont(SITE / "fonts" / name)
    tt.flavor = None
    buf = io.BytesIO()
    tt.save(buf)
    buf.seek(0)
    f = ImageFont.truetype(buf, size)
    axes = {"wght": weight}
    if opsz is not None:
        axes["opsz"] = opsz
    names = [ax.axisTag for ax in tt["fvar"].axes]
    f.set_variation_by_axes([axes.get(n, 400) for n in names])
    return f


def stills() -> None:
    out = SITE / "stills"
    out.mkdir(exist_ok=True)
    for name in GIFS:
        gif = Image.open(MEDIA / f"{name}.gif")
        frames = [fr.convert("RGB") for fr in ImageSequence.Iterator(gif)]
        # The last frame is the finished state each animation builds up to.
        frames[-1].quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(
            out / f"{name}.png", optimize=True
        )


def social() -> None:
    w, h = 1200, 630
    img = Image.new("RGB", (w, h), PAPER)
    draw = ImageDraw.Draw(img)

    # Screenshot card on the right, bleeding off the edge, with the app's warm shadow.
    shot = Image.open(MEDIA / "pipeline.png").convert("RGB")
    shot = shot.resize((1040, 650), Image.Resampling.LANCZOS)
    x, y = 560, 150
    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x - 2, y + 8, x + 1040, y + 680), 18, fill=90)
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    img.paste(Image.new("RGB", (w, h), oklch(0.6, 0.03, 55)), (0, 0), shadow)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *shot.size), 16, fill=255)
    img.paste(shot, (x, y), mask)
    draw.rounded_rectangle((x, y, x + 1040, y + 650), 16, outline=oklch(0.87, 0.018, 75), width=2)

    serif = font("newsreader-latin-opsz-normal.woff2", 92, 500, 72)
    serif_i = font("newsreader-latin-opsz-italic.woff2", 46, 400, 48)
    sans = font("public-sans-latin-wght-normal.woff2", 25, 450)
    sans_b = font("public-sans-latin-wght-normal.woff2", 21, 650)

    draw.text((64, 70), "RoleHawk", font=serif, fill=INK)
    draw.text((66, 190), "Your job search,", font=serif_i, fill=INK)
    draw.text((66, 242), "on your computer.", font=serif_i, fill=ACCENT)
    lines = [
        "Finds and ranks jobs, writes a",
        "tailored CV and cover letter, and",
        "tracks every application.",
    ]
    for i, line in enumerate(lines):
        draw.text((66, 330 + i * 36), line, font=sans, fill=INK_2)

    tag = "FREE  ·  OPEN SOURCE  ·  LOCAL"
    bbox = draw.textbbox((0, 0), tag, font=sans_b)
    tw = bbox[2] - bbox[0]
    draw.rounded_rectangle((64, 500, 64 + tw + 40, 548), 24, fill=ESPRESSO)
    draw.text((84, 511), tag, font=sans_b, fill=CREAM)

    img.save(SITE / "social.png", optimize=True)


def touch_icon() -> None:
    size = 180
    img = Image.new("RGB", (size, size), ESPRESSO)
    draw = ImageDraw.Draw(img)
    serif = font("newsreader-latin-opsz-normal.woff2", 132, 500, 72)
    bbox = draw.textbbox((0, 0), "R", font=serif)
    gx = (size - (bbox[2] - bbox[0])) / 2 - bbox[0]
    gy = (size - (bbox[3] - bbox[1])) / 2 - bbox[1]
    draw.text((gx, gy), "R", font=serif, fill=ACCENT_SOFT)
    img.save(SITE / "icon-180.png", optimize=True)


if __name__ == "__main__":
    stills()
    social()
    touch_icon()
    print("Wrote stills/, social.png, icon-180.png")
    print("Colors:", {"paper": PAPER, "ink": INK, "espresso": ESPRESSO, "accent": ACCENT})
