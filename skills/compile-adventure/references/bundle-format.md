# Bundle format reference

A bundle is a **directory** of three JSON files. This is the exact contract
[`load_bundle`][osrlib_referee_mcp.bundle.load_bundle] reads and `validate_bundle`
enforces. Write all three; there is **no `catalog.json`**.

## `adventure.json`

The `Adventure.model_dump(mode="json")` of an `osrlib` `Adventure` — the whole spec:
`name`, `description`, `town`, and `dungeons` (each with `levels`, and each level's
`width`/`height`/`entrance`/`edges`/`areas`/`wandering`). The osrlib content model
(`osrlib.crawl.adventure`, `osrlib.crawl.dungeon`) is authoritative for every field;
read its source when a field is unclear. Key rules the compiler must honor:

- **Every `template_id` and `item_id` is a stock SRD id.** Reskins are already resolved
  to SRD templates here — this file never carries a non-SRD id.
- **`edges` keys are canonical.** Each is `"{x},{y}:north"` or `"{x},{y}:west"` only
  (an edge has exactly one entry; a cell's south edge is its neighbour's north). Compute
  them with `bundletool edge-key`, never by hand. A key naming a boundary edge (its
  neighbour off-grid) is a dead entry `validate_bundle` rejects.
- **An edge absent from the map is a wall.** Declare only passages (`{"kind": "open"}`)
  and doors (`{"kind": "door", "door": {...}}`).
- **`AreaSpec.id` is the stable prose handle.** Assign each keyed area a short, unique id;
  `prose.json` keys against it.

A minimal shape (one level, one door, one keyed encounter):

```json
{
  "name": "The Example Delve",
  "description": "A short crawl.",
  "town": {"name": "Hearth", "travel_turns": {"example_dungeon": 1}},
  "dungeons": [
    {
      "id": "example_dungeon",
      "name": "The Example Delve",
      "levels": [
        {
          "number": 1,
          "width": 3,
          "height": 1,
          "entrance": [0, 0],
          "edges": {
            "1,0:west": {"kind": "door", "door": {"kind": "normal"}},
            "2,0:west": {"kind": "open"}
          },
          "areas": [
            {"id": "mouth", "name": "Cave mouth", "description": "A dark opening.", "cells": [[0, 0]]},
            {
              "id": "guardroom",
              "name": "Guard room",
              "cells": [[2, 0]],
              "encounter": {"monsters": [{"template_id": "skeleton", "count_fixed": 3}]}
            }
          ],
          "wandering": {"chance_in_six": 0}
        }
      ]
    }
  ]
}
```

## `prose.json`

`{area_id: {read_aloud, referee_notes}}`, keyed by `AreaSpec.id`, plus the reserved key
`"town"`. `read_aloud` is delivered verbatim in play; `referee_notes` stays with the
referee. Every key must be a real area id or `"town"` (`validate_bundle` flags a key that
is neither). Prose sets the scene — it **never** renames a reskinned creature.

```json
{
  "town": {"read_aloud": "Hearth is a ring of huts.", "referee_notes": "Safe ground."},
  "mouth": {"read_aloud": "A cold wind breathes from the dark.", "referee_notes": "The entrance cell."},
  "guardroom": {
    "read_aloud": "Bones stir in the corners and rise.",
    "referee_notes": "Three skeletons. Narrate by appearance, never 'skeleton'."
  }
}
```

## `manifest.json`

```json
{
  "bundle_id": "example_delve",
  "name": "The Example Delve",
  "description": "A short crawl.",
  "osrlib_version": "1.1.0",
  "license": "CC0-1.0",
  "approximations": {
    "reskins": [
      {"source_name": "Barrow Wight", "template_id": "skeleton", "area_id": "guardroom"}
    ],
    "geometry": [
      "Level 1's circular cavern is approximated as a 3x3 block of cells."
    ],
    "escape_hatch": [
      "The Whispering Idol's mind-control beat has no SRD analogue; run it live via RollDice + SetFlag."
    ]
  }
}
```

- `bundle_id` — a filesystem-safe slug (`^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$`). It is the
  discovery key, the `session_new` argument, **and** the default save-slot name, so it
  must be unique and stable.
- `osrlib_version` — the engine version the bundle was compiled and validated against
  (use `bundletool`'s environment; it prints on validate). Provenance only.
- `license` — the source module's license (`CC0-1.0` for original content).
- `approximations` — always present, with all three lists (empty is fine). This is the
  audit log; every reskin, geometry approximation, and escape-hatch beat gets an entry.
  A `reskins` entry is `{source_name, template_id, area_id}`: the module called it
  *source_name*; it is statted and named as SRD *template_id* in *area_id*.
