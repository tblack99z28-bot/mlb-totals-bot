print("🚀 SHARP+ BOT STARTING...")

import requests
import time
import os

WEBHOOK = os.getenv("DISCORD_WEBHOOK")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

print("WEBHOOK:", "SET" if WEBHOOK else "MISSING")
print("ODDS API:", "SET" if ODDS_API_KEY else "MISSING")

alerted = set()
last_markets = {}

# ---------------- DISCORD ----------------
def send(msg):
    if WEBHOOK:
        try:
            requests.post(WEBHOOK, json={"content": msg})
        except:
            pass

# ---------------- ESPN ----------------
def get_espn_games():
    url = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
    try:
        return requests.get(url).json().get("events", [])
    except:
        return []

# ---------------- ODDS ----------------
def get_odds():
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "totals"
    }

    try:
        data = requests.get(url, params=params).json()
        if isinstance(data, list):
            return data
    except:
        pass

    return []

# ---------------- MATCH ----------------
def clean(name):
    return name.lower().replace(" ", "")

def find_market(home, away, odds):
    home = clean(home)
    away = clean(away)

    for game in odds:
        h = clean(game.get("home_team", ""))
        a = clean(game.get("away_team", ""))

        if home in h and away in a:
            for book in game.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market.get("key") == "totals":
                        for o in market.get("outcomes", []):
                            if "point" in o:
                                return o["point"]
    return None

# ---------------- MODEL ----------------
def project_total(runs, inning, half, outs):
    BASELINE = 8.8

    innings = inning - 1
    if half == "bottom":
        innings += 0.5
    innings += outs / 3

    if innings < 2:
        return BASELINE

    pace = runs / innings
    raw = pace * 9

    if innings < 4:
        w = 0.25
    elif innings < 6:
        w = 0.5
    elif innings < 8:
        w = 0.7
    else:
        w = 0.85

    proj = (raw * w) + (BASELINE * (1 - w))

    if proj > 15:
        proj = 15
    if proj < 3:
        proj = 3

    if inning >= 7:
        proj += 0.4
    elif inning >= 5:
        proj += 0.2

    return round(proj, 2)

# ---------------- MAIN ----------------
def check():
    espn_games = get_espn_games()
    odds = get_odds()

    for g in espn_games:
        try:
            comp = g["competitions"][0]
            teams = comp["competitors"]

            home = teams[0]["team"]["displayName"]
            away = teams[1]["team"]["displayName"]

            home_score = int(teams[0]["score"])
            away_score = int(teams[1]["score"])
            runs = home_score + away_score

            status = g["status"]["type"]["description"]
            if "In Progress" not in status:
                continue

            situation = comp.get("situation", {})
            inning = situation.get("inning", 1)
            half = situation.get("halfInning", "top")
            outs = situation.get("outs", 0)

            innings = inning - 1
            if half == "bottom":
                innings += 0.5
            innings += outs / 3

            if innings < 2.5:
                continue

            market = find_market(home, away, odds)
            if market is None:
                continue

            # 🚫 ignore broken totals
            if market < 5 or market > 15:
                continue

            model = project_total(runs, inning, half, outs)
            edge = round(model - market, 2)

            game_id = f"{home}-{away}"

            # ---------------- 📈 LINE MOVEMENT ----------------
            prev = last_markets.get(game_id)
            movement = 0

            if prev:
                movement = market - prev

            last_markets[game_id] = market

            print(f"{away} vs {home}")
            print("Runs:", runs, "| Market:", market, "| Model:", model)
            print("Edge:", edge, "| Move:", movement)

            key = f"{game_id}-{inning}"

            if key in alerted:
                continue

            # ---------------- 🎯 SIGNAL TIERS ----------------
            bet = "OVER" if edge > 0 else "UNDER"

            # 🔥 A+ PLAY
            if abs(edge) >= 1.5 and abs(movement) >= 0.5:
                send(
                    f"🔥 A+ PLAY ({bet})\n"
                    f"{away} vs {home}\n"
                    f"Inning {inning}\n\n"
                    f"Runs: {runs}\nMarket: {market}\nModel: {model}\nEdge: {edge}\nMove: {movement}"
                )
                alerted.add(key)
                continue

            # ⚡ B PLAY
            if abs(edge) >= 1.0:
                send(
                    f"⚡ B PLAY ({bet})\n"
                    f"{away} vs {home}\n"
                    f"Inning {inning}\n\n"
                    f"Runs: {runs}\nMarket: {market}\nModel: {model}\nEdge: {edge}"
                )
                alerted.add(key)

        except Exception as e:
            print("Error:", e)

# ---------------- LOOP ----------------
while True:
    try:
        print("\n=== SHARP CHECK ===")
        check()
    except Exception as e:
        print("MAIN ERROR:", e)

    time.sleep(20)
