'use strict';

// Вход, уточнение ответов медиками, личный кабинет и админка.
// Работает поверх app.js: берёт оттуда el(), icon(), T(), thread(), state.
//
// Правила, которые здесь важнее всего:
//  · уточнение начинает действовать только после подтверждений других медиков;
//  · своё уточнение автор не подтверждает; одного несогласия достаточно для отклонения;
//  · чужую формулировку принимает или отклоняет автор уточнения, после чего
//    голосование идёт заново.

const Review = (() => {
  const session = { user: null, counts: { queue: 0, unread: 0 }, required: 3 };
  const view = { open: false, group: 'refine', tab: null, items: [], busy: false, form: null, day: null };
  const LANG_KEY = 'ui-lang'; // язык интерфейса — не клинические данные

  const isMedic = () => !!session.user && session.user.role === 'medic';
  const isAdmin = () => !!session.user && session.user.role === 'admin';
  const signedIn = () => !!session.user && session.user.id > 0;
  const fill = (text, values) => String(text).replace(/\{(\w+)\}/g, (_, key) => (key in values ? values[key] : ''));

  // ── запросы ─────────────────────────────────────────────
  async function api(path, options) {
    const opts = options || {};
    const response = await fetch('/api/v1' + path, {
      method: opts.method || 'GET',
      headers: opts.body ? { 'Content-Type': 'application/json' } : undefined,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      cache: 'no-store',
    });
    let body = {};
    try { body = await response.json(); } catch (_) { /* пустое тело */ }
    if (response.status === 401 && !opts.quiet) showLogin();
    if (!response.ok) {
      const error = new Error(body.message || T().errGeneric);
      error.code = body.code;
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function toast(text, bad) {
    const node = el('div', { class: 'rv-toast' + (bad ? ' bad' : ''), role: 'status', text: text });
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 4200);
  }

  const fail = (error) => toast(error.message || T().errGeneric, true);

  // ── вход ────────────────────────────────────────────────
  function showLogin(message) {
    session.user = null;
    closeWorkspace();
    hideMenu();
    let box = document.getElementById('rv-login');
    if (box) box.remove();
    const login = el('input', { id: 'rv-login-name', type: 'text', autocomplete: 'username', autocapitalize: 'none', spellcheck: 'false' });
    const password = el('input', { id: 'rv-login-password', type: 'password', autocomplete: 'current-password' });
    const error = el('div', { class: 'rv-error', role: 'alert', text: message || '' });
    const submit = el('button', { class: 'rv-primary', type: 'submit', text: T().loginBtn });
    const form = el('form', { class: 'rv-login-card' }, [
      el('div', { class: 'rv-login-brand' }, [
        el('span', { class: 'rv-login-mark' }, [mark(20)]),
        el('span', { class: 'rv-login-text' }, [
          el('span', { class: 'rv-login-name', lang: 'en', translate: 'no', text: 'meyar' }),
          el('span', { class: 'rv-login-tagline', text: T().brandTagline }),
        ]),
        languagePicker(),
      ]),
      el('h2', { text: T().loginTitle }),
      el('p', { class: 'rv-muted', text: T().loginSub }),
      el('label', { for: 'rv-login-name', text: T().loginName }), login,
      el('label', { for: 'rv-login-password', text: T().loginPassword }), password,
      error, submit,
    ]);
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      submit.disabled = true;
      try {
        const body = await api('/auth/login', { method: 'POST', quiet: true, body: { login: login.value, password: password.value } });
        session.user = body.user;
        box.remove();
        // Чужие диалоги на общей рабочей станции новому пользователю не показываем:
        // вкладка очищается, история входящего загружается с сервера.
        History.reset();
        state.chats = [];
        newChat();
        await refreshMe();
        applyStatic();
        render();
      } catch (err) {
        error.textContent = err.status === 429 ? T().loginThrottle : T().loginBad;
        submit.disabled = false;
        password.value = '';
        password.focus();
      }
    });
    box = el('div', { id: 'rv-login', class: 'rv-login' }, [form]);
    document.body.appendChild(box);
    login.focus();
  }

  // Флаги нарисованы здесь же: эмодзи-флаги есть не во всех системах, а
  // картинок с CDN на машине без интернета не будет.
  const FLAGS = {
    uz: '<rect width="24" height="16" fill="#fff"/><rect width="24" height="5.2" fill="#0099b5"/><rect y="10.8" width="24" height="5.2" fill="#1eb53a"/><rect y="5.2" width="24" height=".5" fill="#ce1126"/><rect y="10.3" width="24" height=".5" fill="#ce1126"/><circle cx="4.4" cy="2.6" r="1.6" fill="#fff"/><circle cx="5" cy="2.6" r="1.6" fill="#0099b5"/><g fill="#fff"><circle cx="7.4" cy="1.5" r=".35"/><circle cx="8.8" cy="1.5" r=".35"/><circle cx="10.2" cy="1.5" r=".35"/><circle cx="7.4" cy="2.7" r=".35"/><circle cx="8.8" cy="2.7" r=".35"/><circle cx="10.2" cy="2.7" r=".35"/><circle cx="8.8" cy="3.9" r=".35"/><circle cx="10.2" cy="3.9" r=".35"/></g>',
    ru: '<rect width="24" height="16" fill="#fff"/><rect y="5.33" width="24" height="5.34" fill="#0039a6"/><rect y="10.67" width="24" height="5.33" fill="#d52b1e"/>',
    en: '<rect width="24" height="16" fill="#012169"/><path d="M0 0l24 16M24 0L0 16" stroke="#fff" stroke-width="3.2"/><path d="M0 0l24 16M24 0L0 16" stroke="#c8102e" stroke-width="1.2"/><path d="M12 0v16M0 8h24" stroke="#fff" stroke-width="5"/><path d="M12 0v16M0 8h24" stroke="#c8102e" stroke-width="2.8"/>',
  };

  function flag(code) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 16');
    svg.setAttribute('class', 'rv-flag');
    svg.setAttribute('aria-hidden', 'true');
    svg.innerHTML = FLAGS[code] || '';
    return svg;
  }

  // Значок с флагом текущего языка; по нажатию — список языков.
  function languagePicker() {
    const current = LANGUAGES.find((l) => l.code === state.lang);
    const list = el('div', { class: 'rv-lang-list', role: 'menu', hidden: true }, LANGUAGES.filter((l) => l.ready).map((l) =>
      el('button', {
        type: 'button', role: 'menuitemradio', 'aria-checked': l.code === state.lang ? 'true' : 'false',
        onClick: () => { setLanguage(l.code); showLogin(); },
      }, [flag(l.code), el('span', { text: l.native })])
    ));
    const toggle = el('button', {
      class: 'rv-lang-toggle', type: 'button', 'aria-haspopup': 'menu', 'aria-expanded': 'false',
      'aria-label': 'Til · Язык · Language: ' + current.native,
      onClick: () => {
        list.hidden = !list.hidden;
        toggle.setAttribute('aria-expanded', list.hidden ? 'false' : 'true');
        if (!list.hidden) list.querySelector('[aria-checked="true"]').focus();
      },
    }, [flag(state.lang), el('span', { text: state.lang.toUpperCase() }), icon('caret-down')]);
    const box = el('div', { class: 'rv-lang' }, [toggle, list]);
    // Закрытие по нажатию мимо списка. Не по потере фокуса: Safari не
    // переводит фокус на кнопку при нажатии мышью, список закрывался раньше,
    // чем срабатывал выбор языка.
    const outside = (e) => {
      if (!box.isConnected) { document.removeEventListener('pointerdown', outside, true); return; }
      if (box.contains(e.target) || list.hidden) return;
      list.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
    };
    document.addEventListener('pointerdown', outside, true);
    box.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || list.hidden) return;
      list.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
      toggle.focus();
    });
    return box;
  }

  function setLanguage(code) {
    state.lang = code;
    try { localStorage.setItem(LANG_KEY, code); } catch (_) { /* приватный режим */ }
    applyStatic();
    render();
  }

  async function logout() {
    try { await api('/auth/logout', { method: 'POST', quiet: true }); } catch (_) { /* сеанс уже закрыт */ }
    History.reset();
    state.chats = [];
    newChat();
    render();
    showLogin();
  }

  async function refreshMe() {
    try {
      const body = await api('/auth/me', { quiet: true });
      session.user = body.user;
      session.counts = body.counts;
      session.required = body.required_confirmations;
      if (signedIn() && History.owner() !== session.user.id) History.load(session.user.id);
    } catch (err) {
      if (err.status === 401) { showLogin(); return; }
    }
    paintSide();
  }

  // ── боковая панель ──────────────────────────────────────
  function paintSide() {
    const who = document.getElementById('whoami');
    const open = document.getElementById('rv-open');
    const out = document.getElementById('rv-logout');
    if (!who || !open || !out) return;
    const user = session.user;
    who.textContent = signedIn() ? user.name + ' · ' + T().roles[user.role] : T().whoami;
    open.hidden = !signedIn();
    out.hidden = !signedIn();
    document.getElementById('rv-admin').hidden = !isAdmin();
    document.getElementById('rv-admin-label').textContent = T().adminMenu;
    // Профиль живёт в меню «Настройки», рядом с языком.
    const extra = document.getElementById('rv-settings-extra');
    extra.hidden = !signedIn();
    const entry = (name, label, tab) => el('button', {
      class: 'lang-row', type: 'button',
      onClick: () => { toggleSettings(false); openWorkspace('settings', tab); },
    }, [icon(name), el('span', { class: 'lang-label', text: label })]);
    extra.replaceChildren(...(signedIn() ? [entry('user-circle', T().tabProfile, 'profile')] : []));
    document.getElementById('rv-open-label').textContent = T().workspace;
    document.getElementById('rv-logout-label').textContent = T().logout;
    const total = session.counts.queue + session.counts.unread;
    const badge = document.getElementById('rv-badge');
    badge.hidden = !total;
    badge.textContent = String(total);
  }

  // ── правый клик по ответу ───────────────────────────────
  function refinable(item) {
    return isMedic() && item && item.role === 'assistant' && item.done && !item.local && !item.broken && !item.stopped && !item.error;
  }

  function hideMenu() {
    const menu = document.getElementById('rv-menu');
    if (menu) menu.remove();
  }

  function onContextMenu(e) {
    const holder = e.target.closest('[data-item]');
    if (!holder) return;
    const item = thread()[Number(holder.getAttribute('data-item'))];
    if (!refinable(item)) return; // остаётся обычное меню браузера
    e.preventDefault();
    hideMenu();
    const menu = el('div', { id: 'rv-menu', class: 'rv-menu', role: 'menu' }, [
      el('button', { type: 'button', role: 'menuitem', onClick: () => { hideMenu(); openRefine(item); } }, [icon('pencil'), T().refineAction]),
    ]);
    document.body.appendChild(menu);
    menu.style.left = Math.min(e.clientX, window.innerWidth - menu.offsetWidth - 8) + 'px';
    menu.style.top = Math.min(e.clientY, window.innerHeight - menu.offsetHeight - 8) + 'px';
    menu.firstChild.focus();
  }

  // Текст ответа без маркеров сносок: уточнение пишет человек, ссылок в нём нет.
  const cleanAnswer = (text) => plainText(text).replace(CITATION, '').replace(/[ \t]+([.,;:])/g, '$1').trim();

  function openRefine(item) {
    const items = thread();
    const at = items.indexOf(item);
    let q = at - 1;
    while (q >= 0 && !(items[q].role === 'user' && !items[q].local)) q -= 1;
    if (q < 0) return;
    const history = items.slice(0, q)
      .filter((m) => (m.role === 'user' || m.role === 'assistant') && !m.local && !m.error && (m.content || '').trim())
      .map((m) => ({ role: m.role, content: m.content.trim() }));
    const answer = cleanAnswer(item.content);
    const text = el('textarea', { id: 'rv-refine-text', rows: '9' });
    text.value = answer;
    const send = el('button', { class: 'rv-primary', type: 'button', text: T().refineSend });
    const dialog = modal(T().refineTitle, [
      el('p', { class: 'rv-muted', text: fill(T().refineHint, { n: session.required }) }),
      history.length ? el('p', { class: 'rv-warn', text: T().refineFollowUp }) : null,
      el('span', { class: 'rv-label', text: T().refineQuestion }),
      el('div', { class: 'rv-quote', text: items[q].content }),
      el('details', {}, [el('summary', { text: T().refineModel }), el('div', { class: 'rv-quote', text: answer })]),
      el('label', { class: 'rv-label', for: 'rv-refine-text', text: T().refineYours }),
      text,
      el('div', { class: 'rv-row end' }, [
        el('button', { type: 'button', text: T().cancel, onClick: () => dialog.remove() }),
        send,
      ]),
    ]);
    send.addEventListener('click', async () => {
      if (!text.value.trim()) { text.focus(); return; }
      send.disabled = true;
      try {
        await api('/refinements', {
          method: 'POST',
          body: { question: items[q].content, text: text.value, model_answer: answer, language: state.lang, history: history },
        });
        dialog.remove();
        toast(T().refineSent);
      } catch (err) { fail(err); send.disabled = false; }
    });
    text.focus();
  }

  function modal(title, children) {
    const box = el('div', { class: 'rv-overlay' }, [
      el('div', { class: 'rv-dialog', role: 'dialog', 'aria-modal': 'true', 'aria-label': title }, [
        el('div', { class: 'rv-dialog-head' }, [
          el('h2', { text: title }),
          el('button', { class: 'rv-x', type: 'button', 'aria-label': T().close, onClick: () => box.remove() }, [icon('x')]),
        ]),
        el('div', { class: 'rv-dialog-body sc' }, children),
      ]),
    ]);
    box.addEventListener('mousedown', (e) => { if (e.target === box) box.remove(); });
    document.body.appendChild(box);
    return box;
  }

  // ── пометка принятого ответа ────────────────────────────
  function renderVerified(item) {
    return el('div', { class: 'card verified' }, [
      el('div', { class: 'card-head' }, [icon('seal-check'), el('span', { class: 'card-title', text: T().verifiedTitle })]),
      el('span', { class: 'card-note', text: fill(T().verifiedNote, { n: item.verified.confirmations }) }),
      // Совпадение по смыслу, а не дословное: показываем исходный вопрос.
      item.verified.similarity < 1 && item.verified.question
        ? el('span', { class: 'card-note', text: T().verifiedFor + ' «' + item.verified.question + '»' })
        : null,
    ]);
  }

  function actionButton(item) {
    if (!refinable(item)) return null;
    return el('button', { type: 'button', onClick: () => openRefine(item) }, [icon('pencil'), T().refineAction]);
  }

  // ── кабинет ─────────────────────────────────────────────
  // Три меню боковой панели: уточнения, администрирование, настройки.
  function tabs() {
    if (view.group === 'admin') return isAdmin() ? ['users', 'settings', 'activity'] : [];
    if (view.group === 'settings') return ['profile'];
    const list = [];
    if (isMedic()) list.push('queue', 'mine');
    if (isMedic() || isAdmin()) list.push('accepted');
    list.push('inbox');
    return list;
  }

  const groupTitle = () => (view.group === 'admin' ? T().adminMenu : view.group === 'settings' ? T().settingsTitle : T().workspace);

  const TAB_LABEL = { queue: 'tabQueue', mine: 'tabMine', accepted: 'tabAccepted', inbox: 'tabInbox', users: 'tabUsers', settings: 'systemSettings', activity: 'tabActivity', profile: 'tabProfile' };

  function openWorkspace(group, tab) {
    view.open = true;
    view.group = group || 'refine';
    view.form = null;
    view.day = null;
    const first = view.group === 'refine' && session.counts.unread && !session.counts.queue ? 'inbox' : tabs()[0];
    loadTab(tab || first);
  }

  function closeWorkspace() {
    view.open = false;
    const box = document.getElementById('rv-workspace');
    if (box) box.remove();
  }

  async function loadTab(tab) {
    view.tab = tab;
    view.items = [];
    view.form = null;
    view.busy = true;
    paintWorkspace();
    try {
      if (tab === 'queue' || tab === 'mine' || tab === 'accepted') view.items = (await api('/refinements?scope=' + tab)).items;
      else if (tab === 'inbox') {
        view.items = (await api('/notifications')).items;
        if (session.counts.unread) await api('/notifications/read', { method: 'POST' });
      } else if (tab === 'users') view.items = (await api('/admin/users')).items;
      else if (tab === 'settings') session.required = (await api('/admin/settings')).required_confirmations;
      else if (tab === 'activity') {
        const tz = '?tz=' + -new Date().getTimezoneOffset();
        view.items = view.day ? (await api('/admin/activity/' + view.day + tz)).items : (await api('/admin/activity' + tz)).days;
      }
    } catch (err) { if (err.status !== 401) fail(err); }
    view.busy = false;
    if (!view.open) return;
    paintWorkspace();
    refreshMe();
  }

  function paintWorkspace() {
    if (!view.open || !session.user) return;
    const old = document.getElementById('rv-workspace');
    const body = el('div', { class: 'rv-ws-body sc' }, view.busy ? [] : renderTab());
    const box = el('div', { id: 'rv-workspace', class: 'rv-overlay' }, [
      el('div', { class: 'rv-ws', role: 'dialog', 'aria-modal': 'true', 'aria-label': groupTitle() }, [
        el('div', { class: 'rv-dialog-head' }, [
          el('h2', { text: groupTitle() }),
          el('button', { class: 'rv-x', type: 'button', 'aria-label': T().close, onClick: closeWorkspace }, [icon('x')]),
        ]),
        el('div', { class: 'rv-tabs', role: 'tablist' }, tabs().map((tab) => {
          const count = tab === 'queue' ? session.counts.queue : tab === 'inbox' ? session.counts.unread : 0;
          return el('button', {
            type: 'button', role: 'tab', 'aria-selected': tab === view.tab ? 'true' : 'false',
            onClick: () => { view.day = null; loadTab(tab); },
          }, [T()[TAB_LABEL[tab]], count ? el('span', { class: 'rv-count', text: String(count) }) : null]);
        })),
        body,
      ]),
    ]);
    box.addEventListener('mousedown', (e) => { if (e.target === box) closeWorkspace(); });
    if (old) old.replaceWith(box); else document.body.appendChild(box);
  }

  function renderTab() {
    const tab = view.tab;
    if (tab === 'queue' || tab === 'mine' || tab === 'accepted') {
      if (!view.items.length) return [empty(T()[{ queue: 'emptyQueue', mine: 'emptyMine', accepted: 'emptyAccepted' }[tab]])];
      return view.items.map(renderRefinement);
    }
    if (tab === 'inbox') return view.items.length ? view.items.map(renderNotification) : [empty(T().emptyInbox)];
    if (tab === 'users') return renderUsers();
    if (tab === 'settings') return renderSettings();
    if (tab === 'activity') return view.day ? renderDay() : renderDays();
    return renderProfile();
  }

  const empty = (text) => el('div', { class: 'rv-empty', text: text });

  async function act(run, done) {
    try {
      await run();
      if (done) toast(done);
      await loadTab(view.tab);
    } catch (err) { if (err.status !== 401) fail(err); }
  }

  function proposalBlock(proposal, canDecide) {
    return el('div', { class: 'rv-proposal' }, [
      el('span', { class: 'rv-label', text: T().proposalFrom + ' ' + proposal.author + ' · ' + T().proposalStatus[proposal.status] }),
      el('div', { class: 'rv-quote', text: proposal.text }),
      proposal.comment ? el('div', { class: 'rv-muted', text: proposal.comment }) : null,
      canDecide && proposal.status === 'pending' ? el('div', { class: 'rv-row' }, [
        el('button', {
          class: 'rv-primary', type: 'button', text: T().proposalAccept,
          onClick: () => act(() => api('/proposals/' + proposal.id + '/decision', { method: 'POST', body: { accept: true } })),
        }),
        el('button', {
          type: 'button', text: T().proposalDecline,
          onClick: () => act(() => api('/proposals/' + proposal.id + '/decision', { method: 'POST', body: { accept: false } })),
        }),
        el('span', { class: 'rv-muted', text: T().proposalAcceptNote }),
      ]) : null,
    ]);
  }

  function renderRefinement(r) {
    const form = view.form && view.form.id === r.id ? view.form : null;
    const children = [
      el('div', { class: 'rv-item-head' }, [
        el('span', { class: 'rv-chip ' + r.status, text: T().status[r.status] }),
        el('span', { class: 'rv-muted', text: fill(T().progress, { a: r.confirmations, n: r.required }) }),
        el('span', { class: 'rv-muted', text: T().by + ': ' + r.author }),
      ]),
      r.history.length ? el('details', {}, [
        el('summary', { text: T().showHistory }),
        el('div', { class: 'rv-quote', text: r.history.map((m) => (m.role === 'user' ? '— ' : '') + m.content).join('\n\n') }),
      ]) : null,
      el('span', { class: 'rv-label', text: T().refineQuestion }),
      el('div', { class: 'rv-question', text: r.question }),
      el('div', { class: 'rv-answer', text: r.text }),
      r.model_answer ? el('details', {}, [el('summary', { text: T().showModel }), el('div', { class: 'rv-quote', text: r.model_answer })]) : null,
    ];
    if (r.votes.length) {
      children.push(el('div', { class: 'rv-votes' }, r.votes.map((v) =>
        el('div', { class: 'rv-vote' + (v.agree ? '' : ' no') }, [
          icon(v.agree ? 'check' : 'x'),
          el('span', { text: v.user + ' — ' + (v.agree ? T().voteAgree : T().voteDisagree) + (v.comment ? ': ' + v.comment : '') }),
        ])
      )));
    }
    for (const p of r.proposals) {
      if (p.status === 'pending' || r.mine) children.push(proposalBlock(p, r.mine && r.status === 'pending'));
    }
    if (form && form.kind === 'disagree') {
      const why = el('textarea', { rows: '3', 'aria-label': T().disagreeWhy, placeholder: T().disagreeWhy });
      children.push(el('div', { class: 'rv-form' }, [
        why,
        el('span', { class: 'rv-muted', text: T().disagreeNote }),
        el('div', { class: 'rv-row' }, [
          el('button', {
            class: 'rv-danger', type: 'button', text: T().disagreeSend,
            onClick: () => {
              if (!why.value.trim()) { why.focus(); return; }
              act(() => api('/refinements/' + r.id + '/vote', { method: 'POST', body: { agree: false, comment: why.value } }));
            },
          }),
          el('button', { type: 'button', text: T().cancel, onClick: () => { view.form = null; paintWorkspace(); } }),
        ]),
      ]));
    } else if (form && form.kind === 'propose') {
      const text = el('textarea', { rows: '6', 'aria-label': T().proposeText });
      text.value = r.text;
      const note = el('input', { type: 'text', 'aria-label': T().proposeComment, placeholder: T().proposeComment });
      children.push(el('div', { class: 'rv-form' }, [
        el('span', { class: 'rv-label', text: T().proposeText }),
        text, note,
        el('div', { class: 'rv-row' }, [
          el('button', {
            class: 'rv-primary', type: 'button', text: T().proposeSend,
            onClick: () => {
              if (!text.value.trim() || text.value.trim() === r.text.trim()) { text.focus(); return; }
              act(() => api('/refinements/' + r.id + '/proposals', { method: 'POST', body: { text: text.value, comment: note.value } }), T().proposeSent);
            },
          }),
          el('button', { type: 'button', text: T().cancel, onClick: () => { view.form = null; paintWorkspace(); } }),
        ]),
      ]));
    } else {
      const buttons = [];
      if (r.can_vote) {
        buttons.push(el('button', {
          class: 'rv-primary', type: 'button',
          onClick: () => act(() => api('/refinements/' + r.id + '/vote', { method: 'POST', body: { agree: true } })),
        }, [icon('check'), T().agree]));
        buttons.push(el('button', { type: 'button', text: T().disagree, onClick: () => { view.form = { id: r.id, kind: 'disagree' }; paintWorkspace(); } }));
      }
      if (r.can_propose) {
        buttons.push(el('button', { type: 'button', onClick: () => { view.form = { id: r.id, kind: 'propose' }; paintWorkspace(); } }, [icon('pencil'), T().proposeBtn]));
      }
      if (isAdmin() && r.status === 'accepted') {
        buttons.push(el('button', {
          class: 'rv-danger', type: 'button', text: T().archiveBtn,
          onClick: () => { if (window.confirm(T().archiveConfirm)) act(() => api('/refinements/' + r.id + '/archive', { method: 'POST' })); },
        }));
      }
      if (buttons.length) children.push(el('div', { class: 'rv-row' }, buttons));
    }
    return el('div', { class: 'rv-item' }, children);
  }

  function renderNotification(n) {
    const when = new Date(n.created_at * 1000).toLocaleString(state.lang === 'en' ? 'en-GB' : 'ru-RU', { dateStyle: 'short', timeStyle: 'short' });
    const children = [
      el('div', { class: 'rv-item-head' }, [
        el('span', { class: 'rv-notif-text', text: fill(T().notif[n.kind] || n.kind, { actor: n.actor || '' }) }),
        el('span', { class: 'rv-muted', text: when }),
      ]),
      n.question ? el('div', { class: 'rv-question', text: n.question }) : null,
    ];
    if (n.kind === 'refinement_rejected' && n.comment) children.push(el('div', { class: 'rv-quote', text: T().reason + ': ' + n.comment }));
    if (n.kind.startsWith('proposal_') && n.proposal_text) {
      children.push(proposalBlock(
        { id: n.proposal_id, author: n.kind === 'proposal_received' ? (n.actor || '') : session.user.name, text: n.proposal_text, comment: n.proposal_comment, status: n.proposal_status },
        n.kind === 'proposal_received' && n.refinement_status === 'pending'
      ));
    } else if (n.text) {
      children.push(el('div', { class: 'rv-answer', text: n.text }));
    }
    return el('div', { class: 'rv-item' + (n.read ? '' : ' unread') }, children);
  }

  // ── админка ─────────────────────────────────────────────
  function roleSelect(value, onChange) {
    const select = el('select', { 'aria-label': T().userRole }, ['medic', 'observer', 'admin'].map((role) =>
      el('option', { value: role, selected: role === value, text: T().roles[role] })
    ));
    if (onChange) select.addEventListener('change', () => onChange(select.value));
    return select;
  }

  function renderUsers() {
    const login = el('input', { type: 'text', placeholder: T().loginName, 'aria-label': T().loginName, autocomplete: 'off', autocapitalize: 'none' });
    const name = el('input', { type: 'text', placeholder: T().userName, 'aria-label': T().userName, autocomplete: 'off' });
    const password = el('input', { type: 'text', placeholder: T().userNewPassword, 'aria-label': T().userNewPassword, autocomplete: 'off' });
    const role = roleSelect('medic');
    const patch = (user, body, done) => act(() => api('/admin/users/' + user.id, { method: 'PATCH', body: body }), done || T().saved);
    return [
      el('div', { class: 'rv-item' }, [
        el('span', { class: 'rv-label', text: T().usersAdd }),
        el('div', { class: 'rv-grid' }, [login, name, role, password]),
        el('div', { class: 'rv-row' }, [
          el('button', {
            class: 'rv-primary', type: 'button', text: T().userCreate,
            onClick: () => act(() => api('/admin/users', { method: 'POST', body: { login: login.value, name: name.value, role: role.value, password: password.value } }), T().userCreated),
          }),
        ]),
      ]),
      el('div', { class: 'rv-users' }, view.items.map((user) => {
        const reset = view.form && view.form.id === user.id;
        const fresh = el('input', { type: 'text', placeholder: T().userNewPassword, 'aria-label': T().userNewPassword, autocomplete: 'off' });
        return el('div', { class: 'rv-user' + (user.active ? '' : ' off') }, [
          el('div', { class: 'rv-user-id' }, [
            el('span', { class: 'rv-user-name', text: user.name }),
            el('span', { class: 'rv-muted', text: user.login + (user.active ? '' : ' · ' + T().userBlocked) }),
          ]),
          roleSelect(user.role, (next) => patch(user, { role: next })),
          reset ? fresh : null,
          reset
            ? el('button', { class: 'rv-primary', type: 'button', text: T().save, onClick: () => patch(user, { password: fresh.value }) })
            : el('button', { type: 'button', text: T().userReset, onClick: () => { view.form = { id: user.id }; paintWorkspace(); } }),
          el('button', { type: 'button', text: user.active ? T().userDisable : T().userEnable, onClick: () => patch(user, { active: !user.active }) }),
        ]);
      })),
    ];
  }

  function renderSettings() {
    const count = el('input', { id: 'rv-required', type: 'number', min: '1', max: '50', value: session.required });
    return [
      el('div', { class: 'rv-item' }, [
        el('label', { class: 'rv-label', for: 'rv-required', text: T().settingsConfirmations }),
        el('div', { class: 'rv-row' }, [
          count,
          el('button', {
            class: 'rv-primary', type: 'button', text: T().save,
            onClick: () => act(() => api('/admin/settings', { method: 'PUT', body: { required_confirmations: Number(count.value) } }), T().saved),
          }),
        ]),
        el('span', { class: 'rv-muted', text: T().settingsNote }),
      ]),
      el('div', { class: 'rv-item' }, [
        el('span', { class: 'rv-label', text: T().exportTitle }),
        el('span', { class: 'rv-muted', text: T().exportNote }),
        el('div', { class: 'rv-row' }, [el('a', { class: 'rv-link', href: '/api/v1/admin/export.jsonl', download: true }, [icon('file-text'), T().exportBtn])]),
      ]),
    ];
  }

  // ── активность (только администратор) ───────────────────
  // Сводка по дням и все события выбранного дня. Сутки — по часам браузера.
  const LOCALE = { en: 'en-GB', uz: 'uz-Latn', ru: 'ru-RU' };
  const locale = () => LOCALE[state.lang] || 'ru-RU';
  const seconds = (ms) => (ms === null || ms === undefined ? '—'
    : (ms / 1000).toLocaleString(locale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' ' + T().actSec);
  const dayLabel = (day) => new Date(day + 'T12:00:00').toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
  const clock = (ts) => new Date(ts * 1000).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const num = (n) => el('span', { class: n ? '' : 'rv-zero', text: n ? String(n) : '0' });

  function activityHead(children) {
    return el('div', { class: 'rv-row rv-act-head' }, [
      ...children,
      el('button', { type: 'button', class: 'rv-act-refresh', onClick: () => loadTab('activity') }, [icon('arrows-clockwise'), T().actRefresh]),
    ]);
  }

  // Лицензия DB-IP Lite (CC BY 4.0) требует указать источник локаций.
  const geoCredit = () => el('div', { class: 'rv-muted rv-act-credit' }, [
    T().actGeo + ' ', el('a', { href: 'https://db-ip.com', target: '_blank', rel: 'noopener', text: 'IP Geolocation by DB-IP' }),
  ]);

  function renderDays() {
    const t = T();
    if (!view.items.length) return [activityHead([]), empty(t.actEmpty)];
    const head = [t.actDay, t.actUsers, t.actLogins, t.actQuestions, t.actAnswerTime, t.actErrors, t.actRefinements, t.actVotes, ''];
    const rows = view.items.map((d) => el('tr', {}, [
      el('td', { class: 'rv-act-day' }, [el('button', { type: 'button', class: 'rv-act-open', onClick: () => { view.day = d.day; loadTab('activity'); } }, [dayLabel(d.day)])]),
      el('td', { class: 'n' }, [num(d.users)]),
      el('td', {}, [
        el('div', { class: 'n' }, [num(d.logins)]),
        d.failed_logins ? el('div', { class: 'rv-act-sub bad', text: fill(t.actFailed, { n: d.failed_logins }) }) : null,
        // Откуда входили: человек — место; IP — во всплывающей подсказке.
        ...(d.places || []).map((p) => el('div', { class: 'rv-act-sub rv-act-place', title: p.ips.join(', '), text: p.user + ': ' + p.place + (p.logins > 1 ? ' ×' + p.logins : '') })),
      ]),
      el('td', {}, [
        el('div', { class: 'n' }, [num(d.questions)]),
        ...d.per_user.map((u) => el('div', { class: 'rv-act-sub', text: u.name + ': ' + u.questions })),
      ]),
      el('td', { class: 'n' }, [
        el('span', { text: seconds(d.answer_ms) }),
        d.first_ms !== null ? el('div', { class: 'rv-act-sub', text: t.actFirst + ' ' + seconds(d.first_ms) }) : null,
      ]),
      el('td', { class: 'n' + (d.errors ? ' bad' : '') }, [num(d.errors), d.stopped ? el('div', { class: 'rv-act-sub', text: fill(t.actStopped, { n: d.stopped }) }) : null]),
      el('td', { class: 'n' }, [
        num(d.refinements),
        d.accepted || d.rejected ? el('div', { class: 'rv-act-sub', text: fill(t.actDecided, { a: d.accepted, r: d.rejected }) }) : null,
        d.proposals ? el('div', { class: 'rv-act-sub', text: fill(t.actProposals, { n: d.proposals }) }) : null,
      ]),
      el('td', { class: 'n' }, [el('span', { class: d.votes_agree + d.votes_disagree ? '' : 'rv-zero', text: d.votes_agree + ' / ' + d.votes_disagree })]),
      el('td', {}, [el('button', { type: 'button', class: 'rv-act-more', onClick: () => { view.day = d.day; loadTab('activity'); } }, [t.actMore])]),
    ]));
    return [
      activityHead([el('span', { class: 'rv-muted', text: t.actNote })]),
      geoCredit(),
      el('div', { class: 'rv-table-wrap sc' }, [el('table', { class: 'rv-table' }, [
        el('thead', {}, [el('tr', {}, head.map((h) => el('th', { text: h })))]),
        el('tbody', {}, rows),
      ])]),
    ];
  }

  function eventDetails(e) {
    const t = T();
    const out = [];
    if (e.question) out.push(el('div', { class: e.kind === 'question' ? 'rv-act-q' : 'rv-act-qref', text: e.question }));
    if (e.kind === 'question') {
      const meta = [t.actStatus[e.status] || e.status];
      if (e.total_ms !== null) meta.push(t.actAnswerTime.toLowerCase() + ': ' + seconds(e.total_ms));
      if (e.first_ms !== null) meta.push(t.actFirst + ' ' + seconds(e.first_ms));
      if (e.language) meta.push(e.language.toUpperCase());
      if (e.followup) meta.push(t.actFollowup);
      if (e.error) meta.push(e.error);
      out.push(el('div', { class: 'rv-act-sub' + (e.status === 'error' ? ' bad' : ''), text: meta.join(' · ') }));
    } else if (e.kind === 'vote') {
      out.push(el('div', { class: 'rv-act-sub' + (e.status === 'agree' ? '' : ' bad'), text: (e.status === 'agree' ? t.voteAgree : t.voteDisagree) + (e.text ? ': ' + e.text : '') }));
    } else if (e.kind === 'refinement' || e.kind === 'proposal') {
      out.push(el('details', {}, [el('summary', { text: t.actShowText }), el('div', { class: 'rv-quote', text: e.text })]));
    } else if (e.kind === 'error' || e.kind === 'login_failed') {
      if (e.error || e.status) out.push(el('div', { class: 'rv-act-sub bad', text: e.error || t.actThrottled }));
    }
    return out;
  }

  function renderDay() {
    const t = T();
    const back = el('button', { type: 'button', onClick: () => { view.day = null; loadTab('activity'); } }, [icon('arrow-left'), t.actBack]);
    const head = activityHead([back, el('span', { class: 'rv-act-title', text: dayLabel(view.day) })]);
    if (!view.items.length) return [head, empty(t.actEmptyDay)];
    return [
      head,
      geoCredit(),
      el('div', { class: 'rv-table-wrap sc' }, [el('table', { class: 'rv-table rv-events' }, [
        el('thead', {}, [el('tr', {}, [t.actTime, t.actWho, t.actEvent, t.actDetails, t.actFrom].map((h) => el('th', { text: h })))]),
        el('tbody', {}, view.items.map((e) => el('tr', { class: 'k-' + e.kind }, [
          el('td', { class: 'n rv-act-time', text: clock(e.time) }),
          el('td', { text: e.user || '—' }),
          el('td', {}, [el('span', { class: 'rv-act-kind k-' + e.kind, text: t.actKind[e.kind] || e.kind })]),
          el('td', {}, eventDetails(e)),
          el('td', { class: 'rv-act-from' }, e.ip ? [
            el('div', { text: e.location || '—' }),
            el('div', { class: 'rv-act-sub', text: e.ip }),
          ] : []),
        ]))),
      ])]),
    ];
  }

  function renderProfile() {
    const current = el('input', { id: 'rv-pw-current', type: 'password', autocomplete: 'current-password' });
    const fresh = el('input', { id: 'rv-pw-new', type: 'password', autocomplete: 'new-password' });
    return [
      el('div', { class: 'rv-item' }, [
        el('span', { class: 'rv-user-name', text: session.user.name }),
        el('span', { class: 'rv-muted', text: session.user.login + ' · ' + T().roles[session.user.role] }),
      ]),
      el('div', { class: 'rv-item' }, [
        el('span', { class: 'rv-label', text: T().profilePassword }),
        el('label', { for: 'rv-pw-current', text: T().profileCurrent }), current,
        el('label', { for: 'rv-pw-new', text: T().userNewPassword }), fresh,
        el('div', { class: 'rv-row' }, [
          el('button', {
            class: 'rv-primary', type: 'button', text: T().save,
            onClick: () => act(() => api('/auth/password', { method: 'POST', body: { current: current.value, new: fresh.value } }), T().profileChanged),
          }),
        ]),
      ]),
    ];
  }

  // ── запуск ──────────────────────────────────────────────
  function applyStaticHook() {
    paintSide();
    if (view.open) paintWorkspace();
  }

  function init() {
    try {
      const saved = localStorage.getItem(LANG_KEY);
      if (saved && I18N[saved] && saved !== state.lang) { state.lang = saved; applyStatic(); render(); }
    } catch (_) { /* приватный режим */ }
    document.getElementById('col').addEventListener('contextmenu', onContextMenu);
    document.addEventListener('click', (e) => { if (!e.target.closest('#rv-menu')) hideMenu(); });
    document.addEventListener('scroll', hideMenu, true);
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      hideMenu();
      const dialogs = document.querySelectorAll('.rv-overlay');
      const top = dialogs[dialogs.length - 1];
      if (!top) return;
      if (top.id === 'rv-workspace') closeWorkspace(); else top.remove();
    });
    document.getElementById('rv-open').addEventListener('click', () => openWorkspace('refine'));
    document.getElementById('rv-admin').addEventListener('click', () => openWorkspace('admin'));
    document.getElementById('rv-logout').addEventListener('click', logout);
    refreshMe();
    setInterval(() => { if (signedIn() && !document.hidden) refreshMe(); }, 60000);
  }

  document.addEventListener('DOMContentLoaded', init);

  return { showLogin, renderVerified, actionButton, applyStatic: applyStaticHook, rememberLanguage: (code) => { try { localStorage.setItem(LANG_KEY, code); } catch (_) { /* приватный режим */ } } };
})();
