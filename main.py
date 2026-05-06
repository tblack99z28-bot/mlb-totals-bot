print("🚀 SHARP+ BOT (FINAL SYSTEM) STARTING...")

import requests
import time
import os
from datetime import datetime, timezone

WEBHOOK = os.getenv("DISCORD_WEBHOOK")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

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
def get_games():
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

# ---------------- HELPERS ----------------
def clean(name):
    return name.lower().replace(" ", "").replace(".", "").replace("-", "")

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

# ---------------- MARKET ----------------
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

def find_market(home, away, odds):
    home_c, away_c = clean(home), clean(away)

    for g in odds:
        h, a = clean(g.get("home_team","")), clean(g.get("away_team",""))
        if home_c in h and away_c in a or home_c in a and away_c in h:
            totals = extract_totals(g)
            if totals:
                return max(totals), min(totals)

    print("⚠️ Trying fallback match...")
    for g in odds:
        h, a = clean(g.get("home_team","")), clean(g.get("away_team",""))
        if home_c in h or away_c in a or home_c in a or away_c in h:
            totals = extract_totals(g)
            if totals:
                print("✅ Fallback match found")
                return max(totals), min(totals)

    return None, None

# ---------------- CONTEXT ----------------
def context_filter(runs, progress):
    if progress < 3.5 and runs >= 7:
        return "early chaos"
    if runs >= 12 and progress < 6:
        return "blowout slowdown"
    return None

# ---------------- MODEL ----------------
def project_total(runs, progress):
    BASE = 8.8
    if progress <= 0:
        return BASE

    pace = runs / progress

    # spike control
    if progress < 3 and pace > 2.2:
        pace = 1.4
    elif progress < 4 and pace > 1.8:
        pace = 1.55
    else:
        pace = min(pace, 1.7)

    # decay
    if progress < 3:
        decay = 0.75
    elif progress < 5:
        decay = 0.85
    elif progress < 7:
        decay = 0.95
    else:
        decay = 1.0

    raw = pace * 9 * decay

    # weighting
    if progress < 3:
        w = 0.15
    elif progress < 5:
        w = 0.3
    elif progress < 7:
        w = 0.5
    else:
        w = 0.7

    proj = (raw * w) + (BASE * (1 - w))

    # bullpen
    if progress > 5:
        proj += 0.3
    if progress > 7:
        proj += 0.6

    proj = max(runs + 0.5, proj)
    proj = min(15.5, proj)

    return round(proj, 2)

# ---------------- SCORING ----------------
def confidence(edge, gap, progress):
    score = 0

    if abs(edge) >= 4:
        score += 3
    elif abs(edge) >= 2.5:
        score += 2

    if gap >= 1.5:
        score += 2
    elif gap >= 0.7:
        score += 1

    if progress > 5:
        score += 2
    elif progress > 4:
        score += 1

    return score

# ---------------- MAIN ----------------
def run():
    games = get_games()
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

            progress = (outs / 3) + (runs * 0.6)

            print(f"\n{away} vs {home}")
            print(f"Runs: {runs} | Progress: {round(progress,2)}")

            if progress < 3:
                print("⏭️ Too early")
                continue

            if progress < 3.5:
                print("⏭️ Not stable")
                continue

            reason = context_filter(runs, progress)
            if reason:
                print(f"⏭️ Context: {reason}")
                continue

            sharp, soft = find_market(home, away, odds)
            if sharp is None:
                print("❌ No market")
                continue

            sharp, soft = round(sharp,1), round(soft,1)
            print("Sharp:", sharp, "| Soft:", soft)

            if runs >= soft:
                print("⏭️ Dead line")
                continue

            gap = round(sharp - soft, 2)
            print("Gap:", gap)

            if gap < 0.6:
                print("⏭️ No edge")
                continue

            model = project_total(runs, progress)

            mid = (sharp + soft) / 2
            edge = round(model - mid, 2)

            print("Model:", model, "| Edge:", edge)

            score = confidence(edge, gap, progress)

            if score < 4:
                print("⏭️ Low confidence")
                continue

            tier = "ELITE" if score >= 6 else "STRONG"

            key = f"{home}-{away}-{int(progress)}"
            if key in alerted:
                print("⏭️ Already sent")
                continue

            bet = "OVER" if edge > 0 else "UNDER"

            print(f"🚨 {tier}: {bet}")

            send(
                f"🚨 {tier} LIVE TOTAL ({bet})\n"
                f"{away} vs {home}\n\n"
                f"Runs: {runs}\nSoft: {soft}\nSharp: {sharp}\nGap: {gap}\nModel: {model}\nEdge: {edge}"
            )

            alerted.add(key)

        except Exception as e:
            print("Error:", e)

# ---------------- LOOP ----------------
while True:
    print("\n=== SHARP CHECK ===")
    run()
    time.sleep(10)
