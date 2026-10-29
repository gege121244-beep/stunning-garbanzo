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
            r"C:\Windows\Fonts\simsun.ttc",
            r"C:\Windows\Fonts\simfang.ttf",
            r"C:\Windows\Fonts\msyh.ttc",
        ]
        if serif
        else [
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


def add_grain(image: Image.Image, sigma: float = 1.8) -> Image.Image:
    base = image.convert("RGB")
    noise = Image.effect_noise(base.size, sigma).convert("RGB")
    return ImageChops.add(base, noise, scale=1.0, offset=-128)


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
    short = min(width, height)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    main_color, secondary_color = text_palette(image)
    title_size = int(short * (0.036 if cover else 0.031))
    subtitle_size = int(short * 0.0215)
    kicker_size = int(short * 0.017)
    signature_size = int(short * 0.014)
    title_font = load_font(title_size, serif=True)
    subtitle_font = load_font(subtitle_size, serif=True)
    kicker_font = load_font(kicker_size, serif=True)
    signature_font = load_font(signature_size, serif=False)
    margin = int(short * 0.07)
    title_max = int(width * (0.68 if cover else 0.58))
    subtitle_max = int(width * 0.57)
    title_lines = wrap_lines(draw, title, title_font, title_max)
    subtitle_lines = wrap_lines(draw, subtitle, subtitle_font, subtitle_max)
    stroke = max(1, int(short * 0.00045))

    variant = layout % 8
    if variant in (0, 4):
        align, x, top = "center", width // 2, int(height * (0.075 if cover else 0.09))
    elif variant in (1, 5):
        align, x, top = "left", margin, int(height * 0.085)
    elif variant in (2, 6):
        align, x, top = "right", width - margin, int(height * 0.08)
    else:
        align, x, top = "left", int(width * 0.17), int(height * 0.07)

    kicker_width = int(draw.textlength(kicker, font=kicker_font))
    kicker_x = width // 2 - kicker_width // 2 if align == "center" else (x - kicker_width if align == "right" else x)
    draw.text((kicker_x, top), kicker, font=kicker_font, fill=secondary_color)
    line_y = top + int(kicker_size * 1.9)
    line_len = int(short * 0.07)
    if align == "center":
        line_x0 = width // 2 - line_len // 2
    elif align == "right":
        line_x0 = x - line_len
    else:
        line_x0 = x
    draw.line((line_x0, line_y, line_x0 + line_len, line_y), fill=(*secondary_color[:3], 100), width=max(1, stroke))

    title_y = line_y + int(title_size * 1.05)
    _, title_height = draw_block(
        draw, title_lines, title_font, main_color, x, title_y, align, int(title_size * 0.34), stroke
    )
    subtitle_y = title_y + title_height + int(subtitle_size * 0.95)
    _, subtitle_height = draw_block(
        draw,
        subtitle_lines,
        subtitle_font,
        secondary_color,
        x,
        subtitle_y,
        align,
        int(subtitle_size * 0.42),
        stroke,
    )

    signature_width = int(draw.textlength(signature, font=signature_font))
    signature_y = min(int(height * 0.42), subtitle_y + subtitle_height + int(signature_size * 1.8))
    if align == "center":
        signature_x = width // 2 - signature_width // 2
    elif align == "right":
        signature_x = x - signature_width
    else:
        signature_x = x
    draw.text((signature_x, signature_y), signature, font=signature_font, fill=(*secondary_color[:3], 145))

    result = Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")
    result = add_grain(result)
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
            layout = 0 if page_index == 0 else (page_index * 3 + album_index * 2) % 8
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
