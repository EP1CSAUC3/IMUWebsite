# Waterjet manufacturability assessment

## Result

The old outside black circle has been removed and replaced by one exact CAD
outer profile. A **15 mm solid plate rim** now separates
the rope artwork from that profile. White is retained plate; black is cut out.

The artwork did **not** work as supplied: it contained
104 floating white material islands.
The cut-ready version has one connected material component. It uses
88 supports at 3 mm nominal
width and removes 16 tiny trapped white
details plus 7 undersized cut details.

No complete object needs removal at this size. The generated supports resolve every retained floating area; only tiny uncuttable details were removed.

## Object review

| Object/area | Supports | Tiny white details removed | Tiny cuts removed | Longest support (mm) | Result |
|---|---:|---:|---:|---:|---|
| airplane and route | 1 | 0 | 0 | 4.14 | works after automatic changes |
| captain portrait | 24 | 5 | 0 | 2.85 | works after automatic changes |
| flag and palms | 1 | 1 | 0 | 2.44 | works after automatic changes |
| globe and hiker | 2 | 1 | 1 | 2.44 | works after automatic changes |
| mountains and forest | 0 | 1 | 0 | 0.00 | works after automatic changes |
| nautical symbols | 12 | 0 | 0 | 4.81 | works after automatic changes |
| quote and dividers | 1 | 0 | 0 | 2.44 | works after automatic changes |
| rope border | 3 | 0 | 6 | 5.86 | works after automatic changes |
| skyline and animals | 26 | 3 | 0 | 4.61 | works after automatic changes |
| tropical island | 0 | 5 | 0 | 0.00 | works after automatic changes |
| yacht and lower waves | 18 | 0 | 0 | 5.37 | works after automatic changes |

Areas absent from the table had no detected floating material or rejected cut
component. Orange in `waterjet-support-plan.png` shows added plate supports;
purple shows tiny trapped white details converted to cutout. The production
preview remains strictly white plate / black cut.

## Fabrication assumptions

- Outside diameter: 500 mm.
- Minimum support/web: 3 mm.
- Minimum independent cut area: 1.5 mm².
- Minimum independent cut width: 1 mm.
- Kerf compensation, lead-ins, and pierce strategy remain CAM operations.
- Cut `CUT_INNER` first and `CUT_OUTER` last.

Scaling the design down also scales every support. Re-run this assessment at
the intended diameter and have the operator simulate the toolpath before
cutting stock.
