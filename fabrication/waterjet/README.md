# 12 inch waterjet medallion

White = retained plate. Black = through-cut.

Primary fabrication file: **`waterjet-ready.dxf`**

- Nominal diameter: **12.0 in (304.8 mm)**
- AutoCAD R12 ASCII DXF, millimetres (`INSUNITS=4`)
- Layers: `CUT_INNER` first, `CUT_OUTER` last
- Matching Fusion file: `waterjet-ready.svg`

## Final artwork used

- `waterjet-final-user.png` — final waterjet-ready raster used for this DXF
- `waterjet-ready-preview.png` — binary production preview
- `waterjet-validation.json` — topology check (1 connected plate, 172 inner cuts)

## Rebuild from the final image

```sh
python3 scripts/build_waterjet_artwork.py \
  fabrication/waterjet/waterjet-final-user.png \
  --output-dir fabrication/waterjet \
  --diameter-mm 304.8 \
  --silhouette-open-mm 0 \
  --silhouette-close-mm 0 \
  --minimum-cut-area-mm2 8 \
  --minimum-cut-width-mm 1.2 \
  --support-width-mm 2.5 \
  --minimum-island-area-mm2 5 \
  --simplify-mm 0.35 \
  --threshold 160 \
  --solid-rim-mm 8
```

Kerf compensation, lead-ins, and pierce strategy remain CAM operations.
