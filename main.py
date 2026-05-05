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

odds_cache = {}
odds_last_fetch = 0

# ---------------- DISCORD ----------------
def send(msg):
    if WEBHOOK:
        try:
            requests.post(WEBHOOK, json={"content": msg})
        except Exception as e:
            print("Webhook error:", e)

# ---------------- TEAM MATCH ----------------
TEAM_MAP = {
    "yankees": "yankees","mets": "mets","dodgers": "dodgers","padres": "padres",
    "giants": "giants","braves": "braves","mariners": "mariners","angels": "angels",
    "white sox": "whitesox","cubs": "cubs","phillies": "phillies","astros": "astros",
    "rangers": "rangers","red sox": "redsox","blue jays": "bluejays","cardinals": "cardinals",
    "brewers": "brewers","guardians": "guardians","twins": "twins","tigers": "tigers",
    "royals": "royals","athletics": "athletics","rockies": "rockies","diamondbacks": "diamondbacks",
    "nationals": "nationals","orioles": "orioles","rays": "rays","pirates": "pirates",
    "reds": "reds","marlins": "marlins"
}

def team_key(name):
    name = name.lower()
    for k in TEAM_MAP:
        if k in name:
            return TEAM_MAP[k]
    return name.replace(" ", "")

# ---------------- SCHEDULE ----------------
def get_schedule():
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={today}&endDate={today}"
    return requests.get(url).json()

def get_live(gamePk):
    url = f"https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live"
    return requests.get(url).json()

# ---------------- REAL LIVE DETECTION ----------------
def is_game_live(live):
    try:
        linescore = live.get("liveData", {}).get("linescore", {})

        inning = linescore.get("currentInning", 0)
        outs = linescore.get("outs", 0)

        home_runs = linescore.get("teams", {}).get("home", {}).get("runs", 0)
        away_runs = linescore.get("teams", {}).get("away", {}).get("runs", 0)

        offense = linescore.get("offense", {})

        # 🔥 REAL GAME SIGNALS
        if inning >= 1:
            return True
        if outs > 0:
            return True
        if home_runs > 0 or away_runs > 0:
            return True
        if offense.get("batter"):
            return True

    except:
        pass

    return False

# ---------------- ODDS ----------------
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
            home = team_key(event.get("home_team", ""))
            away = team_key(event.get("away_team", ""))

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

def get_market_total(game):
    odds = fetch_all_odds()

    home = team_key(game["teams"]["home"]["team"]["name"])
    away = team_key(game["teams"]["away"]["team"]["name"])

    for key, total in odds.items():
        if home in key and away in key:
            return total

    print("❌ NO MATCH:", home, "vs", away)
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

    runners = sum([1 for b in ["first", "second", "third"]
                   if linescore.get("offense", {}).get(b)])
    proj += runners * 0.3

    if inning >= 7:
        proj += 0.6
    elif inning >= 5:
        proj += 0.3

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

            # 🔥 ONLY REAL LIVE GAMES
            if not is_game_live(live):
                continue

            inning = linescore.get("currentInning", 0)
            outs = linescore.get("outs", 0)

            print(f"Game {gamePk} | LIVE | Inning {inning} | Outs {outs}")

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

            home = game["teams"]["home"]["team"]["name"]
            away = game["teams"]["away"]["team"]["name"]

            bet = "OVER" if edge > 0 else "UNDER"

            send(
                f"🚨 LIVE TOTAL EDGE ({bet})\n"
                f"{away} vs {home}\n"
                f"Inning {inning}\n\n"
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
