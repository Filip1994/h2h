const QB = (() => {
  const MARKET = {OVER_2_5:'Over 2.5',UNDER_2_5:'Under 2.5',BTTS_YES:'BTTS — Yes',BTTS_NO:'BTTS — No',HOME_WIN:'Home Win',AWAY_WIN:'Away Win',DRAW:'Draw',GG:'BTTS — Yes',NG:'BTTS — No','Less than 2.5':'Under 2.5','Manje 2.5':'Under 2.5','Više 2.5':'Over 2.5'};
  const BOOK = {8:{name:'Bet365',logo:'https://commons.wikimedia.org/wiki/Special:Redirect/file/Bet_365_logo.png',verified:true},11:{name:'1xBet',logo:'https://commons.wikimedia.org/wiki/Special:Redirect/file/1xbetlogo.png',verified:true}};
  const esc = v => String(v ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
  const market = v => MARKET[v] || v || '—';
  const odd = v => v == null || v === '' ? '—' : Number(v).toFixed(2);
  const pct = v => Number.isFinite(Number(v)) ? (100 * Number(v)).toFixed(1) + '%' : '—';
  const when = v => {
    if (!v) return '—';
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return esc(v);
    return new Intl.DateTimeFormat('sr-RS',{timeZone:'Europe/Belgrade',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(d).replace(',',' ·');
  };
  const clv = v => {
    if (v == null || v === '') return {value:'—',label:'Unavailable',cls:'neutral'};
    const n = Number(v) * 100;
    if (!Number.isFinite(n)) return {value:'—',label:'Unavailable',cls:'neutral'};
    if (n === 0) return {value:'0.00%',label:'Even',cls:'neutral'};
    return {value:(n > 0 ? '+' : '−') + Math.abs(n).toFixed(2) + '%',label:n > 0 ? 'Beat Close' : 'Lost to Close',cls:n > 0 ? 'positive' : 'negative'};
  };
  const outcome = x => {
    const s = String(x?.status || 'PENDING').toUpperCase();
    if (s === 'WIN') return {label:'WIN',cls:'positive'};
    if (s === 'LOSS') return {label:'LOSS',cls:'negative'};
    return {label:s || 'PENDING',cls:'neutral'};
  };
  const lifecycle = x => `<div class="lifecycle">${stage('OPENING',x.opening_odd,x.opening_captured_at || x.opening_odds_captured_at)}${stage('PICK',x.odd,x.pick_captured_at || x.odds_captured_at || x.created_at)}${stage('CLOSING',x.closing_odd || x.closing_5m_odd,x.closing_captured_at || x.closing_odds_captured_at || x.closing_5m_odds_captured_at)}</div>`;
  const book = x => {
    const b = BOOK[Number(x.bookmaker_id)];
    const name = b?.name || x.bookmaker || 'Bookmaker';
    return b?.verified ? `<div class="book"><img class="book-logo" src="${b.logo}" alt="${esc(name)} verified logo"><span><b>${esc(name)}</b><small class="meta"> · verified</small></span></div>` : `<div class="book"><span class="book-fallback">${esc(name.slice(0,3).toUpperCase())}</span><span><b>${esc(name)}</b></span></div>`;
  };
  const stage = (label, value, time) => `<div class="stage"><label>${label}</label><b>${odd(value)}</b><small>${time ? when(time) : 'Unavailable'}</small></div>`;
  const badge = (kind,text) => `<span class="badge ${kind}">${esc(text)}</span>`;
  const load = async name => {
    const r = await fetch('./' + name + '?v=' + Date.now(), {cache:'no-store'});
    if (!r.ok) throw new Error(name + ' HTTP ' + r.status);
    return r.json();
  };
  const optional = async name => { try { return await load(name); } catch (_) { return null; } };
  const findLatest = (...lists) => {
    const values = [];
    lists.forEach(list => {
      if (!Array.isArray(list)) return;
      list.forEach(x => {
        if (!x || typeof x !== 'object') return;
        ['updated_at','created_at','signal_sent_at','settled_at','odds_captured_at','decision_timestamp','date'].forEach(k => { if (x[k]) values.push(x[k]); });
      });
    });
    const dates = values.map(x => new Date(x)).filter(d => !Number.isNaN(d.getTime()));
    dates.sort((a,b) => b-a);
    return dates.length ? dates[0].toISOString() : null;
  };
  const captureTs = state => state && (state.updated_at || state.last_run_at || state.last_capture_at) || null;
  const generationTs = meta => meta && (meta.updated_at || meta.decision_timestamp) || null;
  const fresh = ts => {
    if (!ts) return ['NO DATA','neutral'];
    const age = (Date.now() - new Date(ts).getTime()) / 60000;
    return age < 10 ? ['FRESH','live'] : age < 30 ? ['AGING','stale'] : ['STALE','stale'];
  };
  const production = bets => Array.isArray(bets) ? bets.filter(x => String(x.signal_source || 'DAILY_BULLETIN') !== 'INTRADAY_ALERT') : [];
  const status = (meta,bets,strong,near,capture) => {
    const generation = generationTs(meta);
    const cap = captureTs(capture);
    if (!generation && !cap) return ['NO DATA','neutral'];
    if (!cap) return ['NOT RUN','neutral'];
    const eligible = Number(capture?.eligible_fixture_count ?? capture?.eligible_fixtures);
    if (Number.isFinite(eligible) && eligible === 0) return ['NO ELIGIBLE FIXTURES','neutral'];
    const latest = findLatest(bets,strong,near,meta ? [meta] : []);
    if (!latest) return ['NO SIGNALS','neutral'];
    const age = (Date.now() - new Date(latest).getTime()) / 60000;
    if (age > 180) return ['STALE','stale'];
    const all = [].concat(bets || [], strong || [], near || []);
    const active = all.some(x => String(x.status || 'PENDING').toUpperCase() === 'PENDING');
    return [active ? 'RUNNING' : 'NO SIGNALS', active ? 'live' : 'neutral'];
  };
  const statusCard = (state,detail) => `<div class="notice status-card ${String(state).toLowerCase().replace(/ /g,'-')}"><b>SYSTEM / DATA STATUS · ${esc(state)}</b><div class="sub">${esc(detail)}</div></div>`;
  const resultBlock = x => {
    const o = outcome(x);
    const profit = x.profit == null ? null : Number(x.profit);
    const pcls = profit == null || !Number.isFinite(profit) ? 'neutral' : profit > 0 ? 'positive' : profit < 0 ? 'negative' : 'neutral';
    const pl = profit == null || !Number.isFinite(profit) ? '—' : (profit >= 0 ? '+' : '') + profit.toFixed(2) + ' RSD';
    const settlement = x.settled_at ? ` · Settled ${when(x.settled_at)}` : '';
    const score = x.result ? ` · Result ${esc(x.result)}` : '';
    return `<div class="metric-row"><span class="metric ${o.cls}">OUTCOME <b>${esc(o.label)}</b></span><span class="metric ${pcls}">P/L <b>${esc(pl)}</b></span>${score ? `<span class="metric">${score.slice(3)}</span>` : ''}</div><div class="meta" style="margin-top:8px">${esc(String(x.settlement_type || 'COUNTERFACTUAL'))} · NOT A PRODUCTION BET${esc(settlement)}</div>`;
  };
  const productionCard = x => {
    const c = clv(x.clv_odds_pct);
    const o = outcome(x);
    const profit = Number(x.profit || 0);
    const pcls = profit > 0 ? 'positive' : profit < 0 ? 'negative' : 'neutral';
    return `<article class="card"><div class="match-head"><div><div class="teams">${esc(x.match || 'Meč')}</div><div class="league">${esc(x.league || '')} · ${esc(market(x.market_display || x.market))}</div></div>${badge('production','PRODUCTION · PAPER BET')}</div>${book(x)}${lifecycle(x)}<div class="clv ${c.cls}"><span class="meta">CLV · ${esc(c.label)}</span><br><strong>${esc(c.value)}</strong></div><div class="metric-row"><span class="metric ${o.cls}">RESULT <b>${esc(o.label)}</b></span><span class="metric ${pcls}">P/L <b>${profit >= 0 ? '+' : ''}${profit.toFixed(2)} RSD</b></span><span class="metric">KICKOFF <b>${when(x.kickoff || x.date)}</b></span></div></article>`;
  };
  const signalCard = (x,near) => {
    const c = clv(x.clv_odds_pct);
    return `<article class="card"><div class="match-head"><div><div class="teams">${esc(x.match || 'Meč')}</div><div class="league">${esc(x.league || '')} · ${esc(market(x.market_display || x.market))}</div></div>${badge(near ? 'near' : 'strong',near ? 'NEAR MISS' : 'STRONG SIGNAL')}</div>${book(x)}${lifecycle(x)}<div class="metric-row"><span class="metric">EV <b>${pct(x.expected_value)}</b></span><span class="metric">EDGE <b>${pct(x.probability_edge)}</b></span>${near ? `<span class="metric">REASON <b>${esc(x.near_miss_reason || '—')}</b></span>` : ''}</div><div class="clv ${c.cls}"><span class="meta">CLV · ${esc(c.label)}</span><br><strong>${esc(c.value)}</strong></div>${resultBlock(x)}<div class="meta" style="margin-top:12px">Kickoff · ${when(x.kickoff || x.created_at)}</div></article>`;
  };
  const row = x => {
    const c = clv(x.clv_odds_pct);
    const o = outcome(x);
    const profit = x.profit == null ? null : Number(x.profit);
    const pcls = profit == null || !Number.isFinite(profit) ? 'neutral' : profit > 0 ? 'positive' : profit < 0 ? 'negative' : 'neutral';
    return `<tr><td>${esc(when(x.kickoff || x.date || x.created_at))}</td><td><b>${esc(x.match || '—')}</b><br><span class="meta">${esc(x.league || '')}</span></td><td>${esc(market(x.market_display || x.market))}</td><td>${esc(BOOK[Number(x.bookmaker_id)]?.name || x.bookmaker || '—')}</td><td>${esc(odd(x.opening_odd))} → ${esc(odd(x.odd))} → ${esc(odd(x.closing_odd || x.closing_5m_odd))}</td><td class="${c.cls}">${esc(c.value)}<br><span class="meta">${esc(c.label)}</span></td><td class="${o.cls}">${esc(o.label)}</td><td class="${pcls}">${profit == null || !Number.isFinite(profit) ? '—' : (profit >= 0 ? '+' : '') + profit.toFixed(2)}</td></tr>`;
  };
  const renderBucket = (rows,activeId,historyId,near) => {
    const list = Array.isArray(rows) ? rows : [];
    const active = list.filter(x => String(x.status || 'PENDING').toUpperCase() === 'PENDING');
    const history = list.filter(x => String(x.status || 'PENDING').toUpperCase() !== 'PENDING');
    const a = document.getElementById(activeId), h = document.getElementById(historyId);
    if (a) a.innerHTML = active.slice(0,30).map(x => signalCard(x,near)).join('') || '<div class="card empty">Nema aktivnih opservacija.</div>';
    if (h) h.innerHTML = history.slice().reverse().slice(0,200).map(x => signalCard(x,near)).join('') || '<div class="card empty">Nema istorijskih opservacija.</div>';
  };
  async function render() {
    const page = document.body.dataset.page || 'overview';
    const root = document.querySelector('#cards') || document.querySelector('#summary') || document.querySelector('#rows');
    try {
      const bets = await load('bets.json');
      const meta = await load('ledger_meta.json');
      const capture = await optional('odds_collection_state.json');
      const strong = (await optional('strong_signals.json')) || [];
      const near = (await optional('near_misses.json')) || [];
      const prod = production(bets);
      const settled = prod.filter(x => ['WIN','LOSS','SKIPPED','VOID','REVIEW'].includes(String(x.status || '').toUpperCase()));
      const done = prod.filter(x => ['WIN','LOSS'].includes(String(x.status || '').toUpperCase()));
      const profit = done.reduce((s,x) => s + Number(x.profit || 0), 0);
      const stake = done.reduce((s,x) => s + Number(x.stake || 0), 0);
      const wins = done.filter(x => String(x.status || '').toUpperCase() === 'WIN').length;
      const gen = generationTs(meta), cap = captureTs(capture), latest = findLatest(prod,strong,near,meta ? [meta] : []);
      const fr = fresh(latest), st = status(meta,prod,strong,near,capture);
      document.querySelectorAll('[data-fresh]').forEach(e => { e.textContent = fr[0]; e.classList.add(fr[1]); });
      document.querySelectorAll('[data-status]').forEach(e => { e.textContent = st[0]; e.classList.add(st[1]); });
      document.querySelectorAll('[data-updated]').forEach(e => e.textContent = when(latest));
      document.querySelectorAll('[data-generation]').forEach(e => e.textContent = when(gen));
      document.querySelectorAll('[data-capture]').forEach(e => e.textContent = when(cap));
      if (page === 'overview') {
        const bank = document.querySelector('#bank'), pnl = document.querySelector('#pnl'), roi = document.querySelector('#roi'), win = document.querySelector('#win'), count = document.querySelector('#count'), paper = document.querySelector('#paper'), summary = document.querySelector('#summary');
        if (bank) bank.textContent = (Number(meta.initial_bank || 0) + profit).toFixed(0) + ' RSD';
        if (pnl) pnl.textContent = (profit >= 0 ? '+' : '') + profit.toFixed(2) + ' RSD';
        if (roi) roi.textContent = (stake ? 100 * profit / stake : 0).toFixed(2) + '%';
        if (win) win.textContent = (done.length ? 100 * wins / done.length : 0).toFixed(1) + '%';
        if (count) count.textContent = done.length;
        if (paper) paper.textContent = meta.paper_mode === false ? 'LIVE' : 'PAPER';
        if (summary) summary.innerHTML = prod.length ? prod.slice().reverse().slice(0,4).map(productionCard).join('') : statusCard(st[0], st[0] === 'NO SIGNALS' ? 'Scanner je radio; nema qualifying Production signala.' : 'Canonical dashboard data nije dostupna.');
      }
      if (page === 'production') {
        const count = document.querySelector('#count'), bank = document.querySelector('#bank'), pnl = document.querySelector('#pnl'), roi = document.querySelector('#roi'), cards = document.querySelector('#cards'), rows = document.querySelector('#rows');
        if (count) count.textContent = done.length;
        if (bank) bank.textContent = (Number(meta.initial_bank || 0) + profit).toFixed(0) + ' RSD';
        if (pnl) pnl.textContent = (profit >= 0 ? '+' : '') + profit.toFixed(2) + ' RSD';
        if (roi) roi.textContent = (stake ? 100 * profit / stake : 0).toFixed(2) + '%';
        if (cards) cards.innerHTML = prod.filter(x => ['PENDING','SKIPPED'].includes(String(x.status || '').toUpperCase())).slice(0,30).map(productionCard).join('') || statusCard(st[0], 'Nema aktivnih Production odluka u trenutno dostupnom ledgeru.');
        if (rows) rows.innerHTML = settled.slice().reverse().slice(0,200).map(row).join('') || '<tr><td colspan="8" class="empty">Nema Production history zapisa.</td></tr>';
      }
      if (page === 'strong') {
        const count = document.querySelector('#count'); if (count) count.textContent = strong.length;
        renderBucket(strong,'active-cards','history-cards',false);
      }
      if (page === 'near') {
        const count = document.querySelector('#count'); if (count) count.textContent = near.length;
        renderBucket(near,'active-cards','history-cards',true);
      }
      if (page === 'history') {
        const all = prod.map(x => ({...x,signal_class:'PRODUCTION'})).concat(strong.map(x => ({...x,signal_class:'STRONG_SIGNAL'})),near.map(x => ({...x,signal_class:'NEAR_MISS'})));
        const renderHistory = () => {
          const q = (document.querySelector('#q')?.value || '').toLowerCase(), cls = document.querySelector('#class')?.value || '', statusValue = document.querySelector('#status')?.value || '';
          const filtered = all.filter(x => (!q || JSON.stringify(x).toLowerCase().includes(q)) && (!cls || String(x.signal_class).toUpperCase() === cls) && (!statusValue || String(x.status || '').toUpperCase() === statusValue));
          const rows = document.querySelector('#rows'); if (rows) rows.innerHTML = filtered.slice().reverse().slice(0,500).map(row).join('') || '<tr><td colspan="8" class="empty">Nema rezultata za izabrane filtere.</td></tr>';
          const count = document.querySelector('#count'); if (count) count.textContent = filtered.length;
        };
        window.QB_RENDER_HISTORY = renderHistory;
        document.querySelectorAll('#q,#class,#status').forEach(e => { e.addEventListener('input',renderHistory); e.addEventListener('change',renderHistory); });
        renderHistory();
      }
    } catch (e) {
      console.error('QuantBet dashboard render error', e);
      document.querySelectorAll('[data-fresh]').forEach(x => { x.textContent = 'ERROR'; x.classList.add('error'); });
      document.querySelectorAll('[data-status]').forEach(x => { x.textContent = 'ERROR'; x.classList.add('error'); });
      if (root) root.innerHTML = `<div class="card empty">Podaci trenutno nisu dostupni. ${esc(e.message)}</div>`;
    }
  }
  return {render};
})();
QB.render();
setInterval(QB.render,60000);
