# Offline HashLink findings

Source analyzed:

```text
Farever/hlboot.dat
```

The file is HashLink bytecode version 4 with debug metadata. Its supported-build
fingerprint is:

```text
size:  13,948,223 bytes
CRC32: cf713912
```

The reusable inspector is `tools/hlboot_inspect.py`. It follows the bytecode
layout implemented by HashLink's official `src/code.c` and does not execute the
bytecode.

## Relevant type chain

```text
ent.Entity (type 948)
  -> ent.GameObject (type 1036)
    -> ent.Unit (type 1041)
      -> ent.Hero (type 1366)
```

Important metadata:

- `ent.Entity`: `posx`, `posy`, `posz`, `rotationZ`, `position`
- `h3d.VectorImpl` (type 500): `x`, `y`, `z`
- `ent.Unit`: `target`, `isInCombat`, `attr`, `_level`, `localPosition`
- `ent.Hero`: `player`, `lockedTarget`, `autoTarget`, `name`, `weaponInHand`
- `ent.UnitAttributes` (type 1104): `health`, `maxHealth`, `healthRegen`,
  `shield`, `specialEnergy`, and the primary/secondary combat attributes
- The live Hero's `attr` field is the validated subclass `ent.HeroAttributes`
  (type 6568), whose inherited resource-field offsets come from
  `ent.UnitAttributes`.
- `UnitAttributes.lastResourceAttributesMax` is a HashLink `IntMap` cache
  maintained by `updateResAtbMax` (function 13889). It can contain the
  game-computed resource maximum, but is empty in the currently observed
  client session and therefore cannot be the sole maximum-HP source.

These are bytecode type and field indexes, not live-memory offsets. Runtime
offsets must be derived from HashLink's object-layout rules and validated
against the supported build before any value is read.

## Validated runtime anchor

For the supported `farever-2026-07-20` executable only, offline disassembly
shows that RVA `0x229c8` stores HashLink's `main_ctx` pointer. This corresponds
to the `static main_context *main_ctx` used by HashLink's launcher.

Bridge v0.3.0 validates that anchor live using narrowly bounded read-only
operations:

- read the pointer at `Farever.exe + 0x229c8`;
- read the 40-byte `main_context` structure;
- verify that its UTF-16 file name is `hlboot.dat`;
- verify that its `hl_code` and `hl_module` pointers are non-null;
- verify that the first pointer in `hl_module` equals the same `hl_code`.

This provides a deterministic route to the loaded HashLink module without a
heap scan. No game object or player value is read at this milestone.

## Validated live code metadata

Bridge v0.4.0 validates the live `hl_code` header against the offline HLB:

- version 4;
- 45,843 types;
- 30,206 globals;
- 47,342 functions;
- entrypoint 47,939.

It then follows the live type table directly to index 1366, confirms object
kind 11, and validates the UTF-16 metadata name `ent.Hero`. This resolved the
same live type address previously observed by the earlier bridge tooling, without
its broad region scan or `hl_alloc_obj` hook. The bridge stops at type metadata
and does not dereference a Hero instance.

## Validated global slots

Bridge v0.5.0 validates three object globals:

- `st.Player`: type 1358, global 889;
- `ent.Hero`: type 1366, global 380;
- `st.Group`: type 1418, global 271.

An object type's HLB `global` reference is one-based. The bridge derives
`globals_data + globals_indexes[global - 1]` and requires it to equal the
corresponding type metadata's `global_value` pointer.
All three cross-checks pass and the slots are populated in the current logged-in
session. Their contained objects are not interpreted at this milestone.

Bridge v0.6.0 additionally validates each populated value's leading `hl_type`
pointer. The values are generated class-static holders, not gameplay instances:

- `st.Player` global -> `st.$Player` (type 2772);
- `ent.Hero` global -> `ent.$Hero` (type 1884);
- `st.Group` global -> `st.$Group` (type 1638).

This prevents a static-holder address from being misreported as the current
character. Offline metadata identifies `GameApp` (type 1315) as the strongest
root candidate because it owns both `me: st.Player` and `hero: ent.Hero`.

## Validated live player root and transform

Offline decoding of `$GameApp.get` (function 11669) leads to `App.get`
(function 2926), which reads zero-based global 955 and field 5 (`$App.inst`).
Bridge v0.7.0 validates this live chain:

```text
global[955] -> $App.inst -> GameApp
                           -> field 24: me (st.Player)
                           -> field 25: hero (ent.Hero)
```

Every object pointer is checked against its exact live `hl_type`. Bridge v0.8.0
then uses HashLink's runtime field-offset table for inherited `ent.Entity`
fields 27-30 and reads the Hero's `posx`, `posy`, `posz`, and `rotationZ` as
finite 64-bit floats. This is the first actual gameplay telemetry milestone.

## Calculated HUD attributes

The authoritative local-player maximum health is available through the
persistent HUD's `ui.comp.AttributeBar`. The bridge selects a bar only when its
`atbId` is `Health` and its bound unit is the current `GameApp.hero`. Other
observed named gauges include party-member `Health`, `Oxygen`, and `Poise`, so
those remain viable future telemetry sources.

The UI discovery is bounded to depth 16 and 1024 objects. Once the local Health
gauge is found, its address is cached; ordinary 100 ms samples read that gauge
directly and repeat the tree search only when the cached object becomes invalid.
The sibling `HealthBar.shieldGauge` retains the last shield capacity after an
effect expires, so capacity alone is not current shield. The bridge combines
that normalized capacity with the gauge's inherited `h2d.Object.visible` flag:
visible reports the rounded shield points, hidden reports zero. A recorded
Priest cycle verified `0 -> 71 -> 0` without restarting the bridge.

## Direct hero class

The live combat class is the current Hero's inherited `ent.Unit.kind` string,
not the optional save-side `Player.heroData.kind` and not an inference from
weapons or skills. The extracted assets confirm the canonical identifiers
`Warrior`, `Rogue`, `Priest`, and `Mage`; live telemetry verified `Priest` for
the current local Hero.
