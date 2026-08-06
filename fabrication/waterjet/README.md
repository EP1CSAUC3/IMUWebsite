# Waterjet medallion

`waterjet-ready.dxf` is the primary fabrication file. It is an ASCII
AutoCAD R12 DXF drawn at a nominal **500 mm outside diameter**.
`waterjet-ready.svg` contains the same closed geometry for Fusion 360.

## Files

- `waterjet-ready.dxf` — closed CAD polylines in millimetres.
- `waterjet-ready.svg` — closed Fusion-compatible paths in millimetres.
- `waterjet-ready-preview.png` — white material / black through-cut preview;
  pixels outside the plate are transparent.
- `waterjet-validation.json` — connectivity and export results.
- `waterjet-source-reference.png` — cleaned artwork reference used to build
  the cut files.

The DXF and SVG use two named layers/groups:

- `CUT_INNER`: cut these features first.
- `CUT_OUTER`: cut this profile last so the work remains registered.

## Fabrication assumptions

- Nominal plate diameter: 500 mm.
- Nominal bridge/web width added to trapped material: 3 mm.
- Clear solid rim outside the rope artwork: 15 mm.
- Tiny cut regions under 1.5 mm² were removed.
- Tiny trapped material islands under 3 mm² were converted to cutout.
- All retained white material is one connected component.

Kerf compensation is intentionally not baked into the geometry. Apply the
machine shop's lead-ins, pierce strategy, and kerf offset in CAM for the actual
material, thickness, abrasive, nozzle, and finish requirement.

If the design is scaled down, its 3 mm bridges scale down too. Do not cut a
smaller version without checking the resulting web width against the shop's
minimum. Review the preview at full size and have the waterjet operator run a
toolpath/simulation check before cutting stock.

## Source note

The image attached to the request was visible to the build process but its
original file bytes were not exposed in the cloud workspace. The included
source reference is therefore a clean, manufacturing-oriented reconstruction
of that composition rather than a pixel-for-pixel trace. Replace the reference
input and rerun the builder if exact source fidelity is required:

```sh
python3 scripts/build_waterjet_artwork.py path/to/source.png \
  --output-dir fabrication/waterjet
```
