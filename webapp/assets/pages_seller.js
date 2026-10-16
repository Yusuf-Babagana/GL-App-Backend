/* GLAPP web client — merchant: onboarding, dashboard, products, store, seller orders, promotions. */
(function () {
  'use strict';
  const G = window.GL;
  const { esc, money, $, $$ } = G;

  /* ---------- Onboarding ---------- */
  G.route('/merchant/onboarding', async (el) => {
    const st = await G.get('/market/shop/my-status/');
    if (st.status === 'approved') { G.go('#/merchant'); return; }
    if (st.status === 'pending') { G.go('#/merchant/pending'); return; }
    const u = G.user || {};
    el.innerHTML = '<div class="narrow"><a href="#/more">← Account</a><h1>Become a seller</h1><form class="card" id="f">' +
      '<h2>Your details</h2><label>Full name</label><input name="owner_name" required value="' + esc(u.full_name || '') + '">' +
      '<label>Email</label><input name="owner_email" type="email" required value="' + esc(u.email || '') + '"><label>Phone</label><input name="owner_phone" required inputmode="tel" value="' + esc(u.phone_number || '') + '">' +
      '<label>ID type</label><select name="id_type"><option>NIN</option><option>Voter Card</option><option>Driver License</option><option>International Passport</option></select>' +
      '<label>ID number</label><input name="id_number" required><label>ID photo (optional)</label><input name="id_image" type="file" accept="image/*">' +
      '<h2 style="margin-top:18px">Your shop</h2><label>Shop name</label><input name="shop_name" required><div id="nm" class="small"></div>' +
      '<label>Shop type</label><select name="shop_type"><option value="retailer">Retailer</option><option value="wholesaler">Wholesaler</option><option value="manufacturer">Manufacturer</option><option value="service">Service</option></select>' +
      '<label>Business phone</label><input name="business_phone" inputmode="tel"><label>Shop address</label><input name="shop_address" required>' +
      '<div class="row"><div class="grow"><label>State</label><input name="state" value="Kano"></div><div class="grow"><label>Country</label><input name="country" value="Nigeria"></div></div>' +
      '<label>Registered business?</label><select name="registered"><option value="no">No</option><option value="yes">Yes</option></select><label>CAC number (if registered)</label><input name="cac_number">' +
      '<label>Shop logo</label><input name="logo" type="file" accept="image/*"><div id="err" style="margin-top:10px"></div>' +
      '<button class="btn block" style="margin-top:12px">Submit application</button></form></div>';
    const f = $('#f', el);
    let nameTimer;
    f.shop_name.oninput = () => {
      clearTimeout(nameTimer);
      nameTimer = setTimeout(async () => {
        const v = f.shop_name.value.trim(); const out = $('#nm', el);
        if (v.length < 2) { out.textContent = ''; return; }
        try { const r = await G.get('/market/store/check-name/?name=' + encodeURIComponent(v)); out.innerHTML = r.available ? '<span style="color:var(--ok)">✓ Available</span>' : '<span style="color:var(--bad)">' + esc(r.message) + '</span>'; }
        catch (e) { out.textContent = ''; }
      }, 400);
    };
    f.onsubmit = (e) => {
      e.preventDefault();
      G.busy($('button', f), async () => {
        const fd = new FormData();
        ['owner_name', 'owner_email', 'owner_phone', 'id_type', 'id_number', 'shop_name', 'shop_type', 'business_phone', 'shop_address', 'state', 'country', 'registered', 'cac_number'].forEach((k) => fd.append(k, f[k].value.trim()));
        if (f.id_image.files[0]) fd.append('id_image', f.id_image.files[0]);
        if (f.logo.files[0]) fd.append('logo', f.logo.files[0]);
        try {
          const r = await G.post('/market/store/global-onboard/', fd);
          await G.loadUser();
          G.toast(r.status === 'exists' ? 'You already have a shop registration' : 'Application received');
          G.go('#/merchant/pending');
        } catch (er) { $('#err', el).innerHTML = G.fail(er); }
      });
    };
  }, { auth: true });

  G.route('/merchant/pending', async (el) => {
    const st = await G.get('/market/shop/my-status/');
    if (st.status === 'approved') { G.go('#/merchant'); return; }
    el.innerHTML = '<div class="narrow card center"><div style="font-size:44px">⏳</div><h1>' + (st.status === 'pending' ? 'Application under review' : 'No application yet') + '</h1><p class="mute">' +
      (st.status === 'pending' ? 'Your shop will open once an administrator activates it. We will notify you.' : 'Start your seller application to open a shop.') + '</p>' +
      (st.status === 'none' ? '<a class="btn" href="#/merchant/onboarding">Apply now</a>' : '<a class="btn" href="#/more">Back</a>') + '</div>';
  }, { auth: true });
  G.route('/merchant/success', (el) => { G.go('#/merchant/pending'); }, { auth: true });

  /* Gate: every merchant page needs an approved shop. */
  async function requireShop(el) {
    const st = await G.get('/market/shop/my-status/');
    if (st.status === 'approved') return true;
    G.go(st.status === 'pending' ? '#/merchant/pending' : '#/merchant/onboarding');
    return false;
  }

  /* ---------- Dashboard ---------- */
  G.route('/merchant', async (el) => {
    if (!(await requireShop(el))) return;
    const [an, prods, orders, wallet] = await Promise.all([
      G.get('/market/merchant/analytics/'), G.get('/market/seller/products/').catch(() => []), G.get('/market/seller/orders/').catch(() => []), G.get('/finance/wallet/').catch(() => ({})),
    ]);
    const st = an.stats || {}; const products = G.list(prods); const ords = G.list(orders);
    el.innerHTML = '<div class="row between"><h1>' + esc(an.shop_name || 'My shop') + '</h1><div class="row"><a class="btn sec sm" href="#/merchant/edit-store">Edit store</a><a class="btn sm" href="#/merchant/add-product">+ Add product</a></div></div>' +
      '<div class="row" style="margin-bottom:14px">' +
      [['Sales', st.total_sales], ['Orders', st.total_orders], ['Items sold', st.products_sold], ['Customers', st.new_customers], ['Available', money(wallet.available_balance)], ['In escrow', money(wallet.locked_balance)]].map((s) => '<div class="stat"><div class="small mute">' + s[0] + '</div><div class="v">' + esc(s[1] == null ? '—' : s[1]) + '</div></div>').join('') + '</div>' +
      '<div class="row" style="margin-bottom:14px"><a class="btn ghost" href="#/merchant/withdraw">Withdraw earnings</a><a class="btn ghost" href="#/promote">Promote a post</a><a class="btn ghost" href="#/seller/orders">All orders</a></div>' +
      ((st.top_products || []).length ? '<div class="card"><h2>Top products</h2>' + st.top_products.map((p) => '<div class="item"><div class="grow"><b>' + esc(p.name) + '</b><div class="small mute">' + p.sales_count + ' sold · ' + p.stock + ' left</div></div><span class="pill">' + p.percentage + '%</span></div>').join('') + '</div>' : '') +
      '<div class="card"><h2>Recent orders</h2>' + (ords.length ? ords.slice(0, 5).map((o) => '<a class="item" style="color:inherit" href="#/seller/orders/' + o.id + '"><div class="grow"><b>#' + esc(o.order_number || o.id) + '</b> · ' + esc(o.buyer_name || '') + '<div class="small mute">' + G.date(o.created_at) + '</div></div><div class="right"><b>' + money(o.total_price) + '</b><div>' + G.statusPill(o.delivery_status) + '</div></div></a>').join('') : '<div class="empty">No orders yet.</div>') + '</div>' +
      '<div class="card"><h2>My products (' + products.length + ')</h2>' + (products.length ? products.map((p) => '<div class="item">' + G.img(G.pimg(p)) + '<div class="grow"><a href="#/product/' + p.id + '"><b>' + esc(p.name) + '</b></a><div class="small mute">' + money(p.price) + ' · stock ' + p.stock + '</div></div>' +
        '<a class="btn sm sec" href="#/merchant/edit-product/' + p.id + '">Edit</a><button class="btn sm ghost" data-del="' + p.id + '">Delete</button></div>').join('') : '<div class="empty">No products yet.<br><br><a class="btn" href="#/merchant/add-product">Add your first product</a></div>') + '</div>';
    el.onclick = async (ev) => {
      const d = ev.target.dataset.del; if (!d) return;
      if (!(await G.confirm('Delete this product?'))) return;
      try { await G.del('/market/seller/products/' + d + '/delete/'); G.toast('Product deleted'); G.go('#/merchant?' + Date.now()); } catch (e) { G.toast(G.errMsg(e)); }
    };
  }, { auth: true });

  /* ---------- Product form (add + edit) ---------- */
  async function productForm(el, existing) {
    if (!(await requireShop(el))) return;
    const cats = G.list(await G.get('/market/categories/', { noAuth: true }));
    const p = existing || {};
    const curImg = G.pimg(p); const curVid = p.video_url || '';
    el.innerHTML = '<div class="narrow"><a href="#/merchant">← Dashboard</a><h1>' + (existing ? 'Edit product' : 'Add product') + '</h1><form class="card" id="f">' +
      '<label>Name</label><input name="name" required value="' + esc(p.name || '') + '"><label>Description</label><textarea name="description">' + esc(p.description || '') + '</textarea>' +
      '<div class="row"><div class="grow"><label>Price (₦)</label><input name="price" type="number" min="0" step="0.01" required value="' + esc(p.price || '') + '"></div><div class="grow"><label>Stock</label><input name="stock" type="number" min="0" required value="' + esc(p.stock != null ? p.stock : 1) + '"></div></div>' +
      '<label>Category</label><select name="category"><option value="">None</option>' + cats.map((c) => '<option value="' + c.id + '"' + (String(p.category) === String(c.id) ? ' selected' : '') + '>' + esc(c.name) + '</option>').join('') + '</select>' +
      '<label>Photo</label>' + (curImg ? '<img src="' + esc(curImg) + '" style="width:90px;height:90px;object-fit:cover;border-radius:10px;display:block;margin-bottom:6px" alt="">' : '') + '<input name="image" type="file" accept="image/*">' +
      '<label>Video ad (optional)</label>' + (curVid ? '<div class="small mute">A video is attached. Choose a new file to replace it.</div>' : '') + '<input name="video" type="file" accept="video/*">' +
      '<div id="err" style="margin-top:10px"></div><button class="btn block" style="margin-top:12px">' + (existing ? 'Save changes' : 'Publish') + '</button></form></div>';
    const f = $('#f', el);
    f.onsubmit = (e) => {
      e.preventDefault();
      G.busy($('button', f), async () => {
        try {
          const body = { name: f.elements.name.value.trim(), description: f.description.value.trim(), price: parseFloat(f.price.value) || 0, stock: parseInt(f.stock.value, 10) || 0, category: f.category.value ? Number(f.category.value) : null };
          if (f.image.files[0]) { G.toast('Uploading photo…'); body.image = await G.upload(f.image.files[0], false); }
          else if (!existing) body.image = null;
          if (f.video.files[0]) { G.toast('Uploading video…'); body.video_url = await G.upload(f.video.files[0], true); }
          else if (!existing) body.video_url = null;
          if (existing) await G.patch('/market/seller/products/' + p.id + '/', body);
          else await G.post('/market/seller/products/add/', body);
          G.toast(existing ? 'Product updated' : 'Product published');
          G.go('#/merchant');
        } catch (er) { $('#err', el).innerHTML = G.fail(er); }
      });
    };
  }
  G.route('/merchant/add-product', (el) => productForm(el, null), { auth: true });
  G.route('/merchant/edit-product/:id', async (el, ctx) => productForm(el, await G.get('/market/products/' + ctx.params.id + '/')), { auth: true });

  /* ---------- Store settings ---------- */
  G.route('/merchant/edit-store', async (el) => {
    if (!(await requireShop(el))) return;
    const s = await G.get('/market/store/detail/');
    el.innerHTML = '<div class="narrow"><a href="#/merchant">← Dashboard</a><h1>Edit store</h1><form class="card" id="f">' +
      (s.logo ? '<img src="' + esc(s.logo) + '" style="width:80px;height:80px;object-fit:cover;border-radius:12px" alt="">' : '') +
      '<label>Store name</label><input name="name" required value="' + esc(s.name || '') + '"><label>Description</label><textarea name="description">' + esc(s.description || '') + '</textarea>' +
      '<label>New logo</label><input name="logo" type="file" accept="image/*"><div id="err" style="margin-top:10px"></div><button class="btn block" style="margin-top:12px">Save</button></form></div>';
    const f = $('#f', el);
    f.onsubmit = (e) => {
      e.preventDefault();
      G.busy($('button', f), async () => {
        try {
          const body = { name: f.elements.name.value.trim(), description: f.description.value.trim() };
          if (f.logo.files[0]) body.logo = await G.upload(f.logo.files[0], false);
          await G.patch('/market/store/update/', body); G.toast('Store updated'); G.go('#/merchant');
        } catch (er) { $('#err', el).innerHTML = G.fail(er); }
      });
    };
  }, { auth: true });
  G.route('/merchant/withdraw', (el) => G.withdrawPage(el), { auth: true });

  /* ---------- Seller orders ---------- */
  G.route('/seller/orders', async (el) => {
    const orders = G.list(await G.get('/market/seller/orders/'));
    el.innerHTML = '<a href="#/merchant">← Dashboard</a><h1>Customer orders</h1>' + (orders.length ? orders.map((o) =>
      '<a class="card" style="display:block;color:inherit" href="#/seller/orders/' + o.id + '"><div class="row between"><b>#' + esc(o.order_number || o.id) + '</b><span class="price">' + money(o.total_price) + '</span></div>' +
      '<div class="small mute">' + esc(o.buyer_name || '') + ' · ' + G.date(o.created_at) + '</div><div style="margin-top:6px">' + G.statusPill(o.delivery_status) + ' ' + G.statusPill(o.payment_status) + '</div></a>').join('') : '<div class="empty">No orders yet.</div>');
  }, { auth: true });

  G.route('/seller/orders/:id', async (el, ctx) => {
    const o = await G.get('/market/seller/orders/' + ctx.params.id + '/');
    const sa = o.shipping_address_json || {}; const paid = o.payment_status === 'paid';
    el.innerHTML = '<div class="narrow"><a href="#/seller/orders">← Orders</a><h1>Order #' + esc(o.order_number || o.id) + '</h1>' +
      '<div class="card"><div>' + G.statusPill(o.delivery_status) + ' ' + G.statusPill(o.payment_status) + '</div><div class="small mute" style="margin-top:6px">' + G.date(o.created_at) + '</div></div>' +
      '<div class="card"><h2>Items</h2>' + (o.items || []).map((i) => '<div class="item"><div class="grow">' + esc(i.product_name) + '<div class="small mute">Qty ' + i.quantity + ' × ' + money(i.price) + '</div></div><b>' + money(i.quantity * i.price) + '</b></div>').join('') + '<div class="row between"><b>Total</b><b class="price">' + money(o.total_price) + '</b></div></div>' +
      '<div class="card"><h2>Buyer</h2><div>' + esc(o.buyer_name || '') + '</div><div class="small mute">' + esc(o.buyer_email || '') + '</div><div>' + (o.buyer_phone ? '<a href="tel:' + esc(o.buyer_phone) + '">' + esc(o.buyer_phone) + '</a>' : '') + '</div>' +
      '<h3 style="margin-top:10px">Ship to</h3><div>' + esc(sa.address || '') + ', ' + esc(sa.city || '') + '</div><div>' + esc(sa.phone || '') + '</div></div>' +
      '<div class="row">' + (paid && o.delivery_status === 'pending' ? '<button class="btn sec" id="rdy">Ready for pickup</button><button class="btn" id="ship">Mark as shipped</button>' : '') +
      (paid && o.delivery_status === 'ready_for_pickup' ? '<button class="btn" id="ship">Mark as shipped</button>' : '') + '</div></div>';
    const act = (id, fn) => { const b = $(id, el); if (b) b.onclick = () => G.busy(b, async () => { try { await fn(); G.toast('Order updated'); G.go('#/seller/orders'); } catch (e) { G.toast(G.errMsg(e)); } }); };
    act('#rdy', () => G.post('/market/seller/orders/status-change/' + o.id + '/', { status: 'ready_for_pickup' }));
    act('#ship', () => G.post('/market/seller/orders/' + o.id + '/dispatch/'));
  }, { auth: true });
  G.route('/orders/seller/:id', (el, ctx) => { G.go('#/seller/orders/' + ctx.params.id); }, { auth: true });

  /* ---------- Promoted posts ---------- */
  G.route('/promote', async (el) => {
    const [pricing, cats, prods] = await Promise.all([G.get('/market/promoted-posts/pricing/', { noAuth: true }).catch(() => []), G.get('/market/categories/', { noAuth: true }).catch(() => []), G.get('/market/seller/products/').catch(() => [])]);
    const tiers = G.list(pricing); const products = G.list(prods); const categories = G.list(cats);
    el.innerHTML = '<div class="narrow"><a href="#/more">← Account</a><h1>Promote a post</h1><p class="mute">Your promotion appears in the home ticker. The fee is taken from your wallet.</p><form class="card" id="f">' +
      '<div class="tabs"><span class="chip on" data-t="product">My product</span><span class="chip" data-t="standalone">Other item</span></div>' +
      '<div id="prodBox"><label>Product</label><select name="product">' + (products.length ? products.map((p) => '<option value="' + p.id + '">' + esc(p.name) + '</option>').join('') : '<option value="">No products — use "Other item"</option>') + '</select></div>' +
      '<div id="saBox" style="display:none"><label>Title</label><input name="title"><label>Description</label><textarea name="description"></textarea><label>Price (₦)</label><input name="price" type="number" min="0">' +
      '<label>Location</label><input name="location"><label>Phone</label><input name="phone_number" inputmode="tel"><label>Category</label><select name="category"><option value="">None</option>' + categories.map((c) => '<option value="' + c.id + '">' + esc(c.name) + '</option>').join('') + '</select>' +
      '<label>Photos</label><input name="images" type="file" accept="image/*" multiple></div>' +
      '<label>Promo text</label><textarea name="text_content" required maxlength="280" placeholder="What do you want people to see?"></textarea>' +
      '<label>Duration</label><select name="duration_type">' + tiers.map((t) => '<option value="' + esc(t.duration_type) + '">' + esc(t.label) + ' — ' + money(t.price) + '</option>').join('') + '</select>' +
      '<div id="err" style="margin-top:10px"></div><button class="btn block" style="margin-top:12px">Pay & publish</button></form></div>';
    const f = $('#f', el); let type = 'product';
    $$('.tabs .chip', el).forEach((c) => { c.onclick = () => { type = c.dataset.t; $$('.tabs .chip', el).forEach((x) => x.classList.toggle('on', x === c)); $('#prodBox', el).style.display = type === 'product' ? '' : 'none'; $('#saBox', el).style.display = type === 'standalone' ? '' : 'none'; }; });
    f.onsubmit = (e) => {
      e.preventDefault();
      G.busy($('button', f), async () => {
        try {
          const body = { text_content: f.text_content.value.trim(), duration_type: f.duration_type.value, promotion_type: type };
          if (type === 'product') { if (!f.product.value) throw new Error('Select a product to promote.'); body.product = Number(f.product.value); }
          else {
            if (!f.title.value.trim()) throw new Error('Give your item a title.');
            Object.assign(body, { title: f.title.value.trim(), description: f.description.value.trim(), location: f.location.value.trim() });
            if (f.price.value) body.price = Number(f.price.value);
            if (f.phone_number.value.trim()) body.phone_number = f.phone_number.value.trim();
            if (f.category.value) body.category = Number(f.category.value);
            const files = Array.from(f.images.files || []); if (files.length) { G.toast('Uploading photos…'); body.images = await Promise.all(files.map((x) => G.upload(x, false))); }
          }
          const r = await G.post('/market/promoted-posts/', body);
          const share = r && r.data && r.data.share_url;
          el.innerHTML = '<div class="narrow card center"><div style="font-size:44px">🎉</div><h1>Your promotion is live</h1>' + (share ? '<p>Share this link:</p><input readonly value="' + esc(share) + '" onclick="this.select()">' : '') + '<br><a class="btn" href="#/">See it on home</a></div>';
        } catch (er) { $('#err', el).innerHTML = G.fail(er); }
      });
    };
  }, { auth: true });
  G.route('/promoted-post/create', (el) => { G.go('#/promote'); }, { auth: true });
})();
