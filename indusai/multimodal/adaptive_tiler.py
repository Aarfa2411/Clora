"""
Adaptive High-Resolution Drawing Tiler.
INDUSAI-X / SIH26117 (MRPL)
Partitions high-resolution engineering schematics into coordinate-aware grid patches.
"""

import io
import base64
import math
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image

from .schema import BoundingBox


class AdaptiveTiler:
    """
    Dynamically partitions large drawings (A0-A3 / ANSI D) into overlapping grid tiles.
    Retains coordinate mappings between tile-local coordinates and global canvas coordinates.
    """

    def __init__(self, target_tile_size: int = 1024, overlap_ratio: float = 0.15):
        self.target_tile_size = target_tile_size
        self.overlap_ratio = overlap_ratio

    def compute_grid_spec(self, width: int, height: int) -> Dict[str, Any]:
        """
        Calculates adaptive rows and columns based on drawing dimensions.
        """
        # Minimum tile size of 512 for standard detail preservation
        effective_tile = min(self.target_tile_size, max(width, height))
        effective_tile = max(512, effective_tile)
        
        # Step size considering overlap
        step = int(effective_tile * (1.0 - self.overlap_ratio))
        step = max(100, step)

        cols = max(1, math.ceil((width - effective_tile) / step) + 1 if width > effective_tile else 1)
        rows = max(1, math.ceil((height - effective_tile) / step) + 1 if height > effective_tile else 1)

        # Generate standard grid names A-Z and 1-N
        row_labels = [chr(65 + i) for i in range(min(rows, 26))]
        if rows > 26:
            for i in range(26, rows):
                row_labels.append(f"A{chr(65 + i - 26)}")

        col_labels = [str(i + 1) for i in range(cols)]

        # Calculate cell bounds
        cells = {}
        for r_idx, r_label in enumerate(row_labels):
            for c_idx, c_label in enumerate(col_labels):
                cell_name = f"Grid {r_label}{c_label}"
                
                # Pixel bounds
                x0 = min(c_idx * step, max(0, width - effective_tile))
                y0 = min(r_idx * step, max(0, height - effective_tile))
                x1 = min(width, x0 + effective_tile)
                y1 = min(height, y0 + effective_tile)

                cells[cell_name] = {
                    "cell_name": cell_name,
                    "row": r_label,
                    "col": c_label,
                    "pixel_box": [x0, y0, x1, y1],
                    "norm_bbox": BoundingBox(
                        ymin=y0 / height,
                        xmin=x0 / width,
                        ymax=y1 / height,
                        xmax=x1 / width
                    )
                }

        return {
            "width": width,
            "height": height,
            "rows": len(row_labels),
            "cols": len(col_labels),
            "tile_size": effective_tile,
            "overlap_ratio": self.overlap_ratio,
            "cells": cells
        }

    def get_grid_cell(self, bbox: BoundingBox, grid_spec: Dict[str, Any]) -> str:
        """
        Finds the primary grid cell for a given bounding box based on its center point.
        """
        center_x = (bbox.xmin + bbox.xmax) / 2.0
        center_y = (bbox.ymin + bbox.ymax) / 2.0

        best_cell = "Grid A1"
        min_dist = float("inf")

        for cell_name, data in grid_spec.get("cells", {}).items():
            norm_box: BoundingBox = data["norm_bbox"]
            cell_center_x = (norm_box.xmin + norm_box.xmax) / 2.0
            cell_center_y = (norm_box.ymin + norm_box.ymax) / 2.0

            dist = (center_x - cell_center_x) ** 2 + (center_y - cell_center_y) ** 2
            if dist < min_dist:
                min_dist = dist
                best_cell = cell_name

        return best_cell

    def crop_for_bbox(
        self,
        image: Image.Image,
        bbox: BoundingBox,
        padding_ratio: float = 0.08
    ) -> Tuple[Image.Image, BoundingBox]:
        """
        Extracts a focused crop around a target bounding box with contextual padding.
        Returns the cropped PIL image and the crop's global canvas bounding box.
        """
        img_w, img_h = image.size

        bw = bbox.xmax - bbox.xmin
        bh = bbox.ymax - bbox.ymin

        pad_x = max(0.02, bw * padding_ratio)
        pad_y = max(0.02, bh * padding_ratio)

        c_xmin = max(0.0, bbox.xmin - pad_x)
        c_ymin = max(0.0, bbox.ymin - pad_y)
        c_xmax = min(1.0, bbox.xmax + pad_x)
        c_ymax = min(1.0, bbox.ymax + pad_y)

        px0 = int(c_xmin * img_w)
        py0 = int(c_ymin * img_h)
        px1 = max(px0 + 10, int(c_xmax * img_w))
        py1 = max(py0 + 10, int(c_ymax * img_h))

        crop = image.crop((px0, py0, px1, py1))
        crop_bbox = BoundingBox(ymin=c_ymin, xmin=c_xmin, ymax=c_ymax, xmax=c_xmax)

        return crop, crop_bbox

    @staticmethod
    def image_to_base64(image: Image.Image, img_format: str = "PNG") -> str:
        """Converts PIL image to base64 data string."""
        buffer = io.BytesIO()
        image.save(buffer, format=img_format)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    @staticmethod
    def base64_to_image(b64_str: str) -> Image.Image:
        """Converts base64 data string back to PIL Image."""
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        data = base64.b64decode(b64_str)
        return Image.open(io.BytesIO(data))
