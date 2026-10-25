"""
Safe image loading for single and ZIP uploads. Every file in a ZIP is either
returned as a valid image or skipped with a reason, so bulk mode never crashes.
"""

import io
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tif", ".tiff"}

MAX_IMAGES_PER_ZIP = 50
MAX_FILE_BYTES = 20 * 1024 * 1024    # per image inside a ZIP
MAX_UPLOAD_MB = 50                   # must match server.maxUploadSize in .streamlit/config.toml
Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard

# Everything Pillow / zipfile can raise for a broken file.
DECODE_ERRORS = (
    OSError,
    SyntaxError,
    ValueError,
    Image.DecompressionBombError,
    zipfile.BadZipFile,
    RuntimeError,
)


@dataclass
class ZipImage:
    name: str
    image: Image.Image


@dataclass
class SkippedFile:
    name: str
    reason: str  # not_an_image | corrupt | too_large | over_limit | system_file


def load_image(data: bytes) -> Image.Image:
    """Decode bytes into an RGB image; raises one of DECODE_ERRORS if broken."""
    with Image.open(io.BytesIO(data)) as probe:
        probe.verify()
    image = Image.open(io.BytesIO(data))
    image.load()  # full decode, so truncated files fail here
    return image.convert("RGB")


def extract_images(zip_bytes: bytes) -> tuple[list[ZipImage], list[SkippedFile]]:
    """Split a ZIP (read in memory) into valid images and skipped files."""
    images: list[ZipImage] = []
    skipped: list[SkippedFile] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue

            name = member.filename
            path = PurePosixPath(name)

            if "__MACOSX" in path.parts or path.name.startswith("."):
                skipped.append(SkippedFile(name, "system_file"))
                continue
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                skipped.append(SkippedFile(name, "not_an_image"))
                continue
            if member.file_size > MAX_FILE_BYTES:
                skipped.append(SkippedFile(name, "too_large"))
                continue
            if len(images) >= MAX_IMAGES_PER_ZIP:
                skipped.append(SkippedFile(name, "over_limit"))
                continue

            try:
                image = load_image(archive.read(member))
            except DECODE_ERRORS:
                skipped.append(SkippedFile(name, "corrupt"))
                continue

            images.append(ZipImage(name, image))

    return images, skipped
