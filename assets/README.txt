Project-local loose assets only.

Supported files:
- map/w1_siagarta.webp
- map/w1_siagarta.json
- pois_W1_Siagarta.json
- critter_spawns_W1_Siagarta.json (wild companion spawn points from map prefabs)
- activities.png
- rift_icon_128.png
- currency_gold.png
- currency_craft.png
- currency_demonic_soul.png
- currency_nightblood.png
- currency_caps.json (from data.cdb item.props.currency.max)
- unit_traits.json (critter / Spark / Elite / Boss / Miniboss / Unique kind lists from CastleDB unit sheet)
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

Unit trait kind lists (companions, Spark rares, Elite / Boss / Miniboss /
Unique specials) are in unit_traits.json. Rebuild from extracted data.cdb with:

  python tools/extract_unit_traits.py

UI fonts are prepared by `python -m farever_atlas.fonts` (also run by
./farever setup, farever.bat setup, and the Windows packaging scripts). That
command copies Noto Sans from the machine when available, otherwise downloads
the Google Fonts variable build into fonts/.
