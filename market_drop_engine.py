import os
import sys
import requests
import math
from datetime import datetime
from urllib.parse import quote
import main

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

def generate_superbet_search_link(home_team, away_team):
    clean_home = home_team.split()[0] if home_team else ""
    clean_away = away_team.split()[0] if away_team else ""
    query = quote(f"{clean_home} {clean_away}".strip())
    return f"https://superbet.rs/sr-latn/pretraga?query={query}"

def poisson_prob(lmbda, k):
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

def get_single_candidate_value(home_id, away_id):
    """Računa Poisson edge i prosek golova za potencijalni Single Tip"""
    matches_home = fetch_api("fixtures", {"team": home_id, "last": 10})
    matches_away = fetch_api("fixtures", {"team": away_id, "last": 10})
    
    if not matches_home or not matches_away:
        return 0.0, 0.0

    h_scored = sum((m.get('goals', {}).get('home') or 0) if m.get('teams', {}).get('home', {}).get('id') == home_id else (m.get('goals', {}).get('away') or 0) for m in matches_home) / len(matches_home)
    h_conceded = sum((m.get('goals', {}).get('away') or 0) if m.get('teams', {}).get('home', {}).get('id') == home_id else (m.get('goals', {}).get('home') or 0) for m in matches_home) / len(matches_home)
    
    a_scored = sum((m.get('goals', {}).get('home') or 0) if m.get('teams', {}).get('home', {}).get('id') == away_id else (m.get('goals', {}).get('away') or 0) for m in matches_away) / len(matches_away)
    a_conceded = sum((m.get('goals', {}).get('away') or 0) if m.get('teams', {}).get('home', {}).get('id') == away_id else (m.get('goals', {}).get('home') or 0) for m in matches_away) / len(matches_away)

    lh = (h_scored + a_conceded) / 2.0
    la = (a_scored + h_conceded) / 2.0
    tot_xg = lh + la

    prob_over_2_5 = 0.0
    for h in range(8):
        for a in range(8):
            if (h + a) >= 3:
                prob_over_2_5 += poisson_prob(lh, h) * poisson_prob(la, a)

    return tot_xg, prob_over_2_5 * 100.0

def get_market_drops_and_single_tip(current_bank=50000.0, max_budget=500.0):
    today_str = datetime.now().strftime('%Y-%m-%d')
    saved_bets = main.load_bets()
    fixtures = fetch_api("fixtures", {"date": today_str})
    potential_singles = []

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

            # STROGA SELEKCIJA: Samo elitne lige i ne-zabranjene!
            if not main.is_allowed_league(country, league) or not main.is_top_league(league) or not home_id or not away_id: 
                continue

            odds_data = fetch_api("odds", {"fixture": fixture_id})
            if not odds_data: continue

            tot_xg, prob_3plus = get_single_candidate_value(home_id, away_id)

            for bm in (odds_data[0].get('bookmakers') or []):
                for b in (bm.get('bets') or []):
                    name, values = b.get('name') or '', b.get('values') or []
                    if name in ["Match Winner", "Goals Over/Under"]:
                        for v in values:
                            val_name, current_odd = v.get('value'), float(v.get('odd'))
                            if 2.00 <= current_odd <= 3.20 and val_name in ["Home", "Away", "Over 2.5"]:
                                implied_prob = (1.0 / current_odd) * 100.0
                                edge = prob_3plus - implied_prob if val_name == "Over 2.5" else 0.0
                                
                                # RIGOROZAN FILTER: Mora postojati stvarni matematički value ili jak xG!
                                if (val_name == "Over 2.5" and edge >= 8.0) or (val_name in ["Home", "Away"] and tot_xg >= 2.50):
                                    potential_singles.append({
                                        "fixture_id": fixture_id,
                                        "match": f"{home} vs {away}", "home": home, "away": away,
                                        "league": f"{country} - {league}", "market": f"{name} - {val_name}",
                                        "odd": current_odd, "edge": edge, "xg": tot_xg
                                    })
        except Exception as e: 
            print(f"Greška na Single tipu: {e}")

    potential_singles.sort(key=lambda x: (x['edge'], x['xg']), reverse=True)

    # Ako NEMA meča koji zadovoljava rigorozne kriterijume, VRAĆAMO PRAZNO (Ne silujemo ponudu)
    if not potential_singles:
        return "", 0.0

    best_single = potential_singles[0]
    superbet_link = generate_superbet_search_link(best_single['home'], best_single['away'])
    stake = min(max_budget, max(100.0, round((current_bank * 0.01) / 50.0) * 50))
    spent = stake

    single_html = f"""
    <div style="background:linear-gradient(135deg, #ff416c, #ff4b2b); color:#ffffff; padding:16px; border-radius:8px; margin-bottom:20px; text-align:center;">
        <h3 style="margin:0 0 6px 0;">🔥 EKSKLUZIVNI SINGLE TIP DANA (Kvota {best_single['odd']:.2f})</h3>
        <p style="margin:0 0 6px 0; font-size:14px;">⚽ <b>{best_single['match']}</b> ({best_single['league']})</p>
        <p style="margin:0 0 10px 0; font-size:11px; opacity:0.9; font-style:italic;">
            💡 <b>Market Analiza:</b> Elitna liga, xG projekcija {best_single['xg']:.2f} i potvrđen matematički pritisak na kvotu.
        </p>
        <div style="background:rgba(255,255,255,0.2); display:inline-block; padding:6px 16px; border-radius:20px; font-weight:bold; font-size:13px; margin-bottom:8px;">
            🎯 {best_single['market']} | Kvota: {best_single['odd']:.2f} | Ulog: <b>{stake:,.0f} RSD</b>
        </div><br>
        <a href='{superbet_link}' target='_blank' style='background:#ffffff; color:#ff416c; padding:6px 18px; border-radius:20px; font-weight:bold; text-decoration:none; font-size:13px;'>Uplati na Superbetu 🎟️</a>
    </div>
    """

    new_single = {
        "id": f"{best_single['fixture_id']}_SINGLE", "type": "SINGLE_TIP", "event_id": best_single['fixture_id'], "date": today_str,
        "sport": "Football", "match": best_single['match'], "league": best_single['league'],
        "market": best_single['market'], "stake": stake, "odd": best_single['odd'], "status": "PENDING", "profit": 0
    }
    existing_ids = {b.get('id') for b in saved_bets if isinstance(b, dict)}
    if new_single['id'] not in existing_ids:
        saved_bets.append(new_single)
        main.save_bets(saved_bets)

    return single_html, spent
