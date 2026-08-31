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
    url = f"https://v3.football.api-sports.io/fixtures?date={today}"
    res = requests.get(url, headers=HEADERS_FOOTBALL)
    data = res.json()

    # Provera grešaka u API odzivu
    if data.get('errors'):
        return [f"⚠️ API Greška (Fudbal): {data['errors']}"], 0

    fixtures = data.get('response', [])
    report = []
    
    # Skeniramo prvih 30 neodigranih mečeva radi štednje limita
    fixtures_to_scan = [f for f in fixtures if f['fixture']['status']['short'] == 'NS'][:30]
    api_calls_used = 1

    for item in fixtures_to_scan:
        home = item['teams']['home']['name']
        away = item['teams']['away']['name']
        home_id = item['teams']['home']['id']
        away_id = item['teams']['away']['id']
        league_name = item['league']['name']

        h2h_res = requests.get(f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={home_id}-{away_id}", headers=HEADERS_FOOTBALL)
        api_calls_used += 1
        
        h2h_data = h2h_res.json()
        if h2h_data.get('errors'):
            report.append(f"⚠️ API Limit dostignut tokom skeniranja meča {home} vs {away}")
            break

        h2h_list = h2h_data.get('response', [])
        total = len(h2h_list)

        if total < 3:
            continue

        stats = {
            "3+ Ukupno": 0, "GG (Oba daju)": 0, "1-3 Golova": 0,
            "2-4 Golova": 0, "1+ I pol": 0, "1-3 I pol": 0
        }

        history_lines = []

        for match in h2h_list:
            score = match.get('score', {})
            ht_home, ht_away = score.get('halftime', {}).get('home'), score.get('halftime', {}).get('away')
            ft_home, ft_away = score.get('fulltime', {}).get('home'), score.get('fulltime', {}).get('away')

            if None in (ht_home, ht_away, ft_home, ft_away):
                continue

            ft_goals = ft_home + ft_away
            ht_goals = ht_home + ht_away

            if ft_goals >= 3: stats["3+ Ukupno"] += 1
            if ft_home > 0 and ft_away > 0: stats["GG (Oba daju)"] += 1
            if 1 <= ft_goals <= 3: stats["1-3 Golova"] += 1
            if 2 <= ft_goals <= 4: stats["2-4 Golova"] += 1
            if ht_goals >= 1: stats["1+ I pol"] += 1
            if 1 <= ht_goals <= 3: stats["1-3 I pol"] += 1

            m_date = match['fixture']['date'][:10]
            m_home = match['teams']['home']['name']
            m_away = match['teams']['away']['name']
            history_lines.append(f"   • {m_date}: {m_home} {ft_home}:{ft_away} ({ht_home}:{ht_away}) {m_away}")

        picks = []
        for market, count in stats.items():
            pct = (count / total) * 100
            if pct >= 65.0:  # Spušten prag na 65% prolaznosti za više parova
                picks.append(f"{market} -> {pct:.0f}% ({count}/{total})")

        if picks:
            match_str = f"⚽ {home} vs {away}\n🏆 Liga: {league_name}\n"
            match_str += "🎯 Prepoznati trendovi:\n" + "\n".join([f"   👉 {p}" for p in picks]) + "\n"
            match_str += "📋 Istorija mečeva:\n" + "\n".join(history_lines)
            report.append(match_str)

    return report, api_calls_used

# ==================== RUKOMET ====================
def scan_handball():
    today = datetime.now().strftime('%Y-%m-%d')
    url = f"https://v1.handball.api-sports.io/games?date={today}"
    res = requests.get(url, headers=HEADERS_HANDBALL)
    data = res.json()

    if data.get('errors'):
        return [f"⚠️ API Greška (Rukomet): {data['errors']}"], 0

    games = data.get('response', [])
    report = []
    
    games_to_scan = [g for g in games if g['status']['short'] == 'NS'][:20]
    api_calls_used = 1

    for item in games_to_scan:
        home = item['teams']['home']['name']
        away = item['teams']['away']['name']
        home_id = item['teams']['home']['id']
        away_id = item['teams']['away']['id']
        league_name = item['league']['name']

        h2h_res = requests.get(f"https://v1.handball.api-sports.io/games/headtohead?h2h={home_id}-{away_id}", headers=HEADERS_HANDBALL)
        api_calls_used += 1

        h2h_data = h2h_res.json()
        if h2h_data.get('errors'):
            report.append(f"⚠️ API Limit dostignut tokom skeniranja rukometa ({home} vs {away})")
            break

        h2h_list = h2h_data.get('response', [])
        total = len(h2h_list)

        if total < 3:
            continue

        ft_goals_list = []
        ht_goals_list = []
        history_lines = []

        for match in h2h_list:
            scores = match.get('scores', {})
            ht_home, ht_away = scores.get('halftime', {}).get('home'), scores.get('halftime', {}).get('away')
            ft_home, ft_away = scores.get('fulltime', {}).get('home'), scores.get('fulltime', {}).get('away')

            if None in (ht_home, ht_away, ft_home, ft_away):
                continue

            ft_goals = ft_home + ft_away
            ht_goals = ht_home + ht_away
            ft_goals_list.append(ft_goals)
            ht_goals_list.append(ht_goals)

            m_date = match['date'][:10]
            m_home = match['teams']['home']['name']
            m_away = match['teams']['away']['name']
            history_lines.append(f"   • {m_date}: {m_home} {ft_home}:{ft_away} ({ht_home}:{ht_away}) {m_away}")

        if not ft_goals_list:
            continue

        avg_ft = sum(ft_goals_list) / len(ft_goals_list)
        avg_ht = sum(ht_goals_list) / len(ht_goals_list)

        picks = [
            f"Prosek ukupno golova: {avg_ft:.1f}",
            f"Prosek I poluvreme: {avg_ht:.1f} golova",
            f"Preporučena granica (OVER): Preko {round(avg_ft - 4.5, 1)}",
            f"Preporučena granica (UNDER): Ispod {round(avg_ft + 4.5, 1)}"
        ]

        match_str = f"🤾 {home} vs {away}\n🏆 Liga: {league_name}\n"
        match_str += "🎯 Matematička analitika:\n" + "\n".join([f"   👉 {p}" for p in picks]) + "\n"
        match_str += "📋 Istorija mečeva:\n" + "\n".join(history_lines)
        report.append(match_str)

    return report, api_calls_used

# ==================== MAIN ====================
def main():
    today_str = datetime.now().strftime('%d.%m.%Y')
    
    football_picks, fb_calls = scan_football()
    handball_picks, hb_calls = scan_handball()

    total_calls = fb_calls + hb_calls
    email_sections = [f"📊 Potrošeno API poziva u ovom pokretanju: {total_calls}\n"]

    if football_picks:
        email_sections.append("⚽ FUDBAL ANALITIKA:\n\n" + "\n\n----------------------------------------\n\n".join(football_picks))
    else:
        email_sections.append("⚽ FUDBAL: Nema pronađenih parova za danas.")

    if handball_picks:
        email_sections.append("🤾 RUKOMET ANALITIKA:\n\n" + "\n\n----------------------------------------\n\n".join(handball_picks))
    else:
        email_sections.append("🤾 RUKOMET: Nema pronađenih parova za danas.")

    final_email_body = f"Dnevni H2H Skener V3 za {today_str}\n\n" + "="*40 + "\n\n" + "\n\n".join(email_sections)
    
    # NOV NASLOV KOJI JE DOKAZ DA RADI NOVI KOD:
    send_email(f"🚀 NOVI H2H SKENER V3 - {today_str}", final_email_body)

if __name__ == "__main__":
    main()
