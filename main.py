print("🚀 SHARP+ BOT (ULTRA-SHARP + SAFE TWEAK) STARTING...")

import requests
import time
import os
from datetime import datetime, timezone

WEBHOOK = os.getenv("DISCORD_WEBHOOK")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

print("WEBHOOK:", "SET" if WEBHOOK else "MISSING")
print("ODDS API:", "SET" if ODDS_API_KEY else "MISSING")

alerted = set()

MAX_MARKET_AGE_SEC = 60

# ---------------- DISCORD ----------------
def send(msg):
    if WEBHOOK:
        try:
            requests.post(WEBHOOK, json={"content": msg})
        except:
            pass

# ---------------- ESPN ----------------
def get_espn_games():
    try:
        url = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
        return requests.get(url, timeout=10).json().get("events", [])
    except:
        return []

# ---------------- ODDS ----------------
def get_odds():
    try:
        url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "totals"
        }
        data = requests.get(url, params=params, timeout=10).json()
        return data if isinstance(data, list) else []
    except:
        return []

# ---------------- CLEAN ----------------
def clean(name):
    return (
        name.lower()
        .replace(" ", "")
        .replace(".", "")
        .replace("-", "")
        .replace("newyork", "ny")
        .replace("losangeles", "la")
    )

# ---------------- TIME ----------------
def parse_iso(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except:
        return None

def is_fresh(ts):
    if not ts:
        return True
    dt = parse_iso(ts)
    if not dt:
        return True
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    return age <= MAX_MARKET_AGE_SEC

# ---------------- TOTALS ----------------
def extract_totals(game):
    totals = []
    for book in game.get("bookmakers", []):
        if book.get("in_play") is False:
            continue
        if not is_fresh(book.get("last_update")):
            continue

        for market in book.get("markets", []):
            if market.get("key") == "totals":
                for o in market.get("outcomes", []):
                    if "point" in o:
                        totals.append(float(o["point"]))
    return totals

# ---------------- MATCH ----------------
def find_market(home, away, odds):
    home_c = clean(home)
    away_c = clean(away)

    for game in odds:
        h = clean(game.get("home_team", ""))
        a = clean(game.get("away_team", ""))

        if (home_c in h and away_c in a) or (home_c in a and away_c in h):
            totals = extract_totals(game)
            if totals:
                return max(totals), min(totals)

    print("⚠️ Trying fallback match...")
    for game in odds:
        h = clean(game.get("home_team", ""))
        a = clean(game.get("away_team", ""))

        if home_c in h or away_c in a or home_c in a or away_c in h:
            totals = extract_totals(game)
            if totals:
                print("✅ Fallback match found")
                return max(totals), min(totals)

    return None, None

# ---------------- MODEL ----------------
def project_total(runs, progress):
    BASELINE = 8.8

    if progress < 3:
        return round(BASELINE + (runs * 0.3), 2)

    pace = runs / progress
    raw = pace * 9

    w = 0.25 if progress < 5 else 0.4 if progress < 7 else 0.6
    proj = (raw * w) + (BASELINE * (1 - w))

    return round(max(4, min(14, proj)), 2)

# ---------------- MAIN ----------------
def check():
    games = get_espn_games()
    odds = get_odds()

    print("Games:", len(games), "| Odds:", len(odds))

    for g in games:
        try:
            comp = g["competitions"][0]
            teams = comp["competitors"]

            home = teams[0]["team"]["displayName"]
            away = teams[1]["team"]["displayName"]

            runs = int(teams[0]["score"]) + int(teams[1]["score"])
            outs = comp.get("situation", {}).get("outs", 0)

            print(f"\n{away} vs {home}")
            print(f"Runs: {runs} | Outs: {outs}")

            progress = (outs / 3) + (runs * 0.6)
            print("Progress:", round(progress, 2))

            if progress < 3.0:
                print("⏭️ Too early")
                continue

            # 🔥 ONLY CHANGE HERE
            if progress < 3.5:
                print("⏭️ Game not stable yet")
                continue

            sharp, soft = find_market(home, away, odds)
            if sharp is None:
                print("❌ No market match")
                continue

            sharp, soft = round(sharp, 1), round(soft, 1)
            print("Sharp:", sharp, "| Soft:", soft)

            if runs >= soft:
                print("⏭️ Line already dead")
                continue

            if runs <= soft - 12:
                print("⏭️ Unrealistic low")
                continue

            if soft < 4 or soft > 16:
                print("⏭️ Bad market")
                continue

            gap = round(sharp - soft, 2)
            print("Gap:", gap)

            if gap < 0.6:
                print("⏭️ No sharp disagreement")
                continue

            model = project_total(runs, progress)
            edge = round(model - soft, 2)

            print("Model:", model, "| Edge:", edge)

            key = f"{home}-{away}-{int(progress)}"

            if abs(edge) >= 4:
                tier = "ELITE"
            elif abs(edge) >= 2.8:
                tier = "STRONG"
            else:
                print("⏭️ Edge too small")
                continue

            if key in alerted:
                print("⏭️ Already alerted")
                continue

            bet = "OVER" if edge > 0 else "UNDER"
            print(f"🚨 {tier} SIGNAL:", bet)

            send(
                f"🚨 {tier} LIVE TOTAL ({bet})\n{away} vs {home}\n\n"
                f"Runs: {runs}\nSoft: {soft}\nSharp: {sharp}\nGap: {gap}\nModel: {model}\nEdge: {edge}"
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
