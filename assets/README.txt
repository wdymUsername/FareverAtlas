Project-local loose assets.

Layout:
  map/     world texture, calibration, FOW regions + pattern
  data/    CastleDB / prefab extracts (JSON)
  ui/      chrome SVGs, class/currency/marker/planner icons
  fonts/   Noto Sans (gitignored; prepared by farever setup)
  unused/  local park for superseded originals (gitignored; not shipped)

Raster UI/map bitmaps prefer lossless .webp (SVG stays for chrome). Game-tree
fallbacks may still be .png (e.g. Farever's data/icons/activities.png).

Supported files:
- map/w1_siagarta.webp
- map/w1_siagarta.json
- map/w1_siagarta_fow.json
- map/pattern_fog_of_war_512.webp
- data/w1_siagarta/pois.json
- data/w1_siagarta/critter_spawns.json
- data/w1_siagarta/patrol_paths.json
- data/display_names.json
- data/unit_traits.json
- data/currency_caps.json
- ui/markers/activities.webp
- ui/markers/player_cursor.webp
- ui/markers/rift_icon.webp
- ui/markers/red_orb.webp
- ui/markers/plant.webp
- ui/markers/ore.webp
- ui/currency/currency_gold.webp
- ui/currency/currency_craft.webp
- ui/currency/currency_demonic_soul.webp
- ui/currency/currency_nightblood.webp
- ui/classes/classBlank.webp
- ui/classes/classPriest.webp
- ui/classes/classMage.webp
- ui/classes/classWarrior.webp
- ui/classes/classRogue.webp
- ui/chrome/*.svg (window chrome, help/settings/reload, fog, collect, …)
- ui/planner/planner_talent_placeholder_{gold,silver}.svg
- fonts/NotoSans-Variable.ttf (or NotoSans-Regular/Medium/SemiBold/Bold.ttf)
- fonts/OFL.txt

The Siagarta map texture and tile-grid calibration live under map/. Rebuild
them from Farever's res.map.pak with:

  python3 -m venv tools/.venv
  tools/.venv/bin/pip install -r tools/requirements.txt
  tools/.venv/bin/python tools/build_map_assets.py --scale 0.35

World JSON and marker icons live under data/ and ui/ so Atlas does not depend
on files installed into the Farever game folder. Refresh POI world coordinates
from extracted map prefabs with:

  python tools/extract_pois.py

Wild critter spawn points (authored map spawners, not live entities) are in
data/w1_siagarta/critter_spawns.json. Rebuild from extracted res.map + data.cdb:

  python tools/extract_critter_spawns.py

Ranked/spark patrol polylines are in data/w1_siagarta/patrol_paths.json:

  python tools/extract_patrol_paths.py

Unit trait kind lists are in data/unit_traits.json:

  python tools/extract_unit_traits.py

In-game unit / gatherable tooltip labels are in data/display_names.json:

  python tools/extract_display_names.py

FOW clear regions + pattern WebP:

  tools/.venv/bin/python tools/build_fow_regions.py

UI fonts are prepared by `python -m farever_atlas.fonts` (also run by
./farever setup, farever.bat setup, and the Windows packaging scripts). That
command copies Noto Sans from the machine when available, otherwise downloads
the Google Fonts variable build into fonts/.
