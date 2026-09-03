import os
import time
import requests
from datetime import datetime, timezone, timedelta
import main
import quant_math

API_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {'x-apisports-key': API_KEY}

def fetch_api(endpoint, params=None):
    try:
        res = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=12)
        return res.json().get('response') or []
    except Exception as e:
        print(f"Greška na API [{endpoint}]: {e}")
        return []

def get_market_drops_and_single_tip(current_bank=50000.0, max_budget=500.0):
    today_str = datetime.now().strftime('%Y-%m-%d')
    now_ts = int(time.time())
    saved_bets = main.load_bets()
    fixtures = fetch_api("fixtures", {"date": today_str})
    potential_singles = []

    for event in fixtures:
        try:
            fixture = event.get('fixture') or {}
            fixture_id = fixture.get('id')
            match_ts = fixture.get('timestamp') or 0

            if match_ts <= (now_ts + 900) or match_ts >= (now_ts + 86400): continue
            if (fixture.get('status') or {}).get('short') not in ['NS', 'TBD']: continue

            match_time_str = datetime.fromtimestamp(match_ts, tz=timezone.utc).astimezone(timezone(timedelta(hours=2))).strftime('%H:%M')

            teams = event.get('teams') or {}
            home_id, away_id = (teams.get('home') or {}).get('id'), (teams.get('away') or {}).get('id')
            home, away = (teams.get('home') or {}).get('name', 'Home'), (teams.get('away') or {}).get('name', 'Away')
            league_info = event.get('league') or {}
            league, country = league_info.get('name', ''), league_info.get('country', '')

            if not main.is_allowed_league(country, league) or not home_id or not away_id: continue

            odds_data = fetch_api("odds", {"fixture": fixture_id, "bookmaker": 8})
            if not odds_data: continue

            home_form = main.fetch_recent_form(home_id)
            away_form = main.fetch_recent_form(away_id)
            tot_xg = home_form['avg_goals'] + away_form['avg_goals']

            bookmakers = odds_data[0].get('bookmakers') or []
            target_bm = next((bm for bm in bookmakers if bm.get('id') in [8, 11, 6]), bookmakers[0] if bookmakers else None)

            if target_bm:
                bm_name = target_bm.get('name', 'API Market')
                for b in (target_bm.get('bets') or []):
                    name, values = b.get('name') or '', b.get('values') or []
                    if name == "Goals Over/Under":
                        for v in values:
                            val_name, current_odd = v.get('value'), float(v.get('odd'))
                            if val_name == "Over 2.5" and (2.00 <= current_odd <= 3.20) and tot_xg >= 2.80:
                                potential_singles.append({
                                    "fixture_id": fixture_id, "match": f"(H) {home} vs {away} (A)",
                                    "league": f"{country} - {league}", "market": "Više 2.5 Golova",
                                    "match_time": match_time_str, "odd": current_odd, "bm_source": bm_name, "tot_xg": tot_xg
                                })
        except Exception as e: print(f"Greška na Single tipu: {e}")

    if not potential_singles:
        return "", 0.0, None

    potential_singles.sort(key=lambda x: (x['tot_xg'], x['odd']), reverse=True)
    best = potential_singles[0]

    completed = [b for b in saved_bets if isinstance(b, dict) and b.get('status') in ['WIN', 'LOSS']]
    cb_multiplier = quant_math.check_circuit_breaker(completed, current_bank)
    
    stake = quant_math.calculate_kelly_stake(current_bank, 60.0, best['odd']) * cb_multiplier
    stake = max(100.0, min(max_budget, stake))

    bet_id = f"{best['fixture_id']}_SINGLE"

    analysis_text = (
        f"⚽ <b>{best['match']}</b>\n"
        f"⏰ <b>Početak:</b> {best['match_time']}h | 🏆 {best['league']}\n"
        f"🎯 <b>Predlog:</b> {best['market']} | xG Forme: <b>{best['tot_xg']:.2f}</b>\n"
        f"💵 Kvota: <b>{best['odd']:.2f}</b> ({best['bm_source']}) | Ulog: <b>{stake:,.0f} RSD</b>"
    )

    new_single = {
        "id": bet_id, "type": "SINGLE_TIP", "event_id": best['fixture_id'], "date": today_str,
        "sport": "Football", "match": best['match'], "league": best['league'],
        "market": best['market'], "stake": stake, "odd": best['odd'], "status": "PENDING", "profit": 0
    }
    if not any(b.get('id') == bet_id for b in saved_bets if isinstance(b, dict)):
        saved_bets.append(new_single)
        main.save_bets(saved_bets)

    return analysis_text, stake, best['fixture_id']
