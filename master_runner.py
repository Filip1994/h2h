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
INITIAL_BANK = 50000.0

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
        "total_matches": total_matches
    }

def send_master_daily_email():
    today_formatted = datetime.now().strftime('%d.%m.%Y')
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    stats = calculate_analytics()
    current_bank = stats["current_bank"]
    max_daily_risk = current_bank * 0.10

    h2h_max_budget = max_daily_risk * 0.80
    single_max_budget = max_daily_risk * 0.10
    value_max_budget = max_daily_risk * 0.10

    used_fixture_ids = set()

    # 1. SINGLE TIP DANA
    single_content, single_spent, single_fixture_id = market_drop_engine.get_market_drops_and_single_tip(current_bank, single_max_budget)
    if single_fixture_id:
        used_fixture_ids.add(single_fixture_id)

    # 2. VIP H2H ZICERI
    h2h_picks = main.get_h2h_raw_picks()
    filtered_h2h_picks = [p for p in h2h_picks if p['fixture_id'] not in used_fixture_ids]

    saved_bets = main.load_bets()
    h2h_html_blocks = []
    h2h_spent = 0.0

    base_stake_per_match = current_bank * 0.015
    total_requested = len(filtered_h2h_picks) * base_stake_per_match
    scaling_factor = h2h_max_budget / total_requested if total_requested > h2h_max_budget else 1.0

    for p in filtered_h2h_picks:
        used_fixture_ids.add(p['fixture_id'])
        stake = max(100.0, round((base_stake_per_match * scaling_factor) / 50.0) * 50)
        h2h_spent += stake

        bet_id = f"{p['fixture_id']}_{p['market']}"
        badge = "🔥 <b>SUPER ZICER</b> " if p['pct'] >= 95.0 else ""
        direct_web_skip = f"https://github.com/filipmaric994/QuantBet/issues/new?title=SKIP_{bet_id}"

        pick_str = f"{badge}<b>{p['market']}</b> -> <b style='color:#007bff;'>{p['pct']:.0f}%</b> ({p['count']}/{p['total']}) | Kvota: <b>{p['odd']:.2f}</b> <span style='color:#6c757d; font-size:11px;'>(Izvor: {p['bm_source']})</span> | Ulog: <b style='color:#28a745;'>{stake:,.0f} RSD</b>"
        
        block = f"""
        <div style="background:#ffffff; border-left:4px solid #28a745; padding:12px; margin-bottom:12px; border-radius:6px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
            <div style="float:right;">
                <a href="{direct_web_skip}" target="_blank" style="background:#dc3545; color:#ffffff; padding:4px 10px; border-radius:4px; font-size:11px; text-decoration:none; font-weight:bold;">❌ Preskoči tip</a>
            </div>
            <h3 style="margin:0 0 5px 0; color:#1a2a3a;">⚽ (H) {p['home']} vs {p['away']} (A)</h3>
            <p style="margin:0 0 4px 0; color:#6c757d; font-size:12px;">🏆 Liga: {p['league']} | Forma: {p['home_form']:.1f} vs {p['away_form']:.1f} gol/meču</p>
            <p style="margin:0 0 8px 0; color:#495057; font-size:11px; font-style:italic;">📜 Poslednji dueli: {p['h2h_history']}</p>
            <p style="margin:0; font-size:13px;">👉 {pick_str}</p>
        </div>
        """
        h2h_html_blocks.append(block)

        new_bet = {
            "id": bet_id, "type": "H2H", "event_id": p['fixture_id'], "date": today_str,
            "sport": "Football", "match": f"{p['home']} vs {p['away']}", "league": p['league'],
            "market": p['market'], "stake": stake, "odd": p['odd'], "status": "PENDING", "profit": 0
        }
        if not any(b.get('id') == bet_id for b in saved_bets if isinstance(b, dict)):
            saved_bets.append(new_bet)

    # 3. POISSON VALUE BETS
    value_content, value_spent = value_engine.get_value_html_blocks(current_bank, value_max_budget, used_fixture_ids)

    main.save_bets(saved_bets)

    total_spent_today = h2h_spent + value_spent + single_spent
    roi_color = "#28a745" if stats["roi_pct"] >= 0 else "#dc3545"
    profit_sign = "+" if stats["total_profit"] > 0 else ""

    h2h_final_html = "".join(h2h_html_blocks)

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
            {h2h_final_html if h2h_final_html else '<p style="font-style:italic; color:#777; font-size:13px;">Nema H2H zicera sa prolaznošću iznad 75% za danas.</p>'}

            <br>
            <!-- SEKCIJA 3: POISSON MATH VALUE BETOVI -->
            <h3 style="color:#6f42c1; border-bottom:2px solid #6f42c1; padding-bottom:5px;">📐 2. Pure Math Value Bets (Uloženo: {value_spent:,.0f} RSD)</h3>
            {value_content if value_content else '<p style="font-style:italic; color:#777; font-size:13px;">Nema dodatnih matematičkih odstupanja (Edge >= 12%) za mečeve van H2H ponude.</p>'}

            <div style="background:#eef6ff; padding:12px; text-align:center; border-radius:6px; font-size:12px; color:#0056b3; margin-top:25px;">
                🛡️ Sistem automatski štiti banku i eliminise duplicirane ili kontradiktorne opklade.
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
