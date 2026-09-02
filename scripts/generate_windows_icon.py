from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter


ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def png_frame(source: QImage, size: int) -> bytes:
    scaled = source.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QImage(size, size, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not canvas.save(buffer, "PNG"):
        raise RuntimeError(f"Could not encode the {size}x{size} icon frame")
    return bytes(data)


def generate_icon(source_path: Path, output_path: Path) -> None:
    source = QImage(str(source_path))
    if source.isNull():
        raise RuntimeError(f"Could not load logo image: {source_path}")

    frames = [(size, png_frame(source, size)) for size in ICON_SIZES]
    header_size = 6 + 16 * len(frames)
    offset = header_size
    entries = []
    payload = bytearray()
    for size, frame in frames:
        dimension = 0 if size == 256 else size
        entries.append(
            struct.pack(
                "<BBBBHHII",
                dimension,
                dimension,
                0,
                0,
                1,
                32,
                len(frame),
                offset,
            )
        )
        payload.extend(frame)
        offset += len(frame)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(struct.pack("<HHH", 0, 1, len(frames)) + b"".join(entries) + payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a multi-size Windows ICO from the application logo")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate_icon(args.source.resolve(), args.output.resolve())
    print(f"Generated {args.output} with {len(ICON_SIZES)} icon sizes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
