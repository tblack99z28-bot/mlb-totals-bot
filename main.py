print("🚀 SHARP+ DEBUG BOT STARTING...")

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
        else:
            print("ODDS ERROR:", data)
    except Exception as e:
        print("ODDS EXCEPTION:", e)

    return []

# ---------------- MATCH ----------------
def clean(name):
    return name.lower().replace(" ", "")

def find_market(home, away, odds):
    home_c = clean(home)
    away_c = clean(away)

    for game in odds:
        h = clean(game.get("home_team", ""))
        a = clean(game.get("away_team", ""))

        if home_c in h and away_c in a:
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

    proj = max(3, min(15, proj))

    if inning >= 7:
        proj += 0.4
    elif inning >= 5:
        proj += 0.2

    return round(proj, 2)

# ---------------- MAIN ----------------
def check():
    espn_games = get_espn_games()
    odds = get_odds()

    print("ESPN Games:", len(espn_games))
    print("Odds Games:", len(odds))

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

            print(f"\n{away} vs {home} | Status: {status}")

            if "In Progress" not in status:
                print("⏭️ Skipped: not live")
                continue

            situation = comp.get("situation", {})
            inning = situation.get("inning", 1)
            half = situation.get("halfInning", "top")
            outs = situation.get("outs", 0)

            innings = inning - 1
            if half == "bottom":
                innings += 0.5
            innings += outs / 3

            print(f"Runs: {runs} | Inning: {inning} {half} | Outs: {outs}")
            print(f"Innings calc: {innings}")

            # 🔥 TEMP: loosen filter so you SEE games
            if innings < 1.5:
                print("⏭️ Skipped: too early")
                continue

            market = find_market(home, away, odds)

            if market is None:
                print("❌ No market match")
                continue

            print("Market found:", market)

            # loosen filter for now
            if market < 4 or market > 16:
                print("⏭️ Skipped: weird market")
                continue

            model = project_total(runs, inning, half, outs)
            edge = round(model - market, 2)

            print("Model:", model, "| Edge:", edge)

            game_id = f"{home}-{away}"

            prev = last_markets.get(game_id)
            movement = 0

            if prev:
                movement = round(market - prev, 2)

            last_markets[game_id] = market

            print("Line movement:", movement)

            key = f"{game_id}-{inning}"

            if key in alerted:
                print("⏭️ Already alerted")
                continue

            # 🔥 TEMP LOWER THRESHOLD FOR DEBUG
            if abs(edge) < 0.8:
                print("⏭️ Edge too small")
                continue

            bet = "OVER" if edge > 0 else "UNDER"

            print("🚨 SIGNAL:", bet)

            send(
                f"🚨 LIVE TOTAL ({bet})\n"
                f"{away} vs {home}\n"
                f"Inning {inning}\n\n"
                f"Runs: {runs}\nMarket: {market}\nModel: {model}\nEdge: {edge}"
            )

            alerted.add(key)

        except Exception as e:
            print("Game error:", e)

# ---------------- LOOP ----------------
while True:
    try:
        print("\n=== SHARP DEBUG CHECK ===")
        check()
    except Exception as e:
        print("MAIN ERROR:", e)

    time.sleep(20)
