# Waterjet manufacturability assessment

## Result

Target size is **12 inch** diameter (304.8 mm).
The old outside black border is removed and replaced by one exact CAD outer
profile with a **10 mm solid plate rim** around the rope.
White is retained plate; black is cut out.

The artwork is processed as **bold silhouettes**, not raw illustration:
hairline cuts are opened away and nearby fragments are closed into readable
shapes before manufacturability checks. As supplied it still contained
51 floating white islands. The cut-ready
version has one connected material component, 16
supports at 2.8 mm nominal width,
35 tiny trapped white details removed,
and 1 undersized cut details removed.

No complete object needs removal at 12 inches. Remaining features are bold enough to cut, with only necessary stencil supports kept.

## Object review

| Object/area | Supports | Tiny white details removed | Tiny cuts removed | Longest support (mm) | Result |
|---|---:|---:|---:|---:|---|
| airplane and route | 0 | 1 | 0 | 0.00 | works after automatic changes |
| captain portrait | 1 | 0 | 0 | 3.01 | works after automatic changes |
| flag and palms | 0 | 1 | 0 | 0.00 | works after automatic changes |
| globe and hiker | 2 | 2 | 0 | 2.60 | works after automatic changes |
| mountains and forest | 3 | 0 | 0 | 3.06 | works after automatic changes |
| nautical symbols | 6 | 2 | 0 | 4.24 | works after automatic changes |
| quote and dividers | 1 | 26 | 0 | 1.34 | works after automatic changes |
| rope border | 0 | 0 | 1 | 0.00 | works after automatic changes |
| sailboat and waves | 1 | 1 | 0 | 1.47 | works after automatic changes |
| skyline and animals | 2 | 0 | 0 | 1.64 | works after automatic changes |
| tropical island | 0 | 1 | 0 | 0.00 | works after automatic changes |
| yacht and lower waves | 0 | 1 | 0 | 0.00 | works after automatic changes |

Orange in `waterjet-support-plan.png` is added plate support. Purple is tiny
trapped white detail converted to cutout. The production preview remains
strictly white plate / black cut.

## Fabrication assumptions

- Outside diameter: 12 in (304.8 mm).
- Minimum support/web: 2.8 mm (~0.110 in).
- Minimum independent cut area: 14 mm².
- Minimum independent cut width: 2 mm.
- Silhouette open/close: 0.7 / 1 mm.
- Kerf compensation, lead-ins, and pierce strategy remain CAM operations.
- Cut `CUT_INNER` first and `CUT_OUTER` last.
