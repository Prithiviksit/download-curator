"""
Image metadata and EXIF extractor.
Prefers existing meaningful EXIF metadata without running costly vision models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Set
from PIL import Image, ExifTags

from download_curator.core.models import ExtractedMetadata
from download_curator.extractors.base import BaseExtractor


class ImageExtractor(BaseExtractor):
    @property
    def supported_extensions(self) -> Set[str]:
        return {
            ".jpg",
            ".jpeg",
            ".png",
            ".heic",
            ".webp",
            ".tiff",
            ".tif",
            ".gif",
            ".svg",
            ".bmp",
        }

    def extract(self, file_path: Path) -> ExtractedMetadata:
        ext = file_path.suffix.lower()
        metadata = ExtractedMetadata(file_type="image")

        if ext == ".svg":
            metadata.raw_metadata["format"] = "SVG"
            return metadata

        try:
            with Image.open(file_path) as img:
                metadata.raw_metadata["width"] = img.width
                metadata.raw_metadata["height"] = img.height
                metadata.raw_metadata["format"] = img.format

                # Extract EXIF if available
                exif_data = img.getexif()
                if exif_data:
                    parsed_exif: Dict[str, Any] = {}
                    for tag_id, value in exif_data.items():
                        tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                        if isinstance(value, (str, int, float)):
                            parsed_exif[tag_name] = value

                    metadata.raw_metadata["exif"] = parsed_exif

                    # Date taken
                    date_str = (
                        parsed_exif.get("DateTimeOriginal")
                        or parsed_exif.get("DateTime")
                        or parsed_exif.get("DateTimeDigitized")
                    )
                    if date_str and isinstance(date_str, str):
                        # Format is usually YYYY:MM:DD HH:MM:SS
                        parts = date_str.split(" ")[0].replace(":", "-")
                        if len(parts) == 10:
                            metadata.date = parts
                            try:
                                metadata.year = int(parts.split("-")[0])
                            except Exception:
                                pass

                    # Camera / Model
                    model = parsed_exif.get("Model")
                    if model:
                        metadata.raw_metadata["camera_model"] = str(model).strip()

                    # Image description or software
                    desc = parsed_exif.get("ImageDescription")
                    if desc and isinstance(desc, str) and len(desc.strip()) > 3:
                        metadata.title = desc.strip()

                metadata.excerpt = (
                    f"Image {img.format} {img.width}x{img.height}. "
                    + (f"Date: {metadata.date}. " if metadata.date else "")
                    + (f"Camera: {metadata.raw_metadata.get('camera_model')}" if 'camera_model' in metadata.raw_metadata else "")
                ).strip()

        except Exception as e:
            metadata.raw_metadata["error"] = str(e)

        return metadata
