/* GLAPP web client — marketplace: home, product, markets, live, cart, checkout, orders. */
(function () {
  'use strict';
  const G = window.GL;
  const { esc, money, $, $$ } = G;

  /* ---------- Home ---------- */
  G.route('/', async (el, ctx) => {
    const q = ctx.query.q || '';
    const cat = ctx.query.category || '';
    el.innerHTML =
      '<div id="ticker"></div>' +
      '<form id="sf" class="row" style="margin-bottom:12px"><input class="grow" name="q" placeholder="Search products…" value="' + esc(q) + '">' +
      '<select name="ordering" style="width:auto"><option value="">Newest</option><option value="price">Price ↑</option><option value="-price">Price ↓</option></select>' +
      '<button class="btn">Search</button></form>' +
      '<div class="chips" id="cats"></div><div class="grid" id="grid">' + G.loading + '</div><div class="center" id="more" style="margin:16px"></div>';
    $('#sf', el).ordering.value = ctx.query.ordering || '';
    $('#sf', el).onsubmit = (e) => {
      e.preventDefault();
      const f = e.target; const p = new URLSearchParams();
      if (f.q.value.trim()) p.set('q', f.q.value.trim());
      if (cat) p.set('category', cat);
      if (f.ordering.value) p.set('ordering', f.ordering.value);
      G.go('#/?' + p.toString());
    };
    G.bindProductActions(el);

    G.get('/market/promoted-posts/active/', { noAuth: true }).then((d) => {
      const posts = G.list(d);
      if (!posts.length) return;
      $('#ticker', el).innerHTML = '<div class="ticker"><span>' + posts.map((p) =>
        '<a href="#/promotion/' + esc(p.code) + '">' + esc(p.title || p.product_name || 'Promoted') + (p.price ? ' — ' + money(p.price) : '') + '</a> &nbsp;•&nbsp; ' + esc(p.text_content || '')).join(' &nbsp;&nbsp;|&nbsp;&nbsp; ') + '</span></div>';
    }).catch(() => {});

    G.get('/market/categories/', { noAuth: true }).then((d) => {
      const cats = G.list(d);
      $('#cats', el).innerHTML = '<span class="chip ' + (cat ? '' : 'on') + '" data-c="">All</span>' +
        cats.map((c) => '<span class="chip ' + (String(c.id) === cat ? 'on' : '') + '" data-c="' + c.id + '">' + esc(c.name) + '</span>').join('');
      $$('.chip', $('#cats', el)).forEach((c) => {
        c.onclick = () => {
          const p = new URLSearchParams();
          if (q) p.set('q', q);
          if (c.dataset.c) p.set('category', c.dataset.c);
          G.go('#/?' + p.toString());
        };
      });
    }).catch(() => {});

    let page = 1; const grid = $('#grid', el);
    async function load() {
      const p = new URLSearchParams({ page });
      if (q) p.set('search', q);
      if (cat) p.set('category', cat);
      if (ctx.query.ordering) p.set('ordering', ctx.query.ordering);
      const d = await G.get('/market/products/?' + p.toString(), { noAuth: !G.loggedIn() });
      const items = G.list(d);
      if (page === 1) grid.innerHTML = '';
      if (page === 1 && !items.length) { grid.innerHTML = '<div class="empty" style="grid-column:1/-1">No products found.</div>'; }
      grid.insertAdjacentHTML('beforeend', items.map(G.productCard).join(''));
      $('#more', el).innerHTML = d && d.next ? '<button class="btn ghost" id="lm">Load more</button>' : '';
      const lm = $('#lm', el);
      if (lm) lm.onclick = () => G.busy(lm, async () => { page += 1; await load(); });
    }
    try { await load(); } catch (e) { grid.innerHTML = G.fail(e); }
  });

  /* ---------- Product detail ---------- */
  G.route('/product/:id', async (el, ctx) => {
    const p = await G.get('/market/products/' + ctx.params.id + '/', { noAuth: !G.loggedIn() });
    const imgs = (p.images || []).map((i) => i.image).filter(Boolean);
    if (!imgs.length && p.image) imgs.push(p.image);
    const video = p.video_ad_url || p.video_url;
    const own = G.user && p.seller_id === G.user.id;
    const wished = G.wish.has(String(p.id));
    el.innerHTML = '<div class="gallery"><div>' + (imgs.length ? '<img class="main" id="main" src="' + esc(imgs[0]) + '" alt="">' : '<div class="noimg main">No image</div>') +
      '<div class="thumbs">' + imgs.map((u, i) => '<img src="' + esc(u) + '" class="' + (i ? '' : 'on') + '" alt="">').join('') + '</div>' +
      (video ? '<h3 style="margin-top:12px">Video</h3><video controls preload="metadata" src="' + esc(video) + '"></video>' : '') + '</div>' +
      '<div><h1>' + esc(p.name) + '</h1><div class="price" style="font-size:24px">' + money(p.price) + '</div>' +
      '<p>' + (p.stock > 0 ? '<span class="pill ok">' + p.stock + ' in stock</span>' : '<span class="pill bad">Out of stock</span>') + '</p>' +
      '<p class="mute">' + esc(p.description || '') + '</p>' +
      (p.shop ? '<p>Sold by <a href="#/markets/' + esc(p.shop.id) + '"><b>' + esc(p.shop.name) + '</b></a></p>' : '') +
      '<div class="row"><label style="margin:0">Qty</label><input id="qty" type="number" min="1" max="' + Math.max(1, p.stock) + '" value="1" style="width:80px"></div>' +
      '<div class="row" style="margin-top:12px"><button class="btn" id="add"' + (p.stock < 1 || own ? ' disabled' : '') + '>Add to cart</button>' +
      '<button class="btn sec" id="buy"' + (p.stock < 1 || own ? ' disabled' : '') + '>Buy now</button>' +
      '<button class="heart ' + (wished ? 'on' : '') + '" id="wish">' + (wished ? '♥' : '♡') + '</button></div>' +
      (!own && p.seller_id ? '<p style="margin-top:12px"><button class="btn ghost" id="chat">💬 Message seller</button></p>' : '') +
      (own ? '<p class="mute small">This is your own product.</p>' : '') + '</div></div>';
    $$('.thumbs img', el).forEach((t) => { t.onclick = () => { $('#main', el).src = t.src; $$('.thumbs img', el).forEach((x) => x.classList.remove('on')); t.classList.add('on'); }; });
    const qty = () => Math.max(1, parseInt($('#qty', el).value, 10) || 1);
    $('#add', el).onclick = (e) => {
      if (!G.loggedIn()) return G.requireLogin();
      G.busy(e.target, async () => { try { await G.post('/market/cart/', { product_id: p.id, quantity: qty() }); await G.refreshCart(); G.toast('Added to cart'); } catch (er) { G.toast(G.errMsg(er)); } });
    };
    $('#buy', el).onclick = () => {
      if (!G.loggedIn()) return G.requireLogin();
      G.session.set('gl_buynow', JSON.stringify({ product_id: p.id, quantity: qty(), name: p.name, price: p.price, image: imgs[0] || '' }));
      G.go('#/checkout?mode=buynow');
    };
    $('#wish', el).onclick = async (e) => {
      if (!G.loggedIn()) return G.requireLogin();
      const b = e.currentTarget; const id = String(p.id);
      try {
        if (G.wish.has(id)) { await G.del('/users/wishlist/' + id); G.wish.delete(id); b.classList.remove('on'); b.textContent = '♡'; }
        else { await G.post('/users/wishlist', { productId: p.id }); G.wish.add(id); b.classList.add('on'); b.textContent = '♥'; }
      } catch (er) { G.toast(G.errMsg(er)); }
    };
    const chat = $('#chat', el);
    if (chat) chat.onclick = () => { if (!G.loggedIn()) return G.requireLogin(); G.go('#/chat/with/' + p.seller_id + '?product=' + p.id); };
  });

  /* ---------- Markets (stores) ---------- */
  G.route('/markets', async (el) => {
    el.innerHTML = '<h1>Markets</h1><div id="stores" class="grid">' + G.loading + '</div>';
    const stores = G.list(await G.get('/market/stores/', { noAuth: !G.loggedIn() }));
    $('#stores', el).innerHTML = stores.length ? stores.map((s) =>
      '<a class="pcard" href="#/markets/' + esc(s.id) + '" style="color:inherit">' + G.img(s.logo) +
      '<div class="b"><div class="name">' + esc(s.name) + '</div><div class="small mute">' + (s.product_count || 0) + ' products</div></div></a>').join('')
      : '<div class="empty" style="grid-column:1/-1">No stores yet.</div>';
  });
  G.route('/markets/:id', async (el, ctx) => {
    const [s, prods] = await Promise.all([
      G.get('/market/stores/' + ctx.params.id + '/', { noAuth: !G.loggedIn() }),
      G.get('/market/products/?shop=' + encodeURIComponent(ctx.params.id), { noAuth: !G.loggedIn() }),
    ]);
    const items = G.list(prods);
    el.innerHTML = '<div class="card row">' + (s.logo ? '<img src="' + esc(s.logo) + '" style="width:72px;height:72px;border-radius:12px;object-fit:cover" alt="">' : '') +
      '<div class="grow"><h1 style="margin:0">' + esc(s.name) + '</h1><div class="mute">' + esc(s.description || '') + '</div><div class="small mute">by ' + esc(s.owner_name || '') + '</div></div>' +
      (s.owner_id && !(G.user && G.user.id === s.owner_id) ? '<button class="btn ghost" id="msg">💬 Message</button>' : '') + '</div>' +
      '<div class="grid">' + (items.length ? items.map(G.productCard).join('') : '<div class="empty" style="grid-column:1/-1">No products in this store yet.</div>') + '</div>';
    G.bindProductActions(el);
    const m = $('#msg', el);
    if (m) m.onclick = () => { if (!G.loggedIn()) return G.requireLogin(); G.go('#/chat/with/' + s.owner_id); };
  });

  /* ---------- Live (video ads) ---------- */
  G.route('/live', async (el) => {
    el.innerHTML = '<h1>Live</h1><div id="vids">' + G.loading + '</div><div class="center" id="vm" style="margin:12px"></div>';
    let page = 1;
    async function load() {
      const d = await G.get('/market/video-ads/?page=' + page, { noAuth: !G.loggedIn() });
      const items = G.list(d).filter((p) => p.video_ad_url || p.video_url);
      if (page === 1) $('#vids', el).innerHTML = '';
      if (page === 1 && !items.length) $('#vids', el).innerHTML = '<div class="empty">No videos yet.</div>';
      $('#vids', el).insertAdjacentHTML('beforeend', items.map((p) =>
        '<div class="card"><video controls preload="none" playsinline src="' + esc(p.video_ad_url || p.video_url) + '"></video>' +
        '<div class="row between" style="margin-top:8px"><div><a href="#/product/' + p.id + '"><b>' + esc(p.name) + '</b></a><div class="price">' + money(p.price) + '</div>' +
        '<div class="small mute">' + esc(p.shop_name || '') + '</div></div><a class="btn sm" href="#/product/' + p.id + '">View</a></div></div>').join(''));
      $('#vm', el).innerHTML = d && d.next ? '<button class="btn ghost" id="vmb">Load more</button>' : '';
      const b = $('#vmb', el); if (b) b.onclick = () => G.busy(b, async () => { page += 1; await load(); });
    }
    await load();
  });

  /* ---------- Cart ---------- */
  G.route('/cart', async (el) => {
    async function draw() {
      const c = await G.get('/market/cart/');
      const items = c.items || [];
      G.cartCount = items.reduce((s, i) => s + i.quantity, 0); G.paintBadge();
      if (!items.length) { el.innerHTML = '<h1>Cart</h1><div class="empty">Your cart is empty.<br><br><a class="btn" href="#/">Start shopping</a></div>'; return; }
      el.innerHTML = '<h1>Cart</h1><div class="card">' + items.map((i) =>
        '<div class="item">' + G.img(i.product_image) + '<div class="grow"><a href="#/product/' + i.product + '"><b>' + esc(i.product_name) + '</b></a><div class="price">' + money(i.product_price) + '</div></div>' +
        '<div class="qty"><button data-dec="' + i.id + '" data-p="' + i.product + '" data-q="' + i.quantity + '">−</button><span>' + i.quantity + '</span><button data-inc="' + i.product + '">+</button></div>' +
        '<button class="btn sm ghost" data-rm="' + i.id + '">Remove</button></div>').join('') + '</div>' +
        '<div class="card row between"><div><div class="mute small">Total</div><div class="price" style="font-size:22px">' + money(c.total_price) + '</div></div>' +
        '<div class="row"><button class="btn ghost" id="clr">Clear</button><a class="btn" href="#/checkout">Checkout</a></div></div>';
      el.onclick = async (ev) => {
        const t = ev.target;
        try {
          if (t.dataset.inc) { await G.post('/market/cart/', { product_id: Number(t.dataset.inc), quantity: 1 }); await draw(); }
          else if (t.dataset.dec) {
            if (Number(t.dataset.q) <= 1) await G.del('/market/cart/', { item_id: Number(t.dataset.dec) });
            else await G.post('/market/cart/', { product_id: Number(t.dataset.p), quantity: -1 });
            await draw();
          } else if (t.dataset.rm) { await G.del('/market/cart/', { item_id: Number(t.dataset.rm) }); await draw(); }
          else if (t.id === 'clr') { if (await G.confirm('Clear your cart?')) { await G.del('/market/cart/', { clear_all: true }); await draw(); } }
        } catch (e) { G.toast(G.errMsg(e)); }
      };
    }
    await draw();
  }, { auth: true });

  /* ---------- Checkout ---------- */
  G.route('/checkout', async (el, ctx) => {
    const buyNow = ctx.query.mode === 'buynow';
    let items = [];
    let bn = null;
    if (buyNow) {
      try { bn = JSON.parse(G.session.get('gl_buynow') || 'null'); } catch (e) { bn = null; }
      if (!bn) { G.go('#/cart'); return; }
      items = [{ product: bn.product_id, product_name: bn.name, product_price: bn.price, product_image: bn.image, quantity: bn.quantity }];
    } else {
      items = (await G.get('/market/cart/')).items || [];
    }
    if (!items.length) { el.innerHTML = '<div class="empty">Your cart is empty.<br><br><a class="btn" href="#/">Shop</a></div>'; return; }
    const [wallet, addrData] = await Promise.all([G.get('/finance/wallet/').catch(() => null), G.get('/users/addresses').catch(() => ({ addresses: [] }))]);
    const addrs = addrData.addresses || [];
    const total = items.reduce((s, i) => s + Number(i.product_price) * i.quantity, 0);
    const key = G.uuid();
    el.innerHTML = '<div class="narrow"><h1>Checkout</h1><div class="card"><h2>Items</h2>' + items.map((i) =>
      '<div class="item">' + G.img(i.product_image) + '<div class="grow"><b>' + esc(i.product_name) + '</b><div class="small mute">Qty ' + i.quantity + '</div></div><div>' + money(i.product_price * i.quantity) + '</div></div>').join('') +
      '<div class="row between" style="margin-top:8px"><b>Total</b><b class="price">' + money(total) + '</b></div></div>' +
      '<div class="card"><h2>Delivery address</h2>' +
      (addrs.length ? '<select id="addr">' + addrs.map((a, i) => '<option value="' + i + '"' + (a.isDefault ? ' selected' : '') + '>' + esc(a.label ? a.label + ' — ' : '') + esc(a.streetAddress) + ', ' + esc(a.city) + '</option>').join('') + '<option value="new">Enter a new address…</option></select>' : '') +
      '<div id="manual" style="' + (addrs.length ? 'display:none' : '') + '"><label>Street address</label><input id="m_addr"><label>City</label><input id="m_city"><label>Phone</label><input id="m_phone" inputmode="tel"></div>' +
      '<p class="small mute">Manage saved addresses in <a href="#/addresses">Addresses</a>.</p></div>' +
      '<div class="card"><h2>Payment</h2><p>Pay from your wallet. Funds are held in escrow until you confirm delivery.</p>' +
      (wallet ? '<p>Available balance: <b>' + money(wallet.available_balance != null ? wallet.available_balance : wallet.balance) + '</b></p>' : '') +
      (wallet && !wallet.user_has_pin ? '<div class="alert">You need a transaction PIN. <a href="#/security">Set one now</a>.</div>' : '') +
      (wallet && Number(wallet.available_balance) < total ? '<div class="alert bad">Insufficient balance. <a href="#/wallet/deposit">Top up your wallet</a>.</div>' : '') +
      '<div id="err"></div><button class="btn block" id="pay">Pay ' + money(total) + '</button></div></div>';
    const sel = $('#addr', el);
    if (sel) sel.onchange = () => { $('#manual', el).style.display = sel.value === 'new' ? '' : 'none'; };
    $('#pay', el).onclick = (ev) => {
      let ship;
      if (sel && sel.value !== 'new') {
        const a = addrs[Number(sel.value)];
        ship = { address: a.streetAddress, city: a.city + (a.state ? ', ' + a.state : ''), phone: a.phoneNumber };
      } else {
        ship = { address: $('#m_addr', el).value.trim(), city: $('#m_city', el).value.trim(), phone: $('#m_phone', el).value.trim() };
      }
      if (!ship.address || !ship.city || !ship.phone) return G.toast('Please complete the delivery address');
      G.busy(ev.currentTarget, async () => {
        const pin = await G.askPin('Enter transaction PIN to pay');
        if (!pin) return;
        $('#err', el).innerHTML = '';
        try {
          const res = buyNow
            ? await G.post('/market/buy-now/', { product_id: bn.product_id, quantity: bn.quantity, shipping_address: ship, payment_method: 'wallet', pin })
            : await G.post('/market/checkout/', { items: items.map((i) => ({ product_id: i.product, quantity: i.quantity })), shipping_address: ship, payment_method: 'wallet', pin }, { headers: { 'Idempotency-Key': key } });
          if (buyNow) G.session.del('gl_buynow');
          await G.refreshCart();
          const orders = res.orders || (res.order ? [res.order] : []);
          el.innerHTML = '<div class="narrow card center"><div style="font-size:44px">✅</div><h1>Order placed</h1><p>' + esc(res.message || 'Your order was placed and paid.') + '</p>' +
            (orders.length ? '<p>' + orders.map((o) => '<a href="#/orders/' + o.id + '">Order #' + esc(o.order_number || o.id) + '</a>').join('<br>') + '</p>' : '') +
            '<a class="btn" href="#/orders">View my orders</a></div>';
        } catch (e) { $('#err', el).innerHTML = G.fail(e); }
      });
    };
  }, { auth: true });

  /* ---------- Orders (buyer) ---------- */
  const statusPill = (s) => {
    const cls = { delivered: 'ok', shipped: 'ok', paid: 'ok', confirmed: 'ok', cancelled: 'bad', refunded: 'bad', pending: 'warn' }[s] || '';
    return '<span class="pill ' + cls + '">' + esc(G.pretty(s)) + '</span>';
  };
  G.statusPill = statusPill;

  G.route('/orders', async (el) => {
    const orders = G.list(await G.get('/market/buyer/orders/'));
    el.innerHTML = '<h1>My orders</h1>' + (orders.length ? orders.map((o) =>
      '<a class="card" style="display:block;color:inherit" href="#/orders/' + o.id + '"><div class="row between"><b>#' + esc(o.order_number || o.id) + '</b><span class="price">' + money(o.total_price) + '</span></div>' +
      '<div class="small mute">' + esc(o.shop_name || '') + ' · ' + G.date(o.created_at) + '</div><div style="margin-top:6px">' + statusPill(o.delivery_status) + ' ' + statusPill(o.payment_status) + '</div></a>').join('')
      : '<div class="empty">No orders yet.<br><br><a class="btn" href="#/">Shop now</a></div>');
  }, { auth: true });

  G.route('/orders/track', (el, ctx) => { G.go('#/orders/' + (ctx.query.orderId || '')); }, { auth: true });
  const STAGES = ['pending', 'ready_for_pickup', 'shipped', 'delivered'];
  G.route('/orders/:id', async (el, ctx) => {
    const o = await G.get('/market/buyer/orders/' + ctx.params.id + '/');
    const idx = STAGES.indexOf(o.delivery_status === 'picked_up' || o.delivery_status === 'in_transit' ? 'shipped' : o.delivery_status);
    const sa = o.shipping_address_json || {};
    const canCancel = !['delivered', 'cancelled'].includes(o.delivery_status) && o.payment_status !== 'confirmed' && ['pending', 'ready_for_pickup'].includes(o.delivery_status);
    const canConfirm = o.payment_status === 'paid' && o.delivery_status !== 'cancelled';
    el.innerHTML = '<div class="narrow"><a href="#/orders">← Orders</a><h1>Order #' + esc(o.order_number || o.id) + '</h1>' +
      '<div class="card"><div class="row between"><span>' + statusPill(o.delivery_status) + ' ' + statusPill(o.payment_status) + '</span><span class="small mute">' + G.date(o.created_at) + '</span></div>' +
      (o.delivery_status === 'cancelled' ? '' : '<div class="row" style="margin-top:12px">' + STAGES.map((s, i) => '<div class="grow center small ' + (i <= idx ? '' : 'mute') + '"><div style="font-size:18px">' + (i <= idx ? '●' : '○') + '</div>' + esc(G.pretty(s)) + '</div>').join('') + '</div>') + '</div>' +
      '<div class="card"><h2>Items from ' + esc(o.shop_name || 'shop') + '</h2>' + (o.items || []).map((i) =>
        '<div class="item"><div class="grow"><a href="#/product/' + i.product + '">' + esc(i.product_name) + '</a><div class="small mute">Qty ' + i.quantity + ' × ' + money(i.price) + '</div></div><b>' + money(i.quantity * i.price) + '</b></div>').join('') +
      '<div class="row between"><b>Total</b><b class="price">' + money(o.total_price) + '</b></div></div>' +
      '<div class="card"><h2>Delivery</h2><div>' + esc(sa.address || '') + '</div><div>' + esc(sa.city || '') + '</div><div>' + esc(sa.phone || '') + '</div>' +
      (o.seller_phone ? '<p class="small mute">Seller phone: <a href="tel:' + esc(o.seller_phone) + '">' + esc(o.seller_phone) + '</a></p>' : '') +
      (o.shop_address ? '<p class="small mute">Shop: ' + esc(o.shop_address) + '</p>' : '') + '</div>' +
      '<div class="row">' + (canConfirm ? '<button class="btn" id="conf">Confirm receipt</button>' : '') + (canCancel ? '<button class="btn bad" id="canc">Cancel order</button>' : '') + '</div></div>';
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

  /* ---------- Shared promotion link ---------- */
  G.route('/promotion/:code', async (el, ctx) => {
    let p;
    try { p = await G.get('/market/promotions/' + encodeURIComponent(ctx.params.code) + '/', { noAuth: true }); }
    catch (e) {
      el.innerHTML = '<div class="empty"><h1>' + (e.status === 410 ? 'This promotion has ended' : 'Promotion not found') + '</h1><a class="btn" href="#/">Go home</a></div>';
      return;
    }
    const imgs = p.images && p.images.length ? p.images : (p.image ? [p.image] : []);
    el.innerHTML = '<div class="narrow card"><h1>' + esc(p.title || p.product_name || 'Promotion') + '</h1>' +
      imgs.map((u) => '<img src="' + esc(u) + '" style="width:100%;border-radius:12px;margin-bottom:8px" alt="">').join('') +
      (p.price ? '<div class="price" style="font-size:22px">' + money(p.price) + '</div>' : '') +
      '<p>' + esc(p.text_content || '') + '</p>' + (p.location ? '<p class="mute">📍 ' + esc(p.location) + '</p>' : '') +
      '<p class="small mute">By ' + esc(p.seller_name || p.user_name || '') + '</p>' +
      '<div class="row">' + (p.product_id ? '<a class="btn" href="#/product/' + p.product_id + '">View product</a>' : '') +
      (p.seller_id && !(G.user && G.user.id === p.seller_id) ? '<button class="btn sec" id="msg">💬 Message seller</button>' : '') + '</div></div>';
    const m = $('#msg', el);
    if (m) m.onclick = () => { if (!G.loggedIn()) return G.requireLogin(); G.go('#/chat/with/' + p.seller_id + (p.product_id ? '?product=' + p.product_id : '')); };
  });
})();
