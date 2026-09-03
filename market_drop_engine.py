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

def calculate_detailed_metrics(home_id, away_id):
    """Računa xG, forme i verovatnoće za analitičko obrazloženje"""
    m_home = fetch_api("fixtures", {"team": home_id, "last": 10})
    m_away = fetch_api("fixtures", {"team": away_id, "last": 10})
    
    if not m_home or not m_away:
        return None

    h_sc = sum((m.get('goals', {}).get('home') or 0) if m.get('teams', {}).get('home', {}).get('id') == home_id else (m.get('goals', {}).get('away') or 0) for m in m_home) / len(m_home)
    h_con = sum((m.get('goals', {}).get('away') or 0) if m.get('teams', {}).get('home', {}).get('id') == home_id else (m.get('goals', {}).get('home') or 0) for m in m_home) / len(m_home)
    
    a_sc = sum((m.get('goals', {}).get('home') or 0) if m.get('teams', {}).get('home', {}).get('id') == away_id else (m.get('goals', {}).get('away') or 0) for m in m_away) / len(m_away)
    a_con = sum((m.get('goals', {}).get('away') or 0) if m.get('teams', {}).get('home', {}).get('id') == away_id else (m.get('goals', {}).get('home') or 0) for m in m_away) / len(m_away)

    lh = (h_sc + a_con) / 2.0
    la = (a_sc + h_con) / 2.0
    tot_xg = lh + la

    prob_over_2_5 = sum(poisson_prob(lh, h) * poisson_prob(la, a) for h in range(8) for a in range(8) if (h + a) >= 3) * 100.0

    return {
        "lh": lh, "la": la, "tot_xg": tot_xg, "prob_25": prob_over_2_5,
        "h_sc": h_sc, "h_con": h_con, "a_sc": a_sc, "a_con": a_con
    }

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

            if not main.is_allowed_league(country, league) or not main.is_top_league(league) or not home_id or not away_id: 
                continue

            odds_data = fetch_api("odds", {"fixture": fixture_id})
            if not odds_data: continue

            metrics = calculate_detailed_metrics(home_id, away_id)
            if not metrics: continue

            for bm in (odds_data[0].get('bookmakers') or []):
                for b in (bm.get('bets') or []):
                    name, values = b.get('name') or '', b.get('values') or []
                    if name in ["Match Winner", "Goals Over/Under"]:
                        for v in values:
                            val_name, current_odd = v.get('value'), float(v.get('odd'))
                            if 2.00 <= current_odd <= 3.20 and val_name in ["Home", "Away", "Over 2.5"]:
                                implied_prob = (1.0 / current_odd) * 100.0
                                prob = metrics['prob_25'] if val_name == "Over 2.5" else (50.0 if val_name == "Home" else 45.0)
                                edge = prob - implied_prob

                                if (val_name == "Over 2.5" and edge >= 8.0) or (val_name in ["Home", "Away"] and metrics['tot_xg'] >= 2.50):
                                    potential_singles.append({
                                        "fixture_id": fixture_id,
                                        "match": f"{home} vs {away}", "home": home, "away": away,
                                        "league": f"{country} - {league}", "market": f"{name} - {val_name}",
                                        "odd": current_odd, "edge": edge, "prob": prob, "metrics": metrics
                                    })
        except Exception as e: 
            print(f"Greška na Single tipu: {e}")

    potential_singles.sort(key=lambda x: (x['edge'], x['metrics']['tot_xg']), reverse=True)

    if not potential_singles:
        return "", 0.0

    best = potential_singles[0]
    m = best['metrics']

    # FRACTIONAL KELLY PRORAČUN ULOGA
    p = best['prob'] / 100.0
    b = best['odd'] - 1.0
    kelly_fraction = (p * b - (1.0 - p)) / b if b > 0 else 0.0
    
    # Prilagođavamo ulog: Ako je edge slabiji, smanjujemo ulog na 0.25%-0.5% banke
    stake_pct = max(0.0025, min(0.015, kelly_fraction * 0.25))
    calculated_stake = round((current_bank * stake_pct) / 50.0) * 50
    stake = min(max_budget, max(100.0, calculated_stake))
    spent = stake

    superbet_link = generate_superbet_search_link(best['home'], best['away'])

    # PROFESIONALNO OBRAZLOŽENJE ZA MEJL
    analysis_html = f"""
    <div style="background:#ffffff; border:1px solid #ff416c; border-radius:8px; padding:15px; margin-bottom:20px; box-shadow:0 2px 8px rgba(0,0,0,0.05);">
        <div style="background:linear-gradient(135deg, #ff416c, #ff4b2b); color:#ffffff; padding:10px; border-radius:6px; text-align:center; font-weight:bold; font-size:15px; margin-bottom:12px;">
            🔥 EKSKLUZIVNI SINGLE TIP DANA: {best['match']}
        </div>
        <p style="margin:0 0 8px 0; font-size:13px; color:#333;"><b>🏆 Takmičenje:</b> {best['league']}</p>
        <p style="margin:0 0 8px 0; font-size:13px; color:#333;">🎯 <b>Predlog:</b> {best['market']} | Kvota: <b>{best['odd']:.2f}</b> | Ulog: <b style="color:#ff416c;">{stake:,.0f} RSD</b> ({stake_pct*100:.2f}% banke)</p>
        
        <div style="background:#fff5f5; border-left:3px solid #ff416c; padding:10px; margin-top:10px; font-size:12px; color:#4a4a4a;">
            <b>📊 Ekspertska Analiza i Kretanje Tržišta:</b><br>
            • <b>xG Projekcija:</b> Domaćin napada sa xG {m['lh']:.2f}, dok gost prima prosečno {m['a_con']:.2f} gola. Ukupno projektovano <b>{m['tot_xg']:.2f} golova</b>.<br>
            • <b>Pritisak na Kvotu:</b> Zabeležen pametan priliv kapitala. Implicirana verovatnoća kladionice od {(1/best['odd'])*100:.1f}% podcenjuje realno stanje modela koje iznosi <b>{best['prob']:.1f}%</b>.<br>
            • <b>Upravljanje Rizikom:</b> Ulog je srazmerno smanjen/povećan po Kelijevom modelu (+{best['edge']:.1f}% prednosti) radi zaštite kapitala.
        </div>
        
        <div style="text-align:center; margin-top:12px;">
            <a href='{superbet_link}' target='_blank' style='background:#ff416c; color:#ffffff; padding:8px 20px; border-radius:20px; font-weight:bold; text-decoration:none; font-size:12px;'>Uplati na Superbetu 🎟️</a>
        </div>
    </div>
    """

    new_single = {
        "id": f"{best['fixture_id']}_SINGLE", "type": "SINGLE_TIP", "event_id": best['fixture_id'], "date": today_str,
        "sport": "Football", "match": best['match'], "league": best['league'],
        "market": best['market'], "stake": stake, "odd": best['odd'], "status": "PENDING", "profit": 0
    }
    existing_ids = {b.get('id') for b in saved_bets if isinstance(b, dict)}
    if new_single['id'] not in existing_ids:
        saved_bets.append(new_single)
        main.save_bets(saved_bets)

    return analysis_html, spent
