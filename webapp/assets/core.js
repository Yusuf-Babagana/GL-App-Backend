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

  /* ---------- i18n (same EN/HA/AR dictionary as the mobile app) ---------- */
  G.lang = store.get('settings.lang') || 'en';
  G.t = function (key, fallback, vars) {
    const dict = window.GL_I18N || {};
    let v = (dict[G.lang] && dict[G.lang][key]) || (dict.en && dict.en[key]) || fallback || key;
    if (vars) Object.keys(vars).forEach((k) => { v = v.replace(new RegExp('{{\\s*' + k + '\\s*}}', 'g'), vars[k]); });
    return v;
  };
  G.applyLang = function () {
    document.documentElement.lang = G.lang;
    document.documentElement.dir = G.lang === 'ar' ? 'rtl' : 'ltr';
  };
  G.setLang = function (lng) {
    G.lang = lng; store.set('settings.lang', lng); G.applyLang();
    G.drawChrome();
    window.dispatchEvent(new HashChangeEvent('hashchange')); // re-render current screen
  };
  G.langSwitcher = () => '<div class="langs">' + [['en', 'EN'], ['ha', 'HA'], ['ar', 'AR']].map((l, i) =>
    (i ? '<i>|</i>' : '') + '<button type="button" data-lang="' + l[0] + '" class="' + (G.lang === l[0] ? 'on' : '') + '">' + l[1] + '</button>').join('') + '</div>';
  document.addEventListener('click', (e) => { const b = e.target.closest('[data-lang]'); if (b) G.setLang(b.dataset.lang); });

  /* ---------- icons (Feather/Lucide-style, as used by the mobile app) ---------- */
  const ICONS = {
    search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    heart: '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
    bag: '<path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/>',
    cart: '<circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>',
    pin: '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
    grid: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    headset: '<path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/>',
    user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    userplus: '<path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    right: '<polyline points="9 18 15 12 9 6"/>',
    left: '<polyline points="15 18 9 12 15 6"/>',
    briefcase: '<rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    globe: '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    play: '<circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/>',
    wifi: '<path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>',
    chat: '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
    dots: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    eyeoff: '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/>',
    megaphone: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>',
    wallet: '<path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>',
    store: '<path d="m2 7 4.41-4.41A2 2 0 0 1 7.83 2h8.34a2 2 0 0 1 1.42.59L22 7"/><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><path d="M15 22v-4a2 2 0 0 0-2-2h-2a2 2 0 0 0-2 2v4"/><path d="M2 7h20"/><path d="M22 7v3a2 2 0 0 1-2 2 2.7 2.7 0 0 1-2-.7 2.7 2.7 0 0 1-4 0 2.7 2.7 0 0 1-4 0 2.7 2.7 0 0 1-4 0A2.7 2.7 0 0 1 4 12a2 2 0 0 1-2-2V7"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
    plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    minus: '<line x1="5" y1="12" x2="19" y2="12"/>',
    trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m5 0V4a2 2 0 0 1 2-2h0a2 2 0 0 1 2 2v2"/>',
    arrowr: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    copy: '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    history: '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/><polyline points="12 7 12 12 16 14"/>',
    bank: '<line x1="3" y1="22" x2="21" y2="22"/><line x1="6" y1="18" x2="6" y2="11"/><line x1="10" y1="18" x2="10" y2="11"/><line x1="14" y1="18" x2="14" y2="11"/><line x1="18" y1="18" x2="18" y2="11"/><polygon points="12 2 20 7 4 7"/>',
    down: '<line x1="17" y1="7" x2="7" y2="17"/><polyline points="17 17 7 17 7 7"/>',
    up: '<line x1="7" y1="17" x2="17" y2="7"/><polyline points="7 7 17 7 17 17"/>',
    clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    phone: '<rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>',
    sync: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
  };
  G.icon = (n, size, color) => '<svg viewBox="0 0 24 24" fill="none" stroke="' + (color || 'currentColor') + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"' + (size ? ' width="' + size + '" height="' + size + '"' : '') + ' aria-hidden="true">' + (ICONS[n] || '') + '</svg>';
  G.back = (href) => '<a class="back" href="' + (href || 'javascript:history.back()') + '" aria-label="Back">' + G.icon('left') + '</a>';
  /* Screen header: [back] Title [right html] */
  G.head = (title, back, right) => '<div class="ph">' + (back ? G.back(back === true ? undefined : back) : '') + '<h1>' + G.esc(title) + '</h1>' + (right || '') + '</div>';
  G.emptyState = (icon, title, text, action) => '<div class="empty"><div class="eb">' + G.icon(icon) + '</div><h3>' + G.esc(title) + '</h3>' + (text ? '<p>' + G.esc(text) + '</p>' : '') + (action || '') + '</div>';

  /* ---------- product helpers ---------- */
  G.pimg = (p) => (p && (p.image || (p.images && p.images[0] && (p.images[0].image || p.images[0])) || p.product_image)) || '';
  G.img = (src, cls) => (src ? '<img class="' + (cls || '') + '" loading="lazy" alt="" src="' + G.esc(src) + '">' : '<div class="noimg ' + (cls || '') + '">' + G.icon('image', 22) + '</div>');
  G.productCard = function (p) {
    const wished = G.wish.has(String(p.id));
    const shop = p.shop_name || (p.shop && p.shop.name) || 'Globalink';
    return '<div class="pcard"><div class="im"><a href="#/product/' + p.id + '">' + G.img(G.pimg(p)) + '</a>' +
      '<button class="heart ' + (wished ? 'on' : '') + '" data-wish="' + p.id + '" aria-label="Wishlist">' + G.icon('heart') + '</button></div><div class="b">' +
      '<div class="stars">★★★★★<span>(0)</span></div><span class="shop">' + G.esc(shop) + '</span>' +
      '<a class="name" href="#/product/' + p.id + '">' + G.esc(p.name) + '</a>' +
      '<div class="price">' + G.money(p.price) + '</div>' +
      '<button class="addbtn" data-add="' + p.id + '"' + (p.stock === 0 ? ' disabled' : '') + '>' + (p.stock === 0 ? G.esc(G.t('out_of_stock')) : G.esc(G.t('add_to_cart'))) + '</button></div></div>';
  };
  /* Delegated handlers for add-to-cart / wishlist buttons inside any container. */
  G.bindProductActions = function (root) {
    root.addEventListener('click', async (ev) => {
      const add = ev.target.closest('[data-add]');
      const wish = ev.target.closest('[data-wish]');
      if (add) {
        if (!G.loggedIn()) return G.requireLogin();
        add.disabled = true;
        try { await G.post('/market/cart/', { product_id: Number(add.dataset.add), quantity: 1 }); await G.refreshCart(); G.toast(G.t('added_to_cart')); }
        catch (e) { G.toast(G.errMsg(e)); }
        add.disabled = false;
      } else if (wish) {
        if (!G.loggedIn()) return G.requireLogin();
        const id = wish.dataset.wish;
        try {
          if (G.wish.has(id)) { await G.del('/users/wishlist/' + id); G.wish.delete(id); wish.classList.remove('on'); }
          else { await G.post('/users/wishlist', { productId: Number(id) }); G.wish.add(id); wish.classList.add('on'); }
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
      const m = G.modal('<h2>' + G.esc(title || G.t('enter_pin')) + '</h2>' +
        '<input id="pinv" type="password" inputmode="numeric" maxlength="4" autocomplete="off" placeholder="••••" style="text-align:center;font-size:24px;letter-spacing:12px">' +
        '<div class="row" style="margin-top:16px"><button class="btn grow" id="pinok">OK</button><button class="btn ghost" id="pinno">' + G.esc(G.t('cancel')) + '</button></div>');
      const inp = G.$('#pinv', m); inp.focus();
      const done = (v) => { m.close(); resolve(v); };
      G.$('#pinok', m).onclick = () => { const v = inp.value.trim(); if (v.length !== 4) return G.toast(G.t('invalid_pin_msg')); done(v); };
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
  /* Password input with the mobile app's show/hide eye. */
  G.pwField = (name, ph, auto) => '<div class="pw"><input name="' + name + '" type="password" placeholder="' + G.esc(ph || '') + '" autocomplete="' + (auto || 'current-password') + '" required><button type="button" class="eye" aria-label="Show password">' + G.icon('eye') + '</button></div>';
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.pw .eye'); if (!b) return;
    const i = b.parentNode.querySelector('input'); const show = i.type === 'password';
    i.type = show ? 'text' : 'password'; b.innerHTML = G.icon(show ? 'eyeoff' : 'eye');
  });

  /* ---------- layout: floating pill tab bar (tab screens only, as in the app) ---------- */
  const TABS = [
    ['#/', 'products', 'Products', 'grid'], ['#/live', 'ads', 'Ads', 'play'], ['#/markets', 'market', 'Market', 'cart'],
    ['#/data', 'data_tab', 'Data', 'wifi'], ['#/chat', 'chats', 'Chats', 'chat'], ['#/cart', 'cart_tab', 'Cart', 'bag'], ['#/more', 'more', 'More', 'dots'],
  ];
  G.drawChrome = function () {
    const app = G.$('#app');
    if (!G.$('#view')) app.innerHTML = '<main id="view"></main><nav class="tabbar" id="tabbar"></nav>';
    const cur = (location.hash.split('?')[0] || '#/').replace(/\/$/, '') || '#/';
    const path = cur === '#' ? '#/' : cur;
    const isTab = TABS.some((t) => t[0] === path);
    const bar = G.$('#tabbar');
    bar.style.display = isTab ? '' : 'none';
    bar.innerHTML = TABS.map((t) => '<a href="' + t[0] + '" class="' + (t[0] === path ? 'on' : '') + '"><span class="ic">' + G.icon(t[3]) + '</span>' + G.esc(G.t(t[1], t[2])) +
      (t[3] === 'bag' ? '<span class="badge cart-badge" style="' + (G.cartCount ? '' : 'display:none') + '">' + G.cartCount + '</span>' : '') + '</a>').join('');
    G.$('#view').style.paddingBottom = isTab ? '' : '40px';
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
    G.applyLang();
    if (G.loggedIn()) {
      await G.loadUser(); G.refreshCart(); G.refreshWish();
      if (G.isAdmin() && (!location.hash || location.hash === '#/' || location.hash === '#')) location.hash = '#/admin';
    // Same entry flow as the app: signed-out visitors land on the login screen (they can "Skip, Browse Products").
    } else if (!G.session.get('gl_guest') && (!location.hash || location.hash === '#/' || location.hash === '#')) location.hash = '#/login';
    window.addEventListener('hashchange', dispatch);
    await dispatch();
  };
})();
