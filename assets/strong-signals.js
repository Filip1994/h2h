(() => {
  const MARKET = { OVER_2_5: 'Over 2.5', UNDER_2_5: 'Under 2.5', BTTS_YES: 'BTTS — Yes', BTTS_NO: 'BTTS — No', HOME_WIN: 'Home Win', AWAY_WIN: 'Away Win', DRAW: 'Draw', GG: 'BTTS — Yes', NG: 'BTTS — No' };
  const esc = (value) => String(value ?? '').replace(/[&<>\\\"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', "'": '&#39;' }[char]));
  const market = (value) => MARKET[value] || value || '—';
  const odd = (value) => value == null || value === '' ? '—' : Number(value).toFixed(2);
  const pct = (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : '—';
  const when = (value) => {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return esc(value);
    return new Intl.DateTimeFormat('sr-RS', { timeZone: 'Europe/Belgrade', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(date).replace(',', ' ·');
  };
  const kickoffDate = (row) => {
    if (!row?.kickoff) return null;
    const date = new Date(row.kickoff);
    return Number.isNaN(date.getTime()) ? null : date;
  };
  const isActive = (row) => {
    if (String(row?.status || 'PENDING').toUpperCase() !== 'PENDING') return false;
    const kickoff = kickoffDate(row);
    return !kickoff || kickoff.getTime() > Date.now();
  };
  const effectiveStatus = (row) => {
    const status = String(row?.status || 'PENDING').toUpperCase();
    if (status === 'PENDING' && kickoffDate(row)?.getTime() <= Date.now()) return 'SKIPPED';
    return status;
  };
  const load = async (name) => {
    const response = await fetch(`./${name}?v=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${name} HTTP ${response.status}`);
    return response.json();
  };
  const fixture = (row) => {
    if (row.match) return String(row.match);
    const home = row.home_name || row.home_team || row.home;
    const away = row.away_name || row.away_team || row.away;
    return home && away ? `${home} vs ${away}` : 'Meč';
  };
  const clv = (value) => {
    if (value == null || value === '') return { value: '—', cls: 'neutral' };
    const number = Number(value) * 100;
    if (!Number.isFinite(number)) return { value: '—', cls: 'neutral' };
    if (number === 0) return { value: '0.00%', cls: 'neutral' };
    return { value: `${number > 0 ? '+' : '−'}${Math.abs(number).toFixed(2)}%`, cls: number > 0 ? 'positive' : 'negative' };
  };
  const setStatus = (label, kind = '') => {
    const element = document.getElementById('status');
    if (!element) return;
    element.textContent = label;
    element.className = `status-pill ${kind}`.trim();
  };
  const stage = (label, value, time) => `<div class="stage"><label>${label}</label><b>${odd(value)}</b><small>${time ? when(time) : 'Unavailable'}</small></div>`;
  const lifecycle = (row) => `<div class="lifecycle">${stage('OPENING', row.opening_odd, row.opening_captured_at || row.opening_odds_captured_at)}${stage('PICK', row.odd, row.pick_captured_at || row.odds_captured_at || row.created_at)}${stage('CLOSING', row.closing_odd || row.closing_5m_odd, row.closing_captured_at || row.closing_odds_captured_at || row.closing_5m_odds_captured_at)}</div>`;
  const card = (row) => {
    const close = clv(row.clv_odds_pct);
    const status = effectiveStatus(row);
    return `<article class="card signal-row"><div class="signal-row-main"><div class="signal-row-match"><div class="teams">${esc(fixture(row))}</div><div class="league">${esc(row.league || row.league_name || '')} · ${esc(market(row.market_display || row.market))}</div></div><div class="signal-row-book"><span class="badge strong">STRONG SIGNAL</span><div class="book"><span class="book-fallback">${esc(String(row.bookmaker || 'BOOK').slice(0, 3).toUpperCase())}</span><span><b>${esc(row.bookmaker || 'Bookmaker')}</b></span></div></div><div class="signal-row-odds">${lifecycle(row)}</div><div class="signal-row-metrics"><span class="metric">EV <b>${pct(row.expected_value)}</b></span><span class="metric">EDGE <b>${pct(row.probability_edge)}</b></span><span class="metric ${close.cls}">CLV <b>${esc(close.value)}</b></span></div><div class="signal-row-status"><span class="metric ${status === 'WIN' ? 'positive' : status === 'LOSS' ? 'negative' : 'neutral'}">STATUS <b>${esc(status)}</b></span><span class="metric">P/L <b>${Number(row.virtual_profit || 0) >= 0 ? '+' : ''}${Number(row.virtual_profit || 0).toFixed(2)} RSD</b></span></div></div><div class="meta signal-row-kickoff">Kickoff · ${when(row.kickoff || row.signal_sent_at || row.created_at)}</div></article>`;
  };
  const historyRow = (row) => {
    const close = clv(row.clv_odds_pct);
    const profit = Number(row.virtual_profit || 0);
    return `<tr><td>${esc(when(row.kickoff || row.signal_sent_at || row.created_at))}</td><td><b>${esc(fixture(row))}</b><br><span class="meta">${esc(row.league || row.league_name || '')}</span></td><td>${esc(market(row.market_display || row.market))}</td><td>${esc(row.bookmaker || '—')}</td><td>${esc(odd(row.opening_odd))} → ${esc(odd(row.odd))} → ${esc(row.closing_odd || row.closing_5m_odd)}</td><td class="${close.cls}">${esc(close.value)}</td><td>${esc(effectiveStatus(row))}</td><td class="${profit >= 0 ? 'positive' : 'negative'}">${profit >= 0 ? '+' : ''}${profit.toFixed(2)}</td></tr>`;
  };
  const render = async () => {
    setStatus('LOADING');
    try {
      const [signals, portfolio] = await Promise.all([load('strong_signals.json'), load('strong_signals_portfolio.json')]);
      const rows = Array.isArray(signals) ? signals.filter((row) => String(row.signal_class || '').toUpperCase() === 'STRONG_SIGNAL') : [];
      const active = rows.filter(isActive);
      const history = rows.filter((row) => !isActive(row));
      const activeElement = document.getElementById('active-cards');
      const historyElement = document.getElementById('history-cards');
      if (activeElement) activeElement.innerHTML = active.slice().reverse().slice(0, 30).map(card).join('') || '<div class="card empty">Nema aktivnih Strong Signal opservacija.</div>';
      if (historyElement) historyElement.innerHTML = history.slice().reverse().slice(0, 200).map(historyRow).join('') || '<tr><td colspan="8" class="empty">Nema istorijskih Strong Signal zapisa.</td></tr>';
      document.getElementById('bank').textContent = `${Number(portfolio.current_bank ?? 10000).toFixed(0)} RSD`;
      document.getElementById('pnl').textContent = `${Number(portfolio.total_profit || 0) >= 0 ? '+' : ''}${Number(portfolio.total_profit || 0).toFixed(2)} RSD`;
      document.getElementById('roi').textContent = `${(Number(portfolio.roi || 0) * 100).toFixed(2)}%`;
      document.getElementById('win').textContent = `${(Number(portfolio.win_rate || 0) * 100).toFixed(2)}%`;
      document.getElementById('count').textContent = Number(portfolio.completed_count || 0);
      const latest = rows.map((row) => row.signal_sent_at || row.created_at || row.kickoff).filter(Boolean).sort().pop();
      document.getElementById('updated').textContent = when(latest);
      document.getElementById('portfolio-status').textContent = '10,000 RSD BASE';
      setStatus(`VIRTUAL · ${rows.length} SIGNALS`, active.length ? 'live' : 'stale');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setStatus('DATA ERROR', 'error');
      const activeElement = document.getElementById('active-cards');
      if (activeElement) activeElement.innerHTML = `<div class="notice"><b>STRONG SIGNAL DATA ERROR</b><div class="sub">${esc(message)}</div></div>`;
    }
  };
  render();
})();
