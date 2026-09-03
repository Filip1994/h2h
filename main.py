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
MIN_ODD = 1.45
MAX_DAILY_H2H_PICKS = 5  # Striktan limit na top 5 zicera dana

EXCLUDED_COUNTRIES = ["Brazil", "Argentina", "Colombia", "Chile", "Uruguay", "Paraguay", "Peru", "Ecuador", "Bolivia", "Venezuela", "Egypt", "Morocco", "Tunisia", "Algeria", "South Africa", "Nigeria", "Ghana", "Senegal", "Cameroon", "Kenya", "Ivory Coast"]
EXCLUDED_LEAGUE_KEYWORDS = ["U19", "U20", "U21", "U23", "Sub-19", "Sub-20", "Reserve", "Reserves", "Amateur", "Oberliga", "Regional", "District", "5th Division", "6th Division", "Next Pro", "MLS Next Pro", "II", "B team"]

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

def load_bets():
    if os.path.exists(BETS_FILE):
        try:
            with open(BETS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except Exception: return []
    return []

def save_bets(bets):
    with open(BETS_FILE, 'w', encoding='utf-8') as f: json.dump(bets, f, ensure_ascii=False, indent=4)

def fetch_recent_form(team_id):
    res = fetch_api("fixtures", {"team": team_id, "last": 10})
    if not res: return {"avg_goals": 0.0}
    goals_scored = sum((m.get('goals', {}).get('home') or 0) if m.get('teams', {}).get('home', {}).get('id') == team_id else (m.get('goals', {}).get('away') or 0) for m in res)
    return {"avg_goals": goals_scored / len(res)}

def fetch_real_odds(fixture_id):
    res = fetch_api("odds", {"fixture": fixture_id, "bookmaker": 8})
    if not res: res = fetch_api("odds", {"fixture": fixture_id})
    odds_dict = {}
    if not res: return odds_dict
    try:
        bookmakers = res[0].get('bookmakers') or []
        target_bm = next((bm for bm in bookmakers if bm.get('id') in [8, 11, 6]), bookmakers[0] if bookmakers else None)
        if target_bm:
            bm_name = target_bm.get('name', 'API Market')
            for b in (target_bm.get('bets') or []):
                name, values = b.get('name') or '', b.get('values') or []
                if name == "Goals Over/Under":
                    for v in values:
                        if v.get('value') == "Over 2.5": odds_dict["Ukupno Golova - Više 2.5"] = (float(v.get('odd')), bm_name)
                        elif v.get('value') == "Under 2.5": odds_dict["Ukupno Golova - Manje 2.5"] = (float(v.get('odd')), bm_name)
                        elif v.get('value') == "Over 1.5": odds_dict["Ukupno Golova - Više 1.5"] = (float(v.get('odd')), bm_name)
                elif name == "Both Teams Score":
                    for v in values:
                        if v.get('value') == "Yes": odds_dict["Oba Tima Daju Gol (GG)"] = (float(v.get('odd')), bm_name)
                elif "Goals" in name or "Multi" in name:
                    for v in values:
                        val = v.get('value', '')
                        if val == "1-3": odds_dict["Raspon Golova - 1-3"] = (float(v.get('odd')), bm_name)
                        elif val == "2-3": odds_dict["Raspon Golova - 2-3"] = (float(v.get('odd')), bm_name)
                        elif val == "2-4": odds_dict["Raspon Golova - 2-4"] = (float(v.get('odd')), bm_name)
                        elif val == "3-5": odds_dict["Raspon Golova - 3-5"] = (float(v.get('odd')), bm_name)
                elif "First Half" in name and "Over/Under" in name:
                    for v in values:
                        if v.get('value') == "Over 0.5": odds_dict["I Poluvreme - Više 0.5"] = (float(v.get('odd')), bm_name)
                elif "Halves" in name or "Both Halves" in name:
                    for v in values:
                        if "Over 0.5 Both Halves" in v.get('value', '') or "1+I&1+II" in v.get('value', ''):
                            odds_dict["Gol u oba poluvremena (1+I & 1+II)"] = (float(v.get('odd')), bm_name)
    except Exception: pass
    return odds_dict

def get_h2h_html_blocks(current_bank=50000.0, max_daily_budget=4000.0):
    today_str = datetime.now().strftime('%Y-%m-%d')
    saved_bets = load_bets()
    raw_picks = []
    seen_fixtures = set()

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

            h2h_all = fetch_api("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}"})
            if len(h2h_all) < MIN_H2H_MATCHES: continue

            recent_h2h = h2h_all[:8]
            total = len(recent_h2h)

            home_form = fetch_recent_form(home_id)
            away_form = fetch_recent_form(away_id)

            formatted_h2h_history = []
            stats = {
                "Ukupno Golova - Više 2.5": 0, "Ukupno Golova - Manje 2.5": 0,
                "Oba Tima Daju Gol (GG)": 0, "I Poluvreme - Više 0.5": 0,
                "Gol u oba poluvremena (1+I & 1+II)": 0, "Raspon Golova - 1-3": 0,
                "Raspon Golova - 2-3": 0, "Raspon Golova - 2-4": 0, "Raspon Golova - 3-5": 0
            }

            for m in recent_h2h:
                goals, score = m.get('goals') or {}, m.get('score') or {}
                halftime = score.get('halftime') or {}
                ft_h, ft_a = goals.get('home') or 0, goals.get('away') or 0
                ht_h, ht_a = halftime.get('home') or 0, halftime.get('away') or 0
                ft_goals, ht_goals = ft_h + ft_a, ht_h + ht_a
                sh_goals = ft_goals - ht_goals

                raw_date = (m.get('fixture') or {}).get('date', '')
                date_str = ""
                if raw_date:
                    try:
                        date_str = datetime.strptime(raw_date[:10], '%Y-%m-%d').strftime('%d.%m.')
                    except Exception: date_str = ""

                match_res_str = f"[{date_str}] <b>{ft_h}:{ft_a}</b> (HT {ht_h}:{ht_a})" if date_str else f"<b>{ft_h}:{ft_a}</b> (HT {ht_h}:{ht_a})"
                formatted_h2h_history.append(match_res_str)

                if ft_goals >= 3: stats["Ukupno Golova - Više 2.5"] += 1
                if ft_goals <= 2: stats["Ukupno Golova - Manje 2.5"] += 1
                if ft_h > 0 and ft_a > 0: stats["Oba Tima Daju Gol (GG)"] += 1
                if ht_goals >= 1: stats["I Poluvreme - Više 0.5"] += 1
                if ht_goals >= 1 and sh_goals >= 1: stats["Gol u oba poluvremena (1+I & 1+II)"] += 1
                if 1 <= ft_goals <= 3: stats["Raspon Golova - 1-3"] += 1
                if 2 <= ft_goals <= 3: stats["Raspon Golova - 2-3"] += 1
                if 2 <= ft_goals <= 4: stats["Raspon Golova - 2-4"] += 1
                if 3 <= ft_goals <= 5: stats["Raspon Golova - 3-5"] += 1

            # TREND FILTER
            last_2_ht = [ (m.get('score', {}).get('halftime', {}).get('home') or 0) + (m.get('score', {}).get('halftime', {}).get('away') or 0) for m in recent_h2h[:2] ]
            if len(last_2_ht) >= 2 and last_2_ht[0] == 0 and last_2_ht[1] == 0:
                stats["I Poluvreme - Više 0.5"] = 0
                stats["Gol u oba poluvremena (1+I & 1+II)"] = 0

            odds = fetch_real_odds(fixture_id)

            best_market_for_match = None
            best_pct_for_match = 0.0

            for market, count in stats.items():
                pct = (count / total) * 100.0
                if pct >= MIN_ACCURACY_PCT and pct > best_pct_for_match:
                    odd_tuple = odds.get(market)
                    if odd_tuple and odd_tuple[0] >= MIN_ODD:
                        best_pct_for_match = pct
                        best_market_for_match = (market, pct, odd_tuple[0], odd_tuple[1], count, total)

            if best_market_for_match and fixture_id not in seen_fixtures:
                seen_fixtures.add(fixture_id)
                m_name, m_pct, m_odd, m_source, m_cnt, m_tot = best_market_for_match
                
                raw_picks.append({
                    "fixture_id": fixture_id, "home": home, "away": away, "league": f"{country} - {league}",
                    "market": m_name, "pct": m_pct, "odd": m_odd, "bm_source": m_source, "count": m_cnt, "total": m_tot,
                    "home_form": home_form['avg_goals'], "away_form": away_form['avg_goals'],
                    "h2h_history": " • ".join(formatted_h2h_history[:4])
                })
        except Exception as e: print(f"Greška na meču: {e}")

    if not raw_picks: return "", 0.0

    raw_picks.sort(key=lambda x: (x['pct'], x['odd']), reverse=True)
    raw_picks = raw_picks[:MAX_DAILY_H2H_PICKS]

    base_stake_per_match = current_bank * 0.015
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

        bet_id = f"{p['fixture_id']}_{p['market']}"
        badge = "🔥 <b>SUPER ZICER</b> " if p['pct'] >= 87.5 else ""

        mailto_skip = f"mailto:filip.maric994@gmail.com?subject=SKIP:{bet_id}&body=Preskacem%20tip%20{p['home']}%20vs%20{p['away']}"

        pick_str = f"{badge}<b>{p['market']}</b> -> <b style='color:#007bff;'>{p['pct']:.0f}%</b> ({p['count']}/{p['total']}) | Kvota: <b>{p['odd']:.2f}</b> <span style='color:#6c757d; font-size:11px;'>(Izvor: {p['bm_source']})</span> | Ulog: <b style='color:#28a745;'>{stake:,.0f} RSD</b>"
        
        block = f"""
        <div style="background:#ffffff; border-left:4px solid #28a745; padding:12px; margin-bottom:12px; border-radius:6px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
            <div style="float:right;">
                <a href="{mailto_skip}" style="background:#dc3545; color:#ffffff; padding:4px 10px; border-radius:4px; font-size:11px; text-decoration:none; font-weight:bold;">❌ Preskoči tip</a>
            </div>
            <h3 style="margin:0 0 5px 0; color:#1a2a3a;">⚽ (H) {p['home']} vs {p['away']} (A)</h3>
            <p style="margin:0 0 4px 0; color:#6c757d; font-size:12px;">🏆 Liga: {p['league']} | Forma: {p['home_form']:.1f} vs {p['away_form']:.1f} gol/meču</p>
            <p style="margin:0 0 8px 0; color:#495057; font-size:11px; font-style:italic;">📜 Poslednji dueli: {p['h2h_history']}</p>
            <p style="margin:0; font-size:13px;">👉 {pick_str}</p>
        </div>
        """
        fb_picks_lines.append(block)

        new_bets.append({
            "id": bet_id, "type": "H2H", "event_id": p['fixture_id'], "date": today_str,
            "sport": "Football", "match": f"{p['home']} vs {p['away']}", "league": p['league'],
            "market": p['market'], "stake": stake, "odd": p['odd'], "status": "PENDING", "profit": 0
        })

    existing_ids = {b.get('id') for b in saved_bets if isinstance(b, dict)}
    for nb in new_bets:
        if nb['id'] not in existing_ids: saved_bets.append(nb)
    save_bets(saved_bets)

    return "".join(fb_picks_lines), total_spent

def skip_bet(keyword):
    bets = load_bets()
    updated = False
    for b in bets:
        if isinstance(b, dict) and b.get('status') == 'PENDING':
            if keyword.lower() in b.get('match', '').lower() or keyword.lower() in str(b.get('id', '')).lower():
                b['status'] = 'SKIPPED'
                b['profit'] = 0
                updated = True
                print(f"✅ Tip {b['match']} ({b['market']}) uspesno prebačen u status SKIPPED!")
    if updated: save_bets(bets)

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
                    ft_goals, ht_goals = ft_h + ft_a, ht_h + ht_a
                    sh_goals = ft_goals - ht_goals

                    market = b.get('market')
                    is_win = False

                    if market == "Ukupno Golova - Više 2.5" and ft_goals >= 3: is_win = True
                    elif market == "Ukupno Golova - Manje 2.5" and ft_goals <= 2: is_win = True
                    elif market == "Oba Tima Daju Gol (GG)" and ft_h > 0 and ft_a > 0: is_win = True
                    elif market == "I Poluvreme - Više 0.5" and ht_goals >= 1: is_win = True
                    elif market == "Gol u oba poluvremena (1+I & 1+II)" and ht_goals >= 1 and sh_goals >= 1: is_win = True
                    elif market == "Raspon Golova - 1-3" and 1 <= ft_goals <= 3: is_win = True
                    elif market == "Raspon Golova - 2-3" and 2 <= ft_goals <= 3: is_win = True
                    elif market == "Raspon Golova - 2-4" and 2 <= ft_goals <= 4: is_win = True
                    elif market == "Raspon Golova - 3-5" and 3 <= ft_goals <= 5: is_win = True

                    stake, odd = b.get('stake', 750), b.get('odd', 1.0)

                    if is_win:
                        b['status'] = 'WIN'
                        b['profit'] = round((stake * odd) - stake, 2)
                    else:
                        b['status'] = 'LOSS'
                        b['profit'] = -stake

                    updated = True

    if updated:
        save_bets(bets)
        print("Večernja provera kompletirana!")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "evening": evening_settle()
        elif sys.argv[1] == "skip" and len(sys.argv) > 2: skip_bet(sys.argv[2])
