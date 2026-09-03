import os
import sys
import json
import requests
import math
from datetime import datetime
import main

API_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {'x-apisports-key': API_KEY}

MIN_VALUE_EDGE = 12.0
MIN_HIGH_ODD = 1.75

def fetch_api(endpoint, params=None):
    try:
        res = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=12)
        return res.json().get('response') or []
    except Exception as e:
        print(f"Greška na API [{endpoint}]: {e}")
        return []

def poisson_prob(lmbda, k):
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

def calculate_expected_goals(home_stats, away_stats):
    lambda_home = (home_stats.get('scored_avg', 1.2) + away_stats.get('conceded_avg', 1.2)) / 2.0
    lambda_away = (away_stats.get('scored_avg', 1.0) + home_stats.get('conceded_avg', 1.2)) / 2.0
    return lambda_home, lambda_away

def calculate_market_probabilities(lambda_home, lambda_away):
    prob_over_2_5, prob_gg = 0.0, 0.0
    for h in range(8):
        for a in range(8):
            p = poisson_prob(lambda_home, h) * poisson_prob(lambda_away, a)
            if (h + a) >= 3: prob_over_2_5 += p
            if h > 0 and a > 0: prob_gg += p
    return prob_over_2_5 * 100, prob_gg * 100

def get_team_form_stats(team_id):
    matches = fetch_api("fixtures", {"team": team_id, "last": 10})
    if not matches: return {"scored_avg": 1.2, "conceded_avg": 1.2}
    scored, conceded = 0, 0
    for m in matches:
        goals = m.get('goals') or {}
        is_home = m.get('teams', {}).get('home', {}).get('id') == team_id
        scored += (goals.get('home') or 0) if is_home else (goals.get('away') or 0)
        conceded += (goals.get('away') or 0) if is_home else (goals.get('home') or 0)
    tot = len(matches)
    return {"scored_avg": scored / tot, "conceded_avg": conceded / tot}

def get_match_odds(fixture_id):
    odds_data = fetch_api("odds", {"fixture": fixture_id, "bookmaker": 8})
    if not odds_data: odds_data = fetch_api("odds", {"fixture": fixture_id})
    odds_dict = {}
    if not odds_data: return odds_dict
    try:
        bookmakers = odds_data[0].get('bookmakers') or []
        target_bm = next((bm for bm in bookmakers if bm.get('id') in [8, 11, 6]), bookmakers[0] if bookmakers else None)
        if target_bm:
            bm_name = target_bm.get('name', 'API Market')
            for b in (target_bm.get('bets') or []):
                name, values = b.get('name') or '', b.get('values') or []
                if name == "Goals Over/Under":
                    for v in values:
                        if v.get('value') == "Over 2.5": odds_dict["Ukupno Golova - Više 2.5"] = (float(v.get('odd')), bm_name)
                elif name == "Both Teams Score":
                    for v in values:
                        if v.get('value') == "Yes": odds_dict["Oba Tima Daju Gol (GG)"] = (float(v.get('odd')), bm_name)
    except Exception: pass
    return odds_dict

def get_value_html_blocks(current_bank=50000.0, max_budget=500.0):
    today_str = datetime.now().strftime('%Y-%m-%d')
    saved_bets = main.load_bets()
    fixtures = fetch_api("fixtures", {"date": today_str})
    email_blocks = []
    new_bets = []
    total_spent = 0.0

    for event in fixtures:
        try:
            fixture = event.get('fixture') or {}
            fixture_id = fixture.get('id')
            if (fixture.get('status') or {}).get('short') not in ['NS', 'TBD']: continue

            teams = event.get('teams') or {}
            home_id, away_id = (teams.get('home') or {}).get('id'), (teams.get('away') or {}).get('id')
            home, away = (teams.get('home') or {}).get('name', 'Home'), (teams.get('away') or {}).get('name', 'Away')
            league_info = event.get('league') or {}
            league, country = league_info.get('name', ''), league_info.get('country', '')

            if not main.is_allowed_league(country, league) or not home_id or not away_id: continue

            home_stats = get_team_form_stats(home_id)
            away_stats = get_team_form_stats(away_id)
            lh, la = calculate_expected_goals(home_stats, away_stats)
            prob_3plus, prob_gg = calculate_market_probabilities(lh, la)

            odds = get_match_odds(fixture_id)

            for market, model_prob in {"Ukupno Golova - Više 2.5": prob_3plus, "Oba Tima Daju Gol (GG)": prob_gg}.items():
                odd_tuple = odds.get(market)
                if not odd_tuple or odd_tuple[0] < MIN_HIGH_ODD: continue

                real_odd, bm_source = odd_tuple
                implied_prob = (1.0 / real_odd) * 100.0
                edge = model_prob - implied_prob

                if edge >= MIN_VALUE_EDGE:
                    p = model_prob / 100.0
                    b = real_odd - 1.0
                    k_frac = (p * b - (1.0 - p)) / b if b > 0 else 0.0
                    stake_pct = max(0.0025, min(0.01, k_frac * 0.20))
                    stake = round((current_bank * stake_pct) / 50.0) * 50
                    stake = max(100.0, stake)

                    if (total_spent + stake) <= max_budget:
                        total_spent += stake
                        block = f"""
                        <div style="background:#ffffff; border-left:4px solid #6f42c1; padding:12px; margin-bottom:12px; border-radius:6px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
                            <h3 style="margin:0 0 5px 0; color:#2c3e50;">⚽ (H) {home} vs {away} (A)</h3>
                            <p style="margin:0 0 4px 0; color:#7f8c8d; font-size:12px;">🏆 {country} - {league} | Očekivani golovi (xG): <b>{lh+la:.2f}</b></p>
                            <p style="margin:0 0 6px 0; color:#495057; font-size:11px; font-style:italic;">
                                💡 <b>Poisson Matematika:</b> Prolanost <b>{model_prob:.1f}%</b> vs Kladionica <b>{implied_prob:.1f}%</b> (Edge: <b style='color:#6f42c1;'>+{edge:.1f}%</b>).
                            </p>
                            <p style="margin:0; font-size:13px;">💎 <b>{market}</b> | Kvota: <b>{real_odd:.2f}</b> <span style='color:#6c757d; font-size:11px;'>(Izvor: {bm_source})</span> | Srazmeran ulog: <b style='color:#6f42c1;'>{stake:,.0f} RSD</b></p>
                        </div>
                        """
                        email_blocks.append(block)
                        new_bets.append({
                            "id": f"{fixture_id}_{market}", "type": "VALUE_BET", "event_id": fixture_id, "date": today_str,
                            "sport": "Football", "match": f"{home} vs {away}", "league": f"{country} - {league}",
                            "market": market, "stake": stake, "odd": real_odd, "status": "PENDING", "profit": 0
                        })

        except Exception as e: print(f"Greška na Value meču: {e}")

    existing_ids = {b.get('id') for b in saved_bets if isinstance(b, dict)}
    for nb in new_bets:
        if nb['id'] not in existing_ids: saved_bets.append(nb)
    main.save_bets(saved_bets)

    return "".join(email_blocks), total_spent
