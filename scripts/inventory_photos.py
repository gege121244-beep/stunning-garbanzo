#!/usr/bin/env python3
"""Inventory product photos and group numbered files by their name prefix."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
NUMBERED_STEM = re.compile(r"^(.*?)(?:\s*[（(](\d+)[）)])?$")


def visual_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        width, height = image.size
        orientation = image.getexif().get(274, 1)
        if orientation in (5, 6, 7, 8):
            width, height = height, width
        return width, height


def split_name(path: Path) -> tuple[str, int]:
    match = NUMBERED_STEM.match(path.stem)
    if not match:
        return path.stem, 0
    prefix = match.group(1).strip()
    number = int(match.group(2) or 0)
    return prefix, number


def collect(source: Path) -> list[dict[str, object]]:
    files = [
        path
        for path in source.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]
    groups: dict[str, list[tuple[int, Path]]] = defaultdict(list)
    for path in files:
        prefix, number = split_name(path)
        relative_parent = path.parent.relative_to(source)
        key = str(relative_parent / prefix) if str(relative_parent) != "." else prefix
        groups[key].append((number, path))

    result: list[dict[str, object]] = []
    for group_name, entries in sorted(groups.items()):
        entries.sort(key=lambda item: (item[0], item[1].name.casefold()))
        photos = []
        for number, path in entries:
            width, height = visual_size(path)
            photos.append(
                {
                    "number": number,
                    "file": str(path),
                    "width": width,
                    "height": height,
                }
            )
        result.append(
            {
                "group": group_name,
                "prefix": Path(group_name).name,
                "count": len(photos),
                "photos": photos,
            }
        )
    return result


def write_markdown(groups: list[dict[str, object]], output: Path) -> None:
    lines = ["# 照片盘点", "", f"共 {sum(int(g['count']) for g in groups)} 张，{len(groups)} 组。", ""]
    for index, group in enumerate(groups, start=1):
        lines.append(f"## {index:02d}. {group['group']}（{group['count']}张）")
        lines.append("")
        for photo in group["photos"]:  # type: ignore[index]
            lines.append(
                f"- `{photo['file']}` — {photo['width']}×{photo['height']}"  # type: ignore[index]
            )
        lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Source folder containing photos")
    parser.add_argument("--json", type=Path, help="Write machine-readable inventory JSON")
    parser.add_argument("--markdown", type=Path, help="Write human-readable inventory Markdown")
    args = parser.parse_args()

    groups = collect(args.source)
    payload = {"source": str(args.source), "groups": groups}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(groups, args.markdown)
    if not args.json and not args.markdown:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
