#  Verdant

A local-AI quest master that gets you off the screen: finish an outdoor quest, get a verified voucher, and sponsors ship you a medal or swag.

## Run it
```bash
ollama pull gemma3   # one open-weight model for text and vision
python verdant.py quests --level beginner --season autumn --weather "sunny 12C"
python verdant.py verify --quest q1 --gpx my_walk.gpx --photo leaf.jpg
python verdant.py check voucher.json          # sponsor-side
```
No pip installs needed. If Ollama is offline, built-in quests are used.

## How it works
1. **Quest generation:** a local LLM writes quests from your level, season and weather.
2. **Route check:** a GPX track is validated for distance, human pace and teleporting (rule-based, no AI needed).
3. **Photo check:** an on-device vision model confirms the proof photo (leaf, bird, litter bag).
4. **Voucher:** an HMAC-signed JSON a sponsor can verify and ship against. Only a track hash is shared, never your location.

## Why open matters
- Works offline on the trail, no signal needed.
- Photos and GPS stay on your device.
- Swap models with one env var (`VERDANT_TEXT_MODEL`, `VERDANT_VISION_MODEL`).
- Free to run, and the sponsor catalog is open for PRs.

## Hacktoberfest ideas (good first issues)
- Real sponsor catalog in `sponsors.json`
- Strava/Garmin `.fit` import
- Local TTS audio guide (Piper) so the screen stays in your pocket
- Birdsong quests with BirdNET
- Public-key signed vouchers instead of a shared HMAC key
- Mobile PWA front end
