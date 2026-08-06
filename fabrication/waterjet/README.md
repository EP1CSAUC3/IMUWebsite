# 12 inch waterjet medallion

White = retained plate. Black = through-cut.

This pack is sized for a **12 inch** (304.8 mm) circular plate that fits a
12"×12" blank. The artwork is rebuilt as bold silhouettes so the design stays
readable without relying on hairline illustration detail.

## Review images

- `waterjet-source-12in.png` — revised bold source artwork.
- `waterjet-border-cleaned.png` — old outside black border removed; solid rim kept.
- `waterjet-silhouette-pass.png` — thin cuts simplified into readable silhouettes.
- `waterjet-support-plan.png` — orange = plate supports; purple = tiny trapped white details removed.
- `waterjet-ready-preview.png` — final white/black production preview.
- `ASSESSMENT.md` — object-by-object result.
- `waterjet-validation.json` — machine-readable metrics.

## Fabrication files

- `waterjet-ready.dxf` — primary AutoCAD R12 geometry in millimetres.
- `waterjet-ready.svg` — equivalent closed geometry for Fusion 360.

Cut `CUT_INNER` first, then `CUT_OUTER`. Kerf, lead-ins, and pierce strategy stay in CAM.

## Rebuild

```sh
python3 scripts/build_waterjet_artwork.py \
  fabrication/waterjet/waterjet-source-12in.png \
  --output-dir fabrication/waterjet \
  --diameter-mm 304.8 \
  --silhouette-open-mm 0.7 \
  --silhouette-close-mm 1.0 \
  --minimum-cut-area-mm2 14 \
  --minimum-cut-width-mm 2.0 \
  --support-width-mm 2.8 \
  --minimum-island-area-mm2 12 \
  --simplify-mm 0.7
```
