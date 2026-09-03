import os
import sys
import time
import requests
import math
from datetime import datetime, timezone, timedelta
import main

API_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {'x-apisports-key': API_KEY}
GITHUB_REPO = "Filip1994/h2h"

def fetch_api(endpoint, params=None):
    try:
        res = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=12)
        return res.json().get('response') or []
    except Exception as e:
        print(f"Greška na API [{endpoint}]: {e}")
        return []

def poisson_prob(lmbda, k):
    return (math.pow(lmbda, k) * math.exp(-lmbda)) / math.factorial(k)

def calculate_detailed_metrics(home_id, away_id):
    m_home = fetch_api("fixtures", {"team": home_id, "last": 10})
    m_away = fetch_api("fixtures", {"team": away_id, "last": 10})
    
    completed_h = [m for m in m_home if (m.get('fixture') or {}).get('status', {}).get('short') in ['FT', 'AET', 'PEN']]
    completed_a = [m for m in m_away if (m.get('fixture') or {}).get('status', {}).get('short') in ['FT', 'AET', 'PEN']]

    if not completed_h or not completed_a: return None

    h_sc = sum((m.get('goals', {}).get('home') or 0) if m.get('teams', {}).get('home', {}).get('id') == home_id else (m.get('goals', {}).get('away') or 0) for m in completed_h) / len(completed_h)
    h_con = sum((m.get('goals', {}).get('away') or 0) if m.get('teams', {}).get('home', {}).get('id') == home_id else (m.get('goals', {}).get('home') or 0) for m in completed_h) / len(completed_h)
    
    a_sc = sum((m.get('goals', {}).get('home') or 0) if m.get('teams', {}).get('away', {}).get('id') == away_id else (m.get('goals', {}).get('away') or 0) for m in completed_a) / len(completed_a)
    a_con = sum((m.get('goals', {}).get('away') or 0) if m.get('teams', {}).get('away', {}).get('id') == away_id else (m.get('goals', {}).get('home') or 0) for m in completed_a) / len(completed_a)

    lh, la = (h_sc + a_con) / 2.0, (a_sc + h_con) / 2.0
    tot_xg = lh + la
    prob_over_2_5 = sum(poisson_prob(lh, h) * poisson_prob(la, a) for h in range(8) for a in range(8) if (h + a) >= 3) * 100.0

    return {"lh": lh, "la": la, "tot_xg": tot_xg, "prob_25": prob_over_2_5, "h_sc": h_sc, "h_con": h_con, "a_sc": a_sc, "a_con": a_con}

def get_market_drops_and_single_tip(current_bank=50000.0, max_budget=500.0):
    today_str = datetime.now().strftime('%Y-%m-%d')
    now_ts = int(time.time())
    saved_bets = main.load_bets()
    fixtures = fetch_api("fixtures", {"date": today_str})
    potential_singles = []
    rejection_reasons = []

    for event in fixtures:
        try:
            fixture = event.get('fixture') or {}
            fixture_id = fixture.get('id')
            match_ts = fixture.get('timestamp', 0)

            # STRIKTAN VREMENSKI FILTER (MINIMUN 15 MINUTA UNAPRED)
            if match_ts <= (now_ts + 900): continue
            if (fixture.get('status') or {}).get('short') not in ['NS', 'TBD']: continue

            match_time_str = datetime.fromtimestamp(match_ts, tz=timezone.utc).astimezone(timezone(timedelta(hours=2))).strftime('%H:%M')

            teams = event.get('teams') or {}
            home_id, away_id = (teams.get('home') or {}).get('id'), (teams.get('away') or {}).get('id')
            home, away = (teams.get('home') or {}).get('name', 'Home'), (teams.get('away') or {}).get('name', 'Away')
            league_info = event.get('league') or {}
            league, country = league_info.get('name', ''), league_info.get('country', '')
            full_league_name = f"{country} - {league}"

            if not main.is_allowed_league(country, league) or not home_id or not away_id: 
                continue

            odds_data = fetch_api("odds", {"fixture": fixture_id, "bookmaker": 8})
            if not odds_data: odds_data = fetch_api("odds", {"fixture": fixture_id})
            if not odds_data:
                rejection_reasons.append(f"<b>{home} vs {away}</b> ({full_league_name}): Nema dostupnih kvota.")
                continue

            metrics = calculate_detailed_metrics(home_id, away_id)
            if not metrics: continue

            bookmakers = odds_data[0].get('bookmakers') or []
            target_bm = next((bm for bm in bookmakers if bm.get('id') in [8, 11, 6]), bookmakers[0] if bookmakers else None)

            if target_bm:
                bm_name = target_bm.get('name', 'API Market')
                for b in (target_bm.get('bets') or []):
                    name, values = b.get('name') or '', b.get('values') or []
                    if name in ["Match Winner", "Goals Over/Under"]:
                        for v in values:
                            val_name, current_odd = v.get('value'), float(v.get('odd'))
                            if val_name in ["Home", "Away", "Over 2.5"]:
                                implied_prob = (1.0 / current_odd) * 100.0
                                prob = metrics['prob_25'] if val_name == "Over 2.5" else (50.0 if val_name == "Home" else 45.0)
                                edge = prob - implied_prob

                                if not (2.00 <= current_odd <= 3.20):
                                    rejection_reasons.append(f"<b>{home} vs {away}</b> ({val_name}): Kvota {current_odd:.2f} van opsega [2.00 - 3.20].")
                                    continue

                                if (val_name == "Over 2.5" and edge >= 8.0) or (val_name in ["Home", "Away"] and metrics['tot_xg'] >= 2.50):
                                    potential_singles.append({
                                        "fixture_id": fixture_id,
                                        "match": f"(H) {home} vs {away} (A)", "home": home, "away": away,
                                        "league": full_league_name, "market": f"{name} - {val_name}",
                                        "match_time": match_time_str,
                                        "odd": current_odd, "bm_source": bm_name, "edge": edge, "prob": prob, "metrics": metrics
                                    })
                                else:
                                    rejection_reasons.append(f"<b>{home} vs {away}</b> ({val_name}): Nedovoljan Edge (+{edge:.1f}%) ili xG ({metrics['tot_xg']:.2f} < 2.50).")

        except Exception as e: print(f"Greška na Single tipu: {e}")

    potential_singles.sort(key=lambda x: (x['edge'], x['metrics']['tot_xg']), reverse=True)

    if not potential_singles:
        rejection_html = "<div style='background:#fff3cd; border:1px solid #ffeeba; color:#856404; padding:12px; border-radius:8px; margin-bottom:20px; font-size:12px;'>"
        rejection_html += "<b>⚠️ Danas nema Single Tipa Dana. Razlozi odbijanja kandidata:</b><ul style='margin:5px 0 0 15px; padding:0;'>"
        for r in rejection_reasons[:5]:
            rejection_html += f"<li>{r}</li>"
        rejection_html += "</ul></div>"
        return rejection_html, 0.0, None

    best = potential_singles[0]
    m = best['metrics']

    p, b = best['prob'] / 100.0, best['odd'] - 1.0
    kelly_fraction = (p * b - (1.0 - p)) / b if b > 0 else 0.0
    stake_pct = max(0.0025, min(0.015, kelly_fraction * 0.25))
    stake = min(max_budget, max(100.0, round((current_bank * stake_pct) / 50.0) * 50))
    spent = stake

    bet_id = f"{best['fixture_id']}_SINGLE"
    direct_web_skip = f"https://github.com/{GITHUB_REPO}/issues/new?title=SKIP_{bet_id}"

    analysis_html = f"""
    <div style="background:#ffffff; border:1px solid #6366f1; border-left:5px solid #4338ca; border-radius:8px; padding:15px; margin-bottom:20px; box-shadow:0 4px 12px rgba(67, 56, 202, 0.08);">
        <div style="float:right;">
            <a href="{direct_web_skip}" target="_blank" style="background:#dc3545; color:#ffffff; padding:4px 10px; border-radius:4px; font-size:11px; text-decoration:none; font-weight:bold;">❌ Preskoči tip</a>
        </div>
        <div style="background:linear-gradient(135deg, #1e1b4b, #4338ca); color:#ffffff; padding:10px; border-radius:6px; text-align:center; font-weight:bold; font-size:15px; margin-bottom:12px; letter-spacing:0.5px;">
            ⭐ EKSKLUZIVNI SINGLE TIP DANA: {best['match']}
        </div>
        <p style="margin:0 0 8px 0; font-size:13px; color:#1e293b;"><b>⏰ Početak:</b> <b style="color:#4338ca;">{best['match_time']}h</b> | <b>🏆 Takmičenje:</b> {best['league']}</p>
        <p style="margin:0 0 8px 0; font-size:13px; color:#1e293b;">🎯 <b>Predlog:</b> {best['market']} | Kvota: <b>{best['odd']:.2f}</b> <span style='color:#64748b; font-size:11px;'>(Izvor: {best['bm_source']})</span> | Ulog: <b style="color:#4338ca;">{stake:,.0f} RSD</b> ({stake_pct*100:.2f}% banke)</p>
        
        <div style="background:#f5f3ff; border-left:3px solid #6366f1; padding:10px; margin-top:10px; font-size:12px; color:#334155;">
            <b>📊 Ekspertska Analiza i Kretanje Tržišta:</b><br>
            • <b>xG Projekcija:</b> Domaćin napada sa xG {m['lh']:.2f}, dok gost ima projektovani xG od {m['la']:.2f}. Ukupno očekivano: <b>{m['tot_xg']:.2f} golova</b>.<br>
            • <b>Pritisak na Kvotu:</b> Implicirana verovatnoća kladionice od {(1/best['odd'])*100:.1f}% podcenjuje realno stanje modela od <b>{best['prob']:.1f}%</b> (Prednost: +{best['edge']:.1f}%).<br>
            • <b>Upravljanje Rizikom:</b> Dinamički 1/4 Kelly ulog.
        </div>
    </div>
    """

    new_single = {
        "id": bet_id, "type": "SINGLE_TIP", "event_id": best['fixture_id'], "date": today_str,
        "sport": "Football", "match": best['match'], "league": best['league'],
        "market": best['market'], "stake": stake, "odd": best['odd'], "status": "PENDING", "profit": 0
    }
    existing_ids = {b.get('id') for b in saved_bets if isinstance(b, dict)}
    if new_single['id'] not in existing_ids:
        saved_bets.append(new_single)
        main.save_bets(saved_bets)

    return analysis_html, spent, best['fixture_id']
