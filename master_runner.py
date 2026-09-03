import os
import json
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import main
import value_engine
import market_drop_engine

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASS")
INITIAL_BANK = 50000.0  # Početna banka u RSD

def get_current_bank_roll():
    """Izračunava trenutnu ukupnu banku iz baze bets.json"""
    bets = main.load_bets()
    total_profit = sum(b.get('profit', 0) for b in bets if isinstance(b, dict) and b.get('status') in ['WIN', 'LOSS'])
    current_bank = INITIAL_BANK + total_profit
    return max(10000.0, current_bank) # Sigurnosni minimum

def send_master_daily_email():
    today_formatted = datetime.now().strftime('%d.%m.%Y')
    
    # 1. Čitanje trenutne banke i proračun dnevnog limita (Max 10% banke dnevno)
    current_bank = get_current_bank_roll()
    max_daily_risk = current_bank * 0.10  # Max 5.000 RSD ako je banka 50k
    
    # Raspodela maksimalnog rizka: 80% H2H, 10% Single, 10% Value
    h2h_max_budget = max_daily_risk * 0.80
    single_max_budget = max_daily_risk * 0.10
    value_max_budget = max_daily_risk * 0.10

    print(f"💰 Trenutna Banka: {current_bank:,.0f} RSD | Maksimalni dnevni rizik: {max_daily_risk:,.0f} RSD")

    print("🔄 Skupljam VIP H2H podatke...")
    h2h_content, h2h_spent = main.get_h2h_html_blocks(current_bank, h2h_max_budget)
    
    print("🔄 Skupljam Poisson Math Value Betove...")
    value_content, value_spent = value_engine.get_value_html_blocks(current_bank, value_max_budget)

    print("🔄 Skupljam Single Tip Dana...")
    single_content, single_spent = market_drop_engine.get_market_drops_and_single_tip(current_bank, single_max_budget)

    total_spent_today = h2h_spent + value_spent + single_spent

    master_html = f"""
    <html>
    <body style="font-family:'Segoe UI', Arial, sans-serif; background-color:#f4f4f7; padding:20px; color:#333;">
        <div style="max-width:700px; background:#ffffff; margin:0 auto; padding:25px; border-radius:12px; box-shadow:0 4px 15px rgba(0,0,0,0.06);">
            
            <div style="text-align:center; padding-bottom:15px; border-bottom:2px solid #eef0f2; margin-bottom:20px;">
                <h1 style="color:#1a2a3a; margin:0; font-size:22px;">🚀 MASTER ANALITIČKI BILTEN ({today_formatted})</h1>
                <p style="color:#6c757d; margin:5px 0 0 0; font-size:13px;">
                    🏦 Ukupna Banka: <b>{current_bank:,.0f} RSD</b> | Predloženi Dnevni Ulog: <b>{total_spent_today:,.0f} RSD</b>
                </p>
            </div>

            <!-- SEKCIJA 1: SINGLE TIP DANA (KVOTA 2.00+) -->
            {single_content}

            <!-- SEKCIJA 2: VIP H2H ZICERI & DNEVNI DUBL -->
            <h3 style="color:#28a745; border-bottom:2px solid #28a745; padding-bottom:5px;">⚽ 1. VIP H2H & Form Ziceri (Uloženo: {h2h_spent:,.0f} RSD)</h3>
            {h2h_content if h2h_content else '<p style="font-style:italic; color:#777;">Nema H2H zicera za danas.</p>'}

            <br>
            <!-- SEKCIJA 3: POISSON MATH VALUE BETOVI -->
            <h3 style="color:#6f42c1; border-bottom:2px solid #6f42c1; padding-bottom:5px;">📐 2. Pure Math Value Bets (Uloženo: {value_spent:,.0f} RSD)</h3>
            {value_content if value_content else '<p style="font-style:italic; color:#777;">Nema izrazitih matematičkih odstupanja danas.</p>'}

            <div style="background:#eef6ff; padding:12px; text-align:center; border-radius:6px; font-size:12px; color:#0056b3; margin-top:25px;">
                🛡️ Sistem zaštite banke aktivan (Ulog prilagođen veličini banke i danu u nedelji).
            </div>
        </div>
    </body>
    </html>
    """

    if not GMAIL_USER or not GMAIL_PASS:
        print("⚠️ Nemam Gmail podatke u Secrets.")
        return

    msg = MIMEMultipart("alternative")
    msg['Subject'] = f"🚀 Master Bilten (Banka: {current_bank:,.0f} RSD) - {today_formatted}"
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg.attach(MIMEText(master_html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        print("✅ Master mejl sa pametnim ulozima po utakmici uspešno poslat!")
    except Exception as e:
        print(f"Greška pri slanju mejla: {e}")

if __name__ == "__main__":
    send_master_daily_email()
