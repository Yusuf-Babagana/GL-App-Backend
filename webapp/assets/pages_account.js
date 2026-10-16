/* GLAPP web client — auth, account, addresses, wishlist, KYC, chat, help. */
(function () {
  'use strict';
  const G = window.GL;
  const { esc, $, $$ } = G;

  /* ---------- Auth ---------- */
  function afterAuth() {
    const next = G.session.get('gl_next');
    G.session.del('gl_next');
    G.go(next && next !== '#/login' ? next : '#/');
  }

  G.route('/login', (el) => {
    if (G.loggedIn()) { G.go('#/'); return; }
    el.innerHTML = '<div class="narrow card"><h1>Welcome back</h1><form id="f"><label>Email</label><input name="email" type="email" required autocomplete="email">' +
      '<label>Password</label><input name="password" type="password" required autocomplete="current-password"><div id="err" style="margin-top:10px"></div>' +
      '<button class="btn block" style="margin-top:12px">Sign in</button></form>' +
      '<p class="center small"><a href="#/forgot-password">Forgot password?</a> · <a href="#/register">Create account</a></p></div>';
    $('#f', el).onsubmit = (e) => {
      e.preventDefault();
      const f = e.target;
      G.busy($('button', f), async () => {
        try { await G.login(f.email.value, f.password.value); afterAuth(); }
        catch (er) { $('#err', el).innerHTML = G.fail(er.status === 401 ? { data: { error: 'Invalid email or password.' } } : er); }
      });
    };
  });

  G.route('/register', (el) => {
    if (G.loggedIn()) { G.go('#/'); return; }
    el.innerHTML = '<div class="narrow card"><h1>Create account</h1><form id="f"><div class="row"><div class="grow"><label>First name</label><input name="first" required></div><div class="grow"><label>Last name</label><input name="last" required></div></div>' +
      '<label>Email</label><input name="email" type="email" required autocomplete="email"><label>Password</label><input name="password" type="password" required minlength="8" autocomplete="new-password">' +
      '<div class="small mute">At least 8 characters, not too common, not all numbers.</div><div id="err" style="margin-top:10px"></div>' +
      '<button class="btn block" style="margin-top:12px">Sign up</button></form><p class="center small">Already registered? <a href="#/login">Sign in</a></p></div>';
    $('#f', el).onsubmit = (e) => {
      e.preventDefault();
      const f = e.target;
      G.busy($('button', f), async () => {
        try {
          await G.post('/users/register/', { email: f.email.value.trim(), password: f.password.value, first_name: f.first.value.trim(), last_name: f.last.value.trim() }, { noAuth: true });
          await G.login(f.email.value, f.password.value); // register response has no refresh token
          afterAuth();
        } catch (er) { $('#err', el).innerHTML = G.fail(er); }
      });
    };
  });

  G.route('/forgot-password', (el) => {
    let email = '';
    function step1() {
      el.innerHTML = '<div class="narrow card"><h1>Reset password</h1><form id="f"><label>Email</label><input name="email" type="email" required><div id="err" style="margin-top:10px"></div>' +
        '<button class="btn block" style="margin-top:12px">Send reset code</button></form><p class="center small"><a href="#/login">Back to sign in</a></p></div>';
      $('#f', el).onsubmit = (e) => {
        e.preventDefault();
        G.busy($('button', e.target), async () => {
          try { email = e.target.email.value.trim().toLowerCase(); await G.post('/users/password-reset/request/', { email }, { noAuth: true }); G.toast('If the account exists, a code was sent.'); step2(); }
          catch (er) { $('#err', el).innerHTML = G.fail(er); }
        });
      };
    }
    function step2() {
      el.innerHTML = '<div class="narrow card"><h1>Enter code</h1><p class="mute small">We sent a code to ' + esc(email) + '.</p><form id="f"><label>Reset code</label><input name="otp" inputmode="numeric" required>' +
        '<label>New password</label><input name="pw" type="password" required minlength="8" autocomplete="new-password"><div id="err" style="margin-top:10px"></div>' +
        '<button class="btn block" style="margin-top:12px">Reset password</button></form><p class="center small"><a href="#" id="back">Use a different email</a></p></div>';
      $('#back', el).onclick = (e) => { e.preventDefault(); step1(); };
      $('#f', el).onsubmit = (e) => {
        e.preventDefault();
        G.busy($('button', e.target), async () => {
          try { await G.post('/users/password-reset/confirm/', { email, otp: e.target.otp.value.trim(), new_password: e.target.pw.value }, { noAuth: true }); G.toast('Password updated — please sign in'); G.go('#/login'); }
          catch (er) { $('#err', el).innerHTML = G.fail(er); }
        });
      };
    }
    step1();
  });

  /* ---------- More / account hub ---------- */
  G.route('/more', async (el) => {
    const u = G.user;
    const link = (h, ic, t, sub) => '<a href="' + h + '"><span class="ic">' + ic + '</span><span class="grow"><b>' + t + '</b>' + (sub ? '<div class="small mute">' + sub + '</div>' : '') + '</span><span class="mute">›</span></a>';
    let shopStatus = null;
    if (u) { try { shopStatus = (await G.get('/market/shop/my-status/')).status; } catch (e) { shopStatus = null; } }
    const kyc = u && u.kyc_status;
    el.innerHTML = '<div class="narrow">' +
      (u ? '<div class="card row"><div class="grow"><h2 style="margin:0">' + esc(u.full_name || u.email) + '</h2><div class="small mute">' + esc(u.email) + '</div></div><span class="pill ' + (kyc === 'verified' ? 'ok' : kyc === 'rejected' ? 'bad' : 'warn') + '">KYC: ' + esc(G.pretty(kyc || 'unverified')) + '</span></div>'
        : '<div class="card center"><p>Sign in to access your orders, wallet and more.</p><a class="btn" href="#/login">Sign in</a> <a class="btn sec" href="#/register">Create account</a></div>') +
      '<div class="card menu">' +
      (u ? link('#/profile', '👤', 'My profile', 'Name, phone, photo') + link('#/orders', '📦', 'My orders') + link('#/wallet', '👛', 'Wallet', 'Balance, deposits, withdrawals') + link('#/wishlist', '♡', 'Wishlist') + link('#/addresses', '📍', 'Addresses') + link('#/security', '🔒', 'Privacy & security', 'PIN, delete account') + link('#/kyc', '🪪', 'Identity verification (KYC)') : '') +
      link('#/jobs', '💼', 'Jobs') +
      (u ? (shopStatus === 'approved' ? link('#/merchant', '🏪', 'Merchant dashboard', 'Products, orders, earnings') + link('#/promote', '📣', 'Promote a post') :
        shopStatus === 'pending' ? link('#/merchant/pending', '⏳', 'Shop under review') : link('#/merchant/onboarding', '🏪', 'Become a seller', 'Open your shop on GLAPP')) : '') +
      (G.isAdmin() ? link('#/admin', '🛡', 'Admin dashboard') + link('#/admin/kyc', '🪪', 'KYC requests') : '') +
      link('#/help', '🎧', 'Help & support') + link('#/privacy-policy', '📄', 'Privacy policy') + '</div>' +
      (u ? '<button class="btn bad block" id="out">Sign out</button>' : '') + '</div>';
    const o = $('#out', el); if (o) o.onclick = () => G.logout();
  });

  /* ---------- Profile ---------- */
  G.route('/profile', async (el) => {
    await G.loadUser();
    const u = G.user;
    el.innerHTML = '<div class="narrow"><a href="#/more">← Account</a><h1>My profile</h1><form class="card" id="f">' +
      (u.profile_image ? '<img src="' + esc(u.profile_image) + '" style="width:80px;height:80px;border-radius:50%;object-fit:cover" alt="">' : '') +
      '<label>Full name</label><input name="full_name" value="' + esc(u.full_name || '') + '"><label>Email</label><input value="' + esc(u.email) + '" disabled>' +
      '<label>Phone number</label><input name="phone_number" inputmode="tel" value="' + esc(u.phone_number || '') + '"><label>Profile photo</label><input name="photo" type="file" accept="image/*">' +
      '<label>Preferred language</label><select name="language_preference"><option value="en">English</option><option value="ha">Hausa</option><option value="fr">Français</option><option value="ar">العربية</option></select>' +
      '<div id="err" style="margin-top:10px"></div><button class="btn block" style="margin-top:12px">Save changes</button></form></div>';
    const f = $('#f', el); f.language_preference.value = u.language_preference || 'en';
    f.onsubmit = (e) => {
      e.preventDefault();
      G.busy($('button', f), async () => {
        try {
          const file = f.photo.files[0];
          if (file) {
            const fd = new FormData();
            fd.append('full_name', f.full_name.value.trim()); fd.append('phone_number', f.phone_number.value.trim());
            fd.append('language_preference', f.language_preference.value); fd.append('profile_image', file);
            await G.patch('/users/profile/', fd);
          } else {
            await G.patch('/users/profile/', { full_name: f.full_name.value.trim(), phone_number: f.phone_number.value.trim(), language_preference: f.language_preference.value });
          }
          await G.loadUser(); G.drawChrome(); G.toast('Profile updated');
        } catch (er) { $('#err', el).innerHTML = G.fail(er); }
      });
    };
  }, { auth: true });
  G.route('/profile/edit', (el) => { G.go('#/profile'); }, { auth: true });

  /* ---------- Security: PIN + account deletion ---------- */
  G.route('/security', async (el) => {
    const [w] = await Promise.all([G.get('/finance/wallet/').catch(() => ({})), G.loadUser()]);
    const hasPin = !!w.user_has_pin; const u = G.user;
    el.innerHTML = '<div class="narrow"><a href="#/more">← Account</a><h1>Privacy & security</h1>' +
      '<form class="card" id="pf"><h2>' + (hasPin ? 'Change' : 'Create') + ' transaction PIN</h2>' +
      (hasPin ? '<label>Current PIN</label><input name="old" type="password" inputmode="numeric" maxlength="4">' : '') +
      '<label>' + (hasPin ? 'New PIN' : 'PIN') + '</label><input name="pin" type="password" inputmode="numeric" maxlength="4"><label>Confirm PIN</label><input name="pin2" type="password" inputmode="numeric" maxlength="4">' +
      '<div id="err" style="margin-top:10px"></div><button class="btn block" style="margin-top:12px">Save PIN</button></form>' +
      '<div class="card"><h2>Delete account</h2>' +
      (u.is_deactivation_pending ? '<div class="alert">Deletion requested ' + G.date(u.deletion_requested_at) + '. You can cancel until it is processed.</div><button class="btn" id="cancel">Cancel deletion</button>'
        : '<p class="mute small">Requests account deletion. A confirmation email is sent and you can cancel any time before it is processed. See also <a href="/account-deletion/" target="_blank" rel="noopener">account deletion info</a>.</p><button class="btn bad" id="del">Request deletion</button>') + '</div></div>';
    $('#pf', el).onsubmit = (e) => {
      e.preventDefault(); const f = e.target;
      if (!/^\d{4}$/.test(f.pin.value)) return G.toast('PIN must be 4 digits');
      if (f.pin.value !== f.pin2.value) return G.toast('PINs do not match');
      G.busy($('button', f), async () => {
        try { await G.post('/finance/pin/', { pin: f.pin.value, old_pin: hasPin ? f.old.value : undefined }); G.toast('PIN saved'); G.go('#/more'); }
        catch (er) { $('#err', el).innerHTML = G.fail(er); }
      });
    };
    const del = $('#del', el); const can = $('#cancel', el);
    if (del) del.onclick = () => G.busy(del, async () => {
      if (!(await G.confirm('Request deletion of your account? This cannot be undone once processed.'))) return;
      try { await G.post('/users/request-deletion/'); G.toast('Deletion requested'); G.go('#/more'); } catch (er) { G.toast(G.errMsg(er)); }
    });
    if (can) can.onclick = () => G.busy(can, async () => { try { await G.post('/users/cancel-deletion/'); G.toast('Deletion cancelled'); G.go('#/more'); } catch (er) { G.toast(G.errMsg(er)); } });
  }, { auth: true });
  G.route('/profile/security', (el) => { G.go('#/security'); }, { auth: true });

  /* ---------- Addresses ---------- */
  G.route('/addresses', async (el) => {
    let addrs = (await G.get('/users/addresses')).addresses || [];
    function form(a) {
      a = a || {};
      const m = G.modal('<h2>' + (a._id ? 'Edit' : 'Add') + ' address</h2><form id="af">' +
        ['label:Label (e.g. Home)', 'fullName:Full name', 'streetAddress:Street address', 'city:City', 'state:State', 'country:Country', 'zipCode:Zip code', 'phoneNumber:Phone number'].map((p) => {
          const [k, l] = p.split(':'); return '<label>' + l + '</label><input name="' + k + '" value="' + esc(a[k] || (k === 'country' ? 'Nigeria' : '')) + '"' + (['fullName', 'streetAddress', 'city', 'state', 'phoneNumber'].indexOf(k) >= 0 ? ' required' : '') + '>';
        }).join('') + '<label><input type="checkbox" name="isDefault" ' + (a.isDefault ? 'checked' : '') + '> Make default</label><div id="err"></div>' +
        '<div class="row" style="margin-top:12px"><button class="btn grow">Save</button><button type="button" class="btn ghost" id="x">Cancel</button></div></form>');
      $('#x', m).onclick = () => m.close();
      $('#af', m).onsubmit = (e) => {
        e.preventDefault(); const f = e.target;
        const body = {}; ['label', 'fullName', 'streetAddress', 'city', 'state', 'country', 'zipCode', 'phoneNumber'].forEach((k) => { body[k] = f[k].value.trim(); });
        body.isDefault = f.isDefault.checked;
        G.busy($('button', f), async () => {
          try {
            const r = a._id ? await G.put('/users/addresses/' + a._id, body) : await G.post('/users/addresses', body);
            addrs = r.addresses || []; m.close(); draw();
          } catch (er) { $('#err', m).innerHTML = G.fail(er); }
        });
      };
    }
    function draw() {
      el.innerHTML = '<div class="narrow"><a href="#/more">← Account</a><div class="row between"><h1>Addresses</h1><button class="btn" id="add">+ Add</button></div>' +
        (addrs.length ? addrs.map((a) => '<div class="card"><div class="row between"><b>' + esc(a.label || a.fullName) + '</b>' + (a.isDefault ? '<span class="pill ok">Default</span>' : '') + '</div>' +
          '<div>' + esc(a.fullName) + '</div><div>' + esc(a.streetAddress) + ', ' + esc(a.city) + ', ' + esc(a.state) + ' ' + esc(a.zipCode || '') + '</div><div class="mute">' + esc(a.country) + ' · ' + esc(a.phoneNumber) + '</div>' +
          '<div class="row" style="margin-top:8px"><button class="btn sm sec" data-e="' + a._id + '">Edit</button><button class="btn sm ghost" data-d="' + a._id + '">Delete</button></div></div>').join('') : '<div class="empty">No saved addresses.</div>') + '</div>';
      $('#add', el).onclick = () => form();
      el.onclick = async (ev) => {
        const e = ev.target.dataset.e; const d = ev.target.dataset.d;
        if (e) form(addrs.find((x) => String(x._id) === e));
        if (d && (await G.confirm('Delete this address?'))) { try { addrs = (await G.del('/users/addresses/' + d)).addresses || []; draw(); } catch (er) { G.toast(G.errMsg(er)); } }
      };
    }
    draw();
  }, { auth: true });

  /* ---------- Wishlist ---------- */
  G.route('/wishlist', async (el) => {
    async function draw() {
      const items = (await G.get('/users/wishlist')).wishlist || [];
      G.wish = new Set(items.map((p) => String(p._id)));
      el.innerHTML = '<div class="narrow" style="max-width:none"><a href="#/more">← Account</a><h1>Wishlist</h1>' + (items.length ? '<div class="grid">' + items.map((p) =>
        '<div class="pcard"><a href="#/product/' + p._id + '">' + G.img(p.images && p.images[0]) + '</a><div class="b"><a class="name" href="#/product/' + p._id + '">' + esc(p.name) + '</a><div class="price">' + G.money(p.price) + '</div>' +
        '<div class="row between"><button class="btn sm" data-add="' + p._id + '">Add to cart</button><button class="btn sm ghost" data-rm="' + p._id + '">Remove</button></div></div></div>').join('') + '</div>'
        : '<div class="empty">Your wishlist is empty.</div>') + '</div>';
    }
    await draw();
    el.addEventListener('click', async (ev) => {
      const add = ev.target.closest('[data-add]'); const rm = ev.target.closest('[data-rm]');
      try {
        if (add) { await G.post('/market/cart/', { product_id: Number(add.dataset.add), quantity: 1 }); await G.refreshCart(); G.toast('Added to cart'); }
        if (rm) { await G.del('/users/wishlist/' + rm.dataset.rm); await draw(); }
      } catch (er) { G.toast(G.errMsg(er)); }
    });
  }, { auth: true });

  /* ---------- KYC ---------- */
  G.route('/kyc', async (el) => {
    await G.loadUser(); const u = G.user; const s = u.kyc_status;
    if (s === 'verified' || s === 'pending') {
      el.innerHTML = '<div class="narrow card center"><div style="font-size:44px">' + (s === 'verified' ? '✅' : '⏳') + '</div><h1>' + (s === 'verified' ? 'You are verified' : 'Under review') + '</h1><p class="mute">' +
        (s === 'verified' ? 'Your identity has been verified.' : 'Your documents were submitted. We will notify you once reviewed.') + '</p><a class="btn" href="#/more">Back</a></div>';
      return;
    }
    el.innerHTML = '<div class="narrow"><a href="#/more">← Account</a><h1>Identity verification</h1>' +
      (s === 'rejected' ? '<div class="alert bad">Your last submission was rejected' + (u.rejection_reason ? ': ' + esc(u.rejection_reason) : '') + '. Please resubmit.</div>' : '') +
      '<form class="card" id="f"><label>ID type</label><select name="t"><option>NIN</option><option>Voter Card</option><option>Driver License</option><option>International Passport</option></select>' +
      '<label>ID document photo</label><input name="id" type="file" accept="image/*" required><label>Selfie</label><input name="selfie" type="file" accept="image/*" required>' +
      '<div id="err" style="margin-top:10px"></div><button class="btn block" style="margin-top:12px">Submit for review</button></form></div>';
    $('#f', el).onsubmit = (e) => {
      e.preventDefault(); const f = e.target;
      G.busy($('button', f), async () => {
        const fd = new FormData();
        fd.append('id_document_type', f.t.value); fd.append('id_document_image', f.id.files[0]); fd.append('selfie_image', f.selfie.files[0]);
        try { await G.post('/users/kyc/upload/', fd); await G.loadUser(); G.toast('Documents uploaded'); G.go('#/kyc'); }
        catch (er) { $('#err', el).innerHTML = G.fail(er); }
      });
    };
  }, { auth: true });
  G.route('/kyc/upload', (el) => { G.go('#/kyc'); }, { auth: true });

  /* ---------- Chat ---------- */
  G.route('/chat', async (el) => {
    if (!G.loggedIn()) { el.innerHTML = '<div class="empty">Sign in to chat with buyers and sellers.<br><br><a class="btn" href="#/login">Sign in</a></div>'; return; }
    const convs = G.list(await G.get('/chat/inbox/'));
    el.innerHTML = '<div class="narrow"><h1>Messages</h1>' + (convs.length ? '<div class="card menu">' + convs.map((c) =>
      '<a href="#/chat/' + c.id + '"><span class="ic">' + (c.other_user_avatar ? '<img src="' + esc(c.other_user_avatar) + '" style="width:36px;height:36px;border-radius:50%;object-fit:cover" alt="">' : '👤') + '</span><span class="grow"><b>' + esc(c.other_user_name) +
      '</b>' + (c.product_name ? ' <span class="small mute">· ' + esc(c.product_name) + '</span>' : '') + '<div class="small mute">' + esc(c.last_message || 'No messages yet') + '</div></span>' +
      (c.unread_count ? '<span class="badge">' + c.unread_count + '</span>' : '') + '</a>').join('') + '</div>' : '<div class="empty">No conversations yet.<br>Message a seller from any product page.</div>') + '</div>';
  });

  G.route('/chat/with/:userId', async (el, ctx) => {
    const body = { user_id: Number(ctx.params.userId) };
    if (ctx.query.product) body.product_id = Number(ctx.query.product);
    try { const r = await G.post('/chat/start/', body); G.go('#/chat/' + r.conversation_id); }
    catch (e) { el.innerHTML = G.fail(e) + '<a class="btn ghost" href="#/chat">Back</a>'; }
  }, { auth: true });

  G.route('/chat/:id', async (el, ctx) => {
    const id = ctx.params.id; let lastId = 0; const seen = new Set();
    el.innerHTML = '<div class="narrow"><a href="#/chat">← Messages</a><div class="card"><div class="chat-box" id="box"></div>' +
      '<form class="row" id="f" style="margin-top:8px"><input class="grow" name="t" placeholder="Type a message…" autocomplete="off"><button class="btn">Send</button></form></div></div>';
    const box = $('#box', el);
    function add(m) {
      if (seen.has(m.id)) return; seen.add(m.id); lastId = Math.max(lastId, m.id);
      const mine = G.user && m.sender === G.user.id;
      const d = document.createElement('div'); d.className = 'msg' + (mine ? ' me' : '');
      d.innerHTML = esc(m.text) + '<div class="t">' + G.date(m.created_at) + '</div>'; box.appendChild(d);
    }
    async function poll(first) {
      try {
        const d = await G.get('/chat/conversations/' + id + '/messages/' + (lastId ? '?last_id=' + lastId : ''));
        const items = G.list(d); const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
        items.forEach(add);
        if (first || (items.length && atBottom)) box.scrollTop = box.scrollHeight;
        if (first && !items.length) box.innerHTML = '<div class="empty">Say hello 👋</div>';
        else if (items.length) { const e = $('.empty', box); if (e) e.remove(); }
      } catch (e) { if (first) box.innerHTML = G.fail(e); }
    }
    await poll(true);
    const timer = setInterval(() => poll(false), 4000);
    G.onLeave(() => clearInterval(timer));
    $('#f', el).onsubmit = async (e) => {
      e.preventDefault(); const inp = e.target.t; const text = inp.value.trim(); if (!text) return;
      inp.value = '';
      try { const m = await G.post('/chat/conversations/' + id + '/send/', { text }); if (m && m.id) { add(m); box.scrollTop = box.scrollHeight; } else await poll(false); }
      catch (er) { inp.value = text; G.toast(G.errMsg(er)); }
    };
  }, { auth: true });

  /* ---------- Help / privacy ---------- */
  G.route('/help', (el) => {
    el.innerHTML = '<div class="narrow"><h1>Help & support</h1><div class="card menu">' +
      '<a href="mailto:globalinkmarketplace@gmail.com"><span class="ic">✉</span><span class="grow"><b>Email us</b><div class="small mute">globalinkmarketplace@gmail.com</div></span></a>' +
      '<a href="https://wa.me/2348101293037" target="_blank" rel="noopener"><span class="ic">💬</span><span class="grow"><b>WhatsApp</b><div class="small mute">+234 810 129 3037</div></span></a>' +
      '<a href="tel:+2348101293037"><span class="ic">📞</span><span class="grow"><b>Call</b><div class="small mute">+234 810 129 3037</div></span></a>' +
      '<a href="mailto:globalinkmarketplace@gmail.com?subject=Web%20App%20Issue%20Report"><span class="ic">🐞</span><span class="grow"><b>Report an issue</b></span></a></div></div>';
  });
  G.route('/privacy-policy', (el) => {
    el.innerHTML = '<div class="narrow card"><h1>Privacy policy</h1><p>GLAPP collects the information needed to run the marketplace: your account details, orders, wallet activity, messages and any identity documents you submit for verification.</p>' +
      '<p>We use this information to process payments and deliveries, keep the platform safe and meet legal requirements. We do not sell your personal data.</p>' +
      '<p>You can update your profile at any time and request deletion of your account from <a href="#/security">Privacy & security</a> or <a href="/account-deletion/">this page</a>.</p>' +
      '<p>Questions? <a href="mailto:globalinkmarketplace@gmail.com">globalinkmarketplace@gmail.com</a></p></div>';
  });
})();
