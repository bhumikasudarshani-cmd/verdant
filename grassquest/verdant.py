#!/usr/bin/env python3
"""Verdant: local-AI quest master that rewards real outdoor activity.
Stdlib only. Uses Ollama (open-weight models) if available, with offline fallbacks.

  python verdant.py quests --level beginner --season autumn --weather "sunny 12C"
  python verdant.py verify --quest q1 --gpx run.gpx [--photo leaf.jpg]
  python verdant.py check  voucher.json        # sponsor-side verification
"""
import argparse, base64, hashlib, hmac, json, math, os, sys, time, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
TEXT_MODEL = os.environ.get("VERDANT_TEXT_MODEL", "gemma3")
VISION_MODEL = os.environ.get("VERDANT_VISION_MODEL", "gemma3")
SECRET = os.environ.get("VERDANT_SECRET", "change-me").encode()  # sponsor-shared key (demo)
QUEST_FILE = "quests.json"

# Placeholder sponsors: swap for real ones via a PR (open catalog).
SPONSORS = {
    "bronze": {"sponsor": "TrailCo", "reward": "Finisher sticker pack"},
    "silver": {"sponsor": "RunLab", "reward": "Finisher medal shipped home"},
    "gold": {"sponsor": "GreenSole", "reward": "Swag box + a tree planted in your name"},
}

FALLBACK = [
    {"id": "q1", "title": "Foliage Stroll", "kind": "walk", "km": 3, "photo": "autumn leaves", "tier": "bronze"},
    {"id": "q2", "title": "Park Run 5K", "kind": "run", "km": 5, "photo": "", "tier": "silver"},
    {"id": "q3", "title": "Plog the Path", "kind": "walk", "km": 4, "photo": "a bag of collected litter", "tier": "gold"},
]


def ollama(model, prompt, images=None, json_mode=False):
    body = {"model": model, "prompt": prompt, "stream": False}
    if images:
        body["images"] = [base64.b64encode(open(p, "rb").read()).decode() for p in images]
    if json_mode:
        body["format"] = "json"
    req = urllib.request.Request(f"{OLLAMA}/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["response"]


def gen_quests(level, season, weather):
    prompt = (f"You are a friendly outdoor quest master. Create 3 quests for a {level} person. "
              f"Season: {season}. Weather: {weather}. Return JSON: "
              '{"quests":[{"id":"q1","title":"...","kind":"walk|run","km":number,'
              '"photo":"a SHORT noun phrase of at most 5 words, e.g. a fallen autumn leaf, or empty","tier":"bronze|silver|gold"}]}. '
              "Harder quests get higher tiers. Keep km realistic for the level.")
    try:
        quests = json.loads(ollama(TEXT_MODEL, prompt, json_mode=True))["quests"]
        assert quests and all({"id", "title", "km", "tier"} <= q.keys() for q in quests)
        return quests
    except Exception as e:  # offline or no model: still works on the trail
        print(f"(local model unavailable: {e}; using built-in quests)", file=sys.stderr)
        return FALLBACK


def haversine_km(a, b):
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def read_gpx(path):
    pts = []
    for el in ET.parse(path).iter():
        if el.tag.endswith("trkpt"):
            t = next((c.text for c in el if c.tag.endswith("time")), None)
            ts = datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp() if t else None
            pts.append((float(el.get("lat")), float(el.get("lon")), ts))
    return pts


def verify_gpx(path, quest):
    """Rule-based anti-cheat: distance, plausible human pace, no teleporting."""
    pts = read_gpx(path)
    if len(pts) < 10:
        return False, "track too short"
    km, max_kmh = 0.0, 0.0
    for a, b in zip(pts, pts[1:]):
        d = haversine_km(a, b)
        km += d
        if a[2] and b[2] and b[2] > a[2]:
            max_kmh = max(max_kmh, d / ((b[2] - a[2]) / 3600))
    if any(p[2] is None for p in pts):
        return False, "track has no timestamps"
    hours = (pts[-1][2] - pts[0][2]) / 3600
    avg = km / hours if hours > 0 else 999
    if km < quest["km"]:
        return False, f"only {km:.2f} km of {quest['km']} km"
    if avg > 20 or max_kmh > 30:
        return False, f"pace looks like a vehicle ({avg:.1f} km/h avg, {max_kmh:.1f} max)"
    return True, f"{km:.2f} km at {avg:.1f} km/h"


def verify_photo(path, subject):
    """On-device vision model check; the photo never leaves the machine."""
    try:
        subject = subject.split(".")[0][:60]  # keep it short even if the LLM wrote a paragraph
        ans = ollama(VISION_MODEL, f"Look at this image. Is there {subject} visible in it? "
                     "Start your answer with Yes or No, then give a very short reason.", [path])
        print("  vision model said:", ans.strip()[:120])
        return ans.strip().lower().startswith("yes"), "checked by " + VISION_MODEL
    except Exception as e:
        return False, f"vision model unavailable: {e}"


def sign(payload):
    msg = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(SECRET, msg, hashlib.sha256).hexdigest()


def cmd_verify(a):
    quest = next(q for q in json.load(open(QUEST_FILE)) if q["id"] == a.quest)
    ok, why = verify_gpx(a.gpx, quest)
    print(("PASS" if ok else "FAIL"), "route:", why)
    if ok and quest.get("photo"):
        if not a.photo:
            return print("FAIL photo required:", quest["photo"])
        ok, why = verify_photo(a.photo, quest["photo"])
        print(("PASS" if ok else "FAIL"), "photo:", why)
    if not ok:
        return
    payload = {"quest": quest["id"], "title": quest["title"], "tier": quest["tier"],
               "reward": SPONSORS[quest["tier"]], "track_sha256": hashlib.sha256(open(a.gpx, "rb").read()).hexdigest(),
               "issued": int(time.time())}
    voucher = {"payload": payload, "sig": sign(payload)}
    json.dump(voucher, open("voucher.json", "w"), indent=2)
    print(f"Voucher saved: voucher.json -> {payload['reward']['sponsor']}: {payload['reward']['reward']}")


def cmd_check(a):
    v = json.load(open(a.voucher))
    print("VALID" if hmac.compare_digest(v["sig"], sign(v["payload"])) else "INVALID")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("quests")
    q.add_argument("--level", default="beginner")
    q.add_argument("--season", default="autumn")
    q.add_argument("--weather", default="mild")
    v = sub.add_parser("verify")
    v.add_argument("--quest", required=True)
    v.add_argument("--gpx", required=True)
    v.add_argument("--photo")
    c = sub.add_parser("check")
    c.add_argument("voucher")
    a = ap.parse_args()
    if a.cmd == "quests":
        qs = gen_quests(a.level, a.season, a.weather)
        json.dump(qs, open(QUEST_FILE, "w"), indent=2)
        for x in qs:
            print(f"[{x['id']}] {x['title']}: {x['km']} km ({x['tier']}) {x.get('photo', '')}")
    elif a.cmd == "verify":
        cmd_verify(a)
    else:
        cmd_check(a)


if __name__ == "__main__":
    main()
