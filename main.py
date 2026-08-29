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
    'x-rapidapi-host': "v3.football.api-sports.io",
    'x-rapidapi-key': API_KEY
}

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
    return res.json().get('response', [])

def get_h2h(team1_id, team2_id):
    res = requests.get(f"{BASE_URL}/fixtures/headtohead?h2h={team1_id}-{team2_id}", headers=HEADERS)
    return res.json().get('response', [])

def evaluate_h2h(h2h_list):
    total = len(h2h_list)
    if total < 5:
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

    perfect = [f"{market} (100% - {total}/{total})" for market, count in stats.items() if count == total]
    return perfect

def main():
    fixtures = get_todays_fixtures()
    report = []

    for item in fixtures:
        home = item['teams']['home']['name']
        away = item['teams']['away']['name']
        home_id = item['teams']['home']['id']
        away_id = item['teams']['away']['id']

        h2h_matches = get_h2h(home_id, away_id)
        picks = evaluate_h2h(h2h_matches)

        if picks:
            match_str = f"⚽ {home} vs {away}\n" + "\n".join([f"   👉 {p}" for p in picks])
            report.append(match_str)

    today_str = datetime.now().strftime('%d.%m.%Y')
    if report:
        email_body = f"Dnevni izveštaj H2H 100% tradicije golova ({today_str}):\n\n" + "\n\n".join(report)
        send_email(f"🎯 Fudbal H2H 100% Tipovi - {today_str}", email_body)
    else:
        send_email(f"ℹ️ Fudbal H2H Tipovi - {today_str}", "Danas nema utakmica sa 100% H2H prolaznošću (min 5 mečeva).")

if __name__ == "__main__":
    main()
