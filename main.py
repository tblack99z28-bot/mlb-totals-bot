print("🚀 BOT STARTING...")

import requests
import time
from datetime import datetime
import os

WEBHOOK = os.getenv("DISCORD_WEBHOOK")

print("WEBHOOK:", "SET" if WEBHOOK else "MISSING")

alerted = set()

# ---------------- DISCORD ----------------
def send(msg):
    if WEBHOOK:
        try:
            requests.post(WEBHOOK, json={"content": msg})
        except Exception as e:
            print("Webhook error:", e)

# ---------------- SCHEDULE ----------------
def get_games():
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}"
    return requests.get(url).json()

# ---------------- 🔥 FIXED LIVE FEED (CACHE BUSTER) ----------------
def get_live(gamePk):
    ts = int(time.time())  # 🔥 prevents caching

    url = f"https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live?_={ts}"

    headers = {
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }

    return requests.get(url, headers=headers).json()

# ---------------- 🔥 TRUE LIVE DETECTION ----------------
def is_live(live):
    try:
        plays = live.get("liveData", {}).get("plays", {}).get("allPlays", [])

        if len(plays) > 0:
            return True

    except:
        pass

    return False

# ---------------- MODEL ----------------
def projection(live):
    linescore = live["liveData"]["linescore"]

    inning = linescore.get("currentInning", 1)
    outs = linescore.get("outs", 0)

    home = linescore.get("teams", {}).get("home", {}).get("runs", 0)
    away = linescore.get("teams", {}).get("away", {}).get("runs", 0)

    total = home + away
    innings = inning - 1 + (outs / 3)

    if innings <= 0:
        return total

    return round((total / innings) * 9, 2)

# ---------------- MAIN ----------------
def check():
    data = get_games()

    for d in data.get("dates", []):
        print("DATE:", d["date"], "| Games:", len(d["games"]))

        for game in d["games"]:
            gamePk = game["gamePk"]

            try:
                live = get_live(gamePk)
            except:
                continue

            # 🔥 DEBUG: check plays
            plays = live.get("liveData", {}).get("plays", {}).get("allPlays", [])
            if len(plays) > 0:
                print(f"🔥 Game {gamePk} LIVE | Plays: {len(plays)}")

            if not is_live(live):
                continue

            linescore = live["liveData"]["linescore"]

            inning = linescore.get("currentInning", 0)
            outs = linescore.get("outs", 0)

            print(f"🔥 LIVE GAME: {gamePk} | Inning {inning} | Outs {outs}")

            if inning < 1:
                continue

            if outs not in [0, 2]:
                continue

            model = projection(live)
            print("MODEL:", model)

            key = f"{gamePk}-{inning}"
            if key in alerted:
                continue

            send(
                f"⚡ LIVE GAME DETECTED\n"
                f"Game: {gamePk}\n"
                f"Inning: {inning}\n"
                f"Model Total: {model}"
            )

            alerted.add(key)

# ---------------- LOOP ----------------
while True:
    try:
        print("\n=== Checking games ===")
        check()
    except Exception as e:
        print("ERROR:", e)

    time.sleep(10)
