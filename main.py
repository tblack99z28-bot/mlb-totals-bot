import requests
import time
from datetime import datetime
import os

WEBHOOK = os.getenv("DISCORD_WEBHOOK")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

alerted = set()
last_totals = {}

# ---------------- DISCORD ----------------
def send(msg):
    if WEBHOOK:
        try:
            requests.post(WEBHOOK, json={"content": msg})
        except:
            pass

# ---------------- MLB ----------------
def get_schedule():
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}"
    return requests.get(url).json()

def get_live(gamePk):
    url = f"https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live"
    return requests.get(url).json()

# ---------------- TEAM MATCHING ----------------
def normalize(name):
    return name.lower().replace(" ", "").replace(".", "")

def match_game(event, game):
    home = normalize(game["teams"]["home"]["team"]["name"])
    away = normalize(game["teams"]["away"]["team"]["name"])

    event_home = normalize(event["home_team"])
    event_away = normalize(event["away_team"])

    return home in event_home and away in event_away

# ---------------- ODDS API ----------------
def get_market_total(game):
    try:
        url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "totals"
        }

        data = requests.get(url, params=params).json()

        totals = []

        for event in data:
            if not match_game(event, game):
                continue

            for book in event["bookmakers"]:
                for market in book["markets"]:
                    if market["key"] == "totals":
                        for outcome in market["outcomes"]:
                            totals.append(outcome["point"])

        if not totals:
            return None

        return round(sum(totals) / len(totals), 2)

    except Exception as e:
        print("Odds API error:", e)
        return None

# ---------------- LINE MOVEMENT ----------------
def get_line_movement(gamePk, current):
    prev = last_totals.get(gamePk)
    last_totals[gamePk] = current

    if prev is None:
        return 0

    return round(current - prev, 2)

# ---------------- PITCH DATA ----------------
def get_pitcher_id(live):
    try:
        return live["liveData"]["linescore"]["defense"]["pitcher"]["id"]
    except:
        return None

def get_pitch_count(live):
    try:
        box = live["liveData"]["boxscore"]
        pid = get_pitcher_id(live)

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

    home = linescore["teams"]["home"]["runs"]
    away = linescore["teams"]["away"]["runs"]

    total = home + away
    innings_played = inning - 1 + (outs / 3)

    if innings_played <= 0:
        return total, 0

    proj = (total / innings_played) * 9

    # runners on base
    offense = linescore.get("offense", {})
    runners = sum([1 for b in ["first", "second", "third"] if offense.get(b)])
    proj += runners * 0.3

    # fatigue
    pitch_count = get_pitch_count(live)
    fatigue = 0

    if pitch_count >= 100:
        fatigue += 1.2
    elif pitch_count >= 90:
        fatigue += 0.8
    elif pitch_count >= 75:
        fatigue += 0.5

    if inning <= 5 and pitch_count >= 80:
        fatigue += 0.5

    if runners >= 2 and pitch_count >= 85:
        fatigue += 0.5

    proj += fatigue

    # bullpen
    box = live["liveData"]["boxscore"]
    bullpen = len(box["teams"]["home"]["pitchers"]) > 1 or len(box["teams"]["away"]["pitchers"]) > 1

    if bullpen:
        proj += 0.5

    # leverage
    diff = abs(home - away)

    if inning >= 7:
        proj += 0.6
    elif inning >= 5:
        proj += 0.3

    if diff <= 2:
        proj += 0.5

    return round(proj, 2), fatigue

# ---------------- MAIN ----------------
def check():

    schedule = get_schedule()

    for d in schedule.get("dates", []):
        for game in d.get("games", []):

            gamePk = game["gamePk"]
            live = get_live(gamePk)

            linescore = live["liveData"]["linescore"]

            inning = linescore.get("currentInning", 0)
            outs = linescore.get("outs", 0)

            # only inning breaks
            if inning < 4 or outs != 0:
                continue

            key = f"{gamePk}-{inning}"
            if key in alerted:
                continue

            market = get_market_total(game)
            if market is None:
                continue

            model, fatigue = projection(live)
            edge = round(model - market, 2)

            movement = get_line_movement(gamePk, market)

            # filter weak signals
            if abs(edge) < 1.8:
                continue

            # avoid chasing steam
            if abs(movement) > 1:
                continue

            home = game["teams"]["home"]["team"]["name"]
            away = game["teams"]["away"]["team"]["name"]

            bet = "OVER" if edge > 0 else "UNDER"

            # classify strength
            if abs(edge) >= 2.2 and fatigue > 0.5:
                tag = "🔥 STRONG PLAY"
            elif abs(edge) >= 1.8:
                tag = "⚡ STANDARD"
            else:
                tag = "⚠️ LEAN"

            send(
                f"{tag} ({bet})\n"
                f"{away} vs {home}\n"
                f"End {inning}\n\n"
                f"Model: {model}\n"
                f"Market: {market}\n"
                f"Edge: {edge}\n"
                f"Line Move: {movement}\n"
                f"Pitch Count: {get_pitch_count(live)}"
            )

            alerted.add(key)

# ---------------- LOOP ----------------
while True:
    try:
        print("Checking games...")
        check()
    except Exception as e:
        print("Error:", e)

    time.sleep(30)