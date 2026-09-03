import os
import time
import requests
import math
from datetime import datetime, timezone, timedelta
import main
import quant_math

API_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {'x-apisports-key': API_KEY}
MIN_VALUE_EDGE = 12.0

def fetch_api(endpoint, params=None):
    try:
        res = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=12)
        return res.json().get('response') or []
    except Exception as e:
        print(f"Greška na API [{endpoint}]: {e}")
        return []

def poisson_prob(lmbda, k):
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

def get_value_html_blocks(current_bank=50000.0, max_budget=500.0, blocked_fixture_ids=None):
    if blocked_fixture_ids is None: blocked_fixture_ids = set()

    today_str = datetime.now().strftime('%Y-%m-%d')
    now_ts = int(time.time())
    saved_bets = main.load_bets()
    fixtures = fetch_api("fixtures", {"date": today_str})
    
    value_picks = []
    new_bets = []
    total_spent = 0.0

    completed = [b for b in saved_bets if isinstance(b, dict) and b.get('status') in ['WIN', 'LOSS']]
    cb_multiplier = quant_math.check_circuit_breaker(completed, current_bank)

    for event in fixtures:
        try:
            fixture = event.get('fixture') or {}
            fixture_id = fixture.get('id')
            match_ts = fixture.get('timestamp') or 0

            if match_ts <= (now_ts + 900) or match_ts >= (now_ts + 86400): continue
            if fixture_id in blocked_fixture_ids: continue
            if (fixture.get('status') or {}).get('short') not in ['NS', 'TBD']: continue

            match_time_str = datetime.fromtimestamp(match_ts, tz=timezone.utc).astimezone(timezone(timedelta(hours=2))).strftime('%H:%M')

            teams = event.get('teams') or {}
            home_id, away_id = (teams.get('home') or {}).get('id'), (teams.get('away') or {}).get('id')
            home, away = (teams.get('home') or {}).get('name', 'Home'), (teams.get('away') or {}).get('name', 'Away')
            league_info = event.get('league') or {}
            league, country = league_info.get('name', ''), league_info.get('country', '')

            if not main.is_allowed_league(country, league) or not home_id or not away_id: continue

            home_stats = main.fetch_recent_form(home_id)
            away_stats = main.fetch_recent_form(away_id)
            tot_lambda = home_stats['avg_goals'] + away_stats['avg_goals']

            prob_over_2_5 = sum(poisson_prob(tot_lambda/2, h) * poisson_prob(tot_lambda/2, a) for h in range(8) for a in range(8) if (h + a) >= 3) * 100.0

            odds = main.fetch_real_odds(fixture_id)
            odd_tuple = odds.get("Ukupno Golova - Više 2.5")

            if odd_tuple and odd_tuple[0] >= 1.65:
                real_odd, bm_source = odd_tuple
                implied_prob = (1.0 / real_odd) * 100.0
                edge = prob_over_2_5 - implied_prob

                if edge >= MIN_VALUE_EDGE:
                    stake = quant_math.calculate_kelly_stake(current_bank, prob_over_2_5, real_odd) * cb_multiplier
                    stake = max(100.0, stake)

                    if (total_spent + stake) <= max_budget:
                        total_spent += stake
                        bet_id = f"{fixture_id}_VALUE"

                        text = (
                            f"📐 <b>PURE MATH VALUE BET</b>\n"
                            f"⚽ <b>(H) {home} vs {away} (A)</b>\n"
                            f"⏰ <b>Početak:</b> {match_time_str}h | 🏆 {country} - {league}\n"
                            f"💡 Model Prob: <b>{prob_over_2_5:.1f}%</b> | Edge: <b>+{edge:.1f}%</b>\n"
                            f"💎 <b>Više 2.5 Golova</b> | Kvota: <b>{real_odd:.2f}</b> | Ulog: <b>{stake:,.0f} RSD</b>"
                        )
                        value_picks.append((text, bet_id))

                        new_bets.append({
                            "id": bet_id, "type": "VALUE_BET", "event_id": fixture_id, "date": today_str,
                            "sport": "Football", "match": f"{home} vs {away}", "league": f"{country} - {league}",
                            "market": "Više 2.5 Golova", "stake": stake, "odd": real_odd, "status": "PENDING", "profit": 0
                        })

        except Exception as e: print(f"Greška na Value meču: {e}")

    existing_ids = {b.get('id') for b in saved_bets if isinstance(b, dict)}
    for nb in new_bets:
        if nb['id'] not in existing_ids: saved_bets.append(nb)
    main.save_bets(saved_bets)

    return value_picks, total_spent
