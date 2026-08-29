import os
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

# Top lige (ID-jevi)
TOP_LEAGUES = [39, 140, 135, 78, 61, 283, 218, 94, 203, 2]

def send_email(subject, body):
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, GMAIL_PASS, msg.as_string())
        print("Mejl uspešno poslat!")
    except Exception as e:
        print(f"Greška pri slanju mejla: {e}")

def get_todays_fixtures():
    today = datetime.now().strftime('%Y-%m-%d')
    url = f"{BASE_URL}/fixtures?date={today}"
    res = requests.get(url, headers=HEADERS)
    data = res.json()
    
    api_errors = data.get('errors', {})
    fixtures = data.get('response', [])
    
    popular_fixtures = [f for f in fixtures if f.get('league', {}).get('id') in TOP_LEAGUES]
    
    if len(popular_fixtures) < 70:
        other_fixtures = [f for f in fixtures if f.get('league', {}).get('id') not in TOP_LEAGUES]
        popular_fixtures.extend(other_fixtures[:70 - len(popular_fixtures)])
        
    return popular_fixtures, api_errors

def get_h2h(team1_id, team2_id):
    res = requests.get(f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}", headers=HEADERS)
    data = res.json()
    return data.get('response', [])

def get_fixture_odds(fixture_id):
    """Izvlači kvote za golove za datu utakmicu"""
    res = requests.get(f"{BASE_URL}/odds?fixture={fixture_id}", headers=HEADERS)
    data = res.json()
    response = data.get('response', [])
    
    odds_dict = {}
    if not response:
        return odds_dict
        
    bookmakers = response[0].get('bookmakers', [])
    if not bookmakers:
        return odds_dict
        
    bets = bookmakers[0].get('bets', [])
    for bet in bets:
        name = bet.get('name')
        if name in ["Goals Over/Under", "Match Goals"]:
            for val in bet.get('values', []):
                if val.get('value') == "Over 2.5":
                    odds_dict["3+ Ukupno"] = val.get('odd')
                    
    return odds_dict

def evaluate_h2h(h2h_list):
    # Sortiramo mečeve od najnovijeg ka najstarijem
    sorted_h2h = sorted(h2h_list, key=lambda x: x['fixture']['date'], reverse=True)
    
    # Uzimamo tačno poslednje 3 utakmice
    last_3 = sorted_h2h[:3]
    total = len(last_3)
    
    # Ako nemaju bar 3 međusobna meča u istoriji, preskačemo
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
        score = match.get('score', {})
        ht_home = score.get('halftime', {}).get('home')
        ht_away = score.get('halftime', {}).get('away')
        ft_home = score.get('fulltime', {}).get('home')
        ft_away = score.get('fulltime', {}).get('away')

        if None in (ht_home, ht_away, ft_home, ft_away):
            continue

        ft_goals = ft_home + ft_away
        ht_goals = ht_home + ht_away
        st_goals = ft_goals - ht_goals

        if 1 <= ft_goals <= 3: stats["1-3 Golova"] += 1
        if 2 <= ft_goals <= 4: stats["2-4 Golova"] += 1
        if 3 <= ft_goals <= 5: stats["3-5 Golova"] += 1
        if ft_goals >= 3: stats["3+ Ukupno"] += 1
        if 1 <= ht_goals <= 3: stats["1-3 I pol"] += 1
        if 1 <= st_goals <= 3: stats["1-3 II pol"] += 1
        if ht_goals >= 2: stats["2+ I pol"] += 1

    # Proveravamo šta je došlo 3 od 3 puta (100%)
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
        fixture_id = item['fixture']['id']
        home = item['teams']['home']['name']
        away = item['teams']['away']['name']
        home_id = item['teams']['home']['id']
        away_id = item['teams']['away']['id']
        league_name = item['league']['name']

        h2h_matches = get_h2h(home_id, away_id)
        scanned_count += 1
        picks = evaluate_h2h(h2h_matches)

        if picks:
            odds = get_fixture_odds(fixture_id)
            
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
