import os
import sys
import json
import requests
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

# ==================== ROTATOR API KLJUČEVA ====================
KEYS = [
    os.environ.get("API_FOOTBALL_KEY"),
    os.environ.get("API_KEY_2"),
    os.environ.get("API3")
]
KEYS = [k for k in KEYS if k]

class APIRotator:
    def __init__(self, keys):
        self.keys = keys
        self.current_idx = 0

    def get_headers(self):
        if not self.keys:
            return {}
        return {'x-apisports-key': self.keys[self.current_idx]}

    def rotate(self):
        if len(self.keys) > 1:
            self.current_idx = (self.current_idx + 1) % len(self.keys)
            print(f"🔄 Prebačeno na API ključ #{self.current_idx + 1}")

    def fetch(self, url, params=None):
        attempts = 0
        max_attempts = len(self.keys) * 2 if self.keys else 1
        
        while attempts < max_attempts:
            try:
                res = requests.get(url, headers=self.get_headers(), params=params, timeout=10)
                if res.status_code in [429, 403]:
                    self.rotate()
                    attempts += 1
                    continue
                
                data = res.json()
                if isinstance(data, dict) and data.get("errors"):
                    errs = data.get("errors")
                    if isinstance(errs, dict) and ("requests" in errs or "rateLimit" in errs):
                        self.rotate()
                        attempts += 1
                        continue
                return data
            except Exception as e:
                print(f"Greška na mreži: {e}")
                self.rotate()
                attempts += 1
        return {}

api = APIRotator(KEYS)

# ==================== STRATEGIJA & FILTERI ====================
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASS")
BETS_FILE = "bets.json"

MIN_H2H_MATCHES = 4
MIN_ACCURACY_PCT = 75.0
MIN_ODD = 1.35  # Filter za neisplative kvote

EXCLUDED_COUNTRIES = [
    "Brazil", "Argentina", "Colombia", "Chile", "Uruguay", "Paraguay", "Peru",
    "Ecuador", "Bolivia", "Venezuela", "Egypt", "Morocco", "Tunisia", "Algeria",
    "South Africa", "Nigeria", "Ghana", "Senegal", "Cameroon", "Kenya", "Ivory Coast"
]

EXCLUDED_LEAGUE_KEYWORDS = [
    "U19", "U20", "U21", "U23", "Sub-19", "Sub-20", "Reserve", "Reserves",
    "Amateur", "Oberliga", "Regional", "District", "5th Division", "6th Division",
    "Next Pro", "MLS Next Pro", "II", "B team"
]

def is_allowed_league(country_name, league_name):
    for country in EXCLUDED_COUNTRIES:
        if country and country.lower() in country_name.lower():
            return False
    for kw in EXCLUDED_LEAGUE_KEYWORDS:
        if kw and kw.lower() in league_name.lower():
            return False
    return True

# ==================== POMOĆNE FUNKCIJE ====================
def send_email(subject, body):
    if not GMAIL_USER or not GMAIL_PASS:
        print("⚠️ Gmail kredencijali nisu podešeni u Secrets!")
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

def load_bets():
    if os.path.exists(BETS_FILE):
        try:
            with open(BETS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_bets(bets):
    with open(BETS_FILE, 'w', encoding='utf-8') as f:
        json.dump(bets, f, ensure_ascii=False, indent=4)

def fetch_real_odds(fixture_id):
    url = f"https://v3.football.api-sports.io/odds?fixture={fixture_id}"
    data = api.fetch(url)
    odds_dict = {}
    try:
        response = data.get('response') or []
        if response:
            bookmakers = response[0].get('bookmakers') or []
            if bookmakers:
                bets = bookmakers[0].get('bets') or []
                for b in bets:
                    name = b.get('name') or ''
                    values = b.get('values') or []

                    if name == "Goals Over/Under":
                        for v in values:
                            if v.get('value') == "Over 2.5":
                                odds_dict["3+ Ukupno"] = float(v.get('odd'))
                            elif v.get('value') == "Over 1.5":
                                odds_dict["2-4 Golova"] = float(v.get('odd'))
                    elif name == "Both Teams Score":
                        for v in values:
                            if v.get('value') == "Yes":
                                odds_dict["GG"] = float(v.get('odd'))
                    elif "First Half" in name and "Over/Under" in name:
                        for v in values:
                            if v.get('value') == "Over 0.5":
                                odds_dict["1+ I pol"] = float(v.get('odd'))
                    elif "Second Half" in name and "Over/Under" in name:
                        for v in values:
                            if v.get('value') == "Over 0.5":
                                odds_dict["1+ II pol"] = float(v.get('odd'))
                    elif name in ["Exact Goals Number", "Total Goals"]:
                        for v in values:
                            if v.get('value') in ["2-3", "2 - 3"]:
                                odds_dict["2-3 Golova"] = float(v.get('odd'))
    except Exception as e:
        print(f"Greška pri citiranju kvota za {fixture_id}: {e}")
    return odds_dict

# ==================== JUTARNJE SKENIRANJE ====================
def morning_scan():
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_formatted = datetime.now().strftime('%d.%m.%Y')
    
    saved_bets = load_bets()
    new_bets = []

    fb_data = api.fetch(f"https://v3.football.api-sports.io/fixtures?date={today_str}")
    fb_events = fb_data.get('response') or []

    fb_picks_lines = []
    for event in fb_events:
        try:
            fixture = event.get('fixture') or {}
            fixture_id = fixture.get('id')
            status_short = (fixture.get('status') or {}).get('short')

            if status_short not in ['NS', 'TBD']:
                continue

            teams = event.get('teams') or {}
            home = (teams.get('home') or {}).get('name', 'Home')
            away = (teams.get('away') or {}).get('name', 'Away')
            home_id = (teams.get('home') or {}).get('id')
            away_id = (teams.get('away') or {}).get('id')
            
            league_info = event.get('league') or {}
            league = league_info.get('name', 'Liga')
            country = league_info.get('country', 'Nacionalno')

            if not is_allowed_league(country, league):
                continue

            if not home_id or not away_id:
                continue

            h2h_data = api.fetch(f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={home_id}-{away_id}")
            h2h_matches = h2h_data.get('response') or []
            total = len(h2h_matches)
            if total < MIN_H2H_MATCHES:
                continue

            stats = {
                "3+ Ukupno": 0, 
                "GG": 0, 
                "1-3 Golova": 0, 
                "2-4 Golova": 0,
                "2-3 Golova": 0, 
                "1+ I pol": 0,
                "1+ II pol": 0,
                "1-3 I pol & 1-3 II pol": 0
            }
            history_lines = []

            for m in h2h_matches:
                goals = m.get('goals') or {}
                score = m.get('score') or {}
                halftime = score.get('halftime') or {}

                ft_h = goals.get('home') if goals.get('home') is not None else 0
                ft_a = goals.get('away') if goals.get('away') is not None else 0
                ht_h = halftime.get('home') if halftime.get('home') is not None else 0
                ht_a = halftime.get('away') if halftime.get('away') is not None else 0

                ft_g = ft_h + ft_a
                ht_g = ht_h + ht_a
                sh_g = ft_g - ht_g

                if ft_g >= 3: stats["3+ Ukupno"] += 1
                if ft_h > 0 and ft_a > 0: stats["GG"] += 1
                if 1 <= ft_g <= 3: stats["1-3 Golova"] += 1
                if 2 <= ft_g <= 4: stats["2-4 Golova"] += 1
                if 2 <= ft_g <= 3: stats["2-3 Golova"] += 1
                if ht_g >= 1: stats["1+ I pol"] += 1
                if sh_g >= 1: stats["1+ II pol"] += 1
                if (1 <= ht_g <= 3) and (1 <= sh_g <= 3): stats["1-3 I pol & 1-3 II pol"] += 1

                history_lines.append(f"   • {home} {ft_h}:{ft_a} ({ht_h}:{ht_a}) {away}")

            odds = fetch_real_odds(fixture_id)
            match_picks = []

            for market, count in stats.items():
                pct = (count / total) * 100
                if pct >= MIN_ACCURACY_PCT:
                    real_odd = odds.get(market)
                    
                    if not real_odd or real_odd < MIN_ODD:
                        continue

                    pick_str = f"{market} -> {pct:.0f}% ({count}/{total}) | Kvota: {real_odd:.2f}"
                    match_picks.append(pick_str)

                    new_bets.append({
                        "id": f"{fixture_id}_{market}",
                        "event_id": fixture_id,
                        "date": today_str,
                        "sport": "Football",
                        "match": f"{home} vs {away}",
                        "league": f"{country} - {league}",
                        "market": market,
                        "stake": 1000,
                        "odd": real_odd,
                        "status": "PENDING",
                        "profit": 0
                    })

            if match_picks:
                block = f"⚽ {home} vs {away}\n🏆 Liga: {country} - {league}\n🎯 Predlozi:\n"
                block += "\n".join([f"   👉 {p}" for p in match_picks]) + "\n"
                block += "📋 Istorija H2H:\n" + "\n".join(history_lines[:5])
                fb_picks_lines.append(block)

        except Exception as err:
            print(f"Preskočen meč zbog greške u obradi: {err}")
            continue

    existing_ids = {b['id'] for b in saved_bets}
    for nb in new_bets:
        if nb['id'] not in existing_ids:
            saved_bets.append(nb)
    save_bets(saved_bets)

    body = f"🚀 JUTARNJI H2H SKENER & KVOTE ({today_formatted})\n\n"
    body += "==== ⚽ FUDBAL ====\n\n" + ("\n\n------------------------\n\n".join(fb_picks_lines) if fb_picks_lines else "Nema parova koji ispunjavaju sve kriterijume danas.")
    body += f"\n\n📌 Sve prihvaćene opklade su sačuvane sa ulogom od 1.000 RSD u bazu."

    send_email(f"🎯 Dnevni H2H Skener - {today_formatted}", body)

# ==================== VEČERNJA PROVERA REZULTATA ====================
def evening_settle():
    bets = load_bets()
    updated = False

    for b in bets:
        if b['status'] == 'PENDING':
            fixture_id = b['event_id']
            data = api.fetch(f"https://v3.football.api-sports.io/fixtures?id={fixture_id}")
            response = data.get('response') or []
            if response:
                fixture_data = response[0]
                status_short = (fixture_data.get('fixture') or {}).get('status', {}).get('short')

                if status_short in ['FT', 'AET', 'PEN']:
                    goals = fixture_data.get('goals') or {}
                    score = fixture_data.get('score') or {}
                    halftime = score.get('halftime') or {}

                    ft_h = goals.get('home') if goals.get('home') is not None else 0
                    ft_a = goals.get('away') if goals.get('away') is not None else 0
                    ht_h = halftime.get('home') if halftime.get('home') is not None else 0
                    ht_a = halftime.get('away') if halftime.get('away') is not None else 0

                    ft_goals = ft_h + ft_a
                    ht_goals = ht_h + ht_a
                    sh_goals = ft_goals - ht_goals
                    market = b['market']
                    is_win = False

                    if market == "3+ Ukupno" and ft_goals >= 3: is_win = True
                    elif market == "GG" and ft_h > 0 and ft_a > 0: is_win = True
                    elif market == "1-3 Golova" and 1 <= ft_goals <= 3: is_win = True
                    elif market == "2-4 Golova" and 2 <= ft_goals <= 4: is_win = True
                    elif market == "2-3 Golova" and 2 <= ft_goals <= 3: is_win = True
                    elif market == "1+ I pol" and ht_goals >= 1: is_win = True
                    elif market == "1+ II pol" and sh_goals >= 1: is_win = True
                    elif market == "1-3 I pol & 1-3 II pol" and (1 <= ht_goals <= 3) and (1 <= sh_goals <= 3): is_win = True

                    if is_win:
                        b['status'] = 'WIN'
                        b['profit'] = round((b['stake'] * b['odd']) - b['stake'], 2)
                    else:
                        b['status'] = 'LOSS'
                        b['profit'] = -b['stake']

                    updated = True

    if updated:
        save_bets(bets)
        print("Večernja provera kompletirana. bets.json je ažuriran!")

# ==================== NEDELJNI P&L IZVEŠTAJ ====================
def weekly_report():
    bets = load_bets()
    if not bets:
        return

    wins = sum(1 for b in bets if b['status'] == 'WIN')
    losses = sum(1 for b in bets if b['status'] == 'LOSS')
    pending = sum(1 for b in bets if b['status'] == 'PENDING')

    total_stake = sum(b['stake'] for b in bets if b['status'] != 'PENDING')
    net_profit = sum(b['profit'] for b in bets if b['status'] != 'PENDING')
    roi = (net_profit / total_stake * 100) if total_stake > 0 else 0.0
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0

    report_str = f"📊 NEDELJNI P&L IZVEŠTAJ O PROFITU\n"
    report_str += "="*40 + "\n\n"
    report_str += f"💰 Ukupno Uloženo: {total_stake:,.0f} RSD\n"
    report_str += f"📈 Neto Profit/Gubitak: {net_profit:+,.0f} RSD\n"
    report_str += f"🎯 ROI (Povrat investicije): {roi:+.2f}%\n"
    report_str += f"✅ Uspešnost (Win Rate): {win_rate:.1f}% ({wins}W / {losses}L)\n"
    report_str += f"⏳ Opklade u toku: {pending}\n\n"
    report_str += "📋 Tabela poslednjih opklada:\n"

    for b in bets[-20:]:
        status_icon = "✅" if b['status'] == 'WIN' else ("❌" if b['status'] == 'LOSS' else "⏳")
        report_str += f"{status_icon} {b['match']} | {b['market']} | Kvota: {b['odd']} | Profit: {b['profit']:+} RSD\n"

    send_email(f"📈 Nedeljni Izveštaj Profita (ROI: {roi:+.1f}%)", report_str)

# ==================== GLAVNI DISPEČER ====================
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "morning"

    if mode == "morning":
        morning_scan()
    elif mode == "evening":
        evening_settle()
    elif mode == "weekly":
        weekly_report()
