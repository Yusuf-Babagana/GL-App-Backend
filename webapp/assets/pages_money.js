/* GLAPP web client — money: wallet, deposit, withdraw, history, data bundles. Layouts follow the mobile screens. */
(function () {
  'use strict';
  const G = window.GL;
  const { esc, money, $, $$ } = G;
  const t = (...a) => G.t(...a);
  const N = (v) => Number(v || 0).toLocaleString();
  const avail = (w) => Number(w && (w.available_balance != null ? w.available_balance : w.balance) || 0);

  const txRow = (x) => {
    const amt = Number(x.amount); const inc = amt >= 0;
    return '<div class="tx"><div class="ti ' + (inc ? 'in' : 'out') + '">' + G.icon(inc ? 'down' : 'up') + '</div><div class="grow"><div class="name" style="font-size:14px">' +
      esc(x.description || (inc ? t('deposit') : t('withdrawal'))) + '</div><div class="small mute" style="font-size:10px;font-weight:500">' + new Date(x.created_at).toLocaleDateString() + ' • ' + esc(x.status || t('success_status')) + '</div></div>' +
      '<b style="font-size:16px;font-weight:900;color:' + (inc ? '#16A34A' : 'var(--ink)') + '">' + (inc ? '+' : '-') + '₦' + N(Math.abs(amt)) + '</b></div>';
  };

  /* First-time wallet setup (components/WalletOnboarding.tsx): BVN then PIN. */
  function setup(el, w, redraw) {
    const need = !w.user_has_bvn ? 'bvn' : (!w.user_has_pin ? 'pin' : null);
    if (!need) return false;
    el.innerHTML = G.head(t('gl_wallet'), '#/more') + '<div class="card">' +
      (need === 'bvn' ? '<div class="authbox">' + G.icon('shield') + '</div><h2 class="center">Verify your BVN</h2><p class="mute center small">Required to generate your dedicated funding account.</p><input id="bvn" inputmode="numeric" maxlength="11" placeholder="11-digit BVN"><button class="btn lg block" id="go" style="margin-top:16px">Continue</button>'
        : '<div class="authbox">' + G.icon('lock') + '</div><h2 class="center">Create transaction PIN</h2><p class="mute center small">A 4-digit PIN protects payments and withdrawals.</p><input id="npin" type="password" inputmode="numeric" maxlength="4" placeholder="••••" style="text-align:center;letter-spacing:8px;font-size:20px"><button class="btn lg block" id="go" style="margin-top:16px">Set PIN</button>') +
      '<div id="err" style="margin-top:12px"></div></div>';
    $('#go', el).onclick = (e) => G.busy(e.currentTarget, async () => {
      try {
        if (need === 'bvn') { const v = $('#bvn', el).value.trim(); if (!/^\d{11}$/.test(v)) return G.toast('BVN must be 11 digits'); await G.post('/users/update-bvn/', { bvn: v }); }
        else { const v = $('#npin', el).value.trim(); if (!/^\d{4}$/.test(v)) return G.toast(t('invalid_pin_msg')); await G.post('/finance/pin/', { pin: v }); }
        redraw();
      } catch (er) { $('#err', el).innerHTML = G.fail(er); }
    });
    return true;
  }

  /* ---------- Wallet (wallet/index.tsx) ---------- */
  G.route('/wallet', async (el) => {
    let show = true;
    async function draw() {
      const [w, tx] = await Promise.all([G.get('/finance/wallet/'), G.get('/finance/transactions/').catch(() => ({ results: [] }))]);
      if (setup(el, w, draw)) return;
      const recent = G.list(tx).slice(0, 8);
      const acct = (w.funding_accounts && w.funding_accounts[0]) || null;
      el.innerHTML = '<div class="ph">' + G.back('#/more') + '<h1 class="center" style="font-size:18px">' + esc(t('gl_wallet')) + '</h1><button class="back" id="rf" aria-label="Refresh">' + G.icon('sync', 18) + '</button></div>' +
        '<div class="hero"><div class="row between" style="margin-bottom:20px"><span class="pl"><i></i>' + esc(t('active_wallet')) + '</span><button class="eye" id="eye" style="background:none;border:0;color:rgba(20,83,45,.6);cursor:pointer">' + G.icon(show ? 'eyeoff' : 'eye', 20) + '</button></div>' +
        '<div class="cells" style="margin:0 0 20px"><div class="cell"><small>' + esc(t('withdrawable_balance')) + '</small><b>' + (show ? '₦' + N(w.available_balance) : '••••••') + '</b></div>' +
        '<div class="cell"><small>' + esc(t('in_transit_balance')) + '</small><b>' + (show ? '₦' + N(w.locked_balance) : '••••••') + '</b><small style="font-size:8px;opacity:.8">' + esc(t('pending_settlement')) + '</small></div></div>' +
        '<small style="display:block;font-size:9px;font-weight:800;text-transform:uppercase;color:rgba(20,83,45,.5)">' + esc(t('currency')) + '</small><b style="font-size:14px">' + esc(t('ngn_naira')) + '</b></div>' +
        '<div class="actions3"><a href="#/wallet/deposit"><div class="ib g">' + G.icon('plus') + '</div>' + esc(t('top_up')) + '</a><a href="#/wallet/withdraw"><div class="ib">' + G.icon('bank') + '</div>' + esc(t('withdraw')) + '</a><a href="#/wallet/history"><div class="ib">' + G.icon('history') + '</div>' + esc(t('history')) + '</a></div>' +
        '<div class="card" style="border-radius:35px;padding:24px"><div class="center" style="font-size:14px;font-weight:900;text-transform:uppercase;letter-spacing:.1em;margin-bottom:16px">' + esc(t('your_funding_account')) + '</div>' +
        (acct ? '<div class="acct"><div class="bn">' + esc(acct.bank_name) + '</div><div style="margin:4px 0"><span class="no">' + esc(acct.account_number) + '</span><button class="copy" data-copy="' + esc(acct.account_number) + '" aria-label="Copy">' + G.icon('copy') + '</button></div>' +
          '<div class="small mute" style="font-size:10px">' + esc(t('funds_arrive_instantly')) + '</div><div class="alert" style="margin:16px 0 0;font-size:10px;text-align:center;padding:10px;border-radius:16px">' + esc(t('service_fee')) + '</div></div>'
          : '<div class="acct mute">Generating your account…<br><span class="small">Pull to refresh in a moment.</span></div>') + '</div>' +
        '<div class="row between" style="margin:8px 0 14px"><h2 style="margin:0">' + esc(t('recent_activity')) + '</h2><a class="link small" href="#/wallet/history">' + esc(t('see_all')) + '</a></div>' +
        (recent.length ? recent.map(txRow).join('') : '<div class="empty" style="background:#F9FAFB;border:1px dashed #E5E7EB;border-radius:40px;padding:40px"><div class="eb" style="background:#fff;width:64px;height:64px;border-radius:50%">' + G.icon('history', 28) + '</div><div style="color:#6B7280">' + esc(t('no_recent_activity')) + '</div><div class="small">' + esc(t('transactions_here')) + '</div></div>');
      $('#eye', el).onclick = () => { show = !show; draw(); };
      $('#rf', el).onclick = () => draw();
      el.onclick = (ev) => { const c = ev.target.closest('[data-copy]'); if (c) { try { navigator.clipboard.writeText(c.dataset.copy).then(() => G.toast(t('copied_clipboard'))); } catch (e) { G.toast(c.dataset.copy); } } };
    }
    await draw();
  }, { auth: true });

  G.route('/wallet/deposit', async (el) => {
    const w = await G.get('/finance/wallet/');
    const accts = w.funding_accounts || [];
    el.innerHTML = G.head(t('top_up'), '#/wallet') + '<div class="card"><p style="margin-top:0">' + esc(t('funds_arrive_instantly')) + '</p>' +
      (accts.length ? accts.map((a) => '<div class="acct"><div class="bn">' + esc(a.bank_name) + '</div><div style="margin:4px 0"><span class="no">' + esc(a.account_number) + '</span><button class="copy" data-copy="' + esc(a.account_number) + '" aria-label="Copy">' + G.icon('copy') + '</button></div><div class="small mute">' + esc(a.account_name) + '</div></div>').join('')
        : '<div class="alert">' + (w.user_has_bvn ? 'Your account is still being generated. Check back in a moment.' : 'Add your BVN on the <a href="#/wallet">wallet page</a> to generate your funding account.') + '</div>') +
      '<div class="alert" style="margin:16px 0 0;font-size:11px;text-align:center">' + esc(t('service_fee')) + '</div></div>';
    el.onclick = (ev) => { const c = ev.target.closest('[data-copy]'); if (c) { try { navigator.clipboard.writeText(c.dataset.copy).then(() => G.toast(t('copied_clipboard'))); } catch (e) { G.toast(c.dataset.copy); } } };
  }, { auth: true });

  /* ---------- History (wallet/history.tsx) ---------- */
  G.route('/wallet/history', async (el, ctx) => {
    const type = ctx.query.type || '';
    const types = ['', 'deposit', 'payment', 'withdrawal', 'bill_payment', 'escrow_release', 'refund', 'promotion'];
    el.innerHTML = G.head(t('history'), '#/wallet') + '<div class="chips">' + types.map((x) => '<a class="chip ' + (x === type ? 'on' : '') + '" href="#/wallet/history' + (x ? '?type=' + x : '') + '">' + (x ? esc(G.pretty(x)) : 'All') + '</a>').join('') + '</div><div id="list">' + G.loading + '</div><div class="center" id="m"></div>';
    let page = 1;
    async function load() {
      const d = await G.get('/finance/transactions/?page=' + page);
      let items = G.list(d); if (type) items = items.filter((x) => x.transaction_type === type);
      if (page === 1) $('#list', el).innerHTML = '';
      if (page === 1 && !items.length) $('#list', el).innerHTML = G.emptyState('history', t('no_recent_activity'), t('transactions_here'));
      $('#list', el).insertAdjacentHTML('beforeend', items.map(txRow).join(''));
      $('#m', el).innerHTML = d && d.next ? '<button class="btn ghost sm" id="mb">Load more</button>' : '';
      const b = $('#mb', el); if (b) b.onclick = () => G.busy(b, async () => { page += 1; await load(); });
    }
    await load();
  }, { auth: true });

  /* ---------- Withdraw (wallet/withdraw.tsx) ---------- */
  async function withdrawPage(el) {
    const [w, banksRaw] = await Promise.all([G.get('/finance/wallet/'), G.get('/finance/banks/').catch(() => [])]);
    const banks = G.list(banksRaw).slice().sort((a, b) => a.name.localeCompare(b.name));
    el.innerHTML = G.head(t('withdraw'), '#/wallet') + '<div class="card" style="background:var(--primary-container);border:0"><div class="small" style="font-weight:700;color:var(--primary-dark)">' + esc(t('withdrawable_balance')) + '</div><div class="price" style="font-size:26px;color:var(--primary-dark)">' + money(avail(w)) + '</div></div>' +
      (!w.user_has_pin ? '<div class="alert">Set a transaction PIN first on the <a href="#/security">security page</a>.</div>' : '') +
      '<div class="card"><label style="margin-top:0">Amount (₦)</label><input id="amt" type="number" min="1" inputmode="decimal" placeholder="0.00">' +
      '<label>Bank</label><select id="bank"><option value="">Select bank…</option>' + banks.map((b) => '<option value="' + esc(b.code) + '">' + esc(b.name) + '</option>').join('') + '</select>' +
      '<label>Account number</label><input id="acc" inputmode="numeric" maxlength="10" placeholder="0123456789"><div id="resolved" class="small" style="margin-top:8px;font-weight:700"></div><div id="err"></div>' +
      '<button class="btn lg block" id="go" style="margin-top:16px" disabled>' + esc(t('withdraw')) + '</button></div>';
    let accName = '';
    async function resolve() {
      accName = ''; $('#go', el).disabled = true;
      const acc = $('#acc', el).value.trim(); const code = $('#bank', el).value; const out = $('#resolved', el);
      if (acc.length !== 10 || !code) { out.textContent = ''; return; }
      out.innerHTML = '<span class="spin"></span> Verifying account…';
      try {
        const d = await G.get('/finance/verify-bank/?account_number=' + encodeURIComponent(acc) + '&bank_code=' + encodeURIComponent(code));
        accName = typeof d === 'string' ? d : (d.account_name || d.name || '');
        out.innerHTML = accName ? '<span style="color:var(--primary)">✓ ' + esc(accName) + '</span>' : '';
        $('#go', el).disabled = !accName;
      } catch (e) { out.innerHTML = '<span style="color:var(--error)">' + esc(G.errMsg(e)) + '</span>'; }
    }
    $('#acc', el).oninput = resolve; $('#bank', el).onchange = resolve;
    $('#go', el).onclick = (ev) => G.busy(ev.currentTarget, async () => {
      const amount = Number($('#amt', el).value);
      if (!(amount > 0)) return G.toast('Enter a valid amount');
      if (amount > avail(w)) return G.toast('Amount exceeds available balance');
      const pin = await G.askPin('Confirm withdrawal with PIN'); if (!pin) return;
      const bs = $('#bank', el);
      try {
        const r = await G.post('/finance/withdraw/', { amount: String(amount), bank_code: bs.value, bank_name: bs.options[bs.selectedIndex].text, account_number: $('#acc', el).value.trim(), account_name: accName, pin });
        el.innerHTML = '<div class="card center" style="margin-top:40px"><div class="authbox">' + G.icon('bank') + '</div><h1>Request submitted</h1><p class="mute">' + esc(r.message || 'An admin will process it shortly.') + '</p><a class="btn lg block" href="#/wallet">' + esc(t('gl_wallet')) + '</a></div>';
      } catch (e) { $('#err', el).innerHTML = G.fail(e); }
    });
  }
  G.route('/wallet/withdraw', withdrawPage, { auth: true });
  G.withdrawPage = withdrawPage;

  /* ---------- Data (finance/buy-data.tsx) ---------- */
  const NETS = [['mtn-data', 'MTN', '#FFCC00'], ['glo-data', 'Glo', '#008444'], ['airtel-data', 'Airtel', '#FF0000'], ['9mobile-data', '9mobile', '#006139']];
  function groupPlans(plans) {
    const groups = [];
    plans.forEach((p) => {
      const n = String(p.name || '').toUpperCase(); let ty = 'Direct/Gifting';
      if (n.includes('SME')) ty = 'SME'; else if (n.includes('AWOOF') || n.includes('PROMO')) ty = 'Awoof'; else if (n.includes('CG') || n.includes('CORPORATE')) ty = 'Corporate';
      let g = groups.find((x) => x.title === ty); if (!g) { g = { title: ty, data: [] }; groups.push(g); } g.data.push(p);
    });
    return groups.sort((a) => (a.title === 'SME' ? -1 : 1));
  }
  G.route('/data', async (el) => {
    if (!G.loggedIn()) { el.innerHTML = G.head('Purchase Data') + G.emptyState('wifi', t('login_required'), t('login_cart_msg'), '<a class="btn lg" href="#/login">' + esc(t('login')) + '</a>'); return; }
    const w = await G.get('/finance/wallet/').catch(() => null); const bal = avail(w);
    let net = NETS[0][0]; let groups = []; let sel = null; let type = '';
    el.innerHTML = '<div class="topbar"><img src="/app/assets/logo.jpeg" alt=""><b>Purchase Data</b><span class="bal">₦' + N(bal) + '</span></div>' +
      '<div class="nets" id="nets">' + NETS.map((n, i) => '<button data-n="' + n[0] + '" class="' + (i ? '' : 'on') + '"><span class="c" style="background:' + n[2] + '">' + G.icon('phone') + '</span>' + n[1] + '</button>').join('') + '</div>' +
      '<label style="margin-top:0;text-transform:none;letter-spacing:0;font-size:12px">Phone Number:</label><input id="ph" inputmode="numeric" maxlength="11" placeholder="08012345678">' +
      '<label style="text-transform:none;letter-spacing:0;font-size:12px">Data Type:</label><select id="ty" disabled><option value="">Loading plans...</option></select>' +
      '<label style="text-transform:none;letter-spacing:0;font-size:12px">Plan Type:</label><select id="pl" disabled><option value="">Select a plan</option></select>' +
      '<label style="text-transform:none;letter-spacing:0;font-size:12px">Amount:</label><div class="flat" style="padding:16px;border:1px solid #E5E7EB;border-radius:12px;font-weight:900;font-size:18px" id="amt">₦0.0</div>' +
      '<div id="warn"></div><div id="err"></div><button class="btn lg block" id="buy" disabled>Purchase</button>' +
      '<div class="center" style="margin-top:24px"><a class="link small" href="#/data/history">View Receipt History</a></div>';
    const price = () => (sel ? Math.round(Number(sel.variation_amount)) : 0);
    function refresh() {
      const ph = $('#ph', el).value.trim(); const p = price();
      $('#amt', el).textContent = '₦' + (p ? N(p) : '0.0');
      let warn = '';
      if (sel && p > bal) warn = '<div class="alert bad">Insufficient wallet balance for this plan. Top up your wallet to continue.</div>';
      else if (sel && ph.length > 0 && ph.length !== 11) warn = '<div class="alert">Enter a valid 11-digit phone number to continue.</div>';
      $('#warn', el).innerHTML = warn;
      $('#buy', el).disabled = !(sel && ph.length === 11 && p <= bal);
    }
    async function loadPlans() {
      sel = null; type = ''; groups = [];
      $('#ty', el).disabled = true; $('#ty', el).innerHTML = '<option value="">Loading plans...</option>'; $('#pl', el).disabled = true; $('#pl', el).innerHTML = '<option value="">Select a plan</option>'; refresh();
      try {
        const d = await G.get('/finance/data/plans/?service_id=' + net + '&page_size=100');
        groups = groupPlans(G.list(d));
        $('#ty', el).innerHTML = '<option value="">Select data type</option>' + groups.map((g) => '<option>' + esc(g.title) + '</option>').join('');
        $('#ty', el).disabled = !groups.length;
      } catch (e) { $('#ty', el).innerHTML = '<option value="">Could not load plans</option>'; }
    }
    $('#nets', el).onclick = (e) => { const c = e.target.closest('[data-n]'); if (!c) return; net = c.dataset.n; $$('button', $('#nets', el)).forEach((x) => x.classList.toggle('on', x === c)); loadPlans(); };
    $('#ty', el).onchange = (e) => {
      type = e.target.value; sel = null; const g = groups.find((x) => x.title === type);
      $('#pl', el).disabled = !g;
      $('#pl', el).innerHTML = '<option value="">Select a plan</option>' + (g ? g.data.map((p) => '<option value="' + esc(String(p.variation_code)) + '">' + esc(String(p.name).split('(')[0].trim()) + ' — ₦' + N(Math.round(Number(p.variation_amount))) + '</option>').join('') : '');
      refresh();
    };
    $('#pl', el).onchange = (e) => { const g = groups.find((x) => x.title === type); sel = g ? g.data.find((p) => String(p.variation_code) === e.target.value) || null : null; refresh(); };
    $('#ph', el).oninput = (e) => { e.target.value = e.target.value.replace(/\D/g, ''); refresh(); };
    $('#buy', el).onclick = (ev) => G.busy(ev.currentTarget, async () => {
      const phone = $('#ph', el).value.trim(); const p = price();
      if (!(await G.confirm('Buy ' + sel.name + ' for ' + money(p) + ' on ' + phone + '?'))) return;
      $('#err', el).innerHTML = '';
      try {
        const r = await G.post('/finance/data/purchase/', { service_id: net, variation_code: String(sel.variation_code), phone, amount: p });
        el.innerHTML = '<div class="card center" style="margin-top:40px"><div class="authbox">' + G.icon('wifi') + '</div><h1>Request submitted</h1><p class="mute">' + esc(r.message || 'Your data purchase is being processed.') + '</p>' +
          '<div class="flat small" style="text-align:left"><div class="sumrow"><span class="mute">Network</span><b>' + esc((NETS.find((n) => n[0] === net) || [])[1]) + '</b></div><div class="sumrow"><span class="mute">Plan</span><b>' + esc(sel.name) + '</b></div><div class="sumrow"><span class="mute">Phone</span><b>' + esc(phone) + '</b></div><div class="sumrow"><span class="mute">Amount</span><b>' + money(p) + '</b></div>' + (r.order_id ? '<div class="sumrow"><span class="mute">Ref</span><b>' + esc(r.order_id) + '</b></div>' : '') + '</div>' +
          '<a class="btn lg block" href="#/data/history">View Receipt History</a></div>';
      } catch (e) { $('#err', el).innerHTML = G.fail(e); }
    });
    loadPlans();
  }, { auth: true });

  G.route('/data/history', async (el) => {
    const items = G.list(await G.get('/finance/data/history/'));
    el.innerHTML = G.head('Receipt History', '#/data') + (items.length ? items.map((x) =>
      '<div class="tx"><div class="ti out">' + G.icon('wifi') + '</div><div class="grow"><div class="name" style="font-size:14px">' + esc(x.service_id || 'Data') + ' ' + esc(x.data_plan || '') + '</div><div class="small mute" style="font-size:11px;font-weight:500">' + esc(x.phone || '') + ' · ' + G.date(x.created_at) + '</div></div>' +
      '<div class="right"><b>₦' + N(Math.abs(Number(x.amount))) + '</b><div><span class="pill ' + (x.status === 'success' ? 'ok' : x.status === 'failed' ? 'bad' : 'warn') + '">' + esc(x.status) + '</span></div></div></div>').join('')
      : G.emptyState('wifi', 'No data purchases yet', ''));
  }, { auth: true });
})();
