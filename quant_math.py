import math
from datetime import datetime

# 1. DIXON-COLES TIME DECAY WEIGHTING (Mečevi od pre 2 godine imaju manju težinu)
def calculate_dixon_coles_weights(date_strings, xi=0.0015):
    weights = []
    now = datetime.now()
    for d_str in date_strings:
        try:
            m_date = datetime.strptime(d_str[:10], '%Y-%m-%d')
            days_diff = (now - m_date).days
            weight = math.exp(-xi * max(0, days_diff))
            weights.append(weight)
        except Exception:
            weights.append(0.5)
    return weights

# 2. FRACTIONAL KELLY CRITERION (Jednačina uloga prema očekivanoj vrednosti)
def calculate_kelly_stake(bank, model_prob_pct, real_odd, fraction=0.25, max_stake_pct=0.02):
    p = model_prob_pct / 100.0
    b = real_odd - 1.0
    if b <= 0 or p <= 0: return 0.0
    
    q = 1.0 - p
    f_kelly = (p * b - q) / b
    
    if f_kelly <= 0: return 0.0
    
    stake = bank * f_kelly * fraction
    max_allowed = bank * max_stake_pct
    final_stake = round(min(stake, max_allowed) / 50.0) * 50
    return max(100.0, final_stake)

# 3. DRAWDOWN CIRCUIT BREAKER (Kočnica banke ako padne za >= 10% u 7 dana)
def check_circuit_breaker(completed_bets, current_bank, initial_bank=50000.0):
    if not completed_bets: return 1.0
    
    recent_losses = sum(b.get('profit', 0) for b in completed_bets[-10:] if b.get('profit', 0) < 0)
    drawdown_pct = (abs(recent_losses) / current_bank) * 100.0
    
    if drawdown_pct >= 10.0:
        print(f"⚠️ CIRCUIT BREAKER ACTIVATED: Drawdown {drawdown_pct:.1f}%. Ulozi se smanjuju za 50%!")
        return 0.5
    return 1.0

# 4. CONFLICT FILTER (Odbacuje tip ako H2H protivreči formi timova)
def is_h2h_form_conflicted(market_name, h2h_pct, combined_form_xg):
    if "Manje 2.5" in market_name and combined_form_xg >= 3.10:
        return True, f"Konflikt: H2H sugeriše Manje 2.5, ali xG forme iznosi {combined_form_xg:.2f}"
    if "Više 2.5" in market_name and combined_form_xg <= 1.80:
        return True, f"Konflikt: H2H sugeriše Više 2.5, ali xG forme iznosi {combined_form_xg:.2f}"
    return False, ""
