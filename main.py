print("🚀 SPORTSBOOK BOT STARTING...")

import requests
import time
import os

WEBHOOK = os.getenv("DISCORD_WEBHOOK")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

print("WEBHOOK:", "SET" if WEBHOOK else "MISSING")
print("ODDS API:", "SET" if ODDS_API_KEY else "MISSING")

alerted = set()
last_scores = {}

# ---------------- DISCORD ----------------
def send(msg):
    if WEBHOOK:
        try:
            requests.post(WEBHOOK, json={"content": msg})
        except:
            pass

# ---------------- FETCH ODDS ----------------
def get_odds():
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"

    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "totals",
        "oddsFormat": "decimal"
    }

    try:
        data = requests.get(url, params=params).json()

        if not isinstance(data, list):
            print("ODDS ERROR:", data)
            return []

        return data

    except Exception as e:
        print("Odds fetch error:", e)
        return []

# ---------------- MODEL ----------------
def estimate_total(game, market_total):
    game_id = game["id"]

    # fake "progress" based on score change
    home_score = game.get("scores", {}).get("home", 0)
    away_score = game.get("scores", {}).get("away", 0)

    total_runs = home_score + away_score

    prev = last_scores.get(game_id, 0)
    last_scores[game_id] = total_runs

    # 🔥 estimate pace
    pace = total_runs - prev

    # base projection
    projection = market_total

    # adjust for scoring pace
    projection += pace * 1.5

    return round(projection, 2), total_runs

# ---------------- MAIN ----------------
def check():
    games = get_odds()

    print("Games pulled:", len(games))

    for game in games:
        home = game.get("home_team")
        away = game.get("away_team")

        bookmakers = game.get("bookmakers", [])

        market_total = None

        for book in bookmakers:
            for market in book.get("markets", []):
                if market.get("key") == "totals":
                    for outcome in market.get("outcomes", []):
                        if "point" in outcome:
                            market_total = outcome["point"]
                            break

        if market_total is None:
            continue

        model, runs = estimate_total(game, market_total)

        edge = round(model - market_total, 2)

        print(f"{away} vs {home}")
        print("RUNS:", runs, "| MARKET:", market_total, "| MODEL:", model, "| EDGE:", edge)

        key = f"{game['id']}"

        if key in alerted:
            continue

        # 🔥 thresholds
        if abs(edge) < 0.7:
            continue

        bet = "OVER" if edge > 0 else "UNDER"

        send(
            f"🚨 LIVE TOTAL EDGE ({bet})\n"
            f"{away} vs {home}\n\n"
            f"Runs: {runs}\n"
            f"Market: {market_total}\n"
            f"Model: {model}\n"
            f"Edge: {edge}"
        )

        alerted.add(key)

# ---------------- LOOP ----------------
while True:
    try:
        print("\n=== Checking sportsbook data ===")
        check()
    except Exception as e:
        print("ERROR:", e)

    time.sleep(20)
