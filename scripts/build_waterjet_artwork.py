#!/usr/bin/env python3
"""Build and assess white-material/black-cut waterjet artwork.

The source convention is strict: white is retained plate and black is a
through-cut.  The builder removes the legacy outside border, rejects cuts that
are too small for the stated process, stencils every trapped white island back
to the plate, and exports closed SVG/DXF geometry plus an object-level report.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import cv2
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class Settings:
    diameter_mm: float = 500.0
    threshold: int = 150
    solid_rim_mm: float = 15.0
    support_width_mm: float = 3.0
    minimum_cut_area_mm2: float = 1.5
    minimum_cut_width_mm: float = 1.0
    minimum_island_area_mm2: float = 3.0
    simplify_mm: float = 0.25
    review_support_length_mm: float = 12.0


@dataclass(frozen=True)
class FeatureChange:
    region: str
    area_mm2: float
    width_mm: float
    reason: str


@dataclass(frozen=True)
class IslandResolution:
    region: str
    area_mm2: float
    action: str
    support_length_mm: float | None
    from_xy_mm: tuple[float, float] | None
    to_xy_mm: tuple[float, float] | None


def load_grayscale(path: Path) -> np.ndarray:
    rgba = np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8)
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    rgb = rgba[:, :, :3].astype(np.float32)
    composited = rgb * alpha + 255.0 * (1.0 - alpha)
    return cv2.cvtColor(composited.astype(np.uint8), cv2.COLOR_RGB2GRAY)


def circular_mask(shape: tuple[int, int], radius: float) -> np.ndarray:
    height, width = shape
    cy, cx = (height - 1) / 2.0, (width - 1) / 2.0
    y, x = np.ogrid[:height, :width]
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def region_for_point(x: float, y: float, width: int, height: int) -> str:
    """Map a feature centroid to a named object group."""
    nx, ny = x / width, y / height
    radial = math.hypot(nx - 0.5, ny - 0.5)
    if radial > 0.405:
        return "rope border"
    if ny < 0.39 and nx < 0.34:
        return "mountains and forest"
    if ny < 0.40 and nx < 0.61:
        return "captain portrait"
    if ny < 0.25 and nx >= 0.58:
        return "airplane and route"
    if ny < 0.43 and nx >= 0.57:
        return "nautical symbols"
    if 0.34 <= ny < 0.66 and nx < 0.31:
        return "globe and hiker"
    if 0.36 <= ny < 0.68 and nx < 0.73:
        return "quote and dividers"
    if 0.38 <= ny < 0.65:
        return "tropical island"
    if ny >= 0.77 and 0.31 <= nx < 0.72:
        return "yacht and lower waves"
    if ny >= 0.62 and nx < 0.34:
        return "flag and palms"
    if ny >= 0.62 and nx < 0.67:
        return "skyline and animals"
    if ny >= 0.60:
        return "sailboat and waves"
    return "uncategorized artwork"


def component_boundaries(mask: np.ndarray) -> np.ndarray:
    eroded = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8))
    return np.column_stack(np.where(mask & (eroded == 0)))


def reject_unmanufacturable_cuts(
    black: np.ndarray,
    px_per_mm: float,
    settings: Settings,
) -> tuple[np.ndarray, list[FeatureChange]]:
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        black.astype(np.uint8), connectivity=8
    )
    distance = cv2.distanceTransform(black.astype(np.uint8), cv2.DIST_L2, 5)
    result = black.copy()
    rejected: list[FeatureChange] = []
    minimum_area_px = settings.minimum_cut_area_mm2 * px_per_mm**2
    minimum_width_px = settings.minimum_cut_width_mm * px_per_mm

    for component in range(1, count):
        area_px = int(stats[component, cv2.CC_STAT_AREA])
        width_px = float(2.0 * np.max(distance[labels == component]))
        reason = ""
        if area_px < minimum_area_px:
            reason = "cut area below minimum"
        elif width_px < minimum_width_px:
            reason = "cut width below minimum"
        if not reason:
            continue
        x, y = centroids[component]
        rejected.append(
            FeatureChange(
                region_for_point(x, y, black.shape[1], black.shape[0]),
                area_px / px_per_mm**2,
                width_px / px_per_mm,
                reason,
            )
        )
        result[labels == component] = False
    return result, rejected


def resolve_material_islands(
    black: np.ndarray,
    disc: np.ndarray,
    px_per_mm: float,
    settings: Settings,
) -> tuple[np.ndarray, np.ndarray, list[IslandResolution]]:
    """Remove insignificant islands and bridge every retained island."""
    black = black.copy()
    support_mask = np.zeros_like(black)
    resolutions: list[IslandResolution] = []
    minimum_island_px = settings.minimum_island_area_mm2 * px_per_mm**2
    support_width_px = max(3, round(settings.support_width_mm * px_per_mm))

    while True:
        material = disc & ~black
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(
            material.astype(np.uint8), connectivity=4
        )
        if count <= 2:
            break

        main_id = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        island_ids = [i for i in range(1, count) if i != main_id]
        tiny_ids = [
            i for i in island_ids if stats[i, cv2.CC_STAT_AREA] < minimum_island_px
        ]
        if tiny_ids:
            for component in tiny_ids:
                x, y = centroids[component]
                area_mm2 = stats[component, cv2.CC_STAT_AREA] / px_per_mm**2
                black[labels == component] = True
                resolutions.append(
                    IslandResolution(
                        region_for_point(x, y, black.shape[1], black.shape[0]),
                        area_mm2,
                        "remove tiny trapped detail",
                        None,
                        None,
                        None,
                    )
                )
            continue

        main_boundary = component_boundaries(labels == main_id)
        main_tree = cKDTree(main_boundary)
        best: tuple[float, int, np.ndarray, np.ndarray] | None = None
        for component in island_ids:
            boundary = component_boundaries(labels == component)
            distances, indices = main_tree.query(boundary, k=1)
            candidate = int(np.argmin(distances))
            proposal = (
                float(distances[candidate]),
                component,
                boundary[candidate],
                main_boundary[int(indices[candidate])],
            )
            if best is None or proposal[0] < best[0]:
                best = proposal
        if best is None:
            raise RuntimeError("Could not find a support path for a material island")

        distance_px, component, island_yx, main_yx = best
        before = black.copy()
        cv2.line(
            black,
            (int(island_yx[1]), int(island_yx[0])),
            (int(main_yx[1]), int(main_yx[0])),
            False,
            thickness=support_width_px,
            lineType=cv2.LINE_8,
        )
        support_mask |= before & ~black
        x, y = centroids[component]
        resolutions.append(
            IslandResolution(
                region_for_point(x, y, black.shape[1], black.shape[0]),
                stats[component, cv2.CC_STAT_AREA] / px_per_mm**2,
                "add support",
                distance_px / px_per_mm,
                (island_yx[1] / px_per_mm, island_yx[0] / px_per_mm),
                (main_yx[1] / px_per_mm, main_yx[0] / px_per_mm),
            )
        )

    return black, support_mask, resolutions


def extract_contours(black: np.ndarray, simplify_px: float) -> list[np.ndarray]:
    contours, _ = cv2.findContours(
        black.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    result: list[np.ndarray] = []
    for contour in contours:
        points = cv2.approxPolyDP(contour, simplify_px, True).reshape(-1, 2)
        if len(points) >= 3:
            result.append(points.astype(np.float64))
    return result


def circle_points(cx: float, cy: float, radius: float) -> np.ndarray:
    angles = np.linspace(0.0, 2.0 * math.pi, 720, endpoint=False)
    return np.column_stack((cx + radius * np.cos(angles), cy + radius * np.sin(angles)))


def path_data(points: np.ndarray) -> str:
    commands = [f"M {points[0, 0]:.4f},{points[0, 1]:.4f}"]
    commands.extend(f"L {x:.4f},{y:.4f}" for x, y in points[1:])
    return " ".join(commands) + " Z"


def write_svg(
    path: Path, diameter_mm: float, outer: np.ndarray, inner: list[np.ndarray]
) -> None:
    inner_paths = "\n".join(
        f'    <path d="{escape(path_data(points))}"/>' for points in inner
    )
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{diameter_mm:.4f}mm" height="{diameter_mm:.4f}mm"
     viewBox="0 0 {diameter_mm:.4f} {diameter_mm:.4f}">
  <title>Waterjet medallion cut geometry</title>
  <desc>White plate / black cut convention. Closed paths in millimetres.</desc>
  <g id="CUT_OUTER" fill="none" stroke="#ff0000" stroke-width="0.1">
    <path d="{escape(path_data(outer))}"/>
  </g>
  <g id="CUT_INNER" fill="none" stroke="#0000ff" stroke-width="0.1">
{inner_paths}
  </g>
</svg>
""",
        encoding="utf-8",
    )


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


def write_dxf(
    path: Path, diameter_mm: float, outer: np.ndarray, inner: list[np.ndarray]
) -> None:
    header = (
        dxf_pair(0, "SECTION")
        + dxf_pair(2, "HEADER")
        + dxf_pair(9, "$ACADVER")
        + dxf_pair(1, "AC1009")
        + dxf_pair(9, "$INSUNITS")
        + dxf_pair(70, 4)
        + dxf_pair(0, "ENDSEC")
        + dxf_pair(0, "SECTION")
        + dxf_pair(2, "ENTITIES")
    )
    entities = dxf_polyline(outer, "CUT_OUTER")
    entities += "".join(dxf_polyline(points, "CUT_INNER") for points in inner)
    path.write_text(
        header + entities + dxf_pair(0, "ENDSEC") + dxf_pair(0, "EOF"),
        encoding="ascii",
    )


def rgba_preview(black: np.ndarray, disc: np.ndarray) -> np.ndarray:
    image = np.zeros((*black.shape, 4), dtype=np.uint8)
    image[disc] = (255, 255, 255, 255)
    image[black & disc] = (0, 0, 0, 255)
    return image


def write_analysis_preview(
    path: Path,
    initial_black: np.ndarray,
    final_black: np.ndarray,
    support_mask: np.ndarray,
    disc: np.ndarray,
) -> None:
    image = rgba_preview(final_black, disc)
    removed_detail = final_black & ~initial_black
    image[removed_detail] = (170, 45, 210, 255)
    image[support_mask] = (255, 125, 0, 255)
    Image.fromarray(image, mode="RGBA").save(path)


def build_assessment(
    resolutions: list[IslandResolution],
    rejected: list[FeatureChange],
    settings: Settings,
) -> list[dict[str, object]]:
    grouped_resolutions: dict[str, list[IslandResolution]] = defaultdict(list)
    grouped_rejections: dict[str, list[FeatureChange]] = defaultdict(list)
    for item in resolutions:
        grouped_resolutions[item.region].append(item)
    for item in rejected:
        grouped_rejections[item.region].append(item)

    all_regions = sorted(set(grouped_resolutions) | set(grouped_rejections))
    assessment: list[dict[str, object]] = []
    for region in all_regions:
        items = grouped_resolutions[region]
        supports = [i for i in items if i.action == "add support"]
        removals = [i for i in items if i.action.startswith("remove")]
        lengths = [i.support_length_mm for i in supports if i.support_length_mm]
        rejected_items = grouped_rejections[region]
        if lengths and max(lengths) > settings.review_support_length_mm:
            resolution = "simplify or remove this object; required support is too long"
            final_status = "manual redesign required"
        elif supports or removals or rejected_items:
            resolution = "retained with stencil supports and/or tiny-detail cleanup"
            final_status = "works after automatic changes"
        else:
            resolution = "no change"
            final_status = "works as supplied"
        assessment.append(
            {
                "object": region,
                "as_supplied": "fails: floating material or undersized cuts",
                "support_count": len(supports),
                "longest_support_mm": round(max(lengths), 3) if lengths else 0.0,
                "tiny_material_details_removed": len(removals),
                "undersized_cut_details_removed": len(rejected_items),
                "resolution": resolution,
                "final_status": final_status,
            }
        )
    return assessment


def write_report(
    path: Path,
    settings: Settings,
    metrics: dict[str, object],
    assessment: list[dict[str, object]],
) -> None:
    rows = []
    for item in assessment:
        rows.append(
            "| {object} | {support_count} | {tiny_material_details_removed} | "
            "{undersized_cut_details_removed} | {longest_support_mm:.2f} | "
            "{final_status} |".format(**item)
        )
    manual = [
        item["object"]
        for item in assessment
        if item["final_status"] == "manual redesign required"
    ]
    recommendation = (
        "Remove or redraw: " + ", ".join(manual) + "."
        if manual
        else "No complete object needs removal at this size. The generated supports "
        "resolve every retained floating area; only tiny uncuttable details were removed."
    )
    path.write_text(
        f"""# Waterjet manufacturability assessment

## Result

The old outside black circle has been removed and replaced by one exact CAD
outer profile. A **{settings.solid_rim_mm:g} mm solid plate rim** now separates
the rope artwork from that profile. White is retained plate; black is cut out.

The artwork did **not** work as supplied: it contained
{metrics["initial_material_islands"]} floating white material islands.
The cut-ready version has one connected material component. It uses
{metrics["support_count"]} supports at {settings.support_width_mm:g} mm nominal
width and removes {metrics["tiny_material_details_removed"]} tiny trapped white
details plus {metrics["undersized_cut_details_removed"]} undersized cut details.

{recommendation}

## Object review

| Object/area | Supports | Tiny white details removed | Tiny cuts removed | Longest support (mm) | Result |
|---|---:|---:|---:|---:|---|
{chr(10).join(rows)}

Areas absent from the table had no detected floating material or rejected cut
component. Orange in `waterjet-support-plan.png` shows added plate supports;
purple shows tiny trapped white details converted to cutout. The production
preview remains strictly white plate / black cut.

## Fabrication assumptions

- Outside diameter: {settings.diameter_mm:g} mm.
- Minimum support/web: {settings.support_width_mm:g} mm.
- Minimum independent cut area: {settings.minimum_cut_area_mm2:g} mm².
- Minimum independent cut width: {settings.minimum_cut_width_mm:g} mm.
- Kerf compensation, lead-ins, and pierce strategy remain CAM operations.
- Cut `CUT_INNER` first and `CUT_OUTER` last.

Scaling the design down also scales every support. Re-run this assessment at
the intended diameter and have the operator simulate the toolpath before
cutting stock.
""",
        encoding="utf-8",
    )


def validate(
    black: np.ndarray, disc: np.ndarray, contours: list[np.ndarray]
) -> dict[str, int]:
    material_count, _, material_stats, _ = cv2.connectedComponentsWithStats(
        (disc & ~black).astype(np.uint8), connectivity=4
    )
    cut_count, _, cut_stats, _ = cv2.connectedComponentsWithStats(
        black.astype(np.uint8), connectivity=8
    )
    if material_count != 2:
        raise RuntimeError(f"Plate has {material_count - 1} material components")
    if cut_count - 1 != len(contours):
        raise RuntimeError(
            f"Raster has {cut_count - 1} cuts but export has {len(contours)}"
        )
    return {
        "material_components": material_count - 1,
        "material_pixels": int(material_stats[1, cv2.CC_STAT_AREA]),
        "cut_components": cut_count - 1,
        "cut_pixels": int(np.sum(cut_stats[1:, cv2.CC_STAT_AREA])),
        "closed_inner_contours": len(contours),
    }


def build(source: Path, output_dir: Path, settings: Settings) -> dict[str, object]:
    gray = load_grayscale(source)
    height, width = gray.shape
    if height != width:
        raise ValueError("Source must be square so the outside profile stays circular")
    px_per_mm = width / settings.diameter_mm
    profile_radius = width / 2.0 - 3.0
    disc = circular_mask(gray.shape, profile_radius)

    initial_black = (gray < settings.threshold) & disc
    art_radius = profile_radius - settings.solid_rim_mm * px_per_mm
    border_pixels_removed = int(np.count_nonzero(initial_black & ~circular_mask(gray.shape, art_radius)))
    initial_black &= circular_mask(gray.shape, art_radius)

    initial_material_count, _, _, _ = cv2.connectedComponentsWithStats(
        (disc & ~initial_black).astype(np.uint8), connectivity=4
    )
    black, rejected_before = reject_unmanufacturable_cuts(
        initial_black, px_per_mm, settings
    )
    black, support_mask, resolutions = resolve_material_islands(
        black, disc, px_per_mm, settings
    )
    black, rejected_after = reject_unmanufacturable_cuts(black, px_per_mm, settings)
    black, extra_support_mask, extra_resolutions = resolve_material_islands(
        black, disc, px_per_mm, settings
    )
    support_mask |= extra_support_mask
    resolutions.extend(extra_resolutions)
    rejected = rejected_before + rejected_after

    contours = extract_contours(
        black, max(0.25, settings.simplify_mm * px_per_mm)
    )
    center = np.array([(width - 1) / 2.0, (height - 1) / 2.0])

    def to_mm(points: np.ndarray) -> np.ndarray:
        return (
            (points - center)
            * (settings.diameter_mm / (2.0 * profile_radius))
            + settings.diameter_mm / 2.0
        )

    outer_svg = to_mm(circle_points(center[0], center[1], profile_radius))
    inner_svg = [to_mm(points) for points in contours]
    outer_dxf = outer_svg.copy()
    outer_dxf[:, 1] = settings.diameter_mm - outer_dxf[:, 1]
    inner_dxf = []
    for points in inner_svg:
        flipped = points.copy()
        flipped[:, 1] = settings.diameter_mm - flipped[:, 1]
        inner_dxf.append(flipped)

    output_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba_preview(initial_black, disc), mode="RGBA").save(
        output_dir / "waterjet-border-cleaned.png"
    )
    Image.fromarray(rgba_preview(black, disc), mode="RGBA").save(
        output_dir / "waterjet-ready-preview.png"
    )
    write_analysis_preview(
        output_dir / "waterjet-support-plan.png",
        initial_black,
        black,
        support_mask,
        disc,
    )
    write_svg(output_dir / "waterjet-ready.svg", settings.diameter_mm, outer_svg, inner_svg)
    write_dxf(output_dir / "waterjet-ready.dxf", settings.diameter_mm, outer_dxf, inner_dxf)

    validation = validate(black, disc, contours)
    support_items = [r for r in resolutions if r.action == "add support"]
    tiny_items = [r for r in resolutions if r.action.startswith("remove")]
    metrics: dict[str, object] = {
        **validation,
        "source": str(source),
        "source_pixels": width,
        "nominal_diameter_mm": settings.diameter_mm,
        "pixels_per_mm": round(px_per_mm, 6),
        "solid_rim_mm": settings.solid_rim_mm,
        "legacy_border_pixels_removed": border_pixels_removed,
        "initial_material_islands": max(0, initial_material_count - 2),
        "support_count": len(support_items),
        "support_width_mm": settings.support_width_mm,
        "longest_support_mm": round(
            max((r.support_length_mm or 0.0) for r in support_items), 4
        ),
        "tiny_material_details_removed": len(tiny_items),
        "undersized_cut_details_removed": len(rejected),
        "settings": asdict(settings),
        "island_resolutions": [asdict(item) for item in resolutions],
        "rejected_cut_details": [asdict(item) for item in rejected],
    }
    assessment = build_assessment(resolutions, rejected, settings)
    metrics["object_assessment"] = assessment
    (output_dir / "waterjet-validation.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_report(output_dir / "ASSESSMENT.md", settings, metrics, assessment)
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("fabrication/waterjet")
    )
    parser.add_argument("--diameter-mm", type=float, default=500.0)
    parser.add_argument("--threshold", type=int, default=150)
    parser.add_argument("--solid-rim-mm", type=float, default=15.0)
    parser.add_argument("--support-width-mm", type=float, default=3.0)
    parser.add_argument("--minimum-cut-area-mm2", type=float, default=1.5)
    parser.add_argument("--minimum-cut-width-mm", type=float, default=1.0)
    parser.add_argument("--minimum-island-area-mm2", type=float, default=3.0)
    parser.add_argument("--simplify-mm", type=float, default=0.25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings(
        diameter_mm=args.diameter_mm,
        threshold=args.threshold,
        solid_rim_mm=args.solid_rim_mm,
        support_width_mm=args.support_width_mm,
        minimum_cut_area_mm2=args.minimum_cut_area_mm2,
        minimum_cut_width_mm=args.minimum_cut_width_mm,
        minimum_island_area_mm2=args.minimum_island_area_mm2,
        simplify_mm=args.simplify_mm,
    )
    metrics = build(args.source, args.output_dir, settings)
    summary_keys = (
        "legacy_border_pixels_removed",
        "initial_material_islands",
        "support_count",
        "tiny_material_details_removed",
        "undersized_cut_details_removed",
        "material_components",
        "cut_components",
    )
    for key in summary_keys:
        print(f"{key}: {metrics[key]}")


if __name__ == "__main__":
    main()
