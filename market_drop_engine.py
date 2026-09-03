import os
import sys
import requests
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

def get_market_drops_and_single_tip(current_bank=50000.0, max_budget=500.0):
    today_str = datetime.now().strftime('%Y-%m-%d')
    saved_bets = main.load_bets()

    # ZAMRZAVANJE: Ako je Tip Dana za danas već izabran, prikaži ga i NE menjaj
    today_single_bets = [b for b in saved_bets if isinstance(b, dict) and b.get('date') == today_str and b.get('type') == 'SINGLE_TIP']
    if today_single_bets:
        b = today_single_bets[0]
        teams = b.get('match', '').split(' vs ')
        h_team = teams[0] if len(teams) > 0 else ""
        a_team = teams[1] if len(teams) > 1 else ""
        superbet_link = generate_superbet_search_link(h_team, a_team)
        single_html = f"""
        <div style="background:linear-gradient(135deg, #ff416c, #ff4b2b); color:#ffffff; padding:16px; border-radius:8px; margin-bottom:20px; text-align:center;">
            <h3 style="margin:0 0 6px 0;">🔥 EKSKLUZIVNI SINGLE TIP DANA (Kvota {b.get('odd'):.2f})</h3>
            <p style="margin:0 0 6px 0; font-size:14px;">⚽ <b>{b.get('match')}</b> ({b.get('league')})</p>
            <p style="margin:0 0 10px 0; font-size:11px; opacity:0.9; font-style:italic;">
                💡 <b>Market Analiza:</b> Zabeležen pametan priliv novca i pritisak uplatne mase na ovu kvotu u elitnoj ligi.
            </p>
            <div style="background:rgba(255,255,255,0.2); display:inline-block; padding:6px 16px; border-radius:20px; font-weight:bold; font-size:13px; margin-bottom:8px;">
                🎯 {b.get('market')} | Kvota: {b.get('odd'):.2f} | Ulog: <b>{b.get('stake', 0):,.0f} RSD</b>
            </div><br>
            <a href='{superbet_link}' target='_blank' style='background:#ffffff; color:#ff416c; padding:6px 18px; border-radius:20px; font-weight:bold; text-decoration:none; font-size:13px;'>Uplati na Superbetu 🎟️</a>
        </div>
        """
        return single_html, b.get('stake', 0)

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
            league, country = league_info.get('name', ''), league_info.get('country', '')

            # STROGA SELEKCIJA: Samo dozvoljene i poznate lige!
            if not main.is_allowed_league(country, league) or not main.is_top_league(league): continue

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
                                    "fixture_id": fixture_id,
                                    "match": f"{home} vs {away}", "home": home, "away": away,
                                    "league": f"{country} - {league}", "market": f"{name} - {val_name}", "odd": current_odd
                                })
        except Exception as e: print(f"Greška na Single tipu: {e}")

    single_html = ""
    spent = 0.0
    if potential_singles:
        best_single = potential_singles[0]
        superbet_link = generate_superbet_search_link(best_single['home'], best_single['away'])
        stake = min(max_budget, max(100.0, round((current_bank * 0.01) / 50.0) * 50))
        spent = stake

        single_html = f"""
        <div style="background:linear-gradient(135deg, #ff416c, #ff4b2b); color:#ffffff; padding:16px; border-radius:8px; margin-bottom:20px; text-align:center;">
            <h3 style="margin:0 0 6px 0;">🔥 EKSKLUZIVNI SINGLE TIP DANA (Kvota {best_single['odd']:.2f})</h3>
            <p style="margin:0 0 6px 0; font-size:14px;">⚽ <b>{best_single['match']}</b> ({best_single['league']})</p>
            <p style="margin:0 0 10px 0; font-size:11px; opacity:0.9; font-style:italic;">
                💡 <b>Market Analiza:</b> Zabeležen pametan priliv novca i pritisak uplatne mase na ovu kvotu u elitnoj ligi.
            </p>
            <div style="background:rgba(255,255,255,0.2); display:inline-block; padding:6px 16px; border-radius:20px; font-weight:bold; font-size:13px; margin-bottom:8px;">
                🎯 {best_single['market']} | Kvota: {best_single['odd']:.2f} | Ulog: <b>{stake:,.0f} RSD</b>
            </div><br>
            <a href='{superbet_link}' target='_blank' style='background:#ffffff; color:#ff416c; padding:6px 18px; border-radius:20px; font-weight:bold; text-decoration:none; font-size:13px;'>Uplati na Superbetu 🎟️</a>
        </div>
        """

        # Sačuvaj Tip Dana u bets.json da se ZAMRZNUTI ne bi menjao u toku dana
        saved_bets.append({
            "id": f"{best_single['fixture_id']}_SINGLE", "type": "SINGLE_TIP", "event_id": best_single['fixture_id'], "date": today_str,
            "sport": "Football", "match": best_single['match'], "league": best_single['league'],
            "market": best_single['market'], "stake": stake, "odd": best_single['odd'], "status": "PENDING", "profit": 0
        })
        main.save_bets(saved_bets)

    return single_html, spent
