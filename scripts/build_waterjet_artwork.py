#!/usr/bin/env python3
"""Create Fusion 360 / waterjet-ready cut geometry from monochrome artwork.

The source convention is white material and black through-cuts.  The exporter:

* removes artwork outside the circular plate profile;
* removes a raster outline at the outside edge (the DXF/SVG circle replaces it);
* removes cuts too small to manufacture;
* fills tiny trapped material islands and bridges larger islands to the plate;
* exports closed SVG and DXF cut contours at a nominal diameter in millimetres.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import cv2
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class BuildSettings:
    diameter_mm: float
    threshold: int
    bridge_mm: float
    minimum_cut_area_mm2: float
    minimum_island_area_mm2: float
    simplify_mm: float
    perimeter_clearance_mm: float


def load_source(path: Path) -> np.ndarray:
    """Load a source image as an 8-bit grayscale image on white."""
    rgba = np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8)
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    rgb = rgba[:, :, :3].astype(np.float32)
    composited = rgb * alpha + 255.0 * (1.0 - alpha)
    gray = cv2.cvtColor(composited.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    return gray


def circular_mask(height: int, width: int, radius: float) -> np.ndarray:
    cy = (height - 1) / 2.0
    cx = (width - 1) / 2.0
    y, x = np.ogrid[:height, :width]
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def remove_small_black_components(
    black: np.ndarray, minimum_area_px: int
) -> tuple[np.ndarray, int]:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        black.astype(np.uint8), connectivity=8
    )
    cleaned = black.copy()
    removed = 0
    for component in range(1, count):
        x = stats[component, cv2.CC_STAT_LEFT]
        y = stats[component, cv2.CC_STAT_TOP]
        width = stats[component, cv2.CC_STAT_WIDTH]
        height = stats[component, cv2.CC_STAT_HEIGHT]
        component_crop = (labels[y : y + height, x : x + width] == component).astype(
            np.uint8
        )
        contours, _ = cv2.findContours(
            component_crop,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        geometric_area = max(
            (abs(cv2.contourArea(contour)) for contour in contours),
            default=0.0,
        )
        if (
            stats[component, cv2.CC_STAT_AREA] < minimum_area_px
            or geometric_area < minimum_area_px
        ):
            cleaned[labels == component] = False
            removed += 1
    return cleaned, removed


def component_boundaries(mask: np.ndarray) -> np.ndarray:
    eroded = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8))
    return np.column_stack(np.where(mask & (eroded == 0)))


def bridge_material_islands(
    black: np.ndarray,
    disc: np.ndarray,
    bridge_width_px: int,
    minimum_island_area_px: int,
) -> tuple[np.ndarray, int, int]:
    """Make all retained material one connected component.

    Tiny trapped white regions are changed to cutout.  Larger regions receive
    the shortest practical white bridge to the main plate.  Connectivity is
    recalculated after every bridge so a bridge never targets a stale island.
    """
    black = black.copy()
    bridged = 0
    filled = 0

    while True:
        material = disc & ~black
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            material.astype(np.uint8), connectivity=4
        )
        if count <= 2:
            break

        main_id = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        island_ids = [
            component
            for component in range(1, count)
            if component != main_id
        ]

        tiny = [
            component
            for component in island_ids
            if stats[component, cv2.CC_STAT_AREA] < minimum_island_area_px
        ]
        if tiny:
            for component in tiny:
                black[labels == component] = True
                filled += 1
            continue

        main_boundary = component_boundaries(labels == main_id)
        main_tree = cKDTree(main_boundary)

        best_distance = math.inf
        best_pair: tuple[np.ndarray, np.ndarray] | None = None
        for component in island_ids:
            boundary = component_boundaries(labels == component)
            distances, indices = main_tree.query(boundary, k=1)
            candidate = int(np.argmin(distances))
            if distances[candidate] < best_distance:
                best_distance = float(distances[candidate])
                best_pair = (
                    boundary[candidate],
                    main_boundary[int(indices[candidate])],
                )

        if best_pair is None:
            raise RuntimeError("Unable to bridge a retained material island")

        island_yx, main_yx = best_pair
        cv2.line(
            black,
            (int(island_yx[1]), int(island_yx[0])),
            (int(main_yx[1]), int(main_yx[0])),
            False,
            thickness=bridge_width_px,
            lineType=cv2.LINE_8,
        )
        bridged += 1

    return black, bridged, filled


def extract_cut_contours(
    black: np.ndarray,
    minimum_area_px: int,
    simplify_px: float,
) -> list[np.ndarray]:
    contours, _ = cv2.findContours(
        black.astype(np.uint8),
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_NONE,
    )
    result: list[np.ndarray] = []
    for contour in contours:
        if abs(cv2.contourArea(contour)) < minimum_area_px:
            continue
        approximate = cv2.approxPolyDP(contour, simplify_px, True)
        points = approximate.reshape(-1, 2).astype(np.float64)
        if len(points) >= 3:
            result.append(points)
    return result


def circle_points(
    center_x: float,
    center_y: float,
    radius: float,
    point_count: int = 720,
) -> np.ndarray:
    angles = np.linspace(0.0, 2.0 * math.pi, point_count, endpoint=False)
    return np.column_stack(
        (
            center_x + radius * np.cos(angles),
            center_y + radius * np.sin(angles),
        )
    )


def svg_path(points_mm: np.ndarray) -> str:
    commands = [f"M {points_mm[0, 0]:.4f},{points_mm[0, 1]:.4f}"]
    commands.extend(f"L {x:.4f},{y:.4f}" for x, y in points_mm[1:])
    commands.append("Z")
    return " ".join(commands)


def write_cutline_svg(
    path: Path,
    diameter_mm: float,
    outer_mm: np.ndarray,
    inner_mm: list[np.ndarray],
) -> None:
    inner_paths = "\n".join(
        f'    <path d="{escape(svg_path(points))}"/>' for points in inner_mm
    )
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{diameter_mm:.4f}mm" height="{diameter_mm:.4f}mm"
     viewBox="0 0 {diameter_mm:.4f} {diameter_mm:.4f}">
  <title>Waterjet medallion cut geometry</title>
  <desc>Nominal {diameter_mm:g} mm plate. Closed paths only; units are millimetres.</desc>
  <g id="CUT_OUTER" fill="none" stroke="#ff0000" stroke-width="0.1">
    <path d="{escape(svg_path(outer_mm))}"/>
  </g>
  <g id="CUT_INNER" fill="none" stroke="#0000ff" stroke-width="0.1">
{inner_paths}
  </g>
</svg>
"""
    path.write_text(content, encoding="utf-8")


def dxf_pair(code: int, value: str | int | float) -> str:
    return f"{code}\n{value}\n"


def dxf_polyline(points: np.ndarray, layer: str) -> str:
    body = (
        dxf_pair(0, "POLYLINE")
        + dxf_pair(8, layer)
        + dxf_pair(66, 1)
        + dxf_pair(70, 1)
    )
    for x, y in points:
        body += (
            dxf_pair(0, "VERTEX")
            + dxf_pair(8, layer)
            + dxf_pair(10, f"{x:.4f}")
            + dxf_pair(20, f"{y:.4f}")
            + dxf_pair(30, "0.0")
        )
    return body + dxf_pair(0, "SEQEND") + dxf_pair(8, layer)


def write_r12_dxf(
    path: Path,
    diameter_mm: float,
    outer_mm: np.ndarray,
    inner_mm: list[np.ndarray],
) -> None:
    header = (
        dxf_pair(0, "SECTION")
        + dxf_pair(2, "HEADER")
        + dxf_pair(9, "$ACADVER")
        + dxf_pair(1, "AC1009")
        + dxf_pair(9, "$INSUNITS")
        + dxf_pair(70, 4)
        + dxf_pair(9, "$EXTMIN")
        + dxf_pair(10, "0.0")
        + dxf_pair(20, "0.0")
        + dxf_pair(9, "$EXTMAX")
        + dxf_pair(10, f"{diameter_mm:.4f}")
        + dxf_pair(20, f"{diameter_mm:.4f}")
        + dxf_pair(0, "ENDSEC")
        + dxf_pair(0, "SECTION")
        + dxf_pair(2, "ENTITIES")
    )
    entities = dxf_polyline(outer_mm, "CUT_OUTER")
    entities += "".join(dxf_polyline(points, "CUT_INNER") for points in inner_mm)
    footer = dxf_pair(0, "ENDSEC") + dxf_pair(0, "EOF")
    path.write_text(header + entities + footer, encoding="ascii")


def write_preview(path: Path, black: np.ndarray, disc: np.ndarray) -> None:
    height, width = black.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[disc] = (255, 255, 255, 255)
    rgba[black & disc] = (0, 0, 0, 255)
    Image.fromarray(rgba, mode="RGBA").save(path)


def validate(
    black: np.ndarray,
    disc: np.ndarray,
    contours: list[np.ndarray],
) -> dict[str, int | float]:
    material = disc & ~black
    material_count, _, material_stats, _ = cv2.connectedComponentsWithStats(
        material.astype(np.uint8), connectivity=4
    )
    cut_count, _, cut_stats, _ = cv2.connectedComponentsWithStats(
        black.astype(np.uint8), connectivity=8
    )
    if material_count != 2:
        raise RuntimeError(
            f"Plate has {material_count - 1} disconnected material components"
        )
    if not contours:
        raise RuntimeError("No interior cut contours were generated")
    if any(len(contour) < 3 for contour in contours):
        raise RuntimeError("An exported contour is not a closed polygon")
    if cut_count - 1 != len(contours):
        raise RuntimeError(
            f"Raster has {cut_count - 1} cuts but exports {len(contours)} contours"
        )

    return {
        "material_components": material_count - 1,
        "material_pixels": int(material_stats[1, cv2.CC_STAT_AREA]),
        "cut_components": cut_count - 1,
        "cut_pixels": int(np.sum(cut_stats[1:, cv2.CC_STAT_AREA])),
        "closed_inner_contours": len(contours),
    }


def build(source: Path, output_dir: Path, settings: BuildSettings) -> dict[str, object]:
    gray = load_source(source)
    height, width = gray.shape
    if height != width:
        raise ValueError("The source must be square so the plate stays circular")

    px_per_mm = width / settings.diameter_mm
    profile_radius_px = width / 2.0 - 3.0
    disc = circular_mask(height, width, profile_radius_px)

    black = gray < settings.threshold
    black &= disc

    # Replace any old raster edge/background with one exact CAD profile and a
    # clean material rim outside the braided border.
    inner_art_limit = (
        profile_radius_px - settings.perimeter_clearance_mm * px_per_mm
    )
    black[~circular_mask(height, width, inner_art_limit)] = False

    minimum_cut_area_px = max(
        4, round(settings.minimum_cut_area_mm2 * px_per_mm**2)
    )
    black, removed_cutouts = remove_small_black_components(
        black, minimum_cut_area_px
    )

    bridge_width_px = max(3, round(settings.bridge_mm * px_per_mm))
    minimum_island_area_px = max(
        4, round(settings.minimum_island_area_mm2 * px_per_mm**2)
    )
    black, bridges, filled_islands = bridge_material_islands(
        black,
        disc,
        bridge_width_px,
        minimum_island_area_px,
    )
    black, post_bridge_removed_cutouts = remove_small_black_components(
        black, minimum_cut_area_px
    )

    simplify_px = max(0.25, settings.simplify_mm * px_per_mm)
    contours_px = extract_cut_contours(
        black,
        minimum_cut_area_px,
        simplify_px,
    )

    center_px = np.array([(width - 1) / 2.0, (height - 1) / 2.0])

    def pixels_to_mm(points: np.ndarray) -> np.ndarray:
        return (
            (points - center_px)
            * (settings.diameter_mm / (2.0 * profile_radius_px))
            + settings.diameter_mm / 2.0
        )

    outer_px = circle_points(
        (width - 1) / 2.0,
        (height - 1) / 2.0,
        profile_radius_px,
    )
    outer_svg_mm = pixels_to_mm(outer_px)
    inner_svg_mm = [pixels_to_mm(points) for points in contours_px]

    # DXF uses conventional positive-up Y while SVG/raster use positive-down Y.
    outer_dxf_mm = outer_svg_mm.copy()
    outer_dxf_mm[:, 1] = settings.diameter_mm - outer_dxf_mm[:, 1]
    inner_dxf_mm: list[np.ndarray] = []
    for points in inner_svg_mm:
        flipped = points.copy()
        flipped[:, 1] = settings.diameter_mm - flipped[:, 1]
        inner_dxf_mm.append(flipped)

    output_dir.mkdir(parents=True, exist_ok=True)
    source_copy = output_dir / "waterjet-source-reference.png"
    if source.resolve() != source_copy.resolve():
        shutil.copyfile(source, source_copy)

    preview_path = output_dir / "waterjet-ready-preview.png"
    svg_path_out = output_dir / "waterjet-ready.svg"
    dxf_path_out = output_dir / "waterjet-ready.dxf"
    write_preview(preview_path, black, disc)
    write_cutline_svg(
        svg_path_out,
        settings.diameter_mm,
        outer_svg_mm,
        inner_svg_mm,
    )
    write_r12_dxf(
        dxf_path_out,
        settings.diameter_mm,
        outer_dxf_mm,
        inner_dxf_mm,
    )

    metrics = validate(black, disc, contours_px)
    metrics.update(
        {
            "source_pixels": width,
            "nominal_diameter_mm": settings.diameter_mm,
            "bridge_width_mm": settings.bridge_mm,
            "bridge_width_pixels": bridge_width_px,
            "perimeter_clearance_mm": settings.perimeter_clearance_mm,
            "small_cutouts_removed": removed_cutouts,
            "post_bridge_cutouts_removed": post_bridge_removed_cutouts,
            "material_islands_bridged": bridges,
            "tiny_material_islands_filled": filled_islands,
            "svg": str(svg_path_out),
            "dxf": str(dxf_path_out),
            "preview": str(preview_path),
        }
    )
    report_path = output_dir / "waterjet-validation.json"
    report_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    metrics["validation_report"] = str(report_path)
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("fabrication/waterjet"),
    )
    parser.add_argument("--diameter-mm", type=float, default=500.0)
    parser.add_argument("--threshold", type=int, default=150)
    parser.add_argument("--bridge-mm", type=float, default=3.0)
    parser.add_argument("--minimum-cut-area-mm2", type=float, default=1.5)
    parser.add_argument("--minimum-island-area-mm2", type=float, default=3.0)
    parser.add_argument("--simplify-mm", type=float, default=0.25)
    parser.add_argument("--perimeter-clearance-mm", type=float, default=15.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = BuildSettings(
        diameter_mm=args.diameter_mm,
        threshold=args.threshold,
        bridge_mm=args.bridge_mm,
        minimum_cut_area_mm2=args.minimum_cut_area_mm2,
        minimum_island_area_mm2=args.minimum_island_area_mm2,
        simplify_mm=args.simplify_mm,
        perimeter_clearance_mm=args.perimeter_clearance_mm,
    )
    metrics = build(args.source, args.output_dir, settings)
    for key, value in metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
