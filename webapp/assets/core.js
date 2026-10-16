/* GLAPP web client — core: API client, auth, helpers, layout, router. */
(function () {
  'use strict';
  const G = (window.GL = {});
  const API = '/api';
  const CLOUD = { name: 'dvj6cw5dq', preset: 'gl_app_preset' }; // same unsigned preset the mobile app uses

  /* ---------- small helpers ---------- */
  G.esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  G.money = (n) => '₦' + Number(n || 0).toLocaleString('en-NG', { maximumFractionDigits: 2 });
  G.date = (d) => { try { return new Date(d).toLocaleString(); } catch (e) { return ''; } };
  G.pretty = (s) => String(s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  G.list = (d) => (Array.isArray(d) ? d : (d && d.results) || []);
  G.$ = (s, r) => (r || document).querySelector(s);
  G.$$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  G.uuid = () => (window.crypto && crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } },
  };
  G.store = store;
  G.session = {
    get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* ignore */ } },
    del(k) { try { sessionStorage.removeItem(k); } catch (e) { /* ignore */ } },
  };

  let toastTimer;
  G.toast = (msg) => {
    const t = G.$('#toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), 3200);
  };

  G.errMsg = (e) => {
    if (!e) return 'Something went wrong.';
    const d = e.data;
    if (d) {
      if (typeof d === 'string') return d.length < 300 ? d : 'Request failed.';
      if (d.message && typeof d.message === 'string') return d.message;
      if (d.error && typeof d.error === 'string') return d.error;
      if (d.detail && typeof d.detail === 'string') return d.detail;
      const flat = [];
      const walk = (v, k) => {
        if (v == null) return;
        if (typeof v === 'string') flat.push(k && !/^(non_field_errors|errors)$/.test(k) ? k + ': ' + v : v);
        else if (Array.isArray(v)) v.forEach((x) => walk(x, k));
        else if (typeof v === 'object') Object.keys(v).forEach((kk) => walk(v[kk], kk));
      };
      walk(d.errors || d);
      if (flat.length) return flat.join(' · ');
    }
    if (e.status === 0 || /fetch|network/i.test(e.message || '')) return 'Network error — please check your connection.';
    return e.message || 'Something went wrong.';
  };

  /* ---------- API client (JWT, silent refresh) ---------- */
  let refreshing = null;
  async function refreshToken() {
    const r = store.get('gl_refresh');
    if (!r) return false;
    if (!refreshing) {
      refreshing = fetch(API + '/users/token/refresh/', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh: r }),
      }).then(async (res) => {
        if (!res.ok) return false;
        const d = await res.json();
        if (!d.access) return false;
        store.set('gl_access', d.access);
        if (d.refresh) store.set('gl_refresh', d.refresh);
        return true;
      }).catch(() => false).finally(() => { setTimeout(() => { refreshing = null; }, 0); });
    }
    return refreshing;
  }

  G.api = async function (method, path, body, opt) {
    opt = opt || {};
    const headers = Object.assign({}, opt.headers || {});
    const tok = store.get('gl_access');
    if (tok && !opt.noAuth) headers.Authorization = 'Bearer ' + tok;
    let payload;
    if (body instanceof FormData) payload = body;
    else if (body !== undefined && body !== null) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
    let res;
    try {
      res = await fetch(API + path, { method, headers, body: payload });
    } catch (e) {
      throw Object.assign(new Error('Network error'), { status: 0 });
    }
    if (res.status === 401 && !opt.noAuth && !opt._retry && tok) {
      if (await refreshToken()) return G.api(method, path, body, Object.assign({}, opt, { _retry: true }));
      G.logout(true);
    }
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
    if (!res.ok) {
      const err = new Error('HTTP ' + res.status);
      err.status = res.status; err.data = data;
      err.message = G.errMsg(err);
      throw err;
    }
    return data;
  };
  G.get = (p, o) => G.api('GET', p, undefined, o);
  G.post = (p, b, o) => G.api('POST', p, b === undefined ? {} : b, o);
  G.patch = (p, b, o) => G.api('PATCH', p, b, o);
  G.put = (p, b, o) => G.api('PUT', p, b, o);
  G.del = (p, b, o) => G.api('DELETE', p, b, o);

  /* Direct-to-Cloudinary upload, same as the mobile app (products, logos, promos). */
  G.upload = async function (file, isVideo) {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('upload_preset', CLOUD.preset);
    const kind = isVideo ? 'video' : 'image';
    const res = await fetch('https://api.cloudinary.com/v1_1/' + CLOUD.name + '/' + kind + '/upload', { method: 'POST', body: fd });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error((d.error && d.error.message) || 'Upload failed');
    return d.secure_url;
  };

  /* ---------- auth state ---------- */
  G.user = null;
  G.cartCount = 0;
  G.wish = new Set();
  G.loggedIn = () => !!store.get('gl_access');
  G.isAdmin = () => !!(G.user && (G.user.is_staff || G.user.active_role === 'admin'));
  G.hasRole = (r) => !!(G.user && (G.user.roles || []).indexOf(r) >= 0);

  G.loadUser = async function () {
    if (!G.loggedIn()) { G.user = null; return null; }
    try { G.user = await G.get('/users/profile/'); } catch (e) { if (e.status === 401 || e.status === 403) G.user = null; }
    return G.user;
  };
  G.refreshCart = async function () {
    if (!G.loggedIn()) { G.cartCount = 0; G.paintBadge(); return null; }
    try {
      const c = await G.get('/market/cart/');
      G.cartCount = (c.items || []).reduce((s, i) => s + (i.quantity || 0), 0);
      G.paintBadge();
      return c;
    } catch (e) { return null; }
  };
  G.refreshWish = async function () {
    G.wish = new Set();
    if (!G.loggedIn()) return;
    try { (await G.get('/users/wishlist')).wishlist.forEach((p) => G.wish.add(String(p._id))); } catch (e) { /* ignore */ }
  };
  G.paintBadge = () => {
    G.$$('.cart-badge').forEach((b) => { b.textContent = G.cartCount; b.style.display = G.cartCount ? '' : 'none'; });
  };

  G.login = async function (email, password) {
    const d = await G.post('/users/login/', { email: email.trim(), password }, { noAuth: true });
    store.set('gl_access', d.token);
    if (d.refresh) store.set('gl_refresh', d.refresh);
    await G.loadUser();
    await Promise.all([G.refreshCart(), G.refreshWish()]);
    return d;
  };
  G.logout = function (silent) {
    store.del('gl_access'); store.del('gl_refresh');
    G.user = null; G.cartCount = 0; G.wish = new Set();
    G.drawChrome();
    if (!silent) G.toast('Signed out');
    location.hash = '#/login';
  };
  G.requireLogin = function () {
    G.session.set('gl_next', location.hash || '#/');
    location.hash = '#/login';
  };

  /* ---------- product helpers ---------- */
  G.pimg = (p) => (p && (p.image || (p.images && p.images[0] && (p.images[0].image || p.images[0])) || p.product_image)) || '';
  G.img = (src, cls) => (src ? '<img class="' + (cls || '') + '" loading="lazy" alt="" src="' + G.esc(src) + '">' : '<div class="noimg ' + (cls || '') + '">No image</div>');
  G.productCard = function (p) {
    const wished = G.wish.has(String(p.id));
    return '<div class="pcard"><a href="#/product/' + p.id + '">' + G.img(G.pimg(p)) + '</a><div class="b">' +
      '<a class="name" href="#/product/' + p.id + '">' + G.esc(p.name) + '</a>' +
      '<div class="price">' + G.money(p.price) + '</div>' +
      '<div class="small mute">' + G.esc(p.shop_name || (p.shop && p.shop.name) || '') + '</div>' +
      '<div class="row between" style="margin-top:auto">' +
      '<button class="btn sm" data-add="' + p.id + '"' + (p.stock === 0 ? ' disabled' : '') + '>' + (p.stock === 0 ? 'Sold out' : 'Add to cart') + '</button>' +
      '<button class="heart ' + (wished ? 'on' : '') + '" data-wish="' + p.id + '" title="Wishlist" aria-label="Wishlist">' + (wished ? '♥' : '♡') + '</button>' +
      '</div></div></div>';
  };
  /* Delegated handlers for add-to-cart / wishlist buttons inside any container. */
  G.bindProductActions = function (root) {
    root.addEventListener('click', async (ev) => {
      const add = ev.target.closest('[data-add]');
      const wish = ev.target.closest('[data-wish]');
      if (add) {
        if (!G.loggedIn()) return G.requireLogin();
        add.disabled = true;
        try { await G.post('/market/cart/', { product_id: Number(add.dataset.add), quantity: 1 }); await G.refreshCart(); G.toast('Added to cart'); }
        catch (e) { G.toast(G.errMsg(e)); }
        add.disabled = false;
      } else if (wish) {
        if (!G.loggedIn()) return G.requireLogin();
        const id = wish.dataset.wish;
        try {
          if (G.wish.has(id)) { await G.del('/users/wishlist/' + id); G.wish.delete(id); wish.classList.remove('on'); wish.textContent = '♡'; }
          else { await G.post('/users/wishlist', { productId: Number(id) }); G.wish.add(id); wish.classList.add('on'); wish.textContent = '♥'; }
        } catch (e) { G.toast(G.errMsg(e)); }
      }
    });
  };

  /* ---------- dialogs ---------- */
  G.modal = function (html) {
    const o = document.createElement('div');
    o.className = 'overlay';
    o.innerHTML = '<div class="modal">' + html + '</div>';
    document.body.appendChild(o);
    o.close = () => o.remove();
    o.addEventListener('click', (e) => { if (e.target === o) o.close(); });
    return o;
  };
  G.askPin = function (title) {
    return new Promise((resolve) => {
      const m = G.modal('<h2>' + G.esc(title || 'Enter transaction PIN') + '</h2>' +
        '<input id="pinv" type="password" inputmode="numeric" maxlength="4" autocomplete="off" placeholder="4-digit PIN">' +
        '<div class="row" style="margin-top:12px"><button class="btn grow" id="pinok">Confirm</button><button class="btn ghost" id="pinno">Cancel</button></div>');
      const inp = G.$('#pinv', m); inp.focus();
      const done = (v) => { m.close(); resolve(v); };
      G.$('#pinok', m).onclick = () => { const v = inp.value.trim(); if (v.length !== 4) return G.toast('PIN must be 4 digits'); done(v); };
      G.$('#pinno', m).onclick = () => done(null);
      inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') G.$('#pinok', m).click(); });
    });
  };
  G.confirm = (msg) => Promise.resolve(window.confirm(msg));

  /* Disable a button + show spinner while an async action runs. */
  G.busy = async function (btn, fn) {
    const old = btn.innerHTML;
    btn.disabled = true; btn.innerHTML = '<span class="spin"></span>';
    try { return await fn(); } finally { btn.disabled = false; btn.innerHTML = old; }
  };
  G.loading = '<div class="loading"><span class="spin"></span></div>';
  G.fail = (e) => '<div class="alert bad">' + G.esc(G.errMsg(e)) + '</div>';

  /* ---------- layout ---------- */
  const NAV = [
    ['#/', 'Home', '⌂'], ['#/markets', 'Markets', '▦'], ['#/live', 'Live', '▶'], ['#/data', 'Data', '☎'],
    ['#/chat', 'Chat', '✉'], ['#/cart', 'Cart', '🛒'], ['#/more', 'More', '☰'],
  ];
  G.drawChrome = function () {
    const app = G.$('#app');
    if (!G.$('#view')) {
      app.innerHTML = '<header class="top"><div class="top-in"><a class="brand" href="#/">GLAPP</a><nav class="nav" id="nav"></nav>' +
        '<div id="who" class="small"></div></div></header><main id="view"></main>' +
        '<div class="footer">© GLAPP · <a href="#/help">Help</a> · <a href="#/privacy-policy">Privacy</a></div><nav class="tabbar" id="tabbar"></nav>';
    }
    const cur = location.hash.split('?')[0] || '#/';
    const on = (h) => (h === '#/' ? cur === '#/' || cur === '' : cur.indexOf(h) === 0);
    const cartB = '<span class="badge cart-badge" style="' + (G.cartCount ? '' : 'display:none') + '">' + G.cartCount + '</span>';
    G.$('#nav').innerHTML = NAV.map((n) => '<a href="' + n[0] + '" class="' + (on(n[0]) ? 'on' : '') + '">' + n[1] + (n[1] === 'Cart' ? cartB : '') + '</a>').join('');
    G.$('#tabbar').innerHTML = NAV.map((n) => '<a href="' + n[0] + '" class="' + (on(n[0]) ? 'on' : '') + '"><span class="ic">' + n[2] + '</span>' + n[1] + (n[1] === 'Cart' ? cartB : '') + '</a>').join('');
    G.$('#who').innerHTML = G.user
      ? '<a href="#/wallet">Wallet</a> · <a href="#/profile">' + G.esc((G.user.full_name || G.user.email || 'Account').split(' ')[0]) + '</a>'
      : '<a href="#/login">Sign in</a>';
  };

  /* ---------- router ---------- */
  const routes = [];
  let leaveFns = [];
  G.onLeave = (fn) => leaveFns.push(fn);
  G.route = function (pattern, fn, opt) {
    const keys = [];
    const re = new RegExp('^' + pattern.replace(/:([a-z]+)/gi, (m, k) => { keys.push(k); return '([^/]+)'; }) + '/?$');
    routes.push({ re, keys, fn, opt: opt || {} });
  };
  G.go = (h) => { location.hash = h; };

  async function dispatch() {
    leaveFns.forEach((f) => { try { f(); } catch (e) { /* ignore */ } });
    leaveFns = [];
    window.scrollTo(0, 0);
    const raw = (location.hash || '#/').slice(1) || '/';
    const qi = raw.indexOf('?');
    const path = qi >= 0 ? raw.slice(0, qi) : raw;
    const query = {};
    if (qi >= 0) new URLSearchParams(raw.slice(qi + 1)).forEach((v, k) => { query[k] = v; });
    G.drawChrome();
    const host = G.$('#view');
    const el = document.createElement('div');
    host.replaceChildren(el);
    let match = null; const params = {};
    for (const r of routes) {
      const m = r.re.exec(path);
      if (m) { match = r; r.keys.forEach((k, i) => { params[k] = decodeURIComponent(m[i + 1]); }); break; }
    }
    if (!match) { el.innerHTML = '<div class="empty"><h1>Page not found</h1><a class="btn" href="#/">Go home</a></div>'; return; }
    if (match.opt.auth && !G.loggedIn()) { G.requireLogin(); return; }
    if (match.opt.admin && !G.isAdmin()) { el.innerHTML = '<div class="alert bad">Admin access required.</div>'; return; }
    el.innerHTML = G.loading;
    try { await match.fn(el, { params, query, path }); }
    catch (e) { el.innerHTML = G.fail(e) + '<a class="btn ghost" href="#/">Home</a>'; }
  }
  G.start = async function () {
    if (G.loggedIn()) { await G.loadUser(); G.refreshCart(); G.refreshWish(); }
    window.addEventListener('hashchange', dispatch);
    await dispatch();
  };
})();
