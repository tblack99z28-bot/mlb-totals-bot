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
        except:
            pass

# ---------------- SCHEDULE ----------------
def get_games():
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}"
    return requests.get(url).json()

def get_live(gamePk):
    ts = int(time.time())
    url = f"https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live?_={ts}"
    return requests.get(url).json()

# ---------------- 🔥 LIVE DETECTION (NO PLAYS) ----------------
def is_live(linescore):
    try:
        inning = linescore.get("currentInning", 0)
        outs = linescore.get("outs", 0)

        home = linescore.get("teams", {}).get("home", {}).get("runs", 0)
        away = linescore.get("teams", {}).get("away", {}).get("runs", 0)

        # 🔥 ANY REAL GAME SIGNAL
        if inning >= 1:
            return True
        if outs > 0:
            return True
        if home > 0 or away > 0:
            return True

    except:
        pass

    return False

# ---------------- MODEL ----------------
def projection(linescore):
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
                linescore = live.get("liveData", {}).get("linescore", {})
            except:
                continue

            inning = linescore.get("currentInning", 0)
            outs = linescore.get("outs", 0)

            print(f"Game {gamePk} | Inning {inning} | Outs {outs}")

            if not is_live(linescore):
                continue

            print(f"🔥 LIVE GAME: {gamePk} | Inning {inning} | Outs {outs}")

            if inning < 1:
                continue

            if outs not in [0, 2]:
                continue

            model = projection(linescore)
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
