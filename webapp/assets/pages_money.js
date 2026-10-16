/* GLAPP web client — money: wallet, deposit, withdraw, history, data bundles. */
(function () {
  'use strict';
  const G = window.GL;
  const { esc, money, $, $$ } = G;

  const txRow = (t) => {
    const amt = Number(t.amount);
    return '<div class="item"><div class="grow"><div><b>' + esc(G.pretty(t.transaction_type)) + '</b> <span class="pill ' + (t.status === 'success' ? 'ok' : t.status === 'failed' ? 'bad' : 'warn') + '">' + esc(t.status) + '</span></div>' +
      '<div class="small mute">' + esc(t.description || '') + '</div><div class="small mute">' + G.date(t.created_at) + (t.reference ? ' · ' + esc(t.reference) : '') + '</div></div>' +
      '<b style="color:' + (amt < 0 ? 'var(--bad)' : 'var(--ok)') + '">' + (amt < 0 ? '−' : '+') + money(Math.abs(amt)) + '</b></div>';
  };

  /* First-time wallet setup, same two steps as the mobile WalletOnboarding. */
  function setupCards(el, w, redraw) {
    let html = '';
    if (!w.user_has_bvn) html += '<div class="card"><h2>Verify your BVN</h2><p class="mute small">Required to generate your dedicated funding account.</p><input id="bvn" inputmode="numeric" maxlength="11" placeholder="11-digit BVN"><button class="btn block" id="bvnb" style="margin-top:10px">Save BVN</button></div>';
    if (!w.user_has_pin) html += '<div class="card"><h2>Create transaction PIN</h2><p class="mute small">A 4-digit PIN protects payments and withdrawals.</p><input id="npin" type="password" inputmode="numeric" maxlength="4" placeholder="4-digit PIN"><button class="btn block" id="pinb" style="margin-top:10px">Set PIN</button></div>';
    const slot = document.createElement('div'); slot.innerHTML = html;
    const bvnb = $('#bvnb', slot); const pinb = $('#pinb', slot);
    if (bvnb) bvnb.onclick = () => G.busy(bvnb, async () => {
      const v = $('#bvn', slot).value.trim();
      if (!/^\d{11}$/.test(v)) return G.toast('BVN must be 11 digits');
      try { await G.post('/users/update-bvn/', { bvn: v }); G.toast('BVN saved'); redraw(); } catch (e) { G.toast(G.errMsg(e)); }
    });
    if (pinb) pinb.onclick = () => G.busy(pinb, async () => {
      const v = $('#npin', slot).value.trim();
      if (!/^\d{4}$/.test(v)) return G.toast('PIN must be 4 digits');
      try { await G.post('/finance/pin/', { pin: v }); G.toast('PIN set'); redraw(); } catch (e) { G.toast(G.errMsg(e)); }
    });
    return slot;
  }

  G.route('/wallet', async (el) => {
    async function draw() {
      const [w, tx] = await Promise.all([G.get('/finance/wallet/'), G.get('/finance/transactions/').catch(() => ({ results: [] }))]);
      el.innerHTML = '<h1>Wallet</h1><div class="hero"><div class="small">Available balance</div><div class="big">' + money(w.available_balance != null ? w.available_balance : w.balance) + '</div>' +
        '<div class="small">In escrow: ' + money(w.locked_balance) + '</div><div class="row" style="margin-top:12px"><a class="btn" href="#/wallet/deposit">Add money</a><a class="btn" href="#/wallet/withdraw">Withdraw</a><a class="btn" href="#/data">Buy data</a></div></div>';
      el.appendChild(setupCards(el, w, draw));
      const recent = G.list(tx).slice(0, 8);
      const card = document.createElement('div'); card.className = 'card';
      card.innerHTML = '<div class="row between"><h2>Recent transactions</h2><a href="#/wallet/history">See all</a></div>' + (recent.length ? recent.map(txRow).join('') : '<div class="empty">No transactions yet.</div>');
      el.appendChild(card);
    }
    await draw();
  }, { auth: true });

  G.route('/wallet/deposit', async (el) => {
    const w = await G.get('/finance/wallet/');
    const accts = w.funding_accounts || [];
    el.innerHTML = '<div class="narrow"><a href="#/wallet">← Wallet</a><h1>Add money</h1><div class="card"><p>Transfer any amount to your dedicated account below. Your wallet is credited automatically once the transfer clears.</p>' +
      (accts.length ? accts.map((a) => '<div class="card" style="background:var(--brand-l)"><div class="small mute">Bank</div><b>' + esc(a.bank_name) + '</b><div class="small mute" style="margin-top:8px">Account number</div>' +
        '<div class="row"><b style="font-size:22px;letter-spacing:1px" class="grow">' + esc(a.account_number) + '</b><button class="btn sm sec" data-copy="' + esc(a.account_number) + '">Copy</button></div>' +
        '<div class="small mute" style="margin-top:8px">Account name</div><b>' + esc(a.account_name) + '</b></div>').join('')
        : '<div class="alert">' + (w.user_has_bvn ? 'Your account is still being generated. Refresh in a moment.' : 'Add your BVN on the <a href="#/wallet">wallet page</a> to generate your funding account.') + '</div>') +
      '</div></div>';
    el.onclick = (e) => {
      const c = e.target.closest('[data-copy]');
      if (!c) return;
      try { navigator.clipboard.writeText(c.dataset.copy).then(() => G.toast('Copied')); } catch (er) { G.toast(c.dataset.copy); }
    };
  }, { auth: true });

  G.route('/wallet/history', async (el, ctx) => {
    const type = ctx.query.type || '';
    const types = ['', 'deposit', 'payment', 'withdrawal', 'bill_payment', 'escrow_release', 'refund', 'promotion'];
    el.innerHTML = '<a href="#/wallet">← Wallet</a><h1>Transaction history</h1><div class="chips">' + types.map((t) =>
      '<a class="chip ' + (t === type ? 'on' : '') + '" href="#/wallet/history' + (t ? '?type=' + t : '') + '">' + (t ? esc(G.pretty(t)) : 'All') + '</a>').join('') + '</div><div class="card" id="list">' + G.loading + '</div><div class="center" id="m"></div>';
    let page = 1;
    async function load() {
      const d = await G.get('/finance/transactions/?page=' + page + (type ? '&transaction_type=' + type : ''));
      let items = G.list(d);
      if (type) items = items.filter((t) => t.transaction_type === type);
      if (page === 1) $('#list', el).innerHTML = '';
      if (page === 1 && !items.length) $('#list', el).innerHTML = '<div class="empty">No transactions.</div>';
      $('#list', el).insertAdjacentHTML('beforeend', items.map(txRow).join(''));
      $('#m', el).innerHTML = d && d.next ? '<button class="btn ghost" id="mb">Load more</button>' : '';
      const b = $('#mb', el); if (b) b.onclick = () => G.busy(b, async () => { page += 1; await load(); });
    }
    await load();
  }, { auth: true });

  /* Wallet withdrawal -> creates an admin-processed ticket. */
  async function withdrawPage(el) {
    const [w, banksRaw] = await Promise.all([G.get('/finance/wallet/'), G.get('/finance/banks/').catch(() => [])]);
    const banks = G.list(banksRaw).slice().sort((a, b) => a.name.localeCompare(b.name));
    el.innerHTML = '<div class="narrow"><a href="#/wallet">← Wallet</a><h1>Withdraw</h1><div class="card"><div class="small mute">Available</div><div class="price" style="font-size:22px">' + money(w.available_balance != null ? w.available_balance : w.balance) + '</div></div>' +
      (!w.user_has_pin ? '<div class="alert">Set a transaction PIN first on the <a href="#/security">security page</a>.</div>' : '') +
      '<div class="card"><label>Amount (₦)</label><input id="amt" type="number" min="1" inputmode="decimal">' +
      '<label>Bank</label><select id="bank"><option value="">Select bank…</option>' + banks.map((b) => '<option value="' + esc(b.code) + '">' + esc(b.name) + '</option>').join('') + '</select>' +
      '<label>Account number</label><input id="acc" inputmode="numeric" maxlength="10">' +
      '<div id="resolved" class="small" style="margin-top:6px"></div><div id="err"></div>' +
      '<button class="btn block" id="go" style="margin-top:12px" disabled>Request withdrawal</button></div></div>';
    let accName = '';
    async function resolve() {
      accName = '';
      $('#go', el).disabled = true;
      const acc = $('#acc', el).value.trim(); const code = $('#bank', el).value;
      const out = $('#resolved', el);
      if (acc.length !== 10 || !code) { out.textContent = ''; return; }
      out.innerHTML = '<span class="spin"></span> Verifying account…';
      try {
        const d = await G.get('/finance/verify-bank/?account_number=' + encodeURIComponent(acc) + '&bank_code=' + encodeURIComponent(code));
        accName = typeof d === 'string' ? d : (d.account_name || d.name || '');
        out.innerHTML = accName ? '✅ <b>' + esc(accName) + '</b>' : '';
        $('#go', el).disabled = !accName;
      } catch (e) { out.innerHTML = '<span style="color:var(--bad)">' + esc(G.errMsg(e)) + '</span>'; }
    }
    $('#acc', el).oninput = resolve; $('#bank', el).onchange = resolve;
    $('#go', el).onclick = (ev) => G.busy(ev.currentTarget, async () => {
      const amount = Number($('#amt', el).value);
      if (!(amount > 0)) return G.toast('Enter a valid amount');
      if (amount > Number(w.available_balance != null ? w.available_balance : w.balance)) return G.toast('Amount exceeds available balance');
      const pin = await G.askPin('Confirm withdrawal with PIN');
      if (!pin) return;
      const bankSel = $('#bank', el);
      try {
        const r = await G.post('/finance/withdraw/', { amount: String(amount), bank_code: bankSel.value, bank_name: bankSel.options[bankSel.selectedIndex].text, account_number: $('#acc', el).value.trim(), account_name: accName, pin });
        el.innerHTML = '<div class="narrow card center"><div style="font-size:44px">✅</div><h1>Request submitted</h1><p>' + esc(r.message || 'An admin will process it shortly.') + '</p><a class="btn" href="#/wallet">Back to wallet</a></div>';
      } catch (e) { $('#err', el).innerHTML = G.fail(e); }
    });
  }
  G.route('/wallet/withdraw', withdrawPage, { auth: true });

  /* ---------- Data bundles ---------- */
  const NETS = [['mtn-data', 'MTN'], ['glo-data', 'Glo'], ['airtel-data', 'Airtel'], ['9mobile-data', '9mobile']];
  G.route('/data', async (el) => {
    const w = await G.get('/finance/wallet/').catch(() => null);
    let net = NETS[0][0]; let plans = []; let sel = null;
    el.innerHTML = '<div class="narrow"><div class="row between"><h1>Buy data</h1><a href="#/data/history">History</a></div>' +
      (w ? '<div class="card">Wallet balance: <b>' + money(w.available_balance != null ? w.available_balance : w.balance) + '</b> · <a href="#/wallet/deposit">Top up</a></div>' : '') +
      '<div class="chips" id="nets">' + NETS.map((n, i) => '<span class="chip ' + (i ? '' : 'on') + '" data-n="' + n[0] + '">' + n[1] + '</span>').join('') + '</div>' +
      '<div class="card"><label>Phone number</label><input id="ph" inputmode="tel" maxlength="11" placeholder="08012345678">' +
      '<label>Plan</label><div id="plans">' + G.loading + '</div><div id="err"></div>' +
      '<button class="btn block" id="buy" style="margin-top:12px" disabled>Select a plan</button></div></div>';
    async function loadPlans() {
      sel = null; $('#buy', el).disabled = true; $('#buy', el).textContent = 'Select a plan';
      $('#plans', el).innerHTML = G.loading;
      try {
        const d = await G.get('/finance/data/plans/?service_id=' + net + '&page_size=100');
        plans = G.list(d).sort((a, b) => Number(a.variation_amount) - Number(b.variation_amount));
        $('#plans', el).innerHTML = plans.length ? '<select id="plan"><option value="">Choose a plan…</option>' + plans.map((p, i) =>
          '<option value="' + i + '">' + esc(p.name) + ' — ' + money(Math.round(Number(p.variation_amount))) + '</option>').join('') + '</select>' : '<div class="empty">No plans available.</div>';
        const s = $('#plan', el);
        if (s) s.onchange = () => {
          sel = s.value === '' ? null : plans[Number(s.value)];
          $('#buy', el).disabled = !sel;
          $('#buy', el).textContent = sel ? 'Pay ' + money(Math.round(Number(sel.variation_amount))) : 'Select a plan';
        };
      } catch (e) { $('#plans', el).innerHTML = G.fail(e); }
    }
    $('#nets', el).onclick = (e) => {
      const c = e.target.closest('[data-n]'); if (!c) return;
      net = c.dataset.n; $$('.chip', $('#nets', el)).forEach((x) => x.classList.toggle('on', x === c)); loadPlans();
    };
    $('#buy', el).onclick = (ev) => G.busy(ev.currentTarget, async () => {
      const phone = $('#ph', el).value.trim();
      if (!/^\d{11}$/.test(phone)) return G.toast('Enter a valid 11-digit phone number');
      if (!sel) return G.toast('Select a plan');
      const price = Math.round(Number(sel.variation_amount));
      if (w && Number(w.available_balance != null ? w.available_balance : w.balance) < price) return G.toast('Insufficient balance — please top up your wallet');
      if (!(await G.confirm('Buy ' + sel.name + ' for ' + money(price) + ' on ' + phone + '?'))) return;
      $('#err', el).innerHTML = '';
      try {
        const r = await G.post('/finance/data/purchase/', { service_id: net, variation_code: String(sel.variation_code), phone, amount: price });
        el.innerHTML = '<div class="narrow card center"><div style="font-size:44px">✅</div><h1>Request submitted</h1><p>' + esc(r.message || 'Your data purchase is being processed.') + '</p>' +
          '<div class="small mute">' + esc(sel.name) + ' · ' + esc(phone) + (r.order_id ? ' · Ref ' + esc(r.order_id) : '') + '</div><br><a class="btn" href="#/data/history">View history</a></div>';
      } catch (e) { $('#err', el).innerHTML = G.fail(e); }
    });
    loadPlans();
  }, { auth: true });

  G.route('/data/history', async (el) => {
    const items = G.list(await G.get('/finance/data/history/'));
    el.innerHTML = '<a href="#/data">← Buy data</a><h1>Data history</h1><div class="card">' + (items.length ? items.map((t) =>
      '<div class="item"><div class="grow"><b>' + esc(t.service_id || 'Data') + ' ' + esc(t.data_plan || '') + '</b><div class="small mute">' + esc(t.phone || '') + ' · ' + G.date(t.created_at) + '</div></div>' +
      '<div class="right"><b>' + money(Math.abs(Number(t.amount))) + '</b><div><span class="pill ' + (t.status === 'success' ? 'ok' : t.status === 'failed' ? 'bad' : 'warn') + '">' + esc(t.status) + '</span></div></div></div>').join('')
      : '<div class="empty">No data purchases yet.</div>') + '</div>';
  }, { auth: true });

  G.withdrawPage = withdrawPage;
})();
