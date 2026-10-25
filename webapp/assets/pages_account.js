/* GLAPP web client — auth, account, addresses, wishlist, KYC, chat, help. */
(function () {
  'use strict';
  const G = window.GL;
  const { esc, $, $$ } = G;

  /* ---------- Auth (auth/login, register, forgot-password) ---------- */
  const t = (...a) => G.t(...a);
  function afterAuth() {
    const next = G.session.get('gl_next');
    G.session.del('gl_next');
    if (G.isAdmin() && (!next || next === '#/login')) { G.go('#/admin'); return; }
    G.go(next && next !== '#/login' ? next : '#/');
  }
  const authHead = (icon, title, sub) => '<div class="authhead"><div class="authbox">' + G.icon(icon) + '</div><h1>' + esc(title) + '</h1><p>' + esc(sub) + '</p></div>';
  const field = (label, input) => '<div><label style="margin-top:0">' + esc(label) + '</label>' + input + '</div><div style="height:20px"></div>';

  G.route('/login', (el) => {
    if (G.loggedIn()) { G.go('#/'); return; }
    el.innerHTML = '<div class="authwrap">' + authHead('globe', t('welcome_back'), t('sign_in_account')) +
      '<form id="f">' + field(t('email_address'), '<input name="email" type="email" required autocomplete="email" placeholder="' + esc(t('email_placeholder')) + '">') +
      '<label style="margin-top:0">' + esc(t('password')) + '</label>' + G.pwField('password', t('password_placeholder')) +
      '<div style="text-align:right;margin:8px 0 24px"><a class="link small" href="#/forgot-password">' + esc(t('forgot_password')) + '</a></div>' +
      '<div id="err"></div><button class="btn lg block">' + esc(t('sign_in')) + '</button>' +
      '<div class="center" style="margin-top:16px"><a href="#/" id="skip" class="mute" style="font-weight:500">' + esc(t('skip_browse')) + '</a></div></form>' +
      '<div class="center" style="margin-top:16px"><span class="mute" style="font-weight:500">' + esc(t('no_account')) + ' </span><a class="link" href="#/register">' + esc(t('sign_up')) + '</a></div>' +
      '<div class="center" style="margin-top:16px">' + G.langSwitcher() + '</div></div>';
    $('#skip', el).onclick = () => G.session.set('gl_guest', '1');
    $('#f', el).onsubmit = (e) => {
      e.preventDefault(); const f = e.target;
      if (!f.email.value || !f.password.value) { $('#err', el).innerHTML = '<div class="alert bad">' + esc(t('fill_all_fields')) + '</div>'; return; }
      G.busy($('button', f), async () => {
        try { await G.login(f.email.value, f.password.value); G.session.del('gl_guest'); afterAuth(); }
        catch (er) { $('#err', el).innerHTML = '<div class="alert bad"><b>' + esc(t('authentication_failed')) + '</b><br>' + esc(er.status === 401 ? t('invalid_credentials') : G.errMsg(er)) + '</div>'; }
      });
    };
  });

  G.route('/register', (el) => {
    if (G.loggedIn()) { G.go('#/'); return; }
    el.innerHTML = '<div class="authwrap">' + authHead('userplus', t('create_account'), t('join_community')) +
      '<form id="f">' + field(t('full_name'), '<input name="full_name" required autocomplete="name" placeholder="' + esc(t('full_name_placeholder')) + '">') +
      field(t('email_address'), '<input name="email" type="email" required autocomplete="email" placeholder="' + esc(t('email_placeholder')) + '">') +
      field(t('phone_number'), '<input name="phone" type="tel" autocomplete="tel" placeholder="' + esc(t('phone_placeholder')) + '">') +
      '<label style="margin-top:0">' + esc(t('password')) + '</label>' + G.pwField('password', t('password_placeholder_create'), 'new-password') + '<div style="height:20px"></div>' +
      '<label style="margin-top:0">' + esc(t('confirm_password')) + '</label>' + G.pwField('confirm', t('confirm_password_placeholder'), 'new-password') + '<div style="height:24px"></div>' +
      '<div id="err"></div><button class="btn lg block">' + esc(t('create_account')) + '</button></form>' +
      '<div class="center" style="margin-top:24px"><span class="mute" style="font-weight:500">' + esc(t('have_account')) + ' </span><a class="link" href="#/login">' + esc(t('sign_in')) + '</a></div></div>';
    $('#f', el).onsubmit = (e) => {
      e.preventDefault(); const f = e.target; const bad = (m) => { $('#err', el).innerHTML = '<div class="alert bad">' + esc(m) + '</div>'; };
      const name = f.full_name.value.trim().replace(/\s+/g, ' ');
      if (!name || !f.email.value.trim() || !f.password.value) return bad(t('fill_required'));
      if (f.password.value !== f.confirm.value) return bad(t('passwords_no_match'));
      if (f.password.value.length < 8) return bad(t('password_too_short'));
      const parts = name.split(' ');
      G.busy($('button', f), async () => {
        try {
          await G.post('/users/register/', { email: f.email.value.trim(), password: f.password.value, first_name: parts[0], last_name: parts.slice(1).join(' ') }, { noAuth: true });
          await G.login(f.email.value, f.password.value); // register response carries no refresh token
          if (f.phone.value.trim()) { try { await G.patch('/users/profile/', { phone_number: f.phone.value.trim() }); } catch (x) { /* optional */ } }
          G.session.del('gl_guest'); G.toast(t('account_ready')); afterAuth();
        } catch (er) { bad(G.errMsg(er)); }
      });
    };
  });

  G.route('/forgot-password', (el) => {
    let email = '';
    function step1() {
      el.innerHTML = '<div class="authwrap">' + authHead('lock', t('forgot_password_title'), t('forgot_password_subtitle')) +
        '<form id="f">' + field(t('email_address'), '<input name="email" type="email" required placeholder="' + esc(t('email_placeholder')) + '">') + '<div id="err"></div>' +
        '<button class="btn lg block">' + esc(t('send_reset_code')) + '</button></form><div class="center" style="margin-top:20px"><a class="link" href="#/login">' + esc(t('back_to_login')) + '</a></div></div>';
      $('#f', el).onsubmit = (e) => {
        e.preventDefault();
        G.busy($('button', e.target), async () => {
          try { email = e.target.email.value.trim().toLowerCase(); await G.post('/users/password-reset/request/', { email }, { noAuth: true }); G.toast(t('code_sent_message')); step2(); }
          catch (er) { $('#err', el).innerHTML = G.fail(er); }
        });
      };
    }
    function step2() {
      el.innerHTML = '<div class="authwrap">' + authHead('lock', t('reset_password'), t('enter_code_subtitle')) +
        '<form id="f">' + field(t('otp_code'), '<input name="otp" inputmode="numeric" required maxlength="6" style="text-align:center;letter-spacing:8px;font-size:20px">') +
        '<label style="margin-top:0">' + esc(t('new_password')) + '</label>' + G.pwField('pw', t('new_password_placeholder'), 'new-password') + '<div style="height:20px"></div><div id="err"></div>' +
        '<button class="btn lg block">' + esc(t('reset_password')) + '</button></form><div class="center" style="margin-top:20px"><a class="link" href="#" id="resend">' + esc(t('resend_code')) + '</a></div></div>';
      $('#resend', el).onclick = async (e) => { e.preventDefault(); try { await G.post('/users/password-reset/request/', { email }, { noAuth: true }); G.toast(t('code_sent_message')); } catch (er) { G.toast(G.errMsg(er)); } };
      $('#f', el).onsubmit = (e) => {
        e.preventDefault();
        G.busy($('button', e.target), async () => {
          try { await G.post('/users/password-reset/confirm/', { email, otp: e.target.otp.value.trim(), new_password: e.target.pw.value }, { noAuth: true }); G.toast(t('password_reset_success')); G.go('#/login'); }
          catch (er) { $('#err', el).innerHTML = '<div class="alert bad">' + esc(er.status === 400 ? t('invalid_reset_code') : er.status === 429 ? t('too_many_attempts') : G.errMsg(er)) + '</div>'; }
        });
      };
    }
    step1();
  });

  /* ---------- More (tabs/more.tsx) ---------- */
  G.route('/more', async (el) => {
    const signed = G.loggedIn();
    const menu = [
      ['wishlist', 'heart', t('wishlist'), '#/wishlist'], ['address', 'pin', t('addresses'), '#/addresses'], ['market', 'grid', t('market'), '#/markets'],
      ['jobs', 'briefcase', t('jobs'), '#/jobs'], ['support', 'headset', t('support'), '#/help'], ['profile', 'user', t('profile'), '#/profile'],
      ['privacy', 'lock', t('privacy_security'), '#/security'], ['pp', 'file', t('privacy_policy'), '#/privacy-policy'],
    ];
    if (G.isAdmin()) menu.push(['admin', 'shield', t('admin_panel'), '#/admin']);
    const quick = [[t('orders'), 'bag', '#/orders', '#3B82F6', '#EFF6FF'], [t('wallet'), 'wallet', '#/wallet', '#F59E0B', '#FFFBEB'], [t('cart'), 'cart', '#/cart', '#8B5CF6', '#F5F3FF']];
    el.innerHTML = '<h1 style="margin-bottom:20px">' + esc(t('more')) + '</h1>' +
      '<button class="shopcard" id="shop"><span class="ib">' + G.icon('store') + '</span><span class="grow"><b>' + esc(t('my_shop')) + '</b><span>' + esc(t('my_shop_subtitle')) + '</span></span>' + G.icon('right', 22) + '</button>' +
      '<div class="quick">' + quick.map((q) => '<a href="' + q[2] + '" style="background:' + q[4] + ';box-shadow:0 3px 6px ' + q[3] + '20"><div class="ib" style="color:' + q[3] + '">' + G.icon(q[1]) + '</div>' + esc(q[0]) + '</a>').join('') + '</div>' +
      G.kycBanner() +
      '<div class="menu">' + menu.map((m) => '<a href="' + m[3] + '"><span class="ic">' + G.icon(m[1]) + '</span><span class="grow">' + esc(m[2]) + '</span>' + G.icon('right').replace('<svg', '<svg class="chev"') + '</a>').join('') + '</div>' +
      '<div class="card" style="border-radius:16px;margin-top:24px;padding:16px 20px"><div class="row" style="flex-wrap:nowrap;margin-bottom:6px"><span class="ic" style="width:40px;height:40px;border-radius:12px;background:#F9FAFB;color:var(--primary);display:flex;align-items:center;justify-content:center">' + G.icon('globe', 20) + '</span><b style="font-size:16px">' + esc(t('language')) + '</b></div>' + G.langSwitcher() + '</div>' +
      (signed ? '<button class="sbtn out" id="out">' + G.icon('logout') + esc(t('sign_out')) + '</button>'
        : '<a class="btn lg block" href="#/login">' + G.icon('user', 20) + esc(t('sign_in_continue')) + '</a>') +
      (signed ? '<button class="sbtn dng" id="del" style="margin-top:16px">' + esc(t('delete_account')) + '</button>' : '') +
      '<div class="ver">' + esc(t('version')) + '</div>';
    $('#shop', el).onclick = async (e) => {
      if (!signed) return G.requireLogin();
      const b = e.currentTarget; b.style.opacity = '.7';
      try { const r = await G.get('/market/shop/my-status/'); G.go(r.status === 'approved' || r.status === 'pending' ? '#/merchant' : '#/merchant/onboarding'); }
      catch (er) { G.toast('Unable to load shop. Please check your connection and try again.'); b.style.opacity = ''; }
    };
    const o = $('#out', el); if (o) o.onclick = () => G.logout();
    const d = $('#del', el);
    if (d) d.onclick = async () => {
      if (!(await G.confirm(t('delete_account_title') + '\n\n' + t('delete_account_msg')))) return;
      try { await G.post('/users/request-deletion/'); alert(t('deletion_submitted') + '\n' + t('deletion_email')); } catch (e) { G.toast(G.errMsg(e)); }
    };
  });

  /* ---------- Profile ---------- */
  G.route('/profile', async (el) => {
    await G.loadUser();
    const u = G.user;
    el.innerHTML = '<div>' + G.head('My profile', '#/more') + '<form class="card" id="f">' +
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
    el.innerHTML = '<div>' + G.head('Privacy & security', '#/more') + '' +
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
      el.innerHTML = '<div>' + G.back('#/more') + '<div class="row between"><h1>Addresses</h1><button class="btn" id="add">+ Add</button></div>' +
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
      el.innerHTML = '<div>' + G.head('Wishlist', '#/more') + '' + (items.length ? '<div class="grid">' + items.map((p) =>
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
      el.innerHTML = '<div class="card center"><div style="font-size:44px">' + (s === 'verified' ? '✅' : '⏳') + '</div><h1>' + (s === 'verified' ? 'You are verified' : 'Under review') + '</h1><p class="mute">' +
        (s === 'verified' ? 'Your identity has been verified.' : 'Your documents were submitted. We will notify you once reviewed.') + '</p><a class="btn" href="#/more">Back</a></div>';
      return;
    }
    el.innerHTML = '<div>' + G.head('Identity verification', '#/more') + '' +
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
  const AV = ['#329629', '#3B82F6', '#8B5CF6', '#F59E0B', '#EF4444', '#0EA5E9', '#EC4899'];
  function timeAnchor(iso) {
    if (!iso) return '';
    const d = new Date(iso); const now = new Date();
    if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }
  G.route('/chat', async (el) => {
    if (!G.loggedIn()) { el.innerHTML = '<h1>' + esc(t('chats')) + '</h1>' + G.emptyState('chat', t('login_required'), t('login_cart_msg'), '<a class="btn lg" href="#/login">' + esc(t('login')) + '</a>'); return; }
    const convs = G.list(await G.get('/chat/inbox/'));
    el.innerHTML = '<h1>' + esc(t('chats')) + '</h1>' + (convs.length ? convs.map((c) => {
      const nm = c.other_user_name || '?';
      return '<a class="inbox" href="#/chat/' + c.id + '">' + (c.other_user_avatar ? '<img class="avatar" src="' + esc(c.other_user_avatar) + '" alt="">' : '<span class="avatar" style="background:' + AV[(nm.charCodeAt(0) || 0) % AV.length] + '">' + esc(nm.charAt(0).toUpperCase()) + '</span>') +
        '<div class="grow"><div class="row between" style="flex-wrap:nowrap"><b class="name">' + esc(nm) + '</b><span class="small mute" style="font-size:11px">' + esc(timeAnchor(c.updated_at)) + '</span></div>' +
        '<div class="row between" style="flex-wrap:nowrap"><span class="small mute name" style="font-weight:' + (c.unread_count ? 700 : 500) + '">' + esc(c.last_message || 'No messages yet') + '</span>' + (c.unread_count ? '<span class="badge inline">' + (c.unread_count > 99 ? '99+' : c.unread_count) + '</span>' : '') + '</div></div></a>';
    }).join('') : G.emptyState('chat', 'No conversations yet', 'Message a seller from any product page.'));
  });

  G.route('/chat/with/:userId', async (el, ctx) => {
    const body = { user_id: Number(ctx.params.userId) };
    if (ctx.query.product) body.product_id = Number(ctx.query.product);
    try { const r = await G.post('/chat/start/', body); G.go('#/chat/' + r.conversation_id); }
    catch (e) { el.innerHTML = G.fail(e) + '<a class="btn ghost" href="#/chat">Back</a>'; }
  }, { auth: true });

  G.route('/chat/:id', async (el, ctx) => {
    const id = ctx.params.id; let lastId = 0; const seen = new Set();
    el.innerHTML = '<div>' + G.back('#/chat') + '<div class="card"><div class="chat-box" id="box"></div>' +
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
    el.innerHTML = '<div><h1>Help & support</h1><div class="card menu">' +
      '<a href="mailto:globalinkmarketplace@gmail.com"><span class="ic">✉</span><span class="grow"><b>Email us</b><div class="small mute">globalinkmarketplace@gmail.com</div></span></a>' +
      '<a href="https://wa.me/2348101293037" target="_blank" rel="noopener"><span class="ic">💬</span><span class="grow"><b>WhatsApp</b><div class="small mute">+234 810 129 3037</div></span></a>' +
      '<a href="tel:+2348101293037"><span class="ic">📞</span><span class="grow"><b>Call</b><div class="small mute">+234 810 129 3037</div></span></a>' +
      '<a href="mailto:globalinkmarketplace@gmail.com?subject=Web%20App%20Issue%20Report"><span class="ic">🐞</span><span class="grow"><b>Report an issue</b></span></a></div></div>';
  });
  G.route('/privacy-policy', (el) => {
    el.innerHTML = '<div class="card"><h1>Privacy policy</h1><p>GLAPP collects the information needed to run the marketplace: your account details, orders, wallet activity, messages and any identity documents you submit for verification.</p>' +
      '<p>We use this information to process payments and deliveries, keep the platform safe and meet legal requirements. We do not sell your personal data.</p>' +
      '<p>You can update your profile at any time and request deletion of your account from <a href="#/security">Privacy & security</a> or <a href="/account-deletion/">this page</a>.</p>' +
      '<p>Questions? <a href="mailto:globalinkmarketplace@gmail.com">globalinkmarketplace@gmail.com</a></p></div>';
  });
})();
