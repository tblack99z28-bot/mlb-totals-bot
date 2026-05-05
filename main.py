print("🚀 SHARP LIVE TOTALS BOT STARTING...")

import requests
import time
import os

WEBHOOK = os.getenv("DISCORD_WEBHOOK")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

print("WEBHOOK:", "SET" if WEBHOOK else "MISSING")
print("ODDS API:", "SET" if ODDS_API_KEY else "MISSING")

alerted = set()

# ---------------- DISCORD ----------------
def send(msg):
    if WEBHOOK:
        try:
            requests.post(WEBHOOK, json={"content": msg})
        except:
            pass

# ---------------- ESPN LIVE DATA ----------------
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

# ---------------- MATCH TEAMS ----------------
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

# ---------------- 🔥 FINAL SHARP MODEL ----------------
def project_total(runs, inning, half, outs):
    BASELINE = 8.8

    # innings played
    innings = inning - 1
    if half == "bottom":
        innings += 0.5
    innings += outs / 3

    # 🛑 ignore early chaos
    if innings < 2:
        return round(BASELINE + (runs * 0.2), 2)

    # raw pace
    pace = runs / innings
    raw_proj = pace * 9

    # dynamic weighting
    if innings < 4:
        weight = 0.25
    elif innings < 6:
        weight = 0.5
    elif innings < 8:
        weight = 0.7
    else:
        weight = 0.85

    proj = (raw_proj * weight) + (BASELINE * (1 - weight))

    # cap unrealistic outputs
    if proj > 15:
        proj = 15
    if proj < 3:
        proj = 3

    # late game boost
    if inning >= 7:
        proj += 0.4
    elif inning >= 5:
        proj += 0.2

    return round(proj, 2)

# ---------------- MAIN ----------------
def check():
    espn_games = get_espn_games()
    odds = get_odds()

    print("Games:", len(espn_games))

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

            # only live games
            if "In Progress" not in status:
                continue

            situation = comp.get("situation", {})
            inning = situation.get("inning", 1)
            half = situation.get("halfInning", "top")
            outs = situation.get("outs", 0)

            print(f"{away} vs {home} | Runs: {runs} | Inning {inning} {half} | Outs {outs}")

            market = find_market(home, away, odds)

            if market is None:
                print("No market found")
                continue

            model = project_total(runs, inning, half, outs)
            edge = round(model - market, 2)

            print("MARKET:", market, "| MODEL:", model, "| EDGE:", edge)

            key = f"{home}-{away}-{inning}"

            if key in alerted:
                continue

            # 🛑 no bets early
            if inning < 3:
                continue

            # 🔥 sharp threshold
            if abs(edge) < 1.0:
                continue

            bet = "OVER" if edge > 0 else "UNDER"

            send(
                f"🚨 LIVE TOTAL EDGE ({bet})\n"
                f"{away} vs {home}\n"
                f"Inning {inning} {half}\n\n"
                f"Runs: {runs}\n"
                f"Market: {market}\n"
                f"Model: {model}\n"
                f"Edge: {edge}"
            )

            alerted.add(key)

        except Exception as e:
            print("Game error:", e)

# ---------------- LOOP ----------------
while True:
    try:
        print("\n=== CHECKING LIVE MLB ===")
        check()
    except Exception as e:
        print("ERROR:", e)

    time.sleep(20)
