print("🚀 BOT STARTING...")

import requests
import time
from datetime import datetime
import os

print("✅ Imports loaded")

WEBHOOK = os.getenv("DISCORD_WEBHOOK")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

print("WEBHOOK:", "SET" if WEBHOOK else "MISSING")
print("ODDS API:", "SET" if ODDS_API_KEY else "MISSING")

alerted = set()
last_totals = {}

# ---------------- DISCORD ----------------
def send(msg):
    if WEBHOOK:
        try:
            requests.post(WEBHOOK, json={"content": msg})
        except Exception as e:
            print("Webhook error:", e)

# ---------------- SCHEDULE ----------------
def get_schedule():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={today}&endDate={today}"
    return requests.get(url).json()

def get_live(gamePk):
    url = f"https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live"
    return requests.get(url).json()

# ---------------- ODDS ----------------
def get_market_total(game):
    try:
        url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "totals"
        }

        data = requests.get(url, params=params).json()

        if not isinstance(data, list):
            return None

        home = game["teams"]["home"]["team"]["name"].lower()
        away = game["teams"]["away"]["team"]["name"].lower()

        totals = []

        for event in data:
            if home not in event["home_team"].lower():
                continue
            if away not in event["away_team"].lower():
                continue

            for book in event.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market.get("key") == "totals":
                        for outcome in market.get("outcomes", []):
                            if "point" in outcome:
                                totals.append(outcome["point"])

        if not totals:
            return None

        return round(sum(totals) / len(totals), 2)

    except:
        return None

# ---------------- MODEL ----------------
def projection(live):
    linescore = live["liveData"]["linescore"]

    inning = linescore.get("currentInning", 1)
    outs = linescore.get("outs", 0)

    home = linescore.get("teams", {}).get("home", {}).get("runs", 0)
    away = linescore.get("teams", {}).get("away", {}).get("runs", 0)

    total = home + away
    innings_played = inning - 1 + (outs / 3)

    if innings_played <= 0:
        return total

    proj = (total / innings_played) * 9

    # runners
    offense = linescore.get("offense", {})
    runners = sum([1 for b in ["first", "second", "third"] if offense.get(b)])
    proj += runners * 0.3

    return round(proj, 2)

# ---------------- MAIN ----------------
def check():

    schedule = get_schedule()

    for d in schedule.get("dates", []):
        print("DATE:", d.get("date"), "| Games:", len(d.get("games", [])))

        for game in d.get("games", []):

            gamePk = game["gamePk"]

            try:
                live = get_live(gamePk)
                linescore = live["liveData"]["linescore"]
            except:
                continue

            game_state = live.get("gameData", {}).get("status", {}).get("abstractGameState")
            inning = linescore.get("currentInning", 0)
            outs = linescore.get("outs", 0)

            print(f"Game {gamePk} | {game_state} | Inning {inning} | Outs {outs}")

            # 🚫 DO NOT MODEL PREVIEW
            if game_state != "Live":
                continue

            # must have some game played
            if inning < 2:
                continue

            # inning break only
            if outs != 0:
                continue

            market = get_market_total(game)
            if market is None:
                continue

            model = projection(live)
            edge = round(model - market, 2)

            print(f"MARKET: {market} | MODEL: {model} | EDGE: {edge}")

            key = f"{gamePk}-{inning}"
            if key in alerted:
                continue

            # 🔥 SHARP THRESHOLD
            if abs(edge) < 1.5:
                continue

            home = game["teams"]["home"]["team"]["name"]
            away = game["teams"]["away"]["team"]["name"]

            bet = "OVER" if edge > 0 else "UNDER"

            send(
                f"🚨 LIVE TOTAL EDGE ({bet})\n"
                f"{away} vs {home}\n"
                f"End {inning}\n\n"
                f"Model: {model}\n"
                f"Market: {market}\n"
                f"Edge: {edge}"
            )

            alerted.add(key)

# ---------------- LOOP ----------------
while True:
    try:
        print("\n=== Checking games ===")
        check()
    except Exception as e:
        print("ERROR:", e)

    time.sleep(30)
