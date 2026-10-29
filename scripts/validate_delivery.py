#!/usr/bin/env python3
"""Validate album counts and confirm output dimensions match the source photos."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image


def visual_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        width, height = image.size
        orientation = image.getexif().get(274, 1)
        if orientation in (5, 6, 7, 8):
            width, height = height, width
        return width, height


def natural_number(path: Path) -> tuple[int, str]:
    match = re.search(r"[（(](\d+)[）)]$", path.stem)
    return (int(match.group(1)) if match else 0, path.name.casefold())


def source_files(source_dir: Path, prefix: str) -> list[Path]:
    return sorted(
        [
            path
            for path in source_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
            and path.stem.startswith(prefix)
        ],
        key=natural_number,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    config = json.loads(args.manifest.read_text(encoding="utf-8"))
    source_dir = Path(config["source_dir"])
    output_dir = Path(config["output_dir"])
    issues: list[str] = []
    checked = 0

    for album in config["albums"]:
        sources = source_files(source_dir, album["prefix"])
        results = sorted((output_dir / album["folder"] / "images").glob("*.jpg"))
        if len(sources) != len(results):
            issues.append(
                f"{album['folder']}: source={len(sources)}, output={len(results)}"
            )
            continue
        for index, (source, result) in enumerate(zip(sources, results), start=1):
            source_size = visual_size(source)
            with Image.open(result) as image:
                result_size = image.size
            checked += 1
            if source_size != result_size:
                issues.append(
                    f"{album['folder']} #{index}: source={source_size}, output={result_size}"
                )

    lines = [
        "# 交付尺寸与数量质检",
        "",
        f"- 已核对：{checked} 张",
        f"- 问题数：{len(issues)}",
        "",
    ]
    if issues:
        lines.append("## 问题")
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("全部成品数量与原图一致，视觉尺寸一致，未发生裁剪。")
    report = "\n".join(lines) + "\n"
    print(report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
    raise SystemExit(1 if issues else 0)


if __name__ == "__main__":
    main()
