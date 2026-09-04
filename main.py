import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta
import quant_math

API_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
BETS_FILE = "bets.json"
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {'x-apisports-key': API_KEY}

# STROGA MATEMATIČKA PODEŠAVANJA
MIN_H2H_MATCHES = 5         # Minimum 5 mečeva u uzorku
YEAR_WINDOW = 4             # Maksimalno 4 godine unazad (sve pre 2022. se odbacuje)
MAX_RECENT_DAYS = 730       # Bar 1 meč odigran u poslednja 24 meseca
MIN_ACCURACY_PCT = 75.0
MIN_ODD = 1.45
MAX_DAILY_H2H_PICKS = 5

EXCLUDED_COUNTRIES = ["Brazil", "Argentina", "Colombia", "Chile", "Uruguay", "Paraguay", "Peru", "Ecuador", "Bolivia", "Venezuela", "Egypt", "Morocco", "Tunisia", "Algeria", "South Africa", "Nigeria", "Ghana", "Cameroon", "Kenya", "Ivory Coast"]
EXCLUDED_KEYWORDS = ["U19", "U20", "U21", "U23", "Sub-19", "Sub-20", "Reserve", "Reserves", "Amateur", "Oberliga", "District", "5th Division", "MLS Next Pro", "II", "B team", "Youth"]

def fetch_api(endpoint, params=None):
    try:
        res = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=12)
        return res.json().get('response') or []
    except Exception as e:
        print(f"Greška na API [{endpoint}]: {e}")
        return []

def is_allowed_match(country_name, league_name, home_name, away_name):
    for country in EXCLUDED_COUNTRIES:
        if country and country.lower() in country_name.lower(): return False
    full_text = f"{league_name} {home_name} {away_name}".lower()
    for kw in EXCLUDED_KEYWORDS:
        if kw and kw.lower() in full_text: return False
    return True

def load_bets():
    if os.path.exists(BETS_FILE):
        try:
            with open(BETS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
        except Exception: return []
    return []

def save_bets(bets):
    with open(BETS_FILE, 'w', encoding='utf-8') as f: json.dump(bets, f, ensure_ascii=False, indent=4)

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
                elif name == "Both Teams Score":
                    for v in values:
                        if v.get('value') == "Yes": odds_dict["Oba Tima Daju Gol (GG)"] = (float(v.get('odd')), bm_name)
    except Exception: pass
    return odds_dict

def get_h2h_raw_picks():
    today_str = datetime.now().strftime('%Y-%m-%d')
    current_year = datetime.now().year
    min_year = current_year - YEAR_WINDOW
    now_ts = int(time.time())

    raw_picks = []
    seen_fixtures = set()

    fb_events = fetch_api("fixtures", {"date": today_str})

    for event in fb_events:
        try:
            fixture = event.get('fixture') or {}
            fixture_id = fixture.get('id')
            match_ts = fixture.get('timestamp') or 0

            if match_ts <= (now_ts + 900) or match_ts >= (now_ts + 86400): continue
            if (fixture.get('status') or {}).get('short') not in ['NS', 'TBD']: continue

            match_time_str = datetime.fromtimestamp(match_ts, tz=timezone.utc).astimezone(timezone(timedelta(hours=2))).strftime('%H:%M')

            teams = event.get('teams') or {}
            home, away = (teams.get('home') or {}).get('name', 'Home'), (teams.get('away') or {}).get('name', 'Away')
            home_id, away_id = (teams.get('home') or {}).get('id'), (teams.get('away') or {}).get('id')
            league_info = event.get('league') or {}
            league, country = league_info.get('name', 'Liga'), league_info.get('country', 'Nacionalno')

            if not is_allowed_match(country, league, home, away) or not home_id or not away_id: continue

            h2h_all = fetch_api("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}"})
            
            completed_h2h = []
            dates_list = []
            has_recent_match = False

            for m in h2h_all:
                st = (m.get('fixture') or {}).get('status', {}).get('short')
                if st in ['FT', 'AET', 'PEN']:
                    raw_date = (m.get('fixture') or {}).get('date') or ''
                    if raw_date:
                        try:
                            m_dt = datetime.strptime(raw_date[:10], '%Y-%m-%d')
                            if m_dt.year >= min_year:
                                completed_h2h.append(m)
                                dates_list.append(raw_date)
                                if (datetime.now() - m_dt).days <= MAX_RECENT_DAYS:
                                    has_recent_match = True
                        except Exception: pass

            # MATEMATIČKI FILTERI: Min 5 mečeva u zadnje 4 godine + bar 1 meč u zadnja 24 meseca
            if len(completed_h2h) < MIN_H2H_MATCHES or not has_recent_match: continue

            weights = quant_math.calculate_dixon_coles_weights(dates_list)
            weighted_total = sum(weights) if sum(weights) > 0 else len(completed_h2h)

            formatted_h2h_history = []
            weighted_stats = {"Ukupno Golova - Više 2.5": 0.0, "Ukupno Golova - Manje 2.5": 0.0, "Oba Tima Daju Gol (GG)": 0.0}

            for idx, m in enumerate(completed_h2h):
                goals = m.get('goals') or {}
                halftime = (m.get('score') or {}).get('halftime') or {}
                ft_h, ft_a = goals.get('home') or 0, goals.get('away') or 0
                ht_h, ht_a = halftime.get('home') or 0, halftime.get('away') or 0
                ft_goals = ft_h + ft_a
                w = weights[idx] if idx < len(weights) else 0.5

                raw_date = (m.get('fixture') or {}).get('date') or ''
                date_str = datetime.strptime(raw_date[:10], '%Y-%m-%d').strftime('%d.%m.%Y.') if raw_date else ""

                formatted_h2h_history.append(f"[{date_str}] <b>{ft_h}:{ft_a}</b> (HT {ht_h}:{ht_a})")

                if ft_goals >= 3: weighted_stats["Ukupno Golova - Više 2.5"] += w
                if ft_goals <= 2: weighted_stats["Ukupno Golova - Manje 2.5"] += w
                if ft_h > 0 and ft_a > 0: weighted_stats["Oba Tima Daju Gol (GG)"] += w

            odds = fetch_real_odds(fixture_id)

            best_market_for_match = None
            best_pct_for_match = 0.0

            for market, w_count in weighted_stats.items():
                pct = (w_count / weighted_total) * 100.0
                if pct >= MIN_ACCURACY_PCT and pct > best_pct_for_match:
                    odd_tuple = odds.get(market)
                    if odd_tuple and odd_tuple[0] >= MIN_ODD:
                        best_pct_for_match = pct
                        best_market_for_match = (market, pct, odd_tuple[0], odd_tuple[1], len(completed_h2h))

            if best_market_for_match and fixture_id not in seen_fixtures:
                seen_fixtures.add(fixture_id)
                m_name, m_pct, m_odd, m_source, m_tot = best_market_for_match
                
                display_history = list(reversed(formatted_h2h_history[-5:]))
                
                raw_picks.append({
                    "fixture_id": fixture_id, "home": home, "away": away, "league": f"{country} - {league}",
                    "match_time": match_time_str, "market": m_name, "pct": m_pct, "odd": m_odd,
                    "bm_source": m_source, "total": m_tot, "h2h_history": " • ".join(display_history)
                })
        except Exception as e: print(f"Greška na meču: {e}")

    raw_picks.sort(key=lambda x: (x['pct'], x['odd']), reverse=True)
    return raw_picks[:MAX_DAILY_H2H_PICKS]

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
                    goals = fixture_data.get('goals') or {}
                    ft_h, ft_a = goals.get('home') or 0, goals.get('away') or 0
                    ft_goals = ft_h + ft_a

                    closing_odds = fetch_real_odds(fixture_id)
                    captured_odd = b.get('odd', 1.0)
                    market = b.get('market')
                    
                    if market in closing_odds:
                        c_odd = closing_odds[market][0]
                        clv_edge = ((captured_odd - c_odd) / c_odd) * 100.0 if c_odd > 0 else 0.0
                        b['clv_edge'] = round(clv_edge, 2)

                    is_win = False
                    if market == "Ukupno Golova - Više 2.5" and ft_goals >= 3: is_win = True
                    elif market == "Ukupno Golova - Manje 2.5" and ft_goals <= 2: is_win = True
                    elif market == "Oba Tima Daju Gol (GG)" and ft_h > 0 and ft_a > 0: is_win = True

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
        print("Večernja provera i CLV poravnanje kompletirani!")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "evening": evening_settle()
        elif sys.argv[1] == "skip" and len(sys.argv) > 2: skip_bet(sys.argv[2])
