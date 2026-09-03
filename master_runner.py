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

def calculate_analytics():
    """Računa Trenutnu Banku, Neto Profit, Ukupno Uloženo, Win Rate i ROI %"""
    bets = main.load_bets()
    completed_bets = [b for b in bets if isinstance(b, dict) and b.get('status') in ['WIN', 'LOSS']]
    
    total_stake = sum(b.get('stake', 0) for b in completed_bets)
    total_profit = sum(b.get('profit', 0) for b in completed_bets)
    current_bank = INITIAL_BANK + total_profit
    
    roi_pct = (total_profit / total_stake * 100.0) if total_stake > 0 else 0.0
    wins = sum(1 for b in completed_bets if b.get('status') == 'WIN')
    total_matches = len(completed_bets)
    win_rate = (wins / total_matches * 100.0) if total_matches > 0 else 0.0

    return {
        "current_bank": max(10000.0, current_bank),
        "total_profit": total_profit,
        "total_stake": total_stake,
        "roi_pct": roi_pct,
        "win_rate": win_rate,
        "total_matches": total_matches
    }

def send_master_daily_email():
    today_formatted = datetime.now().strftime('%d.%m.%Y')
    
    stats = calculate_analytics()
    current_bank = stats["current_bank"]
    max_daily_risk = current_bank * 0.10  # Max 10% banke dnevno

    h2h_max_budget = max_daily_risk * 0.80
    single_max_budget = max_daily_risk * 0.10
    value_max_budget = max_daily_risk * 0.10

    print(f"📊 Banka: {current_bank:,.0f} RSD | Profit: {stats['total_profit']:,.0f} RSD | ROI: {stats['roi_pct']:.2f}%")

    h2h_content, h2h_spent = main.get_h2h_html_blocks(current_bank, h2h_max_budget)
    value_content, value_spent = value_engine.get_value_html_blocks(current_bank, value_max_budget)
    single_content, single_spent = market_drop_engine.get_market_drops_and_single_tip(current_bank, single_max_budget)

    total_spent_today = h2h_spent + value_spent + single_spent
    roi_color = "#28a745" if stats["roi_pct"] >= 0 else "#dc3545"
    profit_sign = "+" if stats["total_profit"] > 0 else ""

    master_html = f"""
    <html>
    <body style="font-family:'Segoe UI', Arial, sans-serif; background-color:#f4f4f7; padding:20px; color:#333;">
        <div style="max-width:700px; background:#ffffff; margin:0 auto; padding:25px; border-radius:12px; box-shadow:0 4px 15px rgba(0,0,0,0.06);">
            
            <div style="text-align:center; padding-bottom:15px; border-bottom:2px solid #eef0f2; margin-bottom:20px;">
                <h1 style="color:#1a2a3a; margin:0; font-size:22px;">🚀 MASTER ANALITIČKI BILTEN ({today_formatted})</h1>
                
                <div style="background:#f8f9fa; border:1px solid #e9ecef; border-radius:8px; padding:12px; margin-top:12px; display:inline-block; width:95%;">
                    <table width="100%" style="text-align:center; font-size:13px;">
                        <tr>
                            <td>🏦 <b>Banka:</b><br><span style="font-size:15px; font-weight:bold; color:#1a2a3a;">{current_bank:,.0f} RSD</span></td>
                            <td>📈 <b>Profit:</b><br><span style="font-size:15px; font-weight:bold; color:{roi_color};">{profit_sign}{stats['total_profit']:,.0f} RSD</span></td>
                            <td>📊 <b>ROI:</b><br><span style="font-size:15px; font-weight:bold; color:{roi_color};">{stats['roi_pct']:.2f}%</span></td>
                            <td>🎯 <b>Prolaznost:</b><br><span style="font-size:15px; font-weight:bold; color:#007bff;">{stats['win_rate']:.1f}% ({stats['total_matches']})</span></td>
                        </tr>
                    </table>
                </div>

                <p style="color:#6c757d; margin:10px 0 0 0; font-size:12px;">
                    Predloženi ulog danas: <b>{total_spent_today:,.0f} RSD</b> (Dnevni limit: {max_daily_risk:,.0f} RSD)
                </p>
            </div>

            <!-- SEKCIJA 1: SINGLE TIP DANA -->
            {single_content}

            <!-- SEKCIJA 2: VIP H2H ZICERI -->
            <h3 style="color:#28a745; border-bottom:2px solid #28a745; padding-bottom:5px;">⚽ 1. VIP H2H Ziceri (Uloženo: {h2h_spent:,.0f} RSD)</h3>
            {h2h_content if h2h_content else '<p style="font-style:italic; color:#777;">Nema H2H zicera za danas.</p>'}

            <br>
            <!-- SEKCIJA 3: POISSON MATH VALUE BETOVI -->
            <h3 style="color:#6f42c1; border-bottom:2px solid #6f42c1; padding-bottom:5px;">📐 2. Pure Math Value Bets (Uloženo: {value_spent:,.0f} RSD)</h3>
            {value_content if value_content else '<p style="font-style:italic; color:#777;">Nema izrazitih matematičkih odstupanja danas.</p>'}

            <div style="background:#eef6ff; padding:12px; text-align:center; border-radius:6px; font-size:12px; color:#0056b3; margin-top:25px;">
                🛡️ Sistem automatski preračunava uloge od 1.5% banke i vodi statistiku u bets.json.
            </div>
        </div>
    </body>
    </html>
    """

    if not GMAIL_USER or not GMAIL_PASS:
        print("⚠️ Nemam Gmail podatke u Secrets.")
        return

    msg = MIMEMultipart("alternative")
    msg['Subject'] = f"🚀 Master Bilten (Banka: {current_bank:,.0f} RSD | ROI: {stats['roi_pct']:.1f}%) - {today_formatted}"
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg.attach(MIMEText(master_html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        print("✅ Izveštaj je uspešno poslat!")
    except Exception as e:
        print(f"Greška pri slanju mejla: {e}")

if __name__ == "__main__":
    send_master_daily_email()
