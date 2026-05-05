print("🚀 SHARP+ BOT (FREE SHARP SYSTEM) STARTING...")

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

            totals = []

            for book in game.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market.get("key") == "totals":
                        for o in market.get("outcomes", []):
                            if "point" in o:
                                totals.append(float(o["point"]))

            if totals:
                sharp_line = max(totals)  # highest total
                soft_line = min(totals)   # lowest total
                return sharp_line, soft_line

    return None, None

# ---------------- MODEL ----------------
def project_total(runs, progress):
    BASELINE = 8.8

    if progress < 3:
        return round(BASELINE + (runs * 0.3), 2)

    pace = runs / progress
    raw = pace * 9

    if progress < 5:
        w = 0.25
    elif progress < 7:
        w = 0.4
    else:
        w = 0.6

    proj = (raw * w) + (BASELINE * (1 - w))
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

            progress = (outs / 3) + (runs * 0.6)
            print("Progress:", round(progress, 2))

            sharp, soft = find_market(home, away, odds)

            if sharp is None:
                print("❌ No market match")
                continue

            sharp = round(sharp, 1)
            soft = round(soft, 1)

            print("Sharp:", sharp, "| Soft:", soft)

            if soft < 4 or soft > 16:
                print("⏭️ Bad market")
                continue

            line_gap = round(sharp - soft, 2)
            print("Gap:", line_gap)

            if line_gap < 0.8:
                print("⏭️ No sharp disagreement")
                continue

            model = project_total(runs, progress)
            edge = round(model - soft, 2)

            print("Model:", model, "| Edge:", edge)

            game_id = f"{home}-{away}"
            key = f"{game_id}-{int(progress)}"

            # ======================
            # 🔥 EDGE TIERING
            # ======================
            if abs(edge) >= 4:
                tier = "ELITE"
            elif abs(edge) >= 3:
                tier = "STRONG"
            else:
                tier = "NONE"

            # ======================
            # 🔥 FILTER BLOCK
            # ======================
            skip_reason = None

            if progress < 3.0:
                skip_reason = "Too early"

            elif progress < 4.5:
                skip_reason = "Game not stable yet"

            elif runs >= 6 and progress < 5 and abs(edge) < 3:
                skip_reason = "Weak early spike"

            elif tier == "NONE":
                skip_reason = "Edge too small"

            elif key in alerted:
                skip_reason = "Already alerted"

            if skip_reason:
                print(f"⏭️ {skip_reason}")
                continue

            # ======================
            # 🚨 SIGNAL
            # ======================
            bet = "OVER" if edge > 0 else "UNDER"

            print(f"🚨 {tier} SIGNAL:", bet)

            send(
                f"🚨 {tier} LIVE TOTAL ({bet})\n"
                f"{away} vs {home}\n\n"
                f"Runs: {runs}\nSoft: {soft}\nSharp: {sharp}\nGap: {line_gap}\nModel: {model}\nEdge: {edge}"
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

    time.sleep(10)
