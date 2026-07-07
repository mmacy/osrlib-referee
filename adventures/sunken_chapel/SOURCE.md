# The Sunken Chapel of Neth

An original B/X adventure module for 3–5 characters of levels 1–2. Public domain (CC0).
This is the **source document** the bundle in this directory was compiled from; it is
kept alongside the compiled `adventure.json` / `prose.json` / `manifest.json` as
provenance and as the reference for the visual map-diff review gate.

## Background

Neth was a minor river-god whose chapel drowned when the old dam failed a century ago.
The waters have since receded, leaving a silt-choked shrine below the flood-line. The
cult that tended Neth did not all get out. Something down there still keeps the hours.

## The map

Cells are 10-foot squares; north is up. Doors are marked `+`, open passages `=` or `|`.

```
        col 0    1    2    3    4
       +----+----+----+----+----+
 row 0 |    | 3 == 3 == . ++ 4  |
       +----+----+--+-+----+----+
 row 1 | 2 == . == J == . == 5  |
       +----+----+--+-+----+----+
 row 2 |    |    | . |    |    |
       +----+----+--+-+----+----+
 row 3 |    |    | 1 |    |    |
       +----+----+----+----+----+

 1 Broken stair (entrance)     4 Reliquary  (door west; treasure + trap)
 2 Font hall  (open west)      5 Ossuary    (open west; the guardians)
 3 Nave (two cells)            J unkeyed junction; . unkeyed corridor
```

From the broken stair (1) a silt passage runs north to a junction (J). West of the
junction lies the font hall (2). A stuck door north of the junction opens into the nave
(3), whose east passage runs to a second door into the reliquary (4). East of the
junction, a passage runs to the ossuary (5).

## Keyed areas

### 1. Broken stair

> The stair from the surface ends in a silt-choked landing, ankle-deep in cold water.
> A single passage leads north into the dark. The air smells of river-mud and old incense.

This is where the party descends and the only cell from which they can leave for the
surface. No encounter.

### 2. Font hall

> A shallow basin of black, motionless water fills the middle of this side chamber. Its
> surface does not ripple, even when the floor is disturbed. Faint votive niches, emptied
> long ago, line the walls.

**The Black Font.** A character who drinks from or scries in the font sees a fragmentary
vision of the chapel as it drowned — useful lore, no mechanical effect the rules cover.
This has no SRD analogue; the referee adjudicates it live (a vision, a saving throw
against a moment of despair, referee's call). *(Escape-hatch beat.)*

### 3. Nave

> Two rows of shattered pews face a silt-caked altar. Water has warped everything to a
> grey sameness. Behind the altar, the wall curves away into a low apse where the gold
> still catches what little light there is.

The nave is the hub. The curved apse behind the altar is the approach to the reliquary
(4). No encounter, but the guardians in the ossuary (5) will hear a loud fight here.

### 4. Reliquary

> A niche of flaking gold leaf holds a single iron casket, its lid sealed with wax gone
> black with age.

**The casket** holds a vial of holy water, a silver dagger left as an offering, 120 gp
in old temple coin, and **the Tear of Neth** — a river-blue gem worth 500 gp that is said
to show the bearer glimpses of moving water far away. The gem's scrying is a legendary
property with no SRD analogue; treat its 500 gp as its stock value and adjudicate any
scrying live. *(Escape-hatch beat.)*

**Trap.** The casket lid is needled: opening it without care drives a spring-dart into
the hand (1d4 damage). *(Treasure trap, trigger = open.)*

### 5. Ossuary

> Bone-dust lies thick over a floor of stacked skulls. As the light falls across them,
> two robed shapes at the back of the chamber straighten, and turn, and come.

**Two Gravebound Acolytes** guard the ossuary — see the appendix.

## Appendix: new monster

### Gravebound Acolyte

The dead of Neth's cult, risen and shambling, still wearing the rotted robes of their
order. They move slowly and strike with cold hands; they do not speak, though a dry
chant sometimes rattles in their throats. They carry no treasure.

| Stat | Value |
|---|---|
| Armor Class | 12 (leather-equivalent, rotted robes) |
| Hit Dice | 2 |
| Movement | 90' (30') — slow, shambling |
| Attacks | 1 (cold fist) |
| Damage | 1d8 |
| Morale | 12 (undead, never flees) |
| Special | None beyond undead immunities |

*Design note for the compiler:* the Gravebound Acolyte is a plain 2-HD slow undead with
no special attack — mechanically an SRD **zombie**. Reskin it to `zombie`; the cult
theming is narration only.
