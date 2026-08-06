#!/usr/bin/env python3
"""Build 12-inch waterjet stencil artwork from white-plate / black-cut art.

The builder is tuned for a nominal 12 inch (304.8 mm) circular plate. It:
* removes the legacy outside black border around the rope;
* simplifies thin illustrative cuts into bold silhouettes the eye can read;
* rejects features too small or narrow to cut cleanly at this size;
* adds only the stencil supports needed to keep one connected plate;
* exports closed SVG/DXF geometry plus an object-level assessment.
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

INCH_MM = 25.4
DEFAULT_DIAMETER_MM = 12.0 * INCH_MM  # 304.8 mm


@dataclass(frozen=True)
class Settings:
    diameter_mm: float = DEFAULT_DIAMETER_MM
    threshold: int = 160
    solid_rim_mm: float = 10.0
    support_width_mm: float = 2.5
    minimum_cut_area_mm2: float = 12.0
    minimum_cut_width_mm: float = 1.8
    minimum_island_area_mm2: float = 10.0
    simplify_mm: float = 0.6
    review_support_length_mm: float = 8.0
    silhouette_open_mm: float = 0.9
    silhouette_close_mm: float = 1.1
    working_pixels: int = 2048


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


def load_grayscale(path: Path, working_pixels: int) -> np.ndarray:
    rgba = np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8)
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    rgb = rgba[:, :, :3].astype(np.float32)
    composited = rgb * alpha + 255.0 * (1.0 - alpha)
    gray = cv2.cvtColor(composited.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    if gray.shape[0] != working_pixels or gray.shape[1] != working_pixels:
        gray = cv2.resize(
            gray,
            (working_pixels, working_pixels),
            interpolation=cv2.INTER_AREA,
        )
    return gray


def circular_mask(shape: tuple[int, int], radius: float) -> np.ndarray:
    height, width = shape
    cy, cx = (height - 1) / 2.0, (width - 1) / 2.0
    y, x = np.ogrid[:height, :width]
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def odd_kernel(px: float) -> int:
    size = max(3, int(round(px)))
    if size % 2 == 0:
        size += 1
    return size


def region_for_point(x: float, y: float, width: int, height: int) -> str:
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


def simplify_silhouettes(
    black: np.ndarray,
    disc: np.ndarray,
    px_per_mm: float,
    settings: Settings,
) -> np.ndarray:
    """Turn thin illustrative cuts into bold, readable silhouettes.

    Opening removes hairline cut detail that the eye cannot resolve at 12".
    Closing merges nearby fragments into one solid cut the brain can register.
    """
    opened = black.astype(np.uint8)
    open_px = settings.silhouette_open_mm * px_per_mm
    if open_px >= 1.0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (odd_kernel(open_px), odd_kernel(open_px))
        )
        opened = cv2.morphologyEx(opened, cv2.MORPH_OPEN, kernel)

    closed = opened
    close_px = settings.silhouette_close_mm * px_per_mm
    if close_px >= 1.0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (odd_kernel(close_px), odd_kernel(close_px))
        )
        closed = cv2.morphologyEx(closed, cv2.MORPH_CLOSE, kernel)

    return (closed.astype(bool) & disc)


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
            reason = "cut area below minimum for 12 inch plate"
        elif width_px < minimum_width_px:
            reason = "cut width below minimum for 12 inch plate"
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
  <title>12 inch waterjet medallion</title>
  <desc>White plate / black cut. Nominal {diameter_mm / INCH_MM:.3f} inch diameter.</desc>
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
            resolution = (
                "simplify or remove this object; required support is too long "
                "for a clean 12 inch cut"
            )
            final_status = "manual redesign required"
        elif len(supports) >= 8:
            resolution = (
                "works only with many supports; prefer a bolder silhouette rewrite "
                "if this object must stay crisp"
            )
            final_status = "works after automatic changes"
        elif supports or removals or rejected_items:
            resolution = "retained with stencil supports and/or detail cleanup"
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
    crowded = [
        item["object"]
        for item in assessment
        if item["support_count"] >= 8
        and item["final_status"] != "manual redesign required"
    ]
    parts = []
    if manual:
        parts.append("Remove or redraw: " + ", ".join(manual) + ".")
    if crowded:
        parts.append(
            "These areas work with supports but still read as too detailed for "
            "12 inch plate cutting and should be redrawn as larger silhouettes: "
            + ", ".join(crowded)
            + "."
        )
    if not parts:
        parts.append(
            "No complete object needs removal at 12 inches. Remaining features are "
            "bold enough to cut, with only necessary stencil supports kept."
        )
    recommendation = " ".join(parts)
    inches = settings.diameter_mm / INCH_MM
    path.write_text(
        f"""# Waterjet manufacturability assessment

## Result

Target size is **{inches:g} inch** diameter ({settings.diameter_mm:g} mm).
The old outside black border is removed and replaced by one exact CAD outer
profile with a **{settings.solid_rim_mm:g} mm solid plate rim** around the rope.
White is retained plate; black is cut out.

The artwork is processed as **bold silhouettes**, not raw illustration:
hairline cuts are opened away and nearby fragments are closed into readable
shapes before manufacturability checks. As supplied it still contained
{metrics["initial_material_islands"]} floating white islands. The cut-ready
version has one connected material component, {metrics["support_count"]}
supports at {settings.support_width_mm:g} mm nominal width,
{metrics["tiny_material_details_removed"]} tiny trapped white details removed,
and {metrics["undersized_cut_details_removed"]} undersized cut details removed.

{recommendation}

## Object review

| Object/area | Supports | Tiny white details removed | Tiny cuts removed | Longest support (mm) | Result |
|---|---:|---:|---:|---:|---|
{chr(10).join(rows)}

Orange in `waterjet-support-plan.png` is added plate support. Purple is tiny
trapped white detail converted to cutout. The production preview remains
strictly white plate / black cut.

## Fabrication assumptions

- Outside diameter: {inches:g} in ({settings.diameter_mm:g} mm).
- Minimum support/web: {settings.support_width_mm:g} mm (~{settings.support_width_mm / INCH_MM:.3f} in).
- Minimum independent cut area: {settings.minimum_cut_area_mm2:g} mm².
- Minimum independent cut width: {settings.minimum_cut_width_mm:g} mm.
- Silhouette open/close: {settings.silhouette_open_mm:g} / {settings.silhouette_close_mm:g} mm.
- Kerf compensation, lead-ins, and pierce strategy remain CAM operations.
- Cut `CUT_INNER` first and `CUT_OUTER` last.
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
    gray = load_grayscale(source, settings.working_pixels)
    height, width = gray.shape
    if height != width:
        raise ValueError("Source must be square so the outside profile stays circular")
    px_per_mm = width / settings.diameter_mm
    profile_radius = width / 2.0 - 3.0
    disc = circular_mask(gray.shape, profile_radius)

    raw_black = (gray < settings.threshold) & disc
    art_radius = profile_radius - settings.solid_rim_mm * px_per_mm
    art_mask = circular_mask(gray.shape, art_radius)
    border_pixels_removed = int(np.count_nonzero(raw_black & ~art_mask))
    border_cleaned = raw_black & art_mask

    simplified = simplify_silhouettes(border_cleaned, disc, px_per_mm, settings)
    initial_material_count, _, _, _ = cv2.connectedComponentsWithStats(
        (disc & ~simplified).astype(np.uint8), connectivity=4
    )

    black, rejected_before = reject_unmanufacturable_cuts(
        simplified, px_per_mm, settings
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

    contours = extract_contours(black, max(0.35, settings.simplify_mm * px_per_mm))
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
    Image.fromarray(rgba_preview(border_cleaned, disc), mode="RGBA").save(
        output_dir / "waterjet-border-cleaned.png"
    )
    Image.fromarray(rgba_preview(simplified, disc), mode="RGBA").save(
        output_dir / "waterjet-silhouette-pass.png"
    )
    Image.fromarray(rgba_preview(black, disc), mode="RGBA").save(
        output_dir / "waterjet-ready-preview.png"
    )
    write_analysis_preview(
        output_dir / "waterjet-support-plan.png",
        simplified,
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
        "nominal_diameter_in": round(settings.diameter_mm / INCH_MM, 4),
        "pixels_per_mm": round(px_per_mm, 6),
        "solid_rim_mm": settings.solid_rim_mm,
        "legacy_border_pixels_removed": border_pixels_removed,
        "initial_material_islands": max(0, initial_material_count - 2),
        "support_count": len(support_items),
        "support_width_mm": settings.support_width_mm,
        "longest_support_mm": round(
            max((r.support_length_mm or 0.0) for r in support_items), 4
        )
        if support_items
        else 0.0,
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
    parser.add_argument("--diameter-mm", type=float, default=DEFAULT_DIAMETER_MM)
    parser.add_argument("--threshold", type=int, default=160)
    parser.add_argument("--solid-rim-mm", type=float, default=10.0)
    parser.add_argument("--support-width-mm", type=float, default=2.5)
    parser.add_argument("--minimum-cut-area-mm2", type=float, default=12.0)
    parser.add_argument("--minimum-cut-width-mm", type=float, default=1.8)
    parser.add_argument("--minimum-island-area-mm2", type=float, default=10.0)
    parser.add_argument("--simplify-mm", type=float, default=0.6)
    parser.add_argument("--silhouette-open-mm", type=float, default=0.9)
    parser.add_argument("--silhouette-close-mm", type=float, default=1.1)
    parser.add_argument("--working-pixels", type=int, default=2048)
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
        silhouette_open_mm=args.silhouette_open_mm,
        silhouette_close_mm=args.silhouette_close_mm,
        working_pixels=args.working_pixels,
    )
    metrics = build(args.source, args.output_dir, settings)
    summary_keys = (
        "nominal_diameter_in",
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
