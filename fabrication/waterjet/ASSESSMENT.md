# Waterjet manufacturability assessment

## Result

Target size is **12 inch** diameter (304.8 mm).
The old outside black border is removed and replaced by one exact CAD outer
profile with a **10 mm solid plate rim** around the rope.
White is retained plate; black is cut out.

The artwork is processed as **bold silhouettes**, not raw illustration:
hairline cuts are opened away and nearby fragments are closed into readable
shapes before manufacturability checks. As supplied it still contained
46 floating white islands. The cut-ready
version has one connected material component, 15
supports at 2.5 mm nominal width,
31 tiny trapped white details removed,
and 20 undersized cut details removed.

No complete object needs removal at 12 inches. Remaining features are bold enough to cut, with only necessary stencil supports kept.

## Object review

| Object/area | Supports | Tiny white details removed | Tiny cuts removed | Longest support (mm) | Result |
|---|---:|---:|---:|---:|---|
| airplane and route | 3 | 0 | 0 | 2.74 | works after automatic changes |
| captain portrait | 1 | 1 | 0 | 2.33 | works after automatic changes |
| desert and landmarks | 1 | 8 | 0 | 5.58 | works after automatic changes |
| globe and hiker | 0 | 4 | 0 | 0.00 | works after automatic changes |
| mountains and forest | 1 | 1 | 2 | 1.34 | works after automatic changes |
| nautical symbols | 4 | 0 | 4 | 3.29 | works after automatic changes |
| rope border | 2 | 7 | 13 | 0.87 | works after automatic changes |
| sailboat and waves | 1 | 5 | 0 | 1.66 | works after automatic changes |
| scuba and marine | 0 | 0 | 1 | 0.00 | works after automatic changes |
| skyline and animals | 2 | 4 | 0 | 1.64 | works after automatic changes |
| yacht and lower waves | 0 | 1 | 0 | 0.00 | works after automatic changes |

Orange in `waterjet-support-plan.png` is added plate support. Purple is tiny
trapped white detail converted to cutout. The production preview remains
strictly white plate / black cut.

## Fabrication assumptions

- Outside diameter: 12 in (304.8 mm).
- Minimum support/web: 2.5 mm (~0.098 in).
- Minimum independent cut area: 10 mm².
- Minimum independent cut width: 1.6 mm.
- Silhouette open/close: 0.5 / 0.65 mm.
- Kerf compensation, lead-ins, and pierce strategy remain CAM operations.
- Cut `CUT_INNER` first and `CUT_OUTER` last.
