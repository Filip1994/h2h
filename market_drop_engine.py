import os
import sys
import requests
from datetime import datetime

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
    query = f"{home_team} {away_team}".replace(" ", "%20")
    return f"https://superbet.rs/sr-latn/pretraga?query={query}"

def get_market_drops_and_single_tip(current_bank=50000.0, max_budget=500.0):
    today_str = datetime.now().strftime('%Y-%m-%d')
    fixtures = fetch_api("fixtures", {"date": today_str})
    potential_singles = []

    for event in fixtures:
        try:
            fixture = event.get('fixture') or {}
            fixture_id = fixture.get('id')
            if (fixture.get('status') or {}).get('short') not in ['NS', 'TBD']: continue

            teams = event.get('teams') or {}
            home, away = (teams.get('home') or {}).get('name', 'Home'), (teams.get('away') or {}).get('name', 'Away')
            league_info = event.get('league') or {}
            league = f"{league_info.get('country')} - {league_info.get('name')}"

            odds_data = fetch_api("odds", {"fixture": fixture_id})
            if not odds_data: continue

            for bm in (odds_data[0].get('bookmakers') or []):
                for b in (bm.get('bets') or []):
                    name, values = b.get('name') or '', b.get('values') or []
                    if name in ["Match Winner", "Goals Over/Under"]:
                        for v in values:
                            val_name, current_odd = v.get('value'), float(v.get('odd'))
                            if 2.00 <= current_odd <= 3.20 and val_name in ["Home", "Away", "Over 2.5"]:
                                potential_singles.append({
                                    "match": f"{home} vs {away}", "home": home, "away": away,
                                    "league": league, "market": f"{name} - {val_name}", "odd": current_odd
                                })
        except Exception as e: print(f"Greška na Single tipu: {e}")

    single_html = ""
    spent = 0.0
    if potential_singles:
        best_single = potential_singles[0]
        superbet_link = generate_superbet_search_link(best_single['home'], best_single['away'])
        stake = min(max_budget, max(100.0, round((current_bank * 0.01) / 50.0) * 50)) # 1% Banke
        spent = stake

        single_html = f"""
        <div style="background:linear-gradient(135deg, #ff416c, #ff4b2b); color:#ffffff; padding:16px; border-radius:8px; margin-bottom:20px; text-align:center;">
            <h3 style="margin:0 0 6px 0;">🔥 EKSKLUZIVNI SINGLE TIP DANA (Kvota {best_single['odd']:.2f})</h3>
            <p style="margin:0 0 8px 0; font-size:14px;">⚽ <b>{best_single['match']}</b> ({best_single['league']})</p>
            <div style="background:rgba(255,255,255,0.2); display:inline-block; padding:6px 16px; border-radius:20px; font-weight:bold; font-size:13px; margin-bottom:8px;">
                🎯 {best_single['market']} | Kvota: {best_single['odd']:.2f} | Ulog: <b>{stake:,.0f} RSD</b>
            </div><br>
            <a href='{superbet_link}' target='_blank' style='background:#ffffff; color:#ff416c; padding:6px 18px; border-radius:20px; font-weight:bold; text-decoration:none; font-size:13px;'>Uplati na Superbetu 🎟️</a>
        </div>
        """

    return single_html, spent
