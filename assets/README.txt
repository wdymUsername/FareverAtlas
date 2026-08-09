Project-local loose assets only.

Supported files:
- map/w1_siagarta.webp
- map/w1_siagarta.json
- pois_W1_Siagarta.json
- critter_spawns_W1_Siagarta.json (wild companion spawn points from map prefabs)
- patrol_paths_W1_Siagarta.json (authored patrol splines for ranked/spark spawners)
- activities.png
- rift_icon_128.png
- currency_gold.png
- currency_craft.png
- currency_demonic_soul.png
- currency_nightblood.png
- currency_caps.json (from data.cdb item.props.currency.max)
- unit_traits.json (critter / Spark / Elite / Boss / Miniboss / Unique kind lists from CastleDB unit sheet)
- display_names.json (unit + gatherable in-game labels from CastleDB for map tooltips)
- redOrb.webp
- plant.webp
- ore.webp
- classBlank.webp
- classPriest.webp
- classMage.webp
- classWarrior.webp
- classRogue.webp
- fonts/NotoSans-Variable.ttf (or NotoSans-Regular/Medium/SemiBold/Bold.ttf)
- fonts/OFL.txt

The Siagarta map texture and tile-grid calibration live under map/. Rebuild
them from Farever's res.map.pak with:

  .venv/bin/pip install -r tools/requirements.txt
  .venv/bin/python tools/build_map_assets.py

POI dataset and activity icon atlas stay at the assets root so Atlas does not
depend on files installed into the Farever game folder.

Wild critter spawn points (authored map spawners, not live entities) are in
critter_spawns_W1_Siagarta.json. Rebuild from extracted res.map + data.cdb with:

  python tools/extract_critter_spawns.py

Ranked/spark patrol polylines (spawner path refs resolved to world spline
samples) are in patrol_paths_W1_Siagarta.json. Rebuild with:

  python tools/extract_patrol_paths.py

Unit trait kind lists (companions, Spark rares, Elite / Boss / Miniboss /
Unique specials) are in unit_traits.json. Rebuild from extracted data.cdb with:

  python tools/extract_unit_traits.py

In-game unit / gatherable tooltip labels (e.g. ``2 · Green Slime``,
``Copper Ore · Large``) are in display_names.json. Rebuild with:

  python tools/extract_display_names.py

UI fonts are prepared by `python -m farever_atlas.fonts` (also run by
./farever setup, farever.bat setup, and the Windows packaging scripts). That
command copies Noto Sans from the machine when available, otherwise downloads
the Google Fonts variable build into fonts/.
