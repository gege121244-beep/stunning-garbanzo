#!/usr/bin/env python3
"""Render culture-led Xiaohongshu albums over original photos without cropping."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageStat


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def font_path(serif: bool = True) -> str:
    candidates = (
        [
            r"C:\Windows\Fonts\NotoSerifSC-VF.ttf",
            r"C:\Windows\Fonts\simsun.ttc",
            r"C:\Windows\Fonts\simfang.ttf",
            r"C:\Windows\Fonts\msyh.ttc",
        ]
        if serif
        else [
            r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\arial.ttf",
        ]
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError("No suitable Chinese font found")


def load_font(size: int, serif: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(serif), max(12, size))


def natural_number(path: Path) -> tuple[int, str]:
    match = re.search(r"[（(](\d+)[）)]$", path.stem)
    return (int(match.group(1)) if match else 0, path.name.casefold())


def source_files(source_dir: Path, prefix: str) -> list[Path]:
    return sorted(
        [
            path
            for path in source_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in IMAGE_SUFFIXES
            and path.stem.startswith(prefix)
        ],
        key=natural_number,
    )


def clean_filename(text: str) -> str:
    cleaned = INVALID_FILENAME.sub("-", text).strip().rstrip(".")
    return cleaned[:80] or "untitled"


def text_palette(image: Image.Image) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    width, height = image.size
    sample = image.crop((0, 0, width, int(height * 0.43))).convert("L")
    luminance = ImageStat.Stat(sample.resize((64, 64))).mean[0]
    if luminance < 120:
        return (235, 228, 211, 238), (205, 196, 177, 210)
    return (54, 47, 39, 238), (82, 72, 60, 205)


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    result: list[str] = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for char in paragraph:
            candidate = line + char
            if line and draw.textlength(candidate, font=font) > max_width:
                result.append(line)
                line = char
            else:
                line = candidate
        result.append(line)
    return result


def block_size(draw: ImageDraw.ImageDraw, lines: list[str], font: ImageFont.FreeTypeFont, spacing: int) -> tuple[int, int]:
    widths = [int(draw.textlength(line, font=font)) for line in lines] or [0]
    box = draw.textbbox((0, 0), "国Ag", font=font)
    line_height = box[3] - box[1]
    return max(widths), line_height * len(lines) + spacing * max(0, len(lines) - 1)


def draw_block(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    color: tuple[int, int, int, int],
    x: int,
    y: int,
    align: str,
    spacing: int,
    stroke: int,
) -> tuple[int, int]:
    width, height = block_size(draw, lines, font, spacing)
    anchor_x = x
    if align == "center":
        anchor_x = x - width // 2
    elif align == "right":
        anchor_x = x - width
    line_box = draw.textbbox((0, 0), "国Ag", font=font)
    line_height = line_box[3] - line_box[1]
    for line in lines:
        line_width = int(draw.textlength(line, font=font))
        line_x = anchor_x
        if align == "center":
            line_x = x - line_width // 2
        elif align == "right":
            line_x = x - line_width
        draw.text(
            (line_x, y),
            line,
            font=font,
            fill=color,
            stroke_width=stroke,
            stroke_fill=(0, 0, 0, 25) if color[0] > 150 else (255, 255, 255, 20),
        )
        y += line_height + spacing
    return width, height


def textured_text(
    overlay: Image.Image,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.FreeTypeFont,
    color: tuple[int, int, int],
    opacity: int,
    align: str = "left",
    spacing: int = 4,
) -> None:
    """Draw the confirmed mineral-print text texture without changing the photo."""
    probe = ImageDraw.Draw(overlay)
    x, y = xy
    box = probe.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align=align)
    width = box[2] - box[0]
    if align == "center":
        x -= width // 2
    elif align == "right":
        x -= width
    box = probe.multiline_textbbox((x, y), text, font=font, spacing=spacing, align=align)
    pad = max(8, font.size // 14)
    left, top, right, bottom = (int(round(value)) for value in box)
    mask = Image.new("L", (max(1, right - left + pad * 2), max(1, bottom - top + pad * 2)), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.multiline_text(
        (pad - left + x, pad - top + y),
        text,
        font=font,
        fill=opacity,
        spacing=spacing,
        align=align,
    )
    grain = Image.effect_noise(mask.size, 11).point(lambda p: max(222, min(255, 236 + (p - 128) // 5)))
    mask = ImageChops.multiply(mask, grain)
    ink = Image.new("RGBA", mask.size, (*color, 0))
    ink.putalpha(mask)
    overlay.alpha_composite(ink, (left - pad, top - pad))


def draw_rule(
    overlay: Image.Image,
    xy: tuple[int, int, int, int],
    color: tuple[int, int, int, int],
    width: int,
) -> None:
    ImageDraw.Draw(overlay).line(xy, fill=color, width=width)


def add_grain(image: Image.Image) -> Image.Image:
    """Use the approved subtle neutral soft-light grain; preserve hue and white balance."""
    base = image.convert("RGB")
    noise_l = Image.effect_noise(base.size, 14)
    noise_rgb = Image.merge("RGB", (noise_l, noise_l, noise_l))
    softly_textured = ImageChops.soft_light(base, noise_rgb)
    return Image.blend(base, softly_textured, 0.085)


def render_page(
    source: Path,
    output: Path,
    title: str,
    subtitle: str,
    kicker: str,
    signature: str,
    layout: int,
    cover: bool,
) -> None:
    with Image.open(source) as opened:
        info = opened.info.copy()
        image = ImageOps.exif_transpose(opened).convert("RGB")

    width, height = image.size
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))

    # Locked to the 13-album typography system confirmed on 2026-10-30.
    warm = (218, 211, 198)
    quiet = (202, 195, 182)
    faint = (183, 175, 161)
    title_font = load_font(round(width * 0.041), serif=True)
    cover_first_font = load_font(round(width * 0.046), serif=True)
    title_small_font = load_font(round(width * 0.039), serif=True)
    body_font = load_font(round(width * 0.029), serif=True)
    brand_font = load_font(round(width * 0.018), serif=False)
    vertical_font = load_font(round(width * 0.036), serif=True)
    rule_width = max(2, round(width * 0.00055))

    title_parts = [part for part in title.splitlines() if part] or [title]
    subtitle_parts = [part for part in subtitle.splitlines() if part]
    title_text = "\n".join(title_parts)
    subtitle_text = "\n".join(subtitle_parts)
    variant = layout % 10

    if cover:
        textured_text(layer, kicker, (width // 2, round(height * 0.070)), body_font, faint, 218, "center")
        draw_rule(layer, (round(width * 0.45), round(height * 0.120), round(width * 0.55), round(height * 0.120)), (*faint, 92), rule_width)
        if len(title_parts) == 2:
            textured_text(layer, title_parts[0], (width // 2, round(height * 0.155)), cover_first_font, warm, 232, "center")
            textured_text(layer, title_parts[1], (width // 2, round(height * 0.206)), cover_first_font, warm, 232, "center")
            subtitle_y = round(height * 0.285)
        else:
            textured_text(layer, title_text, (width // 2, round(height * 0.155)), cover_first_font, warm, 232, "center")
            subtitle_y = round(height * 0.235)
        if subtitle_text:
            textured_text(layer, subtitle_text, (width // 2, subtitle_y), body_font, quiet, 236, "center", spacing=round(body_font.size * 0.48))
        textured_text(layer, signature.replace(" ", "  "), (width // 2, round(height * 0.365)), brand_font, faint, 184, "center")

    elif variant == 1:
        # Vertical title + horizontal annotation.
        left = round(width * 0.105)
        textured_text(layer, title_text, (left, round(height * 0.125)), title_font, warm, 226, "left")
        draw_rule(layer, (left, round(height * 0.195), round(width * 0.300), round(height * 0.195)), (*faint, 84), rule_width)
        textured_text(layer, subtitle_text, (left, round(height * 0.230)), body_font, quiet, 232, "left", spacing=round(body_font.size * 0.48))
        textured_text(layer, signature.replace(" ", "  "), (left, round(height * 0.360)), brand_font, faint, 150, "left")

    elif variant == 2:
        right = round(width * 0.875)
        textured_text(layer, signature.replace(" ", "  "), (right, round(height * 0.065)), brand_font, faint, 150, "right")
        textured_text(layer, title_text, (right, round(height * 0.140)), title_font, warm, 226, "right")
        draw_rule(layer, (round(width * 0.655), round(height * 0.205), right, round(height * 0.205)), (*faint, 82), rule_width)
        textured_text(layer, subtitle_text, (right, round(height * 0.240)), body_font, quiet, 232, "right", spacing=round(body_font.size * 0.48))

    elif variant == 3:
        vertical_title = "\n".join("".join(title_parts)[:5])
        textured_text(layer, vertical_title, (round(width * 0.185), round(height * 0.105)), vertical_font, warm, 224, "center", spacing=round(vertical_font.size * 0.42))
        draw_rule(layer, (round(width * 0.270), round(height * 0.115), round(width * 0.270), round(height * 0.410)), (*faint, 78), rule_width)
        textured_text(layer, subtitle_text, (round(width * 0.340), round(height * 0.195)), body_font, quiet, 232, "left", spacing=round(body_font.size * 0.48))
        textured_text(layer, signature.replace(" ", "  "), (round(width * 0.340), round(height * 0.350)), brand_font, faint, 148, "left")

    elif variant == 4:
        left = round(width * 0.110)
        textured_text(layer, title_text, (left, round(height * 0.165)), title_font, warm, 226, "left")
        textured_text(layer, subtitle_text, (left, round(height * 0.245)), body_font, quiet, 232, "left", spacing=round(body_font.size * 0.48))
        textured_text(layer, "器\n物", (round(width * 0.860), round(height * 0.130)), body_font, faint, 148, "center", spacing=round(body_font.size * 0.68))

    elif variant == 5:
        right = round(width * 0.860)
        textured_text(layer, title_text, (right, round(height * 0.115)), title_small_font, warm, 226, "right")
        textured_text(layer, subtitle_text, (right, round(height * 0.195)), body_font, quiet, 232, "right", spacing=round(body_font.size * 0.48))
        draw_rule(layer, (round(width * 0.625), round(height * 0.335), right, round(height * 0.335)), (*faint, 80), rule_width)
        textured_text(layer, signature.replace(" ", "  "), (right, round(height * 0.365)), brand_font, faint, 148, "right")

    elif variant == 6:
        left = round(width * 0.115)
        textured_text(layer, signature.replace(" ", "  "), (left, round(height * 0.060)), brand_font, faint, 148, "left")
        draw_rule(layer, (left, round(height * 0.105), round(width * 0.300), round(height * 0.105)), (*faint, 80), rule_width)
        textured_text(layer, title_text, (left, round(height * 0.145)), title_font, warm, 226, "left")
        textured_text(layer, subtitle_text, (left, round(height * 0.225)), body_font, quiet, 232, "left", spacing=round(body_font.size * 0.48))

    elif variant == 7:
        center = width // 2
        textured_text(layer, title_text, (center, round(height * 0.105)), title_small_font, warm, 226, "center")
        textured_text(layer, subtitle_text, (center, round(height * 0.185)), body_font, quiet, 232, "center", spacing=round(body_font.size * 0.48))
        textured_text(layer, signature.replace(" ", "  "), (center, round(height * 0.335)), brand_font, faint, 148, "center")

    elif variant == 8:
        left = round(width * 0.105)
        textured_text(layer, title_text, (left, round(height * 0.100)), title_small_font, warm, 226, "left")
        textured_text(layer, subtitle_text, (width // 2, round(height * 0.195)), body_font, quiet, 232, "center", spacing=round(body_font.size * 0.48))
        draw_rule(layer, (round(width * 0.410), round(height * 0.335), round(width * 0.590), round(height * 0.335)), (*faint, 80), rule_width)
        textured_text(layer, signature.replace(" ", "  "), (round(width * 0.895), round(height * 0.365)), brand_font, faint, 148, "right")

    elif variant == 9:
        right = round(width * 0.880)
        textured_text(layer, title_text, (right, round(height * 0.105)), title_font, warm, 226, "right")
        textured_text(layer, subtitle_text, (right, round(height * 0.185)), body_font, quiet, 232, "right", spacing=round(body_font.size * 0.48))
        textured_text(layer, "汝\n窑", (round(width * 0.135), round(height * 0.125)), body_font, faint, 145, "center", spacing=round(body_font.size * 0.70))
        textured_text(layer, signature.replace(" ", "  "), (right, round(height * 0.335)), brand_font, faint, 148, "right")

    result = add_grain(image)
    result = Image.alpha_composite(result.convert("RGBA"), layer).convert("RGB")
    output.parent.mkdir(parents=True, exist_ok=True)
    save_args: dict[str, object] = {
        "format": "JPEG",
        "quality": 98,
        "subsampling": 0,
        "optimize": True,
    }
    if info.get("icc_profile"):
        save_args["icc_profile"] = info["icc_profile"]
    if info.get("dpi"):
        save_args["dpi"] = info["dpi"]
    result.save(output, **save_args)


def contact_sheet(images: list[Path], output: Path, columns: int = 4) -> None:
    if not images:
        return
    thumb_width = 340
    gap = 24
    label_height = 34
    opened: list[Image.Image] = []
    for path in images:
        with Image.open(path) as image:
            copy = image.convert("RGB")
            copy.thumbnail((thumb_width, 620), Image.Resampling.LANCZOS)
            opened.append(copy)
    rows = math.ceil(len(opened) / columns)
    cell_height = max(image.height for image in opened) + label_height
    canvas = Image.new(
        "RGB",
        (columns * thumb_width + (columns + 1) * gap, rows * cell_height + (rows + 1) * gap),
        (24, 23, 20),
    )
    draw = ImageDraw.Draw(canvas)
    label_font = load_font(18, serif=False)
    for index, image in enumerate(opened):
        row, column = divmod(index, columns)
        x = gap + column * (thumb_width + gap)
        y = gap + row * (cell_height + gap)
        canvas.paste(image, (x + (thumb_width - image.width) // 2, y))
        draw.text((x, y + image.height + 6), f"{index + 1:02d}", font=label_font, fill=(180, 174, 160))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "JPEG", quality=92, optimize=True)


def write_copy(album: dict[str, object], directory: Path) -> None:
    hashtags = " ".join(f"#{tag.lstrip('#')}" for tag in album.get("hashtags", []))
    lines = [
        "# 小红书发布文案",
        "",
        "## 标题",
        "",
        str(album["post_title"]),
        "",
        "## 正文",
        "",
        str(album.get("post_body", "")),
        "",
        "## 搜索词与话题",
        "",
        hashtags,
        "",
        "## 图册逐页文字",
        "",
    ]
    for index, page in enumerate(album["pages"], start=1):  # type: ignore[index]
        subtitle = str(page.get("subtitle", "")).replace("\n", "；")
        lines.append(f"{index}. **{page['title']}**  ")
        lines.append(f"   {subtitle}")
    sources = album.get("sources", [])
    if sources:
        lines.extend(["", "## 内容核验所用资料（运营留档）", ""])
        for source in sources:  # type: ignore[assignment]
            lines.append(f"- [{source['label']}]({source['url']})")
    (directory / "小红书文案与逐页文字.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    config = json.loads(args.manifest.read_text(encoding="utf-8"))
    source_dir = Path(config["source_dir"])
    output_dir = Path(config["output_dir"])
    signature = config.get("signature", "RUYAO JINGHONG")
    output_dir.mkdir(parents=True, exist_ok=True)
    covers: list[Path] = []
    total = 0

    for album_index, album in enumerate(config["albums"]):
        sources = source_files(source_dir, album["prefix"])
        pages = album["pages"]
        if len(sources) != len(pages):
            raise RuntimeError(
                f"{album['prefix']}: matched {len(sources)} photos but received {len(pages)} pages"
            )
        album_dir = output_dir / album["folder"]
        image_dir = album_dir / "images"
        results: list[Path] = []
        for page_index, (source, page) in enumerate(zip(sources, pages)):
            filename = f"{page_index + 1:02d}-{clean_filename(page['title'])}.jpg"
            result = image_dir / filename
            # Keep the confirmed 13-album rhythm, with variation by photo.
            inner_layouts = [7, 2, 1, 9, 4, 6, 3, 5, 8]
            layout = 0 if page_index == 0 else inner_layouts[(page_index - 1) % len(inner_layouts)]
            if layout == 3 and len(page["title"].replace("\n", "")) > 5:
                layout = 7  # Vertical type must never silently truncate a title.
            render_page(
                source,
                result,
                page["title"],
                page.get("subtitle", ""),
                album.get("kicker", "东方器物｜日常审美"),
                signature,
                layout,
                page_index == 0,
            )
            results.append(result)
            total += 1
            print(f"[{album_index + 1:02d}] {page_index + 1:02d}/{len(pages):02d} {result.name}", flush=True)
        contact_sheet(results, album_dir / f"{album['folder']}-图册总览.jpg")
        write_copy(album, album_dir)
        covers.append(results[0])

    contact_sheet(covers, output_dir / "00-成品封面总览.jpg")
    index = ["# 小红书成品索引", ""]
    for number, album in enumerate(config["albums"], start=1):
        index.append(f"{number}. **{album['post_title']}**  ")
        index.append(f"   {album['folder']}")
    index.extend(["", f"共处理 {total} 张原图；保持原始画幅，无裁剪、无重绘、无改色。", ""])
    (output_dir / "00-交付说明.md").write_text("\n".join(index), encoding="utf-8")
    print(f"DONE {total} images / {len(config['albums'])} albums")


if __name__ == "__main__":
    main()

