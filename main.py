print("🚀 SHARP+ BOT (FAST TIMING + NO LATE INNINGS) STARTING...")

import requests
import time
import os

WEBHOOK = os.getenv("DISCORD_WEBHOOK")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

alerted = set()

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

def find_market(home, away, odds):
    h, a = clean(home), clean(away)

    for g in odds:
        gh, ga = clean(g.get("home_team","")), clean(g.get("away_team",""))
        if h in gh and a in ga or h in ga and a in gh:
            totals = []
            for book in g.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market.get("key") == "totals":
                        for o in market.get("outcomes", []):
                            if "point" in o:
                                totals.append(float(o["point"]))
            if totals:
                return max(totals), min(totals)

    return None, None

# ---------------- MODEL ----------------
def project_total(runs, progress, base):
    if progress <= 0:
        return base

    pace = runs / progress

    if progress < 3 and pace > 2.2:
        pace = 1.4
    elif progress < 4 and pace > 1.8:
        pace = 1.55
    else:
        pace = min(pace, 1.7)

    decay = 0.75 if progress < 3 else 0.85 if progress < 5 else 0.95 if progress < 7 else 1
    raw = pace * 9 * decay

    w = 0.15 if progress < 3 else 0.3 if progress < 5 else 0.5 if progress < 7 else 0.7
    proj = (raw * w) + (base * (1 - w))

    return round(max(runs + 0.5, min(15.5, proj)), 2)

# ---------------- BASELINE ----------------
def get_baseline(progress):
    base = 8.8
    if progress > 5:
        base += 0.3
    if progress > 7:
        base += 0.5
    return base

# ---------------- FILTER ----------------
def passes_confluence(edge, gap, progress):
    checks = 0
    if abs(edge) >= 2.0:
        checks += 1
    if gap >= 1.0:
        checks += 1
    if progress >= 5:
        checks += 1
    return checks >= 2

# ---------------- FAST CONFIRMATION ----------------
def confirm_signal(home, away, runs, progress, original_edge):
    time.sleep(2)  # 🔥 faster confirmation

    odds = get_odds()
    sharp, soft = find_market(home, away, odds)

    if sharp is None:
        return False, None

    mid = (sharp + soft) / 2
    base = get_baseline(progress)
    model = project_total(runs, progress, base)

    new_edge = model - mid

    # 🔥 relaxed threshold
    if abs(new_edge) >= abs(original_edge) * 0.6:
        return True, new_edge

    return False, new_edge

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

            # ---- TIMING FILTERS ----
            if progress < 3:
                print("⏭️ Too early")
                continue

            if progress < 3.5:
                print("⏭️ Not stable")
                continue

            # 🚫 BLOCK LATE GAME (8th+ / 9th)
            if progress >= 8.0:
                print("⏭️ Too late (8th inning+)")
                continue

            sharp, soft = find_market(home, away, odds)
            if sharp is None:
                print("❌ No market")
                continue

            if runs >= soft:
                print("⏭️ Dead line")
                continue

            gap = sharp - soft
            if gap < 0.4:
                print("⏭️ No sharp edge")
                continue

            base = get_baseline(progress)
            model = project_total(runs, progress, base)

            mid = (sharp + soft) / 2
            edge = model - mid

            print(f"📊 MODEL vs MARKET → {model} vs {round(mid,2)}")
            print(f"Edge: {round(edge,2)}")

            if abs(edge) < 1:
                print("⏭️ Edge too small")
                continue

            if not passes_confluence(edge, gap, progress):
                print("⏭️ No confluence")
                continue

            # 🚀 INSTANT ELITE SIGNALS
            if abs(edge) >= 4:
                ok = True
                new_edge = edge
            else:
                ok, new_edge = confirm_signal(home, away, runs, progress, edge)

            if not ok:
                print("⏭️ Lost edge after confirmation")
                continue

            tier = "ELITE" if abs(new_edge) >= 4 else "STRONG"

            key = f"{home}-{away}-{int(progress)}"
            if key in alerted:
                print("⏭️ Already sent")
                continue

            bet = "OVER" if new_edge > 0 else "UNDER"

            print(f"🚨 {tier}: {bet}")

            send(
                f"🚨 {tier} LIVE TOTAL ({bet})\n"
                f"{away} vs {home}\n\n"
                f"Runs: {runs}\nLine: {soft}\nModel: {model}\nEdge: {round(new_edge,2)}"
            )

            alerted.add(key)

        except Exception as e:
            print("Error:", e)

# ---------------- LOOP ----------------
while True:
    print("\n=== SHARP CHECK ===")
    run()
    time.sleep(10)
