Project-local loose assets only.

Supported files:
- map/w1_siagarta.webp
- map/w1_siagarta.json
- pois_W1_Siagarta.json
- activities.png
- rift_icon_128.png
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

UI fonts are prepared by `python -m farever_atlas.fonts` (also run by
./farever setup, farever.bat setup, and the Windows packaging scripts). That
command copies Noto Sans from the machine when available, otherwise downloads
the Google Fonts variable build into fonts/.
