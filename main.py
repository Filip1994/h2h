import os
import sys
import json
import requests
from datetime import datetime

API_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
BETS_FILE = "bets.json"
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {'x-apisports-key': API_KEY}

MIN_H2H_MATCHES = 4
MIN_ACCURACY_PCT = 75.0
MIN_ODD = 1.35

EXCLUDED_COUNTRIES = ["Brazil", "Argentina", "Colombia", "Chile", "Uruguay", "Paraguay", "Peru", "Ecuador", "Bolivia", "Venezuela", "Egypt", "Morocco", "Tunisia", "Algeria", "South Africa", "Nigeria", "Ghana", "Senegal", "Cameroon", "Kenya", "Ivory Coast"]
EXCLUDED_LEAGUE_KEYWORDS = ["U19", "U20", "U21", "U23", "Sub-19", "Sub-20", "Reserve", "Reserves", "Amateur", "Oberliga", "Regional", "District", "5th Division", "6th Division", "Next Pro", "MLS Next Pro", "II", "B team"]
TOP_SUPERBET_LEAGUES = ["Premier League", "Championship", "League One", "La Liga", "Segunda Division", "Serie A", "Serie B", "Bundesliga", "2. Bundesliga", "3. Liga", "Ligue 1", "Ligue 2", "Primeira Liga", "Liga Portugal 2", "Eredivisie", "Eerste Divisie", "Pro League", "Super League", "Bundesliga - Austria", "Premiership", "Superliga", "Allsvenskan", "Eliteserien", "HNL", "1. HNL", "SuperLiga", "Premier League - Russia", "Russian Premier League", "MLS", "Major League Soccer", "UEFA Champions League", "UEFA Europa League", "UEFA Conference League"]

def fetch_api(endpoint, params=None):
    try:
        res = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=12)
        return res.json().get('response') or []
    except Exception as e:
        print(f"Greška na API [{endpoint}]: {e}")
        return []

def is_allowed_league(country_name, league_name):
    for country in EXCLUDED_COUNTRIES:
        if country and country.lower() in country_name.lower(): return False
    for kw in EXCLUDED_LEAGUE_KEYWORDS:
        if kw and kw.lower() in league_name.lower(): return False
    return True

def is_top_league(league_name):
    return any(top.lower() in league_name.lower() for top in TOP_SUPERBET_LEAGUES)

def load_bets():
    if os.path.exists(BETS_FILE):
        try:
            with open(BETS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except Exception: return []
    return []

def save_bets(bets):
    with open(BETS_FILE, 'w', encoding='utf-8') as f: json.dump(bets, f, ensure_ascii=False, indent=4)

def generate_superbet_search_link(home_team, away_team):
    query = f"{home_team} {away_team}".replace(" ", "%20")
    return f"https://superbet.rs/sr-latn/pretraga?query={query}"

def fetch_recent_form(team_id):
    res = fetch_api("fixtures", {"team": team_id, "last": 10})
    if not res: return {"avg_goals": 0.0}
    goals_scored = sum((m.get('goals', {}).get('home') or 0) if m.get('teams', {}).get('home', {}).get('id') == team_id else (m.get('goals', {}).get('away') or 0) for m in res)
    return {"avg_goals": goals_scored / len(res)}

def fetch_real_odds(fixture_id):
    res = fetch_api("odds", {"fixture": fixture_id})
    odds_dict = {}
    if not res: return odds_dict
    try:
        for bm in (res[0].get('bookmakers') or []):
            for b in (bm.get('bets') or []):
                name, values = b.get('name') or '', b.get('values') or []
                if name == "Goals Over/Under":
                    for v in values:
                        if v.get('value') == "Over 2.5" and "Ukupno Golova - Više 2.5" not in odds_dict: odds_dict["Ukupno Golova - Više 2.5"] = float(v.get('odd'))
                        elif v.get('value') == "Over 1.5" and "Raspon Golova - 2-4" not in odds_dict: odds_dict["Raspon Golova - 2-4"] = float(v.get('odd'))
                elif name == "Both Teams Score":
                    for v in values:
                        if v.get('value') == "Yes" and "Oba Tima Daju Gol (GG)" not in odds_dict: odds_dict["Oba Tima Daju Gol (GG)"] = float(v.get('odd'))
                elif "First Half" in name and "Over/Under" in name:
                    for v in values:
                        if v.get('value') == "Over 0.5" and "I Poluvreme - Više 0.5" not in odds_dict: odds_dict["I Poluvreme - Više 0.5"] = float(v.get('odd'))
                elif "Second Half" in name and "Over/Under" in name:
                    for v in values:
                        if v.get('value') == "Over 0.5" and "II Poluvreme - Više 0.5" not in odds_dict: odds_dict["II Poluvreme - Više 0.5"] = float(v.get('odd'))
    except Exception: pass
    return odds_dict

def get_h2h_html_blocks(current_bank=50000.0, max_daily_budget=4000.0):
    today_str = datetime.now().strftime('%Y-%m-%d')
    saved_bets = load_bets()
    raw_picks = []
    fb_events = fetch_api("fixtures", {"date": today_str})

    for event in fb_events:
        try:
            fixture = event.get('fixture') or {}
            fixture_id = fixture.get('id')
            if (fixture.get('status') or {}).get('short') not in ['NS', 'TBD']: continue

            teams = event.get('teams') or {}
            home, away = (teams.get('home') or {}).get('name', 'Home'), (teams.get('away') or {}).get('name', 'Away')
            home_id, away_id = (teams.get('home') or {}).get('id'), (teams.get('away') or {}).get('id')
            league_info = event.get('league') or {}
            league, country = league_info.get('name', 'Liga'), league_info.get('country', 'Nacionalno')

            if not is_allowed_league(country, league) or not home_id or not away_id: continue

            h2h_matches = fetch_api("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}"})
            total = len(h2h_matches)
            if total < MIN_H2H_MATCHES: continue

            home_form = fetch_recent_form(home_id)
            away_form = fetch_recent_form(away_id)

            stats = {"Ukupno Golova - Više 2.5": 0, "Oba Tima Daju Gol (GG)": 0, "Raspon Golova - 1-3": 0, "Raspon Golova - 2-4": 0, "Raspon Golova - 2-3": 0, "I Poluvreme - Više 0.5": 0, "II Poluvreme - Više 0.5": 0}
            for m in h2h_matches:
                goals, score = m.get('goals') or {}, m.get('score') or {}
                halftime = score.get('halftime') or {}
                ft_h, ft_a = goals.get('home') or 0, goals.get('away') or 0
                ht_h, ht_a = halftime.get('home') or 0, halftime.get('away') or 0
                ft_g, ht_g, sh_g = ft_h + ft_a, ht_h + ht_a, (ft_h + ft_a) - (ht_h + ht_a)

                if ft_g >= 3: stats["Ukupno Golova - Više 2.5"] += 1
                if ft_h > 0 and ft_a > 0: stats["Oba Tima Daju Gol (GG)"] += 1
                if 1 <= ft_g <= 3: stats["Raspon Golova - 1-3"] += 1
                if 2 <= ft_g <= 4: stats["Raspon Golova - 2-4"] += 1
                if 2 <= ft_g <= 3: stats["Raspon Golova - 2-3"] += 1
                if ht_g >= 1: stats["I Poluvreme - Više 0.5"] += 1
                if sh_g >= 1: stats["II Poluvreme - Više 0.5"] += 1

            odds = fetch_real_odds(fixture_id)
            allowed_markets = ["Ukupno Golova - Više 2.5", "Oba Tima Daju Gol (GG)", "Raspon Golova - 1-3", "Raspon Golova - 2-4", "Raspon Golova - 2-3", "I Poluvreme - Više 0.5", "II Poluvreme - Više 0.5"] if is_top_league(league) else ["Ukupno Golova - Više 2.5", "Oba Tima Daju Gol (GG)"]

            for market, count in stats.items():
                if market not in allowed_markets: continue
                pct = (count / total) * 100
                if pct >= MIN_ACCURACY_PCT:
                    real_odd = odds.get(market)
                    if not real_odd or real_odd < MIN_ODD: continue
                    raw_picks.append({
                        "fixture_id": fixture_id, "home": home, "away": away, "league": f"{country} - {league}",
                        "market": market, "pct": pct, "odd": real_odd,
                        "home_form": home_form['avg_goals'], "away_form": away_form['avg_goals'],
                        "link": generate_superbet_search_link(home, away)
                    })
        except Exception as e: print(f"Greška na meču: {e}")

    if not raw_picks: return "", 0.0

    base_stake_per_match = current_bank * 0.015  # 1.5% Banke po meču
    total_requested = len(raw_picks) * base_stake_per_match

    scaling_factor = 1.0
    if total_requested > max_daily_budget:
        scaling_factor = max_daily_budget / total_requested

    fb_picks_lines = []
    new_bets = []
    total_spent = 0.0

    for p in raw_picks:
        calculated_stake = round((base_stake_per_match * scaling_factor) / 50.0) * 50
        stake = max(100.0, calculated_stake)
        p['stake'] = stake
        total_spent += stake

        pick_str = f"<b>{p['market']}</b> -> {p['pct']:.0f}% | Kvota: <b>{p['odd']:.2f}</b> | Ulog: <b style='color:#28a745;'>{stake:,.0f} RSD</b> [<a href='{p['link']}' target='_blank' style='color:#28a745; font-weight:bold;'>Uplati 🎟️</a>]"
        
        block = f"""
        <div style="background:#ffffff; border-left:4px solid #28a745; padding:12px; margin-bottom:12px; border-radius:6px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
            <h3 style="margin:0 0 5px 0; color:#1a2a3a;">⚽ {p['home']} vs {p['away']}</h3>
            <p style="margin:0 0 8px 0; color:#6c757d; font-size:12px;">🏆 Liga: {p['league']} | Forma: {p['home_form']:.1f} vs {p['away_form']:.1f}</p>
            <p style="margin:0; font-size:13px;">👉 {pick_str}</p>
        </div>
        """
        fb_picks_lines.append(block)

        new_bets.append({
            "id": f"{p['fixture_id']}_{p['market']}", "event_id": p['fixture_id'], "date": today_str,
            "sport": "Football", "match": f"{p['home']} vs {p['away']}", "league": p['league'],
            "market": p['market'], "stake": stake, "odd": p['odd'], "status": "PENDING", "profit": 0
        })

    existing_ids = {b.get('id') for b in saved_bets if isinstance(b, dict)}
    for nb in new_bets:
        if nb['id'] not in existing_ids: saved_bets.append(nb)
    save_bets(saved_bets)

    return "".join(fb_picks_lines), total_spent

def evening_settle():
    bets = load_bets()
    updated = False

    for b in bets:
        if isinstance(b, dict) and b.get('status') == 'PENDING':
            fixture_id = b.get('event_id')
            if not fixture_id: continue

            data = fetch_api("fixtures", {"id": fixture_id})
            if data:
                fixture_data = data[0]
                status_short = (fixture_data.get('fixture') or {}).get('status', {}).get('short')

                if status_short in ['FT', 'AET', 'PEN']:
                    goals, score = fixture_data.get('goals') or {}, fixture_data.get('score') or {}
                    halftime = score.get('halftime') or {}
                    ft_h, ft_a = goals.get('home') or 0, goals.get('away') or 0
                    ht_h, ht_a = halftime.get('home') or 0, halftime.get('away') or 0
                    ft_goals, ht_goals, sh_goals = ft_h + ft_a, ht_h + ht_a, (ft_h + ft_a) - (ht_h + ht_a)

                    market = b.get('market')
                    is_win = False

                    if market == "Ukupno Golova - Više 2.5" and ft_goals >= 3: is_win = True
                    elif market == "Oba Tima Daju Gol (GG)" and ft_h > 0 and ft_a > 0: is_win = True
                    elif market == "Raspon Golova - 1-3" and 1 <= ft_goals <= 3: is_win = True
                    elif market == "Raspon Golova - 2-4" and 2 <= ft_goals <= 4: is_win = True
                    elif market == "Raspon Golova - 2-3" and 2 <= ft_goals <= 3: is_win = True
                    elif market == "I Poluvreme - Više 0.5" and ht_goals >= 1: is_win = True
                    elif market == "II Poluvreme - Više 0.5" and sh_goals >= 1: is_win = True

                    stake = b.get('stake', 750)
                    odd = b.get('odd', 1.0)

                    if is_win:
                        b['status'] = 'WIN'
                        b['profit'] = round((stake * odd) - stake, 2)
                    else:
                        b['status'] = 'LOSS'
                        b['profit'] = -stake

                    updated = True

    if updated:
        save_bets(bets)
        print("Večernja provera kompletirana. bets.json je ažuriran!")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "evening":
        evening_settle()
