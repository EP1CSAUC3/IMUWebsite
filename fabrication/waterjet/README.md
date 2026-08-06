# Waterjet medallion

This directory is a clean rebuild of the supplied artwork using the convention
**white = retained plate** and **black = through-cut**.

## Review files

- `waterjet-source-reference.png` — source artwork retained for repeatability.
- `waterjet-border-cleaned.png` — first pass with the old outside black border
  removed and a 15 mm solid rim around the rope.
- `waterjet-support-plan.png` — manufacturability markup. Orange is added plate
  support; purple is tiny trapped material converted to cutout.
- `waterjet-ready-preview.png` — final strict white/black production preview.
- `ASSESSMENT.md` — object-by-object result and removal recommendations.
- `waterjet-validation.json` — complete machine-readable measurements.

## Fabrication files

- `waterjet-ready.dxf` — primary AutoCAD R12 geometry at 500 mm diameter.
- `waterjet-ready.svg` — equivalent closed geometry for Fusion 360.

Both vector files separate `CUT_INNER` from `CUT_OUTER`. Cut all inner features
first and the outside profile last. Kerf compensation, lead-ins, and pierce
strategy are intentionally left for CAM.

## Rebuild

```sh
python3 scripts/build_waterjet_artwork.py \
  fabrication/waterjet/waterjet-source-reference.png \
  --output-dir fabrication/waterjet
```

The build fails if retained white material is disconnected or if raster cut
components do not match exported closed contours.
