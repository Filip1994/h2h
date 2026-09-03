import os
import sys
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import main
import value_engine
import market_drop_engine
import quant_math

GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_PASS = os.environ.get("GMAIL_APP_PASS", "").strip()
INITIAL_BANK = 50000.0
GITHUB_REPO = "Filip1994/h2h"

def calculate_analytics():
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
        "total_matches": total_matches,
        "completed_bets": completed_bets
    }

def send_master_daily_email():
    if not GMAIL_USER or not GMAIL_PASS:
        print("⚠️ Nemam Gmail podatke u Secrets (GMAIL_USER / GMAIL_APP_PASS). Preskačem slanje.")
        return

    today_formatted = datetime.now().strftime('%d.%m.%Y.')
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    stats = calculate_analytics()
    current_bank = stats["current_bank"]
    max_daily_risk = current_bank * 0.10

    h2h_max_budget = max_daily_risk * 0.80
    single_max_budget = max_daily_risk * 0.10
    value_max_budget = max_daily_risk * 0.10

    cb_multiplier = quant_math.check_circuit_breaker(stats["completed_bets"], current_bank)
    used_fixture_ids = set()

    # 1. SINGLE TIP DANA
    single_html = ""
    single_spent = 0.0
    try:
        s_text, single_spent, s_fixture_id = market_drop_engine.get_market_drops_and_single_tip(current_bank, single_max_budget)
        if s_fixture_id:
            used_fixture_ids.add(s_fixture_id)
            skip_url = f"https://github.com/{GITHUB_REPO}/issues/new?title=SKIP_{s_fixture_id}_SINGLE"
            single_html = f"""
            <div style="background:#ffffff; border:1px solid #6366f1; border-left:5px solid #4338ca; border-radius:8px; padding:15px; margin-bottom:20px;">
                <div style="float:right;">
                    <a href="{skip_url}" target="_blank" style="background:#dc3545; color:#ffffff; padding:5px 10px; border-radius:4px; font-size:11px; text-decoration:none; font-weight:bold;">❌ Preskoči tip</a>
                </div>
                <div style="background:#4338ca; color:#ffffff; padding:6px 10px; border-radius:4px; font-weight:bold; font-size:13px; margin-bottom:10px; display:inline-block;">⭐ EKSKLUZIVNI SINGLE TIP DANA</div>
                <p style="margin:5px 0; font-size:13px;">{s_text.replace('\n', '<br>')}</p>
            </div>
            """
    except Exception as e:
        print(f"⚠️ Single Tip Engine greška: {e}")

    # 2. VIP H2H ZICERI
    h2h_blocks = []
    h2h_spent = 0.0
    try:
        h2h_picks = main.get_h2h_raw_picks() or []
        filtered_h2h_picks = [p for p in h2h_picks if p.get('fixture_id') not in used_fixture_ids]
        saved_bets = main.load_bets()

        for p in filtered_h2h_picks:
            used_fixture_ids.add(p['fixture_id'])
            stake = quant_math.calculate_kelly_stake(current_bank, p['pct'], p['odd']) * cb_multiplier
            stake = max(100.0, min(h2h_max_budget, stake))
            h2h_spent += stake
            
            bet_id = f"{p['fixture_id']}_{p['market']}"
            badge = "🔥 <b>SUPER ZICER</b> " if p['pct'] >= 95.0 else ""
            skip_url = f"https://github.com/{GITHUB_REPO}/issues/new?title=SKIP_{bet_id}"

            block = f"""
            <div style="background:#ffffff; border-left:4px solid #28a745; padding:12px; margin-bottom:12px; border-radius:6px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
                <div style="float:right;">
                    <a href="{skip_url}" target="_blank" style="background:#dc3545; color:#ffffff; padding:4px 10px; border-radius:4px; font-size:11px; text-decoration:none; font-weight:bold;">❌ Preskoči tip</a>
                </div>
                <h3 style="margin:0 0 5px 0; color:#1a2a3a; font-size:15px;">⚽ (H) {p['home']} vs {p['away']} (A)</h3>
                <p style="margin:0 0 4px 0; color:#6c757d; font-size:12px;"><b>⏰ Početak:</b> <b style="color:#28a745;">{p['match_time']}h</b> | 🏆 {p['league']}</p>
                <p style="margin:0 0 6px 0; color:#495057; font-size:11px; font-style:italic;">📜 Poslednji dueli: {p['h2h_history']}</p>
                <p style="margin:0; font-size:13px;">👉 {badge}<b>{p['market']}</b> ➔ <b style="color:#007bff;">{p['pct']:.0f}%</b> | Kvota: <b>{p['odd']:.2f}</b> ({p['bm_source']}) | Ulog: <b style="color:#28a745;">{stake:,.0f} RSD</b></p>
            </div>
            """
            h2h_blocks.append(block)

            new_bet = {
                "id": bet_id, "type": "H2H", "event_id": p['fixture_id'], "date": today_str,
                "sport": "Football", "match": f"{p['home']} vs {p['away']}", "league": p['league'],
                "market": p['market'], "stake": stake, "odd": p['odd'], "status": "PENDING", "profit": 0
            }
            if not any(b.get('id') == bet_id for b in saved_bets if isinstance(b, dict)):
                saved_bets.append(new_bet)

        main.save_bets(saved_bets)
    except Exception as e:
        print(f"⚠️ H2H Engine greška: {e}")

    # 3. POISSON VALUE BETS
    value_blocks = []
    value_spent = 0.0
    try:
        v_picks, value_spent = value_engine.get_value_html_blocks(current_bank, value_max_budget, used_fixture_ids)
        for text, bet_id in v_picks:
            skip_url = f"https://github.com/{GITHUB_REPO}/issues/new?title=SKIP_{bet_id}"
            block = f"""
            <div style="background:#ffffff; border-left:4px solid #6f42c1; padding:12px; margin-bottom:12px; border-radius:6px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
                <div style="float:right;">
                    <a href="{skip_url}" target="_blank" style="background:#dc3545; color:#ffffff; padding:4px 10px; border-radius:4px; font-size:11px; text-decoration:none; font-weight:bold;">❌ Preskoči tip</a>
                </div>
                <p style="margin:0; font-size:13px;">{text.replace('\n', '<br>')}</p>
            </div>
            """
            value_blocks.append(block)
    except Exception as e:
        print(f"⚠️ Value Engine greška: {e}")

    total_spent_today = h2h_spent + value_spent + single_spent
    roi_color = "#28a745" if stats["roi_pct"] >= 0 else "#dc3545"
    profit_sign = "+" if stats["total_profit"] > 0 else ""

    h2h_final_html = "".join(h2h_blocks)
    value_final_html = "".join(value_blocks)

    master_html = f"""
    <html>
    <body style="font-family:'Segoe UI', Arial, sans-serif; background-color:#f4f4f7; padding:20px; color:#333;">
        <div style="max-width:700px; background:#ffffff; margin:0 auto; padding:25px; border-radius:12px; box-shadow:0 4px 15px rgba(0,0,0,0.06);">
            
            <div style="text-align:center; padding-bottom:15px; border-bottom:2px solid #eef0f2; margin-bottom:20px;">
                <h1 style="color:#1a2a3a; margin:0; font-size:22px;">🚀 QUANT FUND BILTEN ({today_formatted})</h1>
                
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

            {single_html}

            <h3 style="color:#28a745; border-bottom:2px solid #28a745; padding-bottom:5px;">⚽ 1. VIP H2H Ziceri (Uloženo: {h2h_spent:,.0f} RSD)</h3>
            {h2h_final_html if h2h_final_html else '<p style="font-style:italic; color:#777; font-size:13px;">Nema H2H zicera sa prolaznošću iznad 75% za danas.</p>'}

            <br>
            <h3 style="color:#6f42c1; border-bottom:2px solid #6f42c1; padding-bottom:5px;">📐 2. Pure Math Value Bets (Uloženo: {value_spent:,.0f} RSD)</h3>
            {value_final_html if value_final_html else '<p style="font-style:italic; color:#777; font-size:13px;">Nema dodatnih matematičkih odstupanja (Edge >= 12%) za danas.</p>'}

            <div style="background:#eef6ff; padding:12px; text-align:center; border-radius:6px; font-size:12px; color:#0056b3; margin-top:25px;">
                🛡️ Sistem primenjuje Dixon-Coles time-decay i Kelly Criterion stake sizing.
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg['Subject'] = f"🚀 Quant Fund Bilten (Banka: {current_bank:,.0f} RSD | ROI: {stats['roi_pct']:.1f}%) - {today_formatted}"
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg.attach(MIMEText(master_html, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        print("✅ Izveštaj uspešno poslat na Email!")
    except Exception as e:
        print(f"❌ Greška pri slanju mejla: {e}")

if __name__ == "__main__":
    send_master_daily_email()
