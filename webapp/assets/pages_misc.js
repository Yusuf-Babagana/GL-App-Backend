/* GLAPP web client — jobs and admin tools. */
(function () {
  'use strict';
  const G = window.GL;
  const { esc, $, $$ } = G;

  /* ---------- Jobs ---------- */
  const JOB_TYPES = ['full_time', 'part_time', 'contract', 'freelance'];
  const jobBudget = (j) => (j.budget ? j.currency + ' ' + Number(j.budget).toLocaleString() + (j.is_negotiable ? ' (negotiable)' : '') : 'Budget not set');

  G.route('/jobs', async (el, ctx) => {
    const tab = ctx.query.tab || 'browse'; const q = ctx.query.q || '';
    const tabs = [['browse', 'Browse jobs']];
    if (G.loggedIn()) tabs.push(['applied', 'My applications'], ['employer', 'Employer'], ['profile', 'My CV']);
    el.innerHTML = '<h1>Jobs</h1><div class="tabs">' + tabs.map((t) => '<a class="chip ' + (t[0] === tab ? 'on' : '') + '" href="#/jobs?tab=' + t[0] + '">' + t[1] + '</a>').join('') + '</div><div id="body">' + G.loading + '</div>';
    const body = $('#body', el);

    if (tab === 'browse') {
      body.innerHTML = '<form id="sf" class="row" style="margin-bottom:12px"><input class="grow" name="q" placeholder="Search jobs…" value="' + esc(q) + '"><button class="btn">Search</button></form><div id="list">' + G.loading + '</div><div class="center" id="m"></div>';
      $('#sf', body).onsubmit = (e) => { e.preventDefault(); G.go('#/jobs?tab=browse&q=' + encodeURIComponent(e.target.q.value.trim())); };
      let page = 1;
      const load = async () => {
        const d = await G.get('/jobs/list/?page=' + page + (q ? '&search=' + encodeURIComponent(q) : ''), { noAuth: !G.loggedIn() });
        const items = G.list(d);
        if (page === 1) $('#list', body).innerHTML = '';
        if (page === 1 && !items.length) $('#list', body).innerHTML = '<div class="empty">No open jobs found.</div>';
        $('#list', body).insertAdjacentHTML('beforeend', items.map((j) => '<a class="card" style="display:block;color:inherit" href="#/jobs/' + j.id + '"><div class="row between"><b>' + esc(j.title) + '</b><span class="pill">' + esc(G.pretty(j.job_type)) + '</span></div>' +
          '<div class="small mute">' + esc(j.employer_name) + ' · ' + esc(j.location) + '</div><div class="price">' + esc(jobBudget(j)) + '</div></a>').join(''));
        $('#m', body).innerHTML = d && d.next ? '<button class="btn ghost" id="mb">Load more</button>' : '';
        const b = $('#mb', body); if (b) b.onclick = () => G.busy(b, async () => { page += 1; await load(); });
      };
      await load();
    } else if (tab === 'applied') {
      const apps = G.list(await G.get('/jobs/applications/mine/'));
      body.innerHTML = apps.length ? apps.map((a) => '<a class="card" style="display:block;color:inherit" href="#/jobs/' + a.job + '"><div class="row between"><b>' + esc(a.job_title) + '</b><span class="pill ' + (a.status === 'hired' ? 'ok' : a.status === 'rejected' ? 'bad' : 'warn') + '">' + esc(G.pretty(a.status)) + '</span></div><div class="small mute">Applied ' + G.date(a.created_at) + '</div></a>').join('') : '<div class="empty">You have not applied to any jobs yet.</div>';
    } else if (tab === 'employer') {
      if (!G.hasRole('employer')) {
        body.innerHTML = '<div class="card center"><p>Become an employer to post jobs and review applicants.</p><button class="btn" id="be">Become an employer</button></div>';
        $('#be', body).onclick = (e) => G.busy(e.currentTarget, async () => { try { await G.post('/users/roles/add/', { role: 'employer' }); await G.loadUser(); G.go('#/jobs?tab=employer&r=' + Date.now()); } catch (er) { G.toast(G.errMsg(er)); } });
        return;
      }
      const apps = G.list(await G.get('/jobs/applications/received/'));
      body.innerHTML = '<p><a class="btn" href="#/jobs/post">+ Post a job</a></p><h2>Applications received</h2>' + (apps.length ? apps.map((a) => '<div class="card"><div class="row between"><b>' + esc(a.seeker_name) + '</b><span class="pill">' + esc(G.pretty(a.status)) + '</span></div>' +
        '<div class="small mute">' + esc(a.seeker_email) + ' · for ' + esc(a.job_title) + ' · ' + G.date(a.created_at) + '</div><p>' + esc(a.cover_letter || '') + '</p></div>').join('') : '<div class="empty">No applications yet.</div>');
    } else if (tab === 'profile') {
      const p = await G.get('/jobs/profile/me/');
      body.innerHTML = '<form class="card" id="pf"><h2>My CV</h2><label>Skills (comma separated)</label><input name="skills" value="' + esc((p.skills || []).join(', ')) + '"><label>Portfolio URL</label><input name="portfolio_url" type="url" value="' + esc(p.portfolio_url || '') + '">' +
        (p.resume ? '<p class="small"><a href="' + esc(p.resume) + '" target="_blank" rel="noopener">Current resume</a></p>' : '') + '<label>Upload resume</label><input name="resume" type="file"><div id="err" style="margin-top:10px"></div><button class="btn block" style="margin-top:12px">Save</button></form>' +
        (G.hasRole('job_seeker') ? '' : '<div class="card center"><p>Add the Job Seeker role to apply for jobs.</p><button class="btn" id="bs">Become a job seeker</button></div>');
      $('#pf', body).onsubmit = (e) => {
        e.preventDefault(); const f = e.target;
        G.busy($('button', f), async () => {
          try {
            const skills = f.skills.value.split(',').map((s) => s.trim()).filter(Boolean);
            if (f.resume.files[0]) { const fd = new FormData(); skills.forEach((s) => fd.append('skills', s)); fd.append('portfolio_url', f.portfolio_url.value.trim()); fd.append('resume', f.resume.files[0]); await G.patch('/jobs/profile/me/', fd); }
            else await G.patch('/jobs/profile/me/', { skills, portfolio_url: f.portfolio_url.value.trim() || null });
            G.toast('CV saved');
          } catch (er) { $('#err', body).innerHTML = G.fail(er); }
        });
      };
      const bs = $('#bs', body);
      if (bs) bs.onclick = () => G.busy(bs, async () => { try { await G.post('/users/roles/add/', { role: 'job_seeker' }); await G.loadUser(); G.toast('Role added'); G.go('#/jobs?tab=profile&r=' + Date.now()); } catch (er) { G.toast(G.errMsg(er)); } });
    }
  });

  G.route('/jobs/post', (el) => {
    if (!G.hasRole('employer')) { el.innerHTML = '<div class="alert">Only employers can post jobs. <a href="#/jobs?tab=employer">Become an employer</a></div>'; return; }
    el.innerHTML = '<div class="narrow"><a href="#/jobs?tab=employer">← Jobs</a><h1>Post a job</h1><form class="card" id="f"><label>Title</label><input name="title" required><label>Description</label><textarea name="description" required></textarea>' +
      '<label>Requirements (one per line)</label><textarea name="requirements"></textarea><div class="row"><div class="grow"><label>Budget</label><input name="budget" type="number" min="0"></div><div class="grow"><label>Currency</label><input name="currency" value="NGN"></div></div>' +
      '<label><input type="checkbox" name="is_negotiable"> Negotiable</label><label>Location</label><input name="location" required><label>Type</label><select name="job_type">' + JOB_TYPES.map((t) => '<option value="' + t + '">' + G.pretty(t) + '</option>').join('') + '</select>' +
      '<div id="err" style="margin-top:10px"></div><button class="btn block" style="margin-top:12px">Publish job</button></form></div>';
    const f = $('#f', el);
    f.onsubmit = (e) => {
      e.preventDefault();
      G.busy($('button', f), async () => {
        try {
          const body = { title: f.title.value.trim(), description: f.description.value.trim(), requirements: f.requirements.value.split('\n').map((s) => s.trim()).filter(Boolean), currency: f.currency.value.trim() || 'NGN', is_negotiable: f.is_negotiable.checked, location: f.location.value.trim(), job_type: f.job_type.value };
          if (f.budget.value) body.budget = f.budget.value;
          const j = await G.post('/jobs/list/', body); G.toast('Job published'); G.go('#/jobs/' + j.id);
        } catch (er) { $('#err', el).innerHTML = G.fail(er); }
      });
    };
  }, { auth: true });

  G.route('/jobs/:id', async (el, ctx) => {
    const j = await G.get('/jobs/' + ctx.params.id + '/', { noAuth: !G.loggedIn() });
    const mine = G.user && j.employer === G.user.id;
    el.innerHTML = '<div class="narrow"><a href="#/jobs">← Jobs</a><div class="card"><h1>' + esc(j.title) + '</h1><div class="mute">' + esc(j.employer_name) + ' · ' + esc(j.location) + '</div>' +
      '<p><span class="pill">' + esc(G.pretty(j.job_type)) + '</span> <span class="pill ' + (j.status === 'open' ? 'ok' : 'warn') + '">' + esc(G.pretty(j.status)) + '</span></p><div class="price">' + esc(jobBudget(j)) + '</div>' +
      '<h3 style="margin-top:12px">Description</h3><p style="white-space:pre-wrap">' + esc(j.description) + '</p>' +
      ((j.requirements || []).length ? '<h3>Requirements</h3><ul>' + j.requirements.map((r) => '<li>' + esc(r) + '</li>').join('') + '</ul>' : '') + '</div>' +
      (mine ? '<div class="alert">This is your job posting · ' + (j.application_count || 0) + ' application(s).</div>' :
        j.status !== 'open' ? '<div class="alert">This job is no longer accepting applications.</div>' :
          '<form class="card" id="f"><h2>Apply</h2><label>Cover letter</label><textarea name="cl" required placeholder="Tell the employer why you are a good fit…"></textarea><div id="err" style="margin-top:10px"></div><button class="btn block" style="margin-top:12px">Submit application</button></form>') + '</div>';
    const f = $('#f', el); if (!f) return;
    f.onsubmit = (e) => {
      e.preventDefault();
      if (!G.loggedIn()) return G.requireLogin();
      G.busy($('button', f), async () => {
        try {
          if (!G.hasRole('job_seeker') && !G.hasRole('worker')) { await G.post('/users/roles/add/', { role: 'job_seeker' }); await G.loadUser(); }
          await G.post('/jobs/' + j.id + '/apply/', { cover_letter: f.cl.value.trim() });
          G.toast('Application submitted'); G.go('#/jobs?tab=applied');
        } catch (er) { $('#err', el).innerHTML = G.fail(er); }
      });
    };
  });

  /* ---------- Admin ---------- */
  G.route('/admin', async (el) => {
    const [ov, stats] = await Promise.all([G.get('/market/admin/overview/'), G.get('/market/admin/stats/').catch(() => null)]);
    const shops = ov.pending_shops || []; const users = ov.users || [];
    el.innerHTML = '<div class="row between"><h1>Admin</h1><a class="btn ghost" href="#/admin/kyc">KYC requests</a></div>' +
      (stats ? '<div class="row" style="margin-bottom:14px">' + [['Users', stats.users.total], ['Sellers', stats.users.sellers], ['Orders', stats.orders.total], ['Pending', stats.orders.pending], ['GMV', G.money(stats.finance.gmv)], ['Wallet total', G.money(stats.finance.wallet_liability)]].map((s) => '<div class="stat"><div class="small mute">' + s[0] + '</div><div class="v">' + esc(s[1]) + '</div></div>').join('') + '</div>' : '') +
      '<div class="card"><h2>Pending shops (' + shops.length + ')</h2>' + (shops.length ? shops.map((s) => '<div class="item"><div class="grow"><b>' + esc(s.name) + '</b> <span class="pill">' + esc(s.shop_type || '') + '</span><div class="small mute">' + esc(s.owner_name) + ' · ' + esc(s.owner_email) + ' · ' + esc(s.id_type || '') + ' ' + esc(s.id_number || '') + '</div></div>' +
        '<button class="btn sm" data-ap="' + esc(s.id) + '">Approve</button><button class="btn sm bad" data-rj="' + esc(s.id) + '">Reject</button></div>').join('') : '<div class="empty">No pending applications.</div>') + '</div>' +
      '<div class="card"><h2>Users (' + users.length + ')</h2><input id="uq" placeholder="Filter by email or name…"><div id="ul" style="margin-top:8px"></div></div>';
    function drawUsers() {
      const q = $('#uq', el).value.trim().toLowerCase();
      const rows = users.filter((u) => !q || (u.email + ' ' + u.first_name + ' ' + u.last_name).toLowerCase().indexOf(q) >= 0).slice(0, 100);
      $('#ul', el).innerHTML = rows.map((u) => '<div class="item"><div class="grow"><b>' + esc((u.first_name + ' ' + u.last_name).trim() || u.email) + '</b><div class="small mute">' + esc(u.email) + '</div></div>' +
        '<select data-u="' + u.id + '" style="width:auto">' + ['buyer', 'seller', 'admin'].map((r) => '<option' + (u.role === r ? ' selected' : '') + '>' + r + '</option>').join('') + '</select></div>').join('') || '<div class="empty">No users.</div>';
    }
    drawUsers(); $('#uq', el).oninput = drawUsers;
    el.onclick = async (ev) => {
      const ap = ev.target.dataset.ap; const rj = ev.target.dataset.rj;
      try {
        if (ap) { await G.post('/market/admin/approve-shop/' + ap + '/'); G.toast('Shop approved'); G.go('#/admin?r=' + Date.now()); }
        if (rj && (await G.confirm('Reject and delete this application?'))) { await G.post('/market/admin/review-shop/' + rj + '/', { action: 'reject' }); G.toast('Application rejected'); G.go('#/admin?r=' + Date.now()); }
      } catch (e) { G.toast(G.errMsg(e)); }
    };
    el.onchange = async (ev) => {
      const id = ev.target.dataset.u; if (!id) return;
      if (!(await G.confirm('Change this user\'s role to ' + ev.target.value + '?'))) { G.go('#/admin?r=' + Date.now()); return; }
      try { await G.post('/market/admin/update-user-role/' + id + '/', { role: ev.target.value }); G.toast('Role updated'); } catch (e) { G.toast(G.errMsg(e)); }
    };
  }, { auth: true, admin: true });

  G.route('/admin/kyc', async (el) => {
    const list = G.list(await G.get('/users/admin/kyc/pending/'));
    el.innerHTML = '<a href="#/admin">← Admin</a><h1>KYC requests</h1>' + (list.length ? list.map((u) => '<div class="card"><div class="row between"><div><b>' + esc(u.full_name || u.email) + '</b><div class="small mute">' + esc(u.email) + ' · ' + esc(u.phone_number || '') + '</div></div><span class="pill warn">' + esc(u.kyc_status) + '</span></div>' +
      '<div class="small mute">ID type: ' + esc(u.id_document_type || '—') + '</div><div class="row" style="margin:8px 0">' +
      (u.id_document_image ? '<a href="' + esc(u.id_document_image) + '" target="_blank" rel="noopener"><img src="' + esc(u.id_document_image) + '" style="height:110px;border-radius:8px" alt="ID"></a>' : '<span class="mute">No ID</span>') +
      (u.selfie_image ? '<a href="' + esc(u.selfie_image) + '" target="_blank" rel="noopener"><img src="' + esc(u.selfie_image) + '" style="height:110px;border-radius:8px" alt="Selfie"></a>' : '') + '</div>' +
      '<div class="row"><button class="btn sm" data-a="approve" data-id="' + u.id + '">Approve</button><button class="btn sm bad" data-a="reject" data-id="' + u.id + '">Reject</button></div></div>').join('') : '<div class="empty">No pending KYC requests.</div>');
    el.onclick = async (ev) => {
      const a = ev.target.dataset.a; if (!a) return;
      let reason = '';
      if (a === 'reject') { reason = window.prompt('Reason for rejection (shown to the user):', ''); if (reason === null) return; }
      try { await G.post('/users/admin/kyc/' + ev.target.dataset.id + '/action/', { action: a, reason }); G.toast('Done'); G.go('#/admin/kyc?r=' + Date.now()); } catch (e) { G.toast(G.errMsg(e)); }
    };
  }, { auth: true, admin: true });
})();
