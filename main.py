print("🚀 SHARP+ BOT (REALISTIC MODEL) STARTING...")

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

# ---------------- SHARP MODEL ----------------
def project_total(runs, progress):
    BASELINE = 8.8

    # 🔥 strong regression early (KEY FIX)
    if progress < 3:
        return round(BASELINE + (runs * 0.3), 2)

    pace = runs / progress
    raw = pace * 9

    # 🔥 heavier baseline weight = more realistic
    if progress < 5:
        w = 0.25
    elif progress < 7:
        w = 0.4
    else:
        w = 0.6

    proj = (raw * w) + (BASELINE * (1 - w))

    # clamp to realistic MLB totals
    proj = max(4, min(14, proj))

    return round(proj, 2)

# ---------------- MAIN ----------------
def check():
    espn_games = get_espn_games()
    odds = get_odds()

    print("Games:", len(espn_games), "| Odds:", len(odds))

    for g in espn_games:
        try:
            comp = g["competitions"][0]
            teams = comp["competitors"]

            home = teams[0]["team"]["displayName"]
            away = teams[1]["team"]["displayName"]

            home_score = int(teams[0]["score"])
            away_score = int(teams[1]["score"])
            runs = home_score + away_score

            situation = comp.get("situation", {})
            outs = situation.get("outs", 0)

            print(f"\n{away} vs {home}")
            print(f"Runs: {runs} | Outs: {outs}")

            # 🔥 estimated progress (no inning reliance)
            progress = (outs / 3) + (runs * 0.6)
            print("Progress:", round(progress, 2))

            # 🔥 filter early game noise
            if progress < 2.5:
                print("⏭️ Too early")
                continue

            market = find_market(home, away, odds)

            if market is None:
                print("❌ No market match")
                continue

            print("Market:", market)

            if market < 4 or market > 16:
                print("⏭️ Bad market")
                continue

            model = project_total(runs, progress)
            edge = round(model - market, 2)

            print("Model:", model, "| Edge:", edge)

            game_id = f"{home}-{away}"

            prev = last_markets.get(game_id)
            movement = 0
            if prev:
                movement = round(market - prev, 2)

            last_markets[game_id] = market

            print("Movement:", movement)

            key = f"{game_id}-{int(progress)}"

            if key in alerted:
                print("⏭️ Already alerted")
                continue

            # 🔥 tighter edge filter (IMPORTANT)
            if abs(edge) < 1.8:
                print("⏭️ Edge too small")
                continue

            bet = "OVER" if edge > 0 else "UNDER"

            print("🚨 SIGNAL:", bet)

            send(
                f"🚨 LIVE TOTAL ({bet})\n"
                f"{away} vs {home}\n\n"
                f"Runs: {runs}\nMarket: {market}\nModel: {model}\nEdge: {edge}"
            )

            alerted.add(key)

        except Exception as e:
            print("Game error:", e)

# ---------------- LOOP ----------------
while True:
    try:
        print("\n=== SHARP CHECK ===")
        check()
    except Exception as e:
        print("MAIN ERROR:", e)

    time.sleep(20)
