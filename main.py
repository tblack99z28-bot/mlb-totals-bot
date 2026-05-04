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

# 🔥 NEW: odds cache (prevents quota burn)
odds_cache = {}
odds_last_fetch = 0

# ---------------- DISCORD ----------------
def send(msg):
    if WEBHOOK:
        try:
            requests.post(WEBHOOK, json={"content": msg})
        except Exception as e:
            print("Webhook error:", e)

# ---------------- HELPERS ----------------
def normalize(name):
    return name.lower().replace(" ", "").replace(".", "").replace("-", "")

# ---------------- SCHEDULE ----------------
def get_schedule():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={today}&endDate={today}"
    return requests.get(url).json()

def get_live(gamePk):
    url = f"https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live"
    return requests.get(url).json()

# ---------------- FAST LIVE DETECTION ----------------
def is_game_live(live):
    try:
        game = live.get("gameData", {})
        linescore = live.get("liveData", {}).get("linescore", {})

        state = game.get("status", {}).get("abstractGameState")
        detailed = game.get("status", {}).get("detailedState")

        if state == "Live":
            return True

        if linescore.get("outs", 0) > 0:
            return True

        if linescore.get("teams", {}).get("home", {}).get("runs", 0) > 0:
            return True

        if linescore.get("teams", {}).get("away", {}).get("runs", 0) > 0:
            return True

        if linescore.get("defense", {}).get("pitcher"):
            return True

        if linescore.get("offense", {}).get("batter"):
            return True

        if detailed in ["In Progress", "Review", "Manager Challenge"]:
            return True

    except:
        pass

    return False

# ---------------- ODDS FETCH (1 CALL ONLY) ----------------
def fetch_all_odds():
    global odds_cache, odds_last_fetch

    if time.time() - odds_last_fetch < 60:
        return odds_cache

    try:
        url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "totals"
        }

        data = requests.get(url, params=params).json()

        if not isinstance(data, list):
            print("ODDS ERROR:", data)
            return odds_cache

        new_cache = {}

        for event in data:
            home = normalize(event.get("home_team", ""))
            away = normalize(event.get("away_team", ""))

            totals = []

            for book in event.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market.get("key") == "totals":
                        for outcome in market.get("outcomes", []):
                            if "point" in outcome:
                                totals.append(outcome["point"])

            if totals:
                avg = round(sum(totals) / len(totals), 2)
                key = f"{home}-{away}"
                new_cache[key] = avg

        odds_cache = new_cache
        odds_last_fetch = time.time()

        print("✅ ODDS UPDATED:", len(odds_cache), "games")

    except Exception as e:
        print("Odds fetch error:", e)

    return odds_cache

# ---------------- GET MARKET ----------------
def get_market_total(game):
    odds = fetch_all_odds()

    home = normalize(game["teams"]["home"]["team"]["name"])
    away = normalize(game["teams"]["away"]["team"]["name"])

    key = f"{home}-{away}"

    if key in odds:
        return odds[key]

    print("❌ NO MATCH:", home, "vs", away)
    return None

# ---------------- LINE MOVEMENT ----------------
def get_line_movement(gamePk, current):
    prev = last_totals.get(gamePk)
    last_totals[gamePk] = current

    if prev is None:
        return 0

    return round(current - prev, 2)

# ---------------- PITCH COUNT ----------------
def get_pitch_count(live):
    try:
        box = live["liveData"]["boxscore"]
        defense = live["liveData"]["linescore"].get("defense", {})
        pid = defense.get("pitcher", {}).get("id")

        if not pid:
            return 0

        for t in ["home", "away"]:
            players = box["teams"][t]["players"]
            key = f"ID{pid}"
            if key in players:
                return players[key]["stats"]["pitching"].get("numberOfPitches", 0)
    except:
        pass
    return 0

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

    runners = sum([1 for b in ["first", "second", "third"]
                   if linescore.get("offense", {}).get(b)])
    proj += runners * 0.3

    pitch_count = get_pitch_count(live)
    if pitch_count >= 100:
        proj += 1.2
    elif pitch_count >= 90:
        proj += 0.8
    elif pitch_count >= 75:
        proj += 0.5

    box = live["liveData"]["boxscore"]
    bullpen = len(box["teams"]["home"]["pitchers"]) > 1 or len(box["teams"]["away"]["pitchers"]) > 1
    if bullpen:
        proj += 0.5

    diff = abs(home - away)
    if inning >= 7:
        proj += 0.6
    elif inning >= 5:
        proj += 0.3

    if diff <= 2:
        proj += 0.5

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
            detailed = live.get("gameData", {}).get("status", {}).get("detailedState")

            inning = linescore.get("currentInning", 0)
            outs = linescore.get("outs", 0)

            print(f"Game {gamePk} | {game_state} | {detailed} | Inning {inning} | Outs {outs}")

            if not is_game_live(live):
                continue

            if inning < 1:
                continue

            if outs not in [0, 2]:
                continue

            market = get_market_total(game)
            print("MARKET:", market)

            if market is None:
                continue

            model = projection(live)
            edge = round(model - market, 2)

            print(f"MODEL: {model} | EDGE: {edge}")

            key = f"{gamePk}-{inning}"
            if key in alerted:
                continue

            if abs(edge) < 0.5:
                continue

            movement = get_line_movement(gamePk, market)
            if abs(movement) > 1.5:
                continue

            home = game["teams"]["home"]["team"]["name"]
            away = game["teams"]["away"]["team"]["name"]

            bet = "OVER" if edge > 0 else "UNDER"

            send(
                f"🚨 LIVE TOTAL EDGE ({bet})\n"
                f"{away} vs {home}\n"
                f"Inning {inning}\n\n"
                f"Model: {model}\n"
                f"Market: {market}\n"
                f"Edge: {edge}\n"
                f"Move: {movement}\n"
                f"Pitch Count: {get_pitch_count(live)}"
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
