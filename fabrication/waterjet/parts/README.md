# Fusion multi-part import pack

These files split the 12 inch waterjet geometry so toolpaths can be built in
smaller pieces on a slow PC. Every file uses the **same absolute origin and the
same 12 inch / 304.8 mm canvas**, so imports stack and align.

## How to import in Fusion 360

1. Create one component for the plate.
2. Import each `waterjet-part-*.dxf` (preferred) or `.svg` into that component.
3. Place every import at the **same origin** with no extra move/rotate/scale.
4. Confirm the grey `ALIGN` circle from each inner part lands on the same rim.
5. Create toolpaths per part from `CUT_INNER` only.
6. Import / toolpath `00-outer-profile` **last**. Use only `CUT_OUTER`.
7. Do **not** cut the `ALIGN` layer. It is a registration reference only.

Suggested order: `01` → `02` → `03` → `04` → `05` → `06` → `00`.

## Parts

| Part | Inner cuts | Outer profile | Contents |
|---|---:|---|---|
| `00-outer-profile` | 0 | yes | Outside plate profile only. Cut this last. |
| `01-rope-border` | 39 | no | Braided rope border cutouts. |
| `02-quote-and-dividers` | 34 | no | Central quote lettering and divider cuts. |
| `03-top-captain-mountains` | 2 | no | Captain portrait plus mountains and forest. |
| `04-right-nautical-plane` | 9 | no | Airplane, nautical symbols, and tropical island. |
| `05-left-globe-hiker` | 6 | no | Globe, hiker, flag, and left palms. |
| `06-bottom-scene` | 7 | no | Skyline, animals, yacht, sailboat, and lower waves. |

Full combined geometry remains in `../waterjet-ready.dxf` and
`../waterjet-ready.svg` if you want one file later.
