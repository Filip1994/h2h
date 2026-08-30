import os
import requests
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

API_KEY = os.environ.get("API_FOOTBALL_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASS")

HEADERS_FOOTBALL = {
    'x-rapidapi-host': "v3.football.api-sports.io",
    'x-rapidapi-key': API_KEY
}

HEADERS_HANDBALL = {
    'x-rapidapi-host': "v1.handball.api-sports.io",
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

# ==================== FUDBAL ====================
def scan_football():
    today = datetime.now().strftime('%Y-%m-%d')
    res = requests.get(f"https://v3.football.api-sports.io/fixtures?date={today}", headers=HEADERS_FOOTBALL)
    fixtures = res.json().get('response', [])
    report = []

    for item in fixtures:
        if item['fixture']['status']['short'] != 'NS':
            continue

        home = item['teams']['home']['name']
        away = item['teams']['away']['name']
        home_id = item['teams']['home']['id']
        away_id = item['teams']['away']['id']

        h2h_res = requests.get(f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={home_id}-{away_id}", headers=HEADERS_FOOTBALL)
        h2h_list = h2h_res.json().get('response', [])

        total = len(h2h_list)
        if total < 5:
            continue

        stats = {
            "1-3 Golova": 0, "2-4 Golova": 0, "3-5 Golova": 0,
            "3+ Ukupno": 0, "1-3 I pol": 0, "1-3 II pol": 0, "2+ I pol": 0
        }

        for match in h2h_list:
            score = match.get('score', {})
            ht_home, ht_away = score.get('halftime', {}).get('home'), score.get('halftime', {}).get('away')
            ft_home, ft_away = score.get('fulltime', {}).get('home'), score.get('fulltime', {}).get('away')

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

        picks = [f"{market} (100% - {total}/{total})" for market, count in stats.items() if count == total]
        if picks:
            match_str = f"⚽ {home} vs {away}\n" + "\n".join([f"   👉 {p}" for p in picks])
            report.append(match_str)

    return report

# ==================== RUKOMET ====================
def scan_handball():
    today = datetime.now().strftime('%Y-%m-%d')
    res = requests.get(f"https://v1.handball.api-sports.io/games?date={today}", headers=HEADERS_HANDBALL)
    games = res.json().get('response', [])
    report = []

    for item in games:
        if item['status']['short'] != 'NS':
            continue

        home = item['teams']['home']['name']
        away = item['teams']['away']['name']
        home_id = item['teams']['home']['id']
        away_id = item['teams']['away']['id']

        h2h_res = requests.get(f"https://v1.handball.api-sports.io/games/headtohead?h2h={home_id}-{away_id}", headers=HEADERS_HANDBALL)
        h2h_list = h2h_res.json().get('response', [])

        total = len(h2h_list)
        if total < 3:  # Rukomet uslov: Min 3 meča
            continue

        stats = {
            "Ukupno > 50.5": 0, "Ukupno > 53.5": 0, "Ukupno < 58.5": 0, "Ukupno < 61.5": 0,
            "1. pol > 24.5": 0, "1. pol > 26.5": 0, "1. pol < 29.5": 0,
            "2. pol > 25.5": 0, "2. pol > 27.5": 0
        }

        for match in h2h_list:
            scores = match.get('scores', {})
            ht_home, ht_away = scores.get('halftime', {}).get('home'), scores.get('halftime', {}).get('away')
            ft_home, ft_away = scores.get('fulltime', {}).get('home'), scores.get('fulltime', {}).get('away')

            if None in (ht_home, ht_away, ft_home, ft_away):
                continue

            ft_goals = ft_home + ft_away
            ht_goals = ht_home + ht_away
            st_goals = ft_goals - ht_goals

            if ft_goals > 50.5: stats["Ukupno > 50.5"] += 1
            if ft_goals > 53.5: stats["Ukupno > 53.5"] += 1
            if ft_goals < 58.5: stats["Ukupno < 58.5"] += 1
            if ft_goals < 61.5: stats["Ukupno < 61.5"] += 1
            if ht_goals > 24.5: stats["1. pol > 24.5"] += 1
            if ht_goals > 26.5: stats["1. pol > 26.5"] += 1
            if ht_goals < 29.5: stats["1. pol < 29.5"] += 1
            if st_goals > 25.5: stats["2. pol > 25.5"] += 1
            if st_goals > 27.5: stats["2. pol > 27.5"] += 1

        picks = [f"{market} (100% - {total}/{total})" for market, count in stats.items() if count == total]
        if picks:
            match_str = f"🤾 {home} vs {away}\n" + "\n".join([f"   👉 {p}" for p in picks])
            report.append(match_str)

    return report

# ==================== MAIN ====================
def main():
    today_str = datetime.now().strftime('%d.%m.%Y')
    
    football_picks = scan_football()
    handball_picks = scan_handball()

    email_sections = []

    if football_picks:
        email_sections.append("⚽ FUDBAL 100% TIPOVI (min 5 H2H):\n\n" + "\n\n".join(football_picks))
    else:
        email_sections.append("⚽ FUDBAL: Nema utakmica koje ispunjavaju uslove danas.")

    if handball_picks:
        email_sections.append("🤾 RUKOMET 100% TIPOVI (min 3 H2H):\n\n" + "\n\n".join(handball_picks))
    else:
        email_sections.append("🤾 RUKOMET: Nema utakmica koje ispunjavaju uslove danas.")

    final_email_body = f"Dnevni izveštaj H2H statistike za {today_str}\n\n" + "\n\n" + "="*40 + "\n\n" + "\n\n".join(email_sections)
    send_email(f"🎯 Dnevni H2H Izveštaj (Fudbal & Rukomet) - {today_str}", final_email_body)

if __name__ == "__main__":
    main()
