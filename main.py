import os
import time
import requests
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

API_KEY = os.environ.get("API_FOOTBALL_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASS")

BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {
    'x-apisports-key': API_KEY
}

TOP_LEAGUES = [39, 140, 135, 78, 61, 283, 218, 94, 203, 2]

def send_email(subject, body):
    if not GMAIL_USER or not GMAIL_PASS:
        print("❌ Nedostaju Gmail podešavanja.")
        return
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        print("Mejl uspešno poslat!")
    except Exception as e:
        print(f"Greška pri slanju mejla: {e}")

def get_todays_fixtures():
    today = datetime.now().strftime('%Y-%m-%d')
    url = f"{BASE_URL}/fixtures?date={today}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        data = res.json()
    except Exception as e:
        print(f"Greška pri pozivu API-ja: {e}")
        return [], {"error": str(e)}
    
    api_errors = data.get('errors', {})
    response = data.get('response')
    fixtures = response if isinstance(response, list) else []
    
    popular_fixtures = [f for f in fixtures if isinstance(f, dict) and f.get('league', {}).get('id') in TOP_LEAGUES]
    
    if len(popular_fixtures) < 50:
        other_fixtures = [f for f in fixtures if isinstance(f, dict) and f.get('league', {}).get('id') not in TOP_LEAGUES]
        popular_fixtures.extend(other_fixtures[:50 - len(popular_fixtures)])
        
    return popular_fixtures, api_errors

def get_h2h(team1_id, team2_id):
    try:
        res = requests.get(f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}", headers=HEADERS, timeout=15)
        data = res.json()
        response = data.get('response')
        return response if isinstance(response, list) else []
    except Exception as e:
        print(f"Greška u H2H: {e}")
        return []

def get_fixture_odds(fixture_id):
    try:
        res = requests.get(f"{BASE_URL}/odds?fixture={fixture_id}", headers=HEADERS, timeout=15)
        data = res.json()
        response = data.get('response')
        if not isinstance(response, list) or not response:
            return {}
            
        bookmakers = response[0].get('bookmakers', [])
        if not bookmakers or not isinstance(bookmakers, list):
            return {}
            
        bets = bookmakers[0].get('bets', [])
        if not isinstance(bets, list):
            return {}

        odds_dict = {}
        for bet in bets:
            if not isinstance(bet, dict): continue
            name = bet.get('name')
            if name in ["Goals Over/Under", "Match Goals"]:
                vals = bet.get('values', [])
                if isinstance(vals, list):
                    for val in vals:
                        if isinstance(val, dict) and val.get('value') == "Over 2.5":
                            odds_dict["3+ Ukupno"] = val.get('odd')
                        
        return odds_dict
    except Exception:
        return {}

def evaluate_h2h(h2h_list):
    if not isinstance(h2h_list, list) or not h2h_list:
        return []

    def extract_date(match):
        if isinstance(match, dict):
            return match.get('fixture', {}).get('date', '') or ''
        return ''

    sorted_h2h = sorted(h2h_list, key=extract_date, reverse=True)
    last_3 = sorted_h2h[:3]
    total = len(last_3)
    
    if total < 3:
        return []

    stats = {
        "1-3 Golova": 0,
        "2-4 Golova": 0,
        "3-5 Golova": 0,
        "3+ Ukupno": 0,
        "1-3 I pol": 0,
        "1-3 II pol": 0,
        "2+ I pol": 0
    }

    for match in last_3:
        if not isinstance(match, dict):
            continue
            
        score = match.get('score') or {}
        halftime = score.get('halftime') or {}
        fulltime = score.get('fulltime') or {}

        ht_home = halftime.get('home')
        ht_away = halftime.get('away')
        ft_home = fulltime.get('home')
        ft_away = fulltime.get('away')

        if None in (ht_home, ht_away, ft_home, ft_away):
            continue

        try:
            ft_goals = int(ft_home) + int(ft_away)
            ht_goals = int(ht_home) + int(ht_away)
            st_goals = ft_goals - ht_goals
        except (ValueError, TypeError):
            continue

        if 1 <= ft_goals <= 3: stats["1-3 Golova"] += 1
        if 2 <= ft_goals <= 4: stats["2-4 Golova"] += 1
        if 3 <= ft_goals <= 5: stats["3-5 Golova"] += 1
        if ft_goals >= 3: stats["3+ Ukupno"] += 1
        if 1 <= ht_goals <= 3: stats["1-3 I pol"] += 1
        if 1 <= st_goals <= 3: stats["1-3 II pol"] += 1
        if ht_goals >= 2: stats["2+ I pol"] += 1

    perfect = []
    for market, count in stats.items():
        if count == 3:
            perfect.append({
                "market": market,
                "text": f"{market} (100% - 3/3)"
            })
    return perfect

def main():
    fixtures, api_errors = get_todays_fixtures()
    report = []
    scanned_count = 0

    for item in fixtures:
        if not isinstance(item, dict): continue
        
        try:
            fixture_id = item.get('fixture', {}).get('id')
            home = item.get('teams', {}).get('home', {}).get('name', 'Home')
            away = item.get('teams', {}).get('away', {}).get('name', 'Away')
            home_id = item.get('teams', {}).get('home', {}).get('id')
            away_id = item.get('teams', {}).get('away', {}).get('id')
            league_name = item.get('league', {}).get('name', 'League')

            if not home_id or not away_id:
                continue

            h2h_matches = get_h2h(home_id, away_id)
            scanned_count += 1
            picks = evaluate_h2h(h2h_matches)

            if picks:
                odds = get_fixture_odds(fixture_id) if fixture_id else {}
                picks_fmt = []
                for p in picks:
                    market_name = p['market']
                    odd_val = odds.get(market_name)
                    if odd_val:
                        picks_fmt.append(f"   👉 {p['text']} | Kvota: {odd_val}")
                    else:
                        picks_fmt.append(f"   👉 {p['text']}")

                match_str = f"⚽ [{league_name}] {home} vs {away}\n" + "\n".join(picks_fmt)
                report.append(match_str)
                
            time.sleep(0.1)
        except Exception as e:
            print(f"Greška pri obradi utakmice: {e}")
            continue

    today_str = datetime.now().strftime('%d.%m.%Y')
    
    status_header = f"📊 Skenirano utakmica: {scanned_count}\n"
    if api_errors:
        status_header += f"⚠️ API Status/Greške: {api_errors}\n"
    status_header += "\n"

    if report:
        email_body = f"Dnevni izveštaj H2H (Zadnje 3 utakmice = 100%) sa kvotama ({today_str}):\n\n" + status_header + "\n\n".join(report)
        send_email(f"🎯 Fudbal H2H (3/3) Tipovi - {today_str}", email_body)
    else:
        email_body = f"{status_header}Danas nema utakmica sa 100% prolaznošću u zadnja 3 H2H meča."
        send_email(f"ℹ️ Fudbal H2H Tipovi - {today_str}", email_body)

if __name__ == "__main__":
    main()
