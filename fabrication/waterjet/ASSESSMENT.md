# Waterjet manufacturability assessment

## Result

Target size is **12 inch** diameter (304.8 mm).
The old outside black border is removed and replaced by one exact CAD outer
profile with a **8 mm solid plate rim** around the rope.
White is retained plate; black is cut out.

The artwork is processed as **bold silhouettes**, not raw illustration:
hairline cuts are opened away and nearby fragments are closed into readable
shapes before manufacturability checks. As supplied it still contained
0 floating white islands. The cut-ready
version has one connected material component, 0
supports at 2.5 mm nominal width,
0 tiny trapped white details removed,
and 0 undersized cut details removed.

No complete object needs removal at 12 inches. Remaining features are bold enough to cut, with only necessary stencil supports kept.

## Object review

| Object/area | Supports | Tiny white details removed | Tiny cuts removed | Longest support (mm) | Result |
|---|---:|---:|---:|---:|---|


Orange in `waterjet-support-plan.png` is added plate support. Purple is tiny
trapped white detail converted to cutout. The production preview remains
strictly white plate / black cut.

## Fabrication assumptions

- Outside diameter: 12 in (304.8 mm).
- Minimum support/web: 2.5 mm (~0.098 in).
- Minimum independent cut area: 8 mm².
- Minimum independent cut width: 1.2 mm.
- Silhouette open/close: 0 / 0 mm.
- Kerf compensation, lead-ins, and pierce strategy remain CAM operations.
- Cut `CUT_INNER` first and `CUT_OUTER` last.
