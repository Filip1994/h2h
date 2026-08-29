import os
import requests
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

API_KEY = os.environ.get("API_FOOTBALL_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASS")

BASE_URL = "https://v3.football.api-sports.io"

# Ispravljeno zaglavlje za direktne API-Sports ključeve
HEADERS = {
    'x-apisports-key': API_KEY
}

# Lige koje skeniramo (Top 5 + Balkanske i popularne lige da ostanemo unutar 100 API poziva)
# 39: Premier League, 140: La Liga, 135: Serie A, 78: Bundesliga, 61: Ligue 1, 
# 283: SuperLiga (SRB), 218: Eredivisie, 94: Primeir League, 203: Süper Lig, 2: Champions League
TOP_LEAGUES = [39, 140, 135, 78, 61, 283, 218, 94, 203, 2]

def send_email(subject, body):
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
    res = requests.get(f"{BASE_URL}/fixtures?date={today}", headers=HEADERS)
    data = res.json()
    fixtures = data.get('response', [])
    
    # Filtriramo utakmice: prvo tražimo mečeve iz TOP_LEAGUES
    popular_fixtures = [f for f in fixtures if f.get('league', {}).get('id') in TOP_LEAGUES]
    
    # Ako u top ligama nema dovoljno mečeva, dodajemo ostale do max 80 utakmica ukupno
    if len(popular_fixtures) < 80:
        other_fixtures = [f for f in fixtures if f.get('league', {}).get('id') not in TOP_LEAGUES]
        popular_fixtures.extend(other_fixtures[:80 - len(popular_fixtures)])
        
    return popular_fixtures

def get_h2h(team1_id, team2_id):
    res = requests.get(f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}", headers=HEADERS)
    data = res.json()
    return data.get('response', [])

def evaluate_h2h(h2h_list):
    total = len(h2h_list)
    if total < 5:  # Uslov: Minimum 5 H2H utakmica
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

    for match in h2h_list:
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

    # Zadržava SAMO markete sa 100% prolaznošću
    perfect = [f"{market} (100% - {total}/{total})" for market, count in stats.items() if count == total]
    return perfect

def main():
    fixtures = get_todays_fixtures()
    report = []
    scanned_count = 0

    for item in fixtures:
        home = item['teams']['home']['name']
        away = item['teams']['away']['name']
        home_id = item['teams']['home']['id']
        away_id = item['teams']['away']['id']
        league_name = item['league']['name']

        h2h_matches = get_h2h(home_id, away_id)
        scanned_count += 1
        picks = evaluate_h2h(h2h_matches)

        if picks:
            match_str = f"⚽ [{league_name}] {home} vs {away}\n" + "\n".join([f"   👉 {p}" for p in picks])
            report.append(match_str)

    today_str = datetime.now().strftime('%d.%m.%Y')
    
    status_header = f"📊 Skenirano utakmica: {scanned_count}\n\n"
    
    if report:
        email_body = f"Dnevni izveštaj H2H 100% tradicije golova ({today_str}):\n\n" + status_header + "\n\n".join(report)
        send_email(f"🎯 Fudbal H2H 100% Tipovi - {today_str}", email_body)
    else:
        email_body = f"{status_header}Danas nema utakmica sa 100% H2H prolaznošću (min 5 mečeva)."
        send_email(f"ℹ️ Fudbal H2H Tipovi - {today_str}", email_body)

if __name__ == "__main__":
    main()
