// ── история консультаций ──────────────────────────────────
// Диалоги хранятся на сервере, у каждого пользователя свои. Список приходит
// без реплик: сами реплики загружаются, когда диалог открывают. Сохраняется
// диалог целиком после каждого ответа, поэтому его можно продолжить с того же
// места, в том числе с другого компьютера.
const History = (() => {
  let owner = null;            // чей список загружен; null — история выключена
  const pending = new Map();   // chat.id → цепочка сохранений этого диалога
  let warned = false;          // о сбое сохранения говорим один раз

  async function call(path, options) {
    const opts = options || {};
    const response = await fetch('/api/v1/conversations' + path, {
      method: opts.method || 'GET',
      headers: opts.body ? { 'Content-Type': 'application/json' } : undefined,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      cache: 'no-store',
    });
    let body = {};
    try { body = await response.json(); } catch (_) { /* пустое тело */ }
    if (response.status === 401) Review.showLogin();
    if (!response.ok) {
      const error = new Error(body.message || '');
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function toast(text) {
    const node = el('div', { class: 'rv-toast bad', role: 'status', text: text });
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 4200);
  }

  function entry(row) {
    chatSeq += 1;
    return { id: chatSeq, serverId: row.id, title: row.title, updated: row.updated_at, items: null };
  }

  async function load(userId) {
    owner = userId;
    let rows;
    try {
      rows = (await call('')).items;
    } catch (err) {
      if (err.status !== 401) toast(T().historyLoadFailed);
      return;
    }
    if (owner !== userId) return;  // за это время вошёл другой пользователь
    const known = new Set(state.chats.map((c) => c.serverId).filter((id) => id !== null));
    state.chats.unshift(...rows.filter((r) => !known.has(r.id)).map(entry));
    render();
  }

  function reset() {
    owner = null;
    pending.clear();
  }

  // Строки ошибок и недописанные ответы — состояние вкладки, не консультация.
  function payload(chat) {
    const items = chat.items
      .filter((item) => !item.error && !item.streaming)
      .map((item) => Object.assign({}, item));
    return { title: chat.title, language: state.lang, items: items };
  }

  function save(chat) {
    if (owner === null || !chat || !chat.title || chat.items === null) return Promise.resolve();
    const user = owner;
    const body = payload(chat);
    if (!body.items.length) return Promise.resolve();
    const previous = pending.get(chat.id) || Promise.resolve();
    const next = previous.then(async () => {
      if (owner !== user || chat.deleted) return;
      try {
        if (chat.serverId === null) {
          chat.serverId = (await call('', { method: 'POST', body: body })).id;
        } else {
          await call('/' + chat.serverId, { method: 'PUT', body: body });
        }
      } catch (err) {
        if (err.status === 404) { chat.serverId = null; return; }  // удалён в другой вкладке
        if (err.status !== 401 && !warned) { warned = true; toast(T().historySaveFailed); }
      }
    });
    pending.set(chat.id, next);
    return next;
  }

  async function open(chat) {
    if (state.streaming) return;
    state.activeId = chat.id;
    state.stick = true;
    render();
    if (chat.items !== null || chat.serverId === null) return;
    try {
      const body = await call('/' + chat.serverId);
      chat.items = body.items;
    } catch (err) {
      if (err.status === 404) {
        state.chats = state.chats.filter((c) => c !== chat);
        newChat();
      } else if (err.status !== 401) {
        toast(T().historyLoadFailed);
        newChat();  // диалог остаётся в списке: его можно открыть ещё раз
      }
    }
    state.stick = true;
    render();
  }

  async function remove(chat) {
    if (!window.confirm(T().historyConfirm.replace('{title}', chat.title))) return;
    if (chat.id === state.activeId && state.streaming) stopStream();
    await (pending.get(chat.id) || Promise.resolve());
    if (chat.serverId !== null) {
      try {
        await call('/' + chat.serverId, { method: 'DELETE' });
      } catch (err) {
        if (err.status !== 404) {
          if (err.status !== 401) toast(T().historyDeleteFailed);
          return;
        }
      }
    }
    chat.deleted = true;
    pending.delete(chat.id);
    state.chats = state.chats.filter((c) => c !== chat);
    if (chat.id === state.activeId || !activeChat()) newChat();
    render();
  }

  // Сегодня — только время, вчера — «вчера» и время, раньше — дата.
  function when(seconds) {
    if (!seconds) return '';
    const date = new Date(seconds * 1000);
    const locale = state.lang === 'en' ? 'en-GB' : 'ru-RU';
    const time = date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    const today = new Date();
    const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
    if (date.toDateString() === today.toDateString()) return time;
    if (date.toDateString() === yesterday.toDateString()) return T().historyYesterday + ', ' + time;
    const sameYear = date.getFullYear() === today.getFullYear();
    return date.toLocaleDateString(locale, sameYear
      ? { day: '2-digit', month: '2-digit' }
      : { day: '2-digit', month: '2-digit', year: 'numeric' }) + ', ' + time;
  }

  return { load, reset, save, open, remove, when, owner: () => owner };
})();
