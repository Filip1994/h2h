import os
import main
import value_engine
import market_drop_engine
import telegram_engine

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

def send_master_daily_bulletin():
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
    h2h_spent = 0.0

    base_stake_per_match = current_bank * 0.015
    total_requested = len(filtered_h2h_picks) * base_stake_per_match
    scaling_factor = h2h_max_budget / total_requested if total_requested > h2h_max_budget else 1.0

    h2h_formatted_picks = []
    for p in filtered_h2h_picks:
        used_fixture_ids.add(p['fixture_id'])
        stake = max(100.0, round((base_stake_per_match * scaling_factor) / 50.0) * 50)
        h2h_spent += stake
        bet_id = f"{p['fixture_id']}_{p['market']}"
        badge = "🔥 <b>SUPER ZICER</b> " if p['pct'] >= 95.0 else ""

        text = (
            f"⚽ <b>(H) {p['home']} vs {p['away']} (A)</b>\n"
            f"⏰ <b>Početak:</b> {p['match_time']}h | 🏆 {p['league']}\n"
            f"📜 <i>Poslednji dueli:</i> {p['h2h_history']}\n"
            f"👉 {badge}<b>{p['market']}</b> ➔ <b>{p['pct']:.0f}%</b> ({p['count']}/{p['total']})\n"
            f"💵 Kvota: <b>{p['odd']:.2f}</b> ({p['bm_source']}) | Ulog: <b>{stake:,.0f} RSD</b>"
        )
        h2h_formatted_picks.append((text, bet_id))

        new_bet = {
            "id": bet_id, "type": "H2H", "event_id": p['fixture_id'], "date": main.datetime.now().strftime('%Y-%m-%d'),
            "sport": "Football", "match": f"{p['home']} vs {p['away']}", "league": p['league'],
            "market": p['market'], "stake": stake, "odd": p['odd'], "status": "PENDING", "profit": 0
        }
        if not any(b.get('id') == bet_id for b in saved_bets if isinstance(b, dict)):
            saved_bets.append(new_bet)

    # 3. POISSON VALUE BETS
    value_content, value_spent = value_engine.get_value_html_blocks(current_bank, value_max_budget, used_fixture_ids)

    main.save_bets(saved_bets)
    total_spent_today = h2h_spent + value_spent + single_spent

    # SLANJE NA TELEGRAM
    telegram_engine.send_bulletin_header(
        current_bank, stats["total_profit"], stats["roi_pct"],
        stats["win_rate"], stats["total_matches"], total_spent_today, max_daily_risk
    )

    if h2h_formatted_picks:
        telegram_engine.send_telegram_message("⚽ <b>--- VIP H2H ZICERI ---</b>")
        for text, bet_id in h2h_formatted_picks:
            telegram_engine.send_telegram_message(text, bet_id=bet_id)

    print("✅ Telegram bilten uspešno poslat!")

if __name__ == "__main__":
    send_master_daily_bulletin()
