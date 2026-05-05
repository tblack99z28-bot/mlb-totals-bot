print("🚀 SHARP+ BOT (ULTRA-SHARP QUALITY) STARTING...")

import requests
import time
import os
from datetime import datetime, timezone

WEBHOOK = os.getenv("DISCORD_WEBHOOK")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

print("WEBHOOK:", "SET" if WEBHOOK else "MISSING")
print("ODDS API:", "SET" if ODDS_API_KEY else "MISSING")

alerted = set()

# ---------------- SETTINGS ----------------
MAX_MARKET_AGE_SEC = 60   # skip odds older than this (set None to disable)

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
        return requests.get(url, timeout=10).json().get("events", [])
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
        data = requests.get(url, params=params, timeout=10).json()
        if isinstance(data, list):
            return data
        else:
            print("ODDS ERROR:", data)
    except Exception as e:
        print("ODDS EXCEPTION:", e)
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

# ---------------- TIME HELPERS ----------------
def parse_iso(ts):
    if not ts:
        return None
    try:
        # odds API uses ISO8601
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except:
        return None

def is_fresh(ts_iso):
    if MAX_MARKET_AGE_SEC is None:
        return True
    dt = parse_iso(ts_iso)
    if not dt:
        return True  # if unknown, don't auto-reject
    age = (datetime.now(timezone.utc) - dt).total_seconds()
    return age <= MAX_MARKET_AGE_SEC

# ---------------- EXTRACT TOTALS ----------------
def extract_totals(game):
    totals = []
    # prefer in-play books and fresh markets
    for book in game.get("bookmakers", []):
        in_play = book.get("in_play")
        last_update = book.get("last_update")

        # require in-play if provided; otherwise allow but check freshness
        if in_play is False:
            continue
        if last_update and not is_fresh(last_update):
            continue

        for market in book.get("markets", []):
            if market.get("key") == "totals":
                for o in market.get("outcomes", []):
                    if "point" in o:
                        try:
                            totals.append(float(o["point"]))
                        except:
                            pass
    return totals

# ---------------- MATCH ----------------
def find_market(home, away, odds):
    home_c = clean(home)
    away_c = clean(away)

    # PRIMARY MATCH (both teams)
    for game in odds:
        h = clean(game.get("home_team", ""))
        a = clean(game.get("away_team", ""))

        teams_api = {h, a}
        teams_espn = {home_c, away_c}

        match_count = 0
        for t1 in teams_api:
            for t2 in teams_espn:
                if t1 in t2 or t2 in t1:
                    match_count += 1

        if match_count >= 2:
            totals = extract_totals(game)
            if totals:
                return max(totals), min(totals)

    # FALLBACK (one-team match)
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

            # PROGRESS
            progress = (outs / 3) + (runs * 0.6)
            print("Progress:", round(progress, 2))

            # TIMING (strict)
            if progress < 3.0:
                print("⏭️ Too early")
                continue
            if progress < 4.0:
                print("⏭️ Game not stable yet")
                continue

            # MARKET
            sharp, soft = find_market(home, away, odds)
            if sharp is None:
                print("❌ No market match")
                continue

            sharp = round(sharp, 1)
            soft = round(soft, 1)
            print("Sharp:", sharp, "| Soft:", soft)

            # 🚫 DEAD LINE (strict)
            if runs >= soft:
                print("⏭️ Line already dead")
                continue

            # 🚫 UNREALISTIC LOW (stale/broken)
            if runs <= soft - 12:
                print("⏭️ Unrealistic low total vs line")
                continue

            # BASIC RANGE
            if soft < 4 or soft > 16:
                print("⏭️ Bad market")
                continue

            # GAP (strict)
            line_gap = round(sharp - soft, 2)
            print("Gap:", line_gap)
            if line_gap < 0.6:
                print("⏭️ No sharp disagreement")
                continue

            # MODEL
            model = project_total(runs, progress)
            edge = round(model - soft, 2)
            print("Model:", model, "| Edge:", edge)

            game_id = f"{home}-{away}"
            key = f"{game_id}-{int(progress)}"

            # EDGE TIERS (strict)
            if abs(edge) >= 4:
                tier = "ELITE"
            elif abs(edge) >= 2.8:
                tier = "STRONG"
            else:
                print("⏭️ Edge too small")
                continue

            # DUPLICATE
            if key in alerted:
                print("⏭️ Already alerted")
                continue

            # SIGNAL
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
