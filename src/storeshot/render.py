"""Composition: raw screenshot in, store-ready image out."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Fonts we try, in order, when the config does not name one.
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


class RenderError(Exception):
    pass


@dataclass
class Style:
    """Everything about how a screenshot is dressed up."""

    background: list[str] = field(default_factory=lambda: ["#0B1020", "#1E2A5A"])
    caption_color: str = "#FFFFFF"
    font: str | None = None
    font_size: int | None = None  # defaults to 4.6% of canvas width
    padding: float = 0.08  # side padding, fraction of canvas width
    caption_area: float = 0.20  # top band reserved for text, fraction of height
    corner_radius: float = 0.035  # fraction of screenshot width
    shadow: bool = True
    shadow_opacity: int = 90  # 0-255

    @classmethod
    def from_dict(cls, data: dict) -> "Style":
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(data) - known
        if unknown:
            raise RenderError(
                f"unknown style option(s): {', '.join(sorted(unknown))}. "
                f"Valid options: {', '.join(sorted(known))}"
            )
        bg = data.get("background")
        if isinstance(bg, str):
            data = {**data, "background": [bg]}
        return cls(**data)


def load_font(style: Style, canvas_width: int) -> ImageFont.FreeTypeFont:
    size = style.font_size or max(18, round(canvas_width * 0.046))
    candidates = ([style.font] if style.font else []) + list(FONT_CANDIDATES)
    for path in candidates:
        if path and Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    if style.font:
        raise RenderError(f"could not load font: {style.font}")
    # Last resort. Renders, but small and ugly, so say so loudly.
    raise RenderError(
        "no usable TrueType font found. Set 'font: /path/to/Font.ttf' in your "
        "config, or install DejaVu (Linux) / use the system fonts on macOS."
    )


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise RenderError(f"bad color {value!r}, expected #RRGGBB")
    try:
        return tuple(int(v[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as exc:
        raise RenderError(f"bad color {value!r}, expected #RRGGBB") from exc


def make_background(size: tuple[int, int], colors: list[str]) -> Image.Image:
    """Solid fill for one color, smooth vertical gradient for two or more."""
    width, height = size
    rgb = [_hex_to_rgb(c) for c in colors]
    if not rgb:
        raise RenderError("background needs at least one color")
    if len(rgb) == 1:
        return Image.new("RGB", size, rgb[0])

    # Build the ramp one pixel wide, then stretch. Cheap and smooth.
    ramp = Image.new("RGB", (1, height))
    px = ramp.load()
    segments = len(rgb) - 1
    for y in range(height):
        pos = y / max(1, height - 1) * segments
        i = min(int(pos), segments - 1)
        t = pos - i
        a, b = rgb[i], rgb[i + 1]
        px[0, y] = tuple(round(a[c] + (b[c] - a[c]) * t) for c in range(3))
    return ramp.resize(size, Image.Resampling.BILINEAR)


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    # Supersample so the corners are not jagged.
    scale = 4
    big = (size[0] * scale, size[1] * scale)
    mask = Image.new("L", big, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (big[0] - 1, big[1] - 1)], radius=radius * scale, fill=255
    )
    return mask.resize(size, Image.Resampling.LANCZOS)


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words, current = paragraph.split(), ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if font.getlength(candidate) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _draw_caption(
    canvas: Image.Image,
    text: str,
    style: Style,
    font: ImageFont.FreeTypeFont,
    band: tuple[int, int],
) -> None:
    """Draw wrapped, centered text inside the vertical band (top, bottom)."""
    draw = ImageDraw.Draw(canvas)
    pad = round(canvas.width * style.padding)
    lines = _wrap(text, font, canvas.width - 2 * pad)
    line_height = round(font.size * 1.25)
    total = line_height * len(lines)
    top, bottom = band
    y = top + max(0, (bottom - top - total) // 2)
    color = _hex_to_rgb(style.caption_color)
    for line in lines:
        x = (canvas.width - font.getlength(line)) / 2
        draw.text((x, y), line, font=font, fill=color)
        y += line_height


def compose(
    screenshot: Path | None,
    target_size: tuple[int, int],
    style: Style,
    caption: str | None = None,
) -> Image.Image:
    """Render one store image.

    screenshot=None produces a caption-on-background banner, which is what
    the Play Store feature graphic needs.
    """
    canvas = make_background(target_size, style.background)
    font = load_font(style, canvas.width) if caption else None

    if screenshot is None:
        if caption and font:
            _draw_caption(canvas, caption, style, font, (0, canvas.height))
        return canvas

    try:
        shot = Image.open(screenshot)
    except (OSError, ValueError) as exc:
        raise RenderError(f"could not open {screenshot}: {exc}") from exc
    shot = shot.convert("RGBA")

    pad = round(canvas.width * style.padding)
    caption_bottom = round(canvas.height * style.caption_area) if caption else pad
    if caption and font:
        _draw_caption(canvas, caption, style, font, (pad, caption_bottom))

    # Space left for the device image.
    area_w = canvas.width - 2 * pad
    area_h = canvas.height - caption_bottom - pad
    if area_w <= 0 or area_h <= 0:
        raise RenderError(
            f"no room left for the screenshot at {target_size[0]}x{target_size[1]}; "
            f"reduce padding or caption_area"
        )

    ratio = min(area_w / shot.width, area_h / shot.height)
    new_size = (max(1, round(shot.width * ratio)), max(1, round(shot.height * ratio)))
    shot = shot.resize(new_size, Image.Resampling.LANCZOS)

    radius = round(new_size[0] * style.corner_radius)
    if radius > 0:
        mask = _rounded_mask(new_size, radius)
        shot.putalpha(mask)

    x = (canvas.width - new_size[0]) // 2
    y = caption_bottom + (area_h - new_size[1]) // 2

    if style.shadow:
        blur = max(4, round(new_size[0] * 0.03))
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow.paste(
            Image.new("RGBA", new_size, (0, 0, 0, style.shadow_opacity)),
            (x, y + blur // 2),
            shot.getchannel("A"),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow).convert("RGB")

    canvas.paste(shot, (x, y), shot)
    return canvas


def save(image: Image.Image, path: Path, quality: int = 95) -> None:
    """Write the image. Stores reject alpha, so always flatten to RGB."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if image.mode != "RGB":
        image = image.convert("RGB")
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        image.save(path, "JPEG", quality=quality, optimize=True)
    else:
        image.save(path, "PNG", optimize=True)
