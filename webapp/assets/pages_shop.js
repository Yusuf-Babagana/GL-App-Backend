/* GLAPP web client — marketplace: home, product, markets, live, cart, checkout, orders. Layouts follow the mobile screens. */
(function () {
  'use strict';
  const G = window.GL;
  const { esc, money, $, $$, t } = { esc: G.esc, money: G.money, $: G.$, $$: G.$$, t: (...a) => G.t(...a) };
  const N = (v) => Number(v || 0).toLocaleString();

  /* ---------- Promotion banner (carousel, autoplay 4.5s) ---------- */
  function timeLeft(sec) {
    if (sec == null || sec <= 0) return '';
    const h = Math.floor(sec / 3600);
    if (h >= 24) return Math.floor(h / 24) + 'd left';
    if (h >= 1) return h + 'h left';
    return Math.max(1, Math.floor(sec / 60)) + 'm left';
  }
  function promoBanner(el, posts) {
    if (!posts.length) {
      el.innerHTML = '<a class="promo empty" href="#/promote"><div class="sp">' + G.icon('megaphone', 22) + '</div><b>' + esc(t('promote_cta')) + '</b><span>' + esc(t('discover_deals')) + '</span></a>';
      return;
    }
    el.innerHTML = '<a class="promo" id="pb" href="#/promotion/' + esc(posts[0].code) + '">' + posts.map((p, i) =>
      '<div class="slide ' + (i ? '' : 'on') + '" style="' + (p.image ? 'background-image:url(\'' + esc(p.image) + '\')' : '') + '"><div class="by">' + esc(p.seller_name || 'Globalink') + '</div><div class="tx">' + esc(p.text_content || p.title || '') + '</div></div>').join('') +
      '<div class="left" id="pbl">' + esc(timeLeft(posts[0].time_remaining_seconds)) + '</div>' +
      (posts.length > 1 ? '<div class="dots">' + posts.map((p, i) => '<i class="' + (i ? '' : 'on') + '"></i>').join('') + '</div>' : '') + '</a>';
    if (posts.length < 2) return;
    let idx = 0; const a = $('#pb', el);
    const timer = setInterval(() => {
      if (!document.body.contains(a)) { clearInterval(timer); return; }
      idx = (idx + 1) % posts.length;
      $$('.slide', a).forEach((s, i) => s.classList.toggle('on', i === idx));
      $$('.dots i', a).forEach((d, i) => d.classList.toggle('on', i === idx));
      a.href = '#/promotion/' + posts[idx].code;
      $('#pbl', a).textContent = timeLeft(posts[idx].time_remaining_seconds);
    }, 4500);
    G.onLeave(() => clearInterval(timer));
  }

  function kycBanner() {
    if (G.user && G.user.kyc_status === 'pending') {
      return '<a class="kyc" href="#/kyc"><div class="ib">' + G.icon('clock', 18) + '</div><div><b>KYC Under Review</b><span>Your documents are being reviewed</span></div></a>';
    }
    return '';
  }
  G.kycBanner = kycBanner;

  /* ---------- Home (tabs/index.tsx) ---------- */
  G.route('/', async (el, ctx) => {
    const q = ctx.query.q || '';
    el.innerHTML = '<div class="search">' + G.icon('search') + '<input id="q" placeholder="' + esc(t('search_products')) + '" value="' + esc(q) + '" autocomplete="off"></div>' +
      '<div style="margin:12px 0 0"><div id="promo"></div>' +
      (G.loggedIn() ? '<a class="cta" href="#/promote">' + G.icon('megaphone') + (G.hasRole('seller') && G.user && G.user.active_role === 'seller' ? 'Promote Your Product' : 'Advertise Something to Sell') + '</a>' : '') + '</div>' +
      kycBanner() + '<div class="grid" id="grid"><div class="skel"></div><div class="skel"></div><div class="skel"></div><div class="skel"></div></div><div class="center" id="more" style="margin:16px"></div>';
    G.bindProductActions(el);
    G.get('/market/promoted-posts/active/', { noAuth: true }).then((d) => promoBanner($('#promo', el), G.list(d))).catch(() => promoBanner($('#promo', el), []));

    const grid = $('#grid', el);
    let page = 1; let term = q; let seq = 0;
    async function load(reset) {
      const my = ++seq;
      if (reset) { page = 1; }
      const p = new URLSearchParams({ page });
      if (term) p.set('search', term);
      let d;
      try { d = await G.get('/market/products/?' + p.toString(), { noAuth: !G.loggedIn() }); }
      catch (e) { if (my === seq) grid.outerHTML = '<div class="empty" id="grid"><div class="eb">' + G.icon('image') + '</div><h3>Couldn\'t load products</h3><p>Check your connection and try again.</p><button class="btn" id="retry">Retry</button></div>'; const r = $('#retry', el); if (r) r.onclick = () => G.go('#/?r=' + Date.now()); return; }
      if (my !== seq) return;
      const items = G.list(d).filter((x) => !x.video_ad_url);
      if (page === 1) grid.innerHTML = '';
      if (page === 1 && !items.length) grid.innerHTML = '<div style="grid-column:1/-1">' + G.emptyState('bag', t('no_products'), t('check_later')) + '</div>';
      grid.insertAdjacentHTML('beforeend', items.map(G.productCard).join(''));
      $('#more', el).innerHTML = d && d.next ? '<button class="btn ghost sm" id="lm">Load more</button>' : '';
      const lm = $('#lm', el);
      if (lm) lm.onclick = () => G.busy(lm, async () => { page += 1; await load(false); });
    }
    let timer;
    $('#q', el).oninput = (e) => { clearTimeout(timer); timer = setTimeout(() => { term = e.target.value.trim(); load(true); }, 350); };
    await load(true);
  });

  /* ---------- Product detail (product/[id].tsx) ---------- */
  G.route('/product/:id', async (el, ctx) => {
    const p = await G.get('/market/products/' + ctx.params.id + '/', { noAuth: !G.loggedIn() });
    let imgs = (p.images || []).map((i) => (typeof i === 'string' ? i : i.image)).filter(Boolean);
    if (!imgs.length && p.image) imgs = [p.image];
    const video = p.video_url || p.video_ad_url;
    const own = G.user && p.seller_id === G.user.id;
    let qty = 1;
    el.innerHTML = '<div class="pdp"><div class="backabs">' + G.back() + '</div>' +
      '<div class="gallery">' + (imgs.length ? '<img class="main" id="main" src="' + esc(imgs[0]) + '" alt="">' : '<div class="noimg main" style="height:384px">' + G.icon('image', 40) + '</div>') +
      (imgs.length > 1 ? '<div class="thumbs" style="padding:8px 20px 0">' + imgs.map((u, i) => '<img src="' + esc(u) + '" class="' + (i ? '' : 'on') + '" alt="">').join('') + '</div>' : '') + '</div>' +
      '<div class="info"><div class="row between" style="margin-bottom:6px"><span class="row" style="gap:8px;color:#6B7280;font-weight:500">' + G.icon('store', 16) + esc((p.shop && p.shop.name) || p.shop_name || t('official_store')) + '</span>' +
      (!own && p.seller_id ? '<button class="pill" id="chat" style="background:#EFF6FF;color:#2563EB;border:0;cursor:pointer;padding:6px 12px;font-size:12px;text-transform:none">' + G.icon('chat', 14) + ' ' + esc(t('chat')) + '</button>' : '') + '</div>' +
      '<div class="small mute" style="margin-bottom:8px">' + G.icon('pin', 12) + ' ' + esc(t('ships_from')) + ' ' + esc(t('nigeria')) + '</div>' +
      '<div style="font-size:30px;font-weight:700;line-height:1.2;margin-bottom:8px">' + esc(p.name) + '</div>' +
      '<div style="color:#1DB954;font-size:24px;font-weight:700;margin-bottom:20px">' + money(p.price) + '</div><div style="height:1px;background:#F3F4F6;margin-bottom:20px"></div>' +
      (video ? '<h3 style="font-size:18px;margin-bottom:10px">' + esc(t('product_video')) + '</h3><video controls preload="metadata" playsinline src="' + esc(video) + '" style="margin-bottom:20px"></video>' : '') +
      '<h3 style="font-size:18px">' + esc(t('description')) + '</h3><div class="mute" style="line-height:1.6;font-size:16px;white-space:pre-wrap">' + esc(p.description || '') + '</div></div>' +
      '<div class="bar"><div class="row" style="gap:16px;flex-wrap:nowrap"><div class="stepper"><button id="dec">−</button><span id="qv">1</span><button id="inc">+</button></div>' +
      '<button class="btn grow" id="add"' + (p.stock < 1 || own ? ' disabled' : '') + '>' + G.icon('bag', 20) + esc(t('add_to_cart')) + '</button></div></div></div>';
    $$('.thumbs img', el).forEach((th) => { th.onclick = () => { $('#main', el).src = th.src; $$('.thumbs img', el).forEach((x) => x.classList.remove('on')); th.classList.add('on'); }; });
    $('#dec', el).onclick = () => { qty = Math.max(1, qty - 1); $('#qv', el).textContent = qty; };
    $('#inc', el).onclick = () => { qty += 1; $('#qv', el).textContent = qty; };
    $('#add', el).onclick = (e) => {
      if (!G.loggedIn()) { if (confirm(t('login_cart_msg'))) G.requireLogin(); return; }
      G.busy(e.currentTarget, async () => {
        try { await G.post('/market/cart/', { product_id: p.id, quantity: qty }); await G.refreshCart(); G.toast(t('add_cart_success', '', { name: p.name })); }
        catch (er) { G.toast(t('add_cart_failed')); }
      });
    };
    const chat = $('#chat', el);
    if (chat) chat.onclick = () => { if (!G.loggedIn()) { if (confirm(t('login_cart_msg'))) G.requireLogin(); return; } G.go('#/chat/with/' + p.seller_id + '?product=' + p.id); };
  });

  /* ---------- Markets (tabs/markets.tsx) ---------- */
  const logoFor = (s) => (s.logo && s.logo !== 'null' && s.logo !== 'undefined') ? s.logo : 'https://ui-avatars.com/api/?name=' + encodeURIComponent(s.name) + '&background=random';
  G.route('/markets', async (el) => {
    el.innerHTML = '<div class="gradhead"><span class="tag">Directory</span><div class="row between" style="flex-wrap:nowrap"><h1>Verified<br>Markets</h1><div class="ibox">' + G.icon('store', 24) + '</div></div></div><div class="grid" id="stores"><div class="skel"></div><div class="skel"></div></div>';
    const stores = G.list(await G.get('/market/stores/', { noAuth: !G.loggedIn() }));
    $('#stores', el).innerHTML = stores.length ? stores.map((s) =>
      '<a class="card center" href="#/markets/' + esc(s.id) + '" style="padding:16px;margin:0;color:inherit"><div style="width:80px;height:80px;border-radius:16px;overflow:hidden;background:#F8FAFC;border:1px solid #F1F5F9;margin:0 auto 12px"><img src="' + esc(logoFor(s)) + '" alt="" style="width:100%;height:100%;object-fit:cover"></div>' +
      '<div class="name" style="font-size:16px;text-align:center">' + esc(s.name) + '</div><div class="mute small" style="margin:2px 0 12px;font-weight:500">' + (s.product_count || 0) + ' Products</div>' +
      '<div style="background:#F8FAFC;border-radius:20px;padding:6px;color:var(--primary);font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase">View Store</div></a>').join('')
      : '<div style="grid-column:1/-1">' + G.emptyState('store', 'No Stores Found', 'There are no verification merchants available right now.') + '</div>';
  });
  G.route('/markets/:id', async (el, ctx) => {
    const [s, prods] = await Promise.all([
      G.get('/market/stores/' + ctx.params.id + '/', { noAuth: !G.loggedIn() }),
      G.get('/market/products/?shop=' + encodeURIComponent(ctx.params.id), { noAuth: !G.loggedIn() }),
    ]);
    const items = G.list(prods);
    el.innerHTML = G.head(s.name, '#/markets') + '<div class="card row" style="flex-wrap:nowrap"><img src="' + esc(logoFor(s)) + '" style="width:72px;height:72px;border-radius:16px;object-fit:cover" alt="">' +
      '<div class="grow"><div class="mute" style="font-weight:500">' + esc(s.description || '') + '</div><div class="small mute">by ' + esc(s.owner_name || '') + '</div></div></div>' +
      (s.owner_id && !(G.user && G.user.id === s.owner_id) ? '<button class="btn sec block" id="msg" style="margin-bottom:14px">' + G.icon('chat', 16) + ' ' + esc(t('contact_seller')) + '</button>' : '') +
      '<div class="grid">' + (items.length ? items.map(G.productCard).join('') : '<div style="grid-column:1/-1">' + G.emptyState('bag', t('no_products')) + '</div>') + '</div>';
    G.bindProductActions(el);
    const m = $('#msg', el);
    if (m) m.onclick = () => { if (!G.loggedIn()) return G.requireLogin(); G.go('#/chat/with/' + s.owner_id); };
  });

  /* ---------- Ads / Live (tabs/live.tsx) ---------- */
  G.route('/live', async (el) => {
    el.innerHTML = G.head(t('ads')) + '<div id="vids">' + G.loading + '</div><div class="center" id="vm" style="margin:12px"></div>';
    let page = 1;
    async function load() {
      const d = await G.get('/market/video-ads/?page=' + page, { noAuth: !G.loggedIn() });
      const items = G.list(d).filter((p) => p.video_ad_url || p.video_url);
      if (page === 1) $('#vids', el).innerHTML = '';
      if (page === 1 && !items.length) $('#vids', el).innerHTML = G.emptyState('play', 'No videos yet', 'Video ads from sellers will appear here.');
      $('#vids', el).insertAdjacentHTML('beforeend', items.map((p) =>
        '<div class="card" style="padding:12px"><video controls preload="none" playsinline src="' + esc(p.video_ad_url || p.video_url) + '"></video>' +
        '<div class="row between" style="margin-top:10px;flex-wrap:nowrap"><div class="grow"><a class="name" href="#/product/' + p.id + '">' + esc(p.name) + '</a><div class="price">' + money(p.price) + '</div>' +
        '<div class="small mute">' + esc(p.shop_name || '') + '</div></div><a class="btn sm" href="#/product/' + p.id + '">View</a></div></div>').join(''));
      $('#vm', el).innerHTML = d && d.next ? '<button class="btn ghost sm" id="vmb">Load more</button>' : '';
      const b = $('#vmb', el); if (b) b.onclick = () => G.busy(b, async () => { page += 1; await load(); });
    }
    await load();
  });

  /* ---------- Cart (tabs/cart.tsx) ---------- */
  G.route('/cart', async (el) => {
    if (!G.loggedIn()) { el.innerHTML = G.head(t('my_cart')) + G.emptyState('bag', t('login_required'), t('login_cart_msg'), '<a class="btn lg" href="#/login">' + esc(t('login')) + '</a>'); return; }
    async function draw() {
      const c = await G.get('/market/cart/');
      const items = c.items || [];
      G.cartCount = items.reduce((s, i) => s + i.quantity, 0); G.paintBadge();
      const head = '<h1 style="margin-bottom:2px">' + esc(t('my_cart')) + '</h1><div class="sub" style="margin-top:0;margin-bottom:16px">' + items.length + ' ' + esc(items.length === 1 ? t('item') : t('items')) + '</div>';
      if (!items.length) { el.innerHTML = head + G.emptyState('bag', t('cart_empty'), t('cart_empty_desc'), '<a class="btn lg block" href="#/">' + esc(t('start_shopping')) + '</a>'); return; }
      el.innerHTML = head + '<div class="card" style="border-radius:16px;padding:16px 20px 20px"><div class="sumrow"><span class="mute" style="font-weight:500">' + esc(t('subtotal')) + '</span><b>' + money(c.total_price) + '</b></div>' +
        '<div class="sumrow"><span class="mute" style="font-weight:500">' + esc(t('delivery')) + '</span><b style="color:#16A34A">' + esc(t('free')) + '</b></div><div style="height:1px;background:#F3F4F6;margin:12px 0"></div>' +
        '<div class="sumrow" style="align-items:center;margin-bottom:16px"><b style="font-size:16px;font-weight:900">' + esc(t('total')) + '</b><b class="price" style="font-size:20px">' + money(c.total_price) + '</b></div>' +
        '<a class="btn lg block" href="#/checkout">' + esc(t('proceed_checkout')) + G.icon('arrowr', 20) + '</a></div>' +
        items.map((i) => '<div class="cartitem">' + G.img(i.product_image) + '<div class="grow" style="display:flex;flex-direction:column;justify-content:space-between"><div><div class="name" style="font-size:16px">' + esc(i.product_name) + '</div>' +
          '<div class="small mute" style="margin-top:4px;font-weight:500">' + esc(t('qty')) + ': ' + i.quantity + '</div></div>' +
          '<div class="row between" style="flex-wrap:nowrap"><span class="price" style="font-size:18px">' + money(Number(i.product_price) * i.quantity) + '</span><span class="row" style="gap:8px;flex-wrap:nowrap">' +
          '<a class="iconbtn" href="#/product/' + i.product + '" style="background:#EFF6FF;color:#3B82F6;border-radius:12px;padding:10px;display:inline-flex">' + G.icon('chat', 16) + '</a>' +
          '<button class="iconbtn" data-rm="' + i.id + '" style="background:#FEF2F2;color:#EF4444" aria-label="Remove">' + G.icon('trash', 16) + '</button></span></div></div></div>').join('');
      el.onclick = async (ev) => {
        const b = ev.target.closest('[data-rm]'); if (!b) return;
        try { await G.del('/market/cart/', { item_id: Number(b.dataset.rm) }); await draw(); } catch (e) { G.toast(G.errMsg(e)); }
      };
    }
    await draw();
  });

  /* ---------- Checkout (checkout.tsx) ---------- */
  G.route('/checkout', async (el, ctx) => {
    if (!G.loggedIn()) { G.requireLogin(); return; }
    const buyNow = ctx.query.mode === 'buynow';
    let items = []; let bn = null;
    if (buyNow) {
      try { bn = JSON.parse(G.session.get('gl_buynow') || 'null'); } catch (e) { bn = null; }
      if (!bn) { G.go('#/cart'); return; }
      items = [{ product: bn.product_id, product_name: bn.name, product_price: bn.price, product_image: bn.image, quantity: bn.quantity }];
    } else items = (await G.get('/market/cart/')).items || [];
    if (!items.length) { el.innerHTML = G.head(t('checkout'), '#/cart') + G.emptyState('bag', t('cart_empty'), t('cart_empty_desc'), '<a class="btn lg block" href="#/">' + esc(t('start_shopping')) + '</a>'); return; }
    const [wallet, addrData] = await Promise.all([G.get('/finance/wallet/').catch(() => null), G.get('/users/addresses').catch(() => ({ addresses: [] }))]);
    const def = (addrData.addresses || []).find((a) => a.isDefault) || (addrData.addresses || [])[0] || {};
    const total = items.reduce((s, i) => s + Number(i.product_price) * i.quantity, 0);
    const bal = wallet ? Number(wallet.available_balance != null ? wallet.available_balance : wallet.balance) : 0;
    const ok = bal >= total; const key = G.uuid();
    el.innerHTML = G.head(t('checkout'), '#/cart') +
      '<h2>' + esc(t('order_summary')) + '</h2><div class="card">' + items.map((i) => '<div class="sumrow" style="align-items:center"><div class="grow" style="margin-right:16px"><div class="name">' + esc(i.product_name) + '</div><div class="small mute">' + esc(t('qty')) + ': ' + i.quantity + ' × ' + money(i.product_price) + '</div></div><b>' + money(i.product_price * i.quantity) + '</b></div>').join('') +
      '<div style="height:1px;background:#F3F4F6;margin:12px 0"></div><div class="sumrow" style="align-items:center"><b style="font-size:18px;font-weight:900">' + esc(t('order_total')) + '</b><b class="price" style="font-size:24px">' + money(total) + '</b></div></div>' +
      '<h2>' + esc(t('delivery_details')) + '</h2><label style="margin-top:0">' + esc(t('address')) + '</label><input id="a1" placeholder="' + esc(t('address_placeholder')) + '" value="' + esc(def.streetAddress || '') + '">' +
      '<label>' + esc(t('city')) + '</label><input id="a2" placeholder="' + esc(t('city_placeholder')) + '" value="' + esc(def.city || '') + '"><label>' + esc(t('phone_number')) + '</label><input id="a3" inputmode="tel" placeholder="' + esc(t('phone_placeholder')) + '" value="' + esc(def.phoneNumber || (G.user && G.user.phone_number) || '') + '">' +
      '<h2 style="margin-top:24px">' + esc(t('payment_method')) + '</h2><div class="card"><div class="row" style="flex-wrap:nowrap;margin-bottom:12px"><div class="ibox" style="background:var(--primary-container);border:0">' + G.icon('wallet', 24) + '</div>' +
      '<div class="grow"><b>' + esc(t('glapp_wallet')) + '</b><div class="small mute">' + esc(t('balance')) + ': ' + money(bal) + '</div></div><span class="pill ok">' + esc(t('default')) + '</span></div>' +
      '<div class="sumrow"><span class="mute">' + esc(t('wallet_balance')) + '</span><b>' + money(bal) + '</b></div><div class="sumrow"><span class="mute">' + esc(t('order_total')) + '</span><b>' + money(total) + '</b></div>' +
      (ok ? '' : '<div class="alert bad" style="margin-top:8px">' + esc(t('insufficient_balance')) + '<br><span class="small">' + esc(t('shortfall')) + ': ' + money(total - bal) + '</span><br><a class="btn sm bad" href="#/wallet" style="margin-top:10px">' + esc(t('fund_wallet')) + '</a></div>') + '</div>' +
      '<h2>' + esc(t('transaction_pin')) + '</h2><div class="card"><label style="margin-top:0">' + esc(t('enter_pin')) + '</label><input id="pin" type="password" inputmode="numeric" maxlength="4" placeholder="••••" style="text-align:center;font-size:20px;letter-spacing:8px"></div>' +
      '<div id="err"></div><button class="btn lg block" id="pay"' + (ok ? '' : ' disabled') + '>' + esc(t('pay')) + ' ' + money(total) + '</button>';
    $('#pay', el).onclick = (ev) => {
      const ship = { address: $('#a1', el).value.trim(), city: $('#a2', el).value.trim(), phone: $('#a3', el).value.trim() };
      if (!ship.address || !ship.city || !ship.phone) return G.toast(t('missing_info_msg'));
      const pin = $('#pin', el).value.trim();
      if (!/^\d{4}$/.test(pin)) return G.toast(t('invalid_pin_msg'));
      G.busy(ev.currentTarget, async () => {
        $('#err', el).innerHTML = '';
        try {
          const res = buyNow
            ? await G.post('/market/buy-now/', { product_id: bn.product_id, quantity: bn.quantity, shipping_address: ship, payment_method: 'wallet', pin })
            : await G.post('/market/checkout/', { items: items.map((i) => ({ product_id: i.product, quantity: i.quantity })), shipping_address: ship, payment_method: 'wallet', pin }, { headers: { 'Idempotency-Key': key } });
          if (buyNow) G.session.del('gl_buynow');
          await G.refreshCart();
          el.innerHTML = '<div class="card center" style="margin-top:40px"><div class="authbox">' + G.icon('globe', 40) + '</div><h1>' + esc(t('payment_successful')) + '</h1><p class="mute">' + esc(t('order_placed')) + '</p><a class="btn lg block" href="#/orders">' + esc(t('view_orders')) + '</a></div>';
        } catch (e) { $('#err', el).innerHTML = G.fail(e); }
      });
    };
  });

  /* ---------- Orders (orders/index.tsx, orders/[id].tsx) ---------- */
  const statusPill = (s) => {
    const cls = { delivered: 'ok', shipped: 'ok', paid: 'ok', confirmed: 'ok', cancelled: 'bad', refunded: 'bad', pending: 'warn' }[s] || '';
    return '<span class="pill ' + cls + '">' + esc(G.pretty(s)) + '</span>';
  };
  G.statusPill = statusPill;

  G.route('/orders', async (el) => {
    const orders = G.list(await G.get('/market/buyer/orders/'));
    el.innerHTML = G.head(t('my_orders'), '#/more') + (orders.length ? orders.map((o) =>
      '<a class="card" style="display:block;color:inherit;border-radius:24px" href="#/orders/' + o.id + '"><div class="row between"><b>' + esc(t('order_hash')) + esc(o.order_number || o.id) + '</b><span class="price">' + money(o.total_price) + '</span></div>' +
      '<div class="small mute" style="margin:2px 0 8px">' + esc(o.shop_name || '') + ' · ' + new Date(o.created_at).toLocaleDateString() + '</div>' + statusPill(o.delivery_status) + ' ' + statusPill(o.payment_status) + '</a>').join('')
      : G.emptyState('bag', t('no_orders_yet'), t('order_history_empty'), '<a class="btn lg block" href="#/">' + esc(t('start_shopping')) + '</a>'));
  }, { auth: true });
  G.route('/orders/track', (el, ctx) => { G.go('#/orders/' + (ctx.query.orderId || '')); }, { auth: true });

  const STAGES = ['pending', 'ready_for_pickup', 'shipped', 'delivered'];
  G.route('/orders/:id', async (el, ctx) => {
    const o = await G.get('/market/buyer/orders/' + ctx.params.id + '/');
    const idx = STAGES.indexOf(['picked_up', 'in_transit'].includes(o.delivery_status) ? 'shipped' : o.delivery_status);
    const sa = o.shipping_address_json || {};
    const canCancel = ['pending', 'ready_for_pickup'].includes(o.delivery_status) && o.payment_status !== 'confirmed';
    const canConfirm = o.payment_status === 'paid' && o.delivery_status !== 'cancelled';
    el.innerHTML = G.head(t('order_hash') + (o.order_number || o.id), '#/orders') +
      '<div class="card"><div class="row between">' + '<span>' + statusPill(o.delivery_status) + ' ' + statusPill(o.payment_status) + '</span><span class="small mute">' + G.date(o.created_at) + '</span></div>' +
      (o.delivery_status === 'cancelled' ? '' : '<div class="row" style="margin-top:14px;flex-wrap:nowrap">' + STAGES.map((s, i) => '<div class="grow center small" style="color:' + (i <= idx ? 'var(--primary)' : '#CBD5E1') + ';font-weight:700"><div style="font-size:18px">' + (i <= idx ? '●' : '○') + '</div>' + esc(G.pretty(s)) + '</div>').join('') + '</div>') + '</div>' +
      '<h2>' + esc(t('store')) + ': ' + esc(o.shop_name || '') + '</h2><div class="card">' + (o.items || []).map((i) =>
        '<div class="item"><div class="grow"><a class="name" href="#/product/' + i.product + '">' + esc(i.product_name) + '</a><div class="small mute">' + esc(t('qty')) + ' ' + i.quantity + ' × ' + money(i.price) + '</div></div><b>' + money(i.quantity * i.price) + '</b></div>').join('') +
      '<div class="sumrow" style="margin-top:10px"><b>' + esc(t('total')) + '</b><b class="price">' + money(o.total_price) + '</b></div></div>' +
      '<h2>' + esc(t('delivery')) + '</h2><div class="card"><div>' + esc(sa.address || '') + '</div><div>' + esc(sa.city || '') + '</div><div>' + esc(sa.phone || '') + '</div>' +
      (o.seller_phone ? '<p class="small mute">' + esc(t('contact_seller')) + ': <a href="tel:' + esc(o.seller_phone) + '">' + esc(o.seller_phone) + '</a></p>' : '') + (o.shop_address ? '<p class="small mute">' + esc(o.shop_address) + '</p>' : '') + '</div>' +
      (canConfirm ? '<button class="btn lg block" id="conf" style="margin-bottom:12px">Confirm receipt</button>' : '') + (canCancel ? '<button class="btn bad lg block" id="canc">Cancel order</button>' : '');
    const conf = $('#conf', el); const canc = $('#canc', el);
    if (conf) conf.onclick = () => G.busy(conf, async () => {
      if (!(await G.confirm('Confirm you received this order? Funds will be released to the seller.'))) return;
      try { await G.post('/market/buyer/orders/' + o.id + '/confirm/'); G.toast('Receipt confirmed'); G.go('#/orders'); } catch (e) { G.toast(G.errMsg(e)); }
    });
    if (canc) canc.onclick = () => G.busy(canc, async () => {
      if (!(await G.confirm('Cancel this order?'))) return;
      try { await G.post('/market/buyer/orders/' + o.id + '/cancel/'); G.toast('Order cancelled'); G.go('#/orders'); } catch (e) { G.toast(G.errMsg(e)); }
    });
  }, { auth: true });

  /* ---------- Shared promotion link (promotion/[code].tsx) ---------- */
  G.route('/promotion/:code', async (el, ctx) => {
    let p;
    try { p = await G.get('/market/promotions/' + encodeURIComponent(ctx.params.code) + '/', { noAuth: true }); }
    catch (e) { el.innerHTML = G.head('Promotion', '#/') + G.emptyState('megaphone', e.status === 410 ? 'This promotion has ended' : 'Promotion not found', '', '<a class="btn lg block" href="#/">Go home</a>'); return; }
    const imgs = p.images && p.images.length ? p.images : (p.image ? [p.image] : []);
    el.innerHTML = G.head(p.title || p.product_name || 'Promotion', '#/') + '<div class="card">' +
      imgs.map((u) => '<img src="' + esc(u) + '" style="width:100%;border-radius:16px;margin-bottom:10px" alt="">').join('') +
      (p.price ? '<div class="price" style="font-size:24px">' + money(p.price) + '</div>' : '') +
      '<p style="font-size:16px">' + esc(p.text_content || '') + '</p>' + (p.location ? '<p class="mute">' + G.icon('pin', 14) + ' ' + esc(p.location) + '</p>' : '') +
      '<p class="small mute">' + esc(p.seller_name || p.user_name || '') + (p.time_remaining_seconds ? ' · ' + esc(timeLeft(p.time_remaining_seconds)) : '') + '</p>' +
      (p.product_id ? '<a class="btn block" href="#/product/' + p.product_id + '" style="margin-bottom:10px">View product</a>' : '') +
      (p.seller_id && !(G.user && G.user.id === p.seller_id) ? '<button class="btn sec block" id="msg">' + G.icon('chat', 16) + ' ' + esc(t('chat')) + '</button>' : '') +
      (p.share_url ? '<button class="btn ghost block" id="cp" style="margin-top:10px">' + G.icon('copy', 16) + ' Copy link</button>' : '') + '</div>';
    const m = $('#msg', el); const c = $('#cp', el);
    if (m) m.onclick = () => { if (!G.loggedIn()) return G.requireLogin(); G.go('#/chat/with/' + p.seller_id + (p.product_id ? '?product=' + p.product_id : '')); };
    if (c) c.onclick = () => { try { navigator.clipboard.writeText(p.share_url).then(() => G.toast(t('copied'))); } catch (e) { G.toast(p.share_url); } };
  });
})();
