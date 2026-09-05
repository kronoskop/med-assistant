'use strict';

// Клинический справочный ассистент — клиент к локальному API.
// Данные макета (языки, темы, признаки тревоги, руководства) лежат в data.js.
//
// Три правила из спеки web-ui, которые здесь важнее всего:
//  · ссылка на документ никогда не подаётся как источник фрагмента ответа модели;
//  · блок признаков тревоги берётся только из курируемого списка распознанной темы;
//  · локальные карточки интерфейса помечаются и не уходят в модель как её реплики.

// ── значки ────────────────────────────────────────────────
// Встроенный SVG вместо иконочного шрифта с CDN: рабочая станция с локальной
// моделью может не иметь доступа в интернет, а пустые квадраты вместо значков
// в клиническом интерфейсе недопустимы.
const ICONS = {
  'plus': 'M12 5v14M5 12h14',
  'user-circle': 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M12 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6M6.2 18.6a7 7 0 0 1 11.6 0',
  'shield-check': 'M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6zM9 12l2 2 4-4',
  'gear': 'M12 15.4a3.4 3.4 0 1 0 0-6.8 3.4 3.4 0 0 0 0 6.8M19.3 13.1a7.4 7.4 0 0 0 0-2.2l1.9-1.5-2-3.4-2.3 1a7.4 7.4 0 0 0-1.9-1.1L14.7 3.4h-3.9l-.3 2.5a7.4 7.4 0 0 0-1.9 1.1l-2.3-1-2 3.4 1.9 1.5a7.4 7.4 0 0 0 0 2.2l-1.9 1.5 2 3.4 2.3-1a7.4 7.4 0 0 0 1.9 1.1l.3 2.5h3.9l.3-2.5a7.4 7.4 0 0 0 1.9-1.1l2.3 1 2-3.4z',
  'check': 'M5 12.5l4.5 4.5L19 7.5',
  'stethoscope': 'M6 3v5a4 4 0 0 0 8 0V3M10 12v2a4 4 0 0 0 8 0v-1M18 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4',
  'book-bookmark': 'M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5zM10 3v7l2.5-2 2.5 2V3',
  'arrow-up-right': 'M8 16L16 8M9.5 8H16v6.5',
  'warning-diamond': 'M12 3.5l8.5 8.5-8.5 8.5L3.5 12zM12 8.5v4.5M12 16.2h.01',
  'phone': 'M6.5 4h3l1.5 4-2 1.5a11 11 0 0 0 5.5 5.5l1.5-2 4 1.5v3a1.5 1.5 0 0 1-1.6 1.5C10.8 18.6 5.4 13.2 5 6.6A1.5 1.5 0 0 1 6.5 4z',
  'arrows-clockwise': 'M4.5 12a7.5 7.5 0 0 1 12.9-5.2M17.5 3.5V7.5H13.5M19.5 12a7.5 7.5 0 0 1-12.9 5.2M6.5 20.5v-4h4',
  'file-text': 'M7 3h7l4 4v14H7zM14 3v4h4M10 12h6M10 16h5',
  'headset': 'M5 13v-1a7 7 0 0 1 14 0v1M5 13h2.5v5H6.5A1.5 1.5 0 0 1 5 16.5zM19 13h-2.5v5h1a1.5 1.5 0 0 0 1.5-1.5zM16.5 18v.5a2.5 2.5 0 0 1-2.5 2.5h-2',
  'paper-plane-right': 'M20 5L4 10.5l6.5 3 3 6.5zM10.5 13.5L20 5',
  'stop': 'M7 7h10v10H7z',
  'heartbeat': 'M3 12h4l2-4 3 8 2.5-5 1.5 3h5',
  'drop': 'M12 3.5c4 4.5 6 7 6 9.5a6 6 0 0 1-12 0c0-2.5 2-5 6-9.5z',
  'baby': 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M9.5 10.5h.01M14.5 10.5h.01M9.3 14.5a3.6 3.6 0 0 0 5.4 0',
  'test-tube': 'M9 3h6M10 3v13a2 2 0 0 0 4 0V3M10 11h4',
  'first-aid-kit': 'M3.5 7.5h17v12.5h-17zM9 7.5V5h6v2.5M12 11.5v5M9.5 14h5',
  'question': 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M9.6 9.4a2.5 2.5 0 1 1 3.2 2.9c-.5.2-.8.7-.8 1.2v.5M12 16.8h.01',
  'sun': 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4',
};

// Фирменный знак: компасная стрелка из двух долей разной плотности.
// Вертикальная ось вдвое длиннее горизонтальной — это компас, а не звёздочка.
function mark(size, color) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('style', `width:${size}px;height:${size}px;flex:none;display:block`);
  const shapes = [
    ['M12 1.6 Q13.1 10.6 17.9 12 Q13.1 13.4 12 22.4 Z', '1'],
    ['M12 1.6 Q10.9 10.6 6.1 12 Q10.9 13.4 12 22.4 Z', '.58'],
  ];
  for (const [d, opacity] of shapes) {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', d);
    path.setAttribute('fill', color || '#ffffff');
    path.setAttribute('opacity', opacity);
    svg.appendChild(path);
  }
  return svg;
}

function icon(name, cls) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.6');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('class', cls || 'icon');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', ICONS[name] || '');
  svg.appendChild(path);
  return svg;
}

// ── мини-хелпер разметки ──────────────────────────────────
function el(tag, props, children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'text') node.textContent = value;
    else if (key === 'class') node.className = value;
    else if (key === 'onClick') node.addEventListener('click', value);
    else node.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of [].concat(children || [])) {
    if (child === null || child === undefined || child === false) continue;
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

// ── состояние ─────────────────────────────────────────────
// История живёт только в этой вкладке и только в памяти: сервер диалоги
// не хранит, а писать клинические тексты в localStorage на общей рабочей
// станции нельзя.
const state = {
  lang: 'ru',
  chats: [],
  activeId: null,
  consult: 0,
  status: 'checking',
  streaming: false,
  stick: true,
};

let controller = null;
let chatSeq = 0;

const T = () => I18N[state.lang];
const activeChat = () => state.chats.find((c) => c.id === state.activeId);
const thread = () => (activeChat() ? activeChat().items : []);

function newChat() {
  chatSeq += 1;
  const chat = { id: chatSeq, title: '', time: '', items: [] };
  state.chats.push(chat);
  state.activeId = chat.id;
  return chat;
}

// ── сопоставление вопроса с курируемой темой ──────────────
// Ровно та же логика, что в макете: точное совпадение вопроса либо вхождение
// ключевого слова. Ничего не найдено — тема не распознана, и курируемые блоки
// не показываются вообще.


// ── запрос к API ──────────────────────────────────────────
// В модель уходят только реплики диалога: локальные карточки интерфейса и
// сообщения об ошибках исключаются — модель не должна получать как свои
// реплики то, чего она не говорила.
function apiMessages() {
  return thread()
    .filter((m) => (m.role === 'user' || m.role === 'assistant') && !m.local && !m.error)
    .map((m) => ({ role: m.role, content: (m.content || '').trim() }))
    .filter((m) => m.content.length > 0);
}

const ERROR_TEXT = {
  llm_unavailable: 'errUnavailable',
  llm_timeout: 'errTimeout',
  llm_error: 'errLlm',
  validation_error: 'errValidation',
};

function pushError(code, message) {
  thread().push({ role: 'system', error: true, code: code, message: message });
}

async function ask(question) {
  const text = (question || '').trim();
  if (!text || state.streaming) return;

  if (!activeChat()) newChat();
  const chat = activeChat();
  if (!chat.title) {
    chat.title = text;
    chat.time = new Date().toLocaleTimeString(state.lang === 'en' ? 'en-GB' : 'ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  state.stick = true;
  thread().push({ role: 'user', content: text });
  const reply = { role: 'assistant', content: '', streaming: true, sources: [], support: [], questions: [], conflicts: [] };
  thread().push(reply);

  const input = document.getElementById('input');
  input.value = '';
  state.streaming = true;
  render();

  controller = new AbortController();
  let sawDone = false;

  try {
    const response = await fetch('/api/v1/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: apiMessages(), stream: true }),
      signal: controller.signal,
    });

    // Ошибки, возникшие до начала генерации, приходят обычным JSON с кодом.
    if (!response.ok) {
      let body = {};
      try { body = await response.json(); } catch (_) { /* тело может быть пустым */ }
      thread().splice(thread().indexOf(reply), 1);
      pushError(body.code || 'http_' + response.status, body.message || '');
      if (body.code === 'llm_unavailable') setStatus('down');
      finish();
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let split;
      while ((split = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, split);
        buffer = buffer.slice(split + 2);
        for (const line of frame.split('\n')) {
          if (!line.startsWith('data:')) continue;
          const payload = line.slice(5).trim();
          if (payload === '[DONE]') { sawDone = true; continue; }
          try {
            const parsed = JSON.parse(payload);
            if (parsed.text) {
              reply.content += parsed.text;
              paintStream(reply.content);
            } else if (parsed.sources !== undefined) {
              // Последний кадр перед [DONE]: подтверждённые фрагменты и подкрепление.
              reply.sources = parsed.sources;
              reply.support = parsed.support || [];
              reply.questions = parsed.questions || [];
              reply.conflicts = parsed.conflicts || [];
              reply.grounded = parsed.grounded;
              reply.grounding = parsed.grounding;
            }
          } catch (_) { /* неполный кадр — придёт в следующем чтении */ }
        }
      }
    }
    setStatus('ready');
  } catch (err) {
    if (err && err.name === 'AbortError') {
      reply.streaming = false;
      reply.stopped = true;
      reply.done = true;
      finish();
      return;
    }
    thread().splice(thread().indexOf(reply), 1);
    pushError('network_error', '');
    setStatus('down');
    finish();
    return;
  }

  reply.streaming = false;
  if (sawDone) {
    reply.done = true;
  } else {
    // Поток кончился, не дойдя до признака завершения: ошибка возникла уже
    // внутри ответа, и превратить её в JSON сервер не мог. Оборванный текст
    // не выдаём за полный ответ.
    reply.broken = true;
    reply.done = true;
  }
  finish();
}

function finish() {
  state.streaming = false;
  controller = null;
  render();
}

// Во время потока перерисовывается только текстовый узел последнего ответа:
// полная перерисовка ленты на каждый токен была бы дорогой и мигала бы.
function paintStream(text) {
  const node = document.getElementById('streaming-text');
  if (!node) { render(); return; }
  node.textContent = plainText(text);
  node.appendChild(el('span', { class: 'caret' }));
  scrollThread();
}

function stopStream() {
  if (controller) controller.abort();
}

function regenerate() {
  const items = thread();
  let lastUser = null;
  for (let i = items.length - 1; i >= 0; i -= 1) {
    if (items[i].role === 'user') { lastUser = items[i]; break; }
  }
  if (!lastUser) return;
  const at = items.indexOf(lastUser);
  items.splice(at, items.length - at);
  render();
  ask(lastUser.content);
}

function retryLast() {
  const items = thread();
  while (items.length && items[items.length - 1].error) items.pop();
  regenerate();
}

// ── локальные карточки интерфейса ─────────────────────────
// Это текст самого интерфейса, а не вывод модели: он помечается подписью и
// не попадает в apiMessages().
function addProtocolCard() {
  if (!activeChat()) newChat();
  state.stick = true;
  thread().push({ role: 'user', content: T().protocolMsg, local: true });
  thread().push({
    role: 'assistant',
    local: true,
    done: true,
    content: T().protocolBody,
    guides: [LOCAL_GUIDE, { t: 'WHO recommendations on antenatal care for a positive pregnancy experience', src: 'who', y: 2016, href: 'https://www.ncbi.nlm.nih.gov/books/NBK409108/' }],
    links: [{ label: T().protocolsLink, href: T().protocolsHref }],
  });
  render();
}

function addConsultCard() {
  if (!activeChat()) newChat();
  state.stick = true;
  thread().push({ role: 'user', content: T().consultMsg, local: true });
  thread().push({ role: 'assistant', local: true, done: true, content: T().consultBody, escalate: true });
  render();
}

// ── состояние сервиса ─────────────────────────────────────
function setStatus(next) {
  if (state.status === next) return;
  state.status = next;
  paintStatus();
}

function paintStatus() {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  if (!dot || !text) return;
  dot.setAttribute('data-state', state.status);
  text.textContent =
    state.status === 'ready' ? T().stReady : state.status === 'down' ? T().stDown : T().stChecking;
}

async function checkReady() {
  try {
    const response = await fetch('/ready', { cache: 'no-store' });
    setStatus(response.ok ? 'ready' : 'down');
  } catch (_) {
    setStatus('down');
  }
}

// ── отрисовка ─────────────────────────────────────────────
function renderGreeting() {
  return el('div', { class: 'greet' }, [
    el('div', { class: 'greet-text' }, [
      el('h2', { text: T().greetTitle }),
      el('p', { text: T().greetBody }),
    ]),
    el('div', { class: 'topics' },
      TOPICS[state.lang].map((topic) =>
        el('button', { class: 'topic', type: 'button', onClick: () => ask(topic.q) }, [
          icon(topic.icon),
          el('span', { text: topic.q }),
        ])
      )
    ),
  ]);
}

// Извлечение из PDF иногда даёт расплющенную таблицу вместо прозы. Показываем
// начало фрагмента: судить по нему уже можно, а полный текст — в документе.
const QUOTE_LIMIT = 360;

function quote(text) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim();
  if (clean.length <= QUOTE_LIMIT) return '«' + clean + '»';
  const cut = clean.slice(0, QUOTE_LIMIT);
  const stop = Math.max(cut.lastIndexOf('. '), cut.lastIndexOf('; '), cut.lastIndexOf(', '));
  return '«' + (stop > QUOTE_LIMIT * 0.6 ? cut.slice(0, stop + 1) : cut) + ' …»';
}

function renderSources(sources) {
  return el('div', { class: 'card' }, [
    el('div', { class: 'card-head' }, [
      icon('book-bookmark'),
      el('span', { class: 'card-title', text: T().sourcesTitle }),
      el('span', { class: 'card-hint', text: T().sourcesNote }),
    ]),
    el('div', { class: 'card-list' },
      sources.map((s, i) =>
        el('div', { class: 'source', id: 'src-' + s.id }, [
          el('span', { class: 'source-num', text: String(i + 1) }),
          el('div', { class: 'source-body' }, [
            // Таблицу цитировать нечем: извлечение расплющивает её в строку.
            // Врачу показывается ссылка на место в документе.
            s.kind === 'table'
              ? el('div', { class: 'source-table' }, [
                  icon('file-text'),
                  el('span', { text: T().tableInDoc }),
                  s.url ? el('a', { href: s.url, target: '_blank', rel: 'noopener noreferrer', text: T().openDoc }) : null,
                ])
              : el('div', { class: 'source-quote', text: quote(s.text) }),
            el('div', { class: 'source-meta' }, [
              icon('file-text'),
              el('span', { class: 'source-doc', text: s.document_title }),
              el('span', { class: 'source-lang', text: s.language.toUpperCase() }),
              el('span', { class: 'source-place', text: s.location }),
            ]),
          ]),
        ])
      )
    ),
  ]);
}

// Подкрепление — ссылками и без цитат: сноска означает источник утверждения,
// а международный документ им не является.
function renderSupport(support) {
  return el('div', { class: 'card support' }, [
    el('div', { class: 'card-head' }, [
      icon('book-bookmark'),
      el('span', { class: 'card-title', text: T().supportTitle }),
    ]),
    el('div', { class: 'card-list' },
      support.map((d) =>
        el('a', { class: 'support-item', href: d.url, target: '_blank', rel: 'noopener noreferrer' }, [
          icon('arrow-up-right'),
          el('span', {}, [
            el('span', { class: 'support-title', text: d.title }),
            el('span', { class: 'support-meta', text: d.origin + ', ' + d.revision }),
          ]),
        ])
      )
    ),
    el('span', { class: 'card-note', text: T().supportNote }),
  ]);
}

// Уточнение врач дополняет данными пациента, которых у ассистента нет,
// поэтому нажатие подставляет вопрос в поле ввода, а не отправляет его.
function useQuestion(text) {
  const input = document.getElementById('input');
  if (!input) return;
  input.value = text;
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
}

function renderQuestions(questions) {
  return el('div', { class: 'card clarify' }, [
    el('div', { class: 'card-head' }, [
      icon('question'),
      el('span', { class: 'card-title', text: T().questionsTitle }),
      el('span', { class: 'card-hint', text: T().questionsNote }),
    ]),
    el('div', { class: 'card-list' },
      questions.map((q) =>
        el('button', { class: 'clarify-item', type: 'button', onClick: () => useQuestion(q.question) }, [
          el('span', { class: 'clarify-q', text: q.question }),
          // Фрагмент вопроса может быть не процитирован в ответе — сноски,
          // ведущей к нему, тогда нет, и документ называется прямо здесь.
          el('span', { class: 'clarify-src' }, [
            icon('file-text'),
            el('span', { text: T().questionsSource + ' ' + q.source.document_title + ' · ' + q.source.location }),
          ]),
        ])
      )
    ),
  ]);
}

// Заметнее уточнений: это не предложение дополнить, а сообщение о том, что
// сказанное врачом не сходится само с собой.
function renderConflicts(conflicts) {
  return el('div', { class: 'card conflict' }, [
    el('div', { class: 'card-head' }, [
      icon('warning-diamond'),
      el('span', { class: 'card-title', text: T().conflictsTitle }),
    ]),
    el('div', { class: 'card-list' },
      conflicts.map((c) =>
        el('div', { class: 'conflict-row' }, [
          el('span', { class: 'conflict-side', text: quote(c.first) }),
          el('span', { class: 'conflict-vs', text: '↔' }),
          el('span', { class: 'conflict-side', text: quote(c.second) }),
        ])
      )
    ),
    el('span', { class: 'card-note', text: T().conflictsNote }),
  ]);
}

// В корпусе ничего не нашлось: показываем, что покрыто, чтобы отказ не был тупиком.
function renderNotFound() {
  return el('div', { class: 'card notfound' }, [
    el('div', { class: 'card-head' }, [icon('search'), el('span', { class: 'card-title', text: T().notFoundTitle })]),
    el('div', { class: 'links' }, [
      el('a', { href: T().protocolsHref, target: '_blank', rel: 'noopener noreferrer' }, [icon('arrow-up-right'), T().protocolsLink]),
    ]),
    el('span', { class: 'card-note', text: T().coveredTitle }),
    el('div', { class: 'chips-row' },
      TOPICS[state.lang].map((t) => el('button', { type: 'button', text: t.q, onClick: () => ask(t.q) }))
    ),
  ]);
}

function renderEscalate() {
  return el('div', { class: 'card escalate' }, [
    el('span', { class: 'card-title', text: T().escalateTitle }),
    el('span', { class: 'card-body', text: T().escalateBody }),
    el('div', { class: 'consults' },
      T().consults.map((label, i) =>
        el('button', {
          type: 'button',
          'aria-pressed': state.consult === i ? 'true' : 'false',
          text: label,
          onClick: () => { state.consult = i; render(); },
        })
      )
    ),
    el('div', { class: 'escalate-cta' }, [
      el('a', { class: 'call', href: 'tel:+998712637829' }, [icon('phone'), T().escalateCall]),
      el('a', { class: 'secondary', href: T().protocolsHref, target: '_blank', rel: 'noopener noreferrer', text: T().protocolsLink }),
    ]),
  ]);
}

function renderActions() {
  return el('div', { class: 'actions' }, [
    el('button', { type: 'button', onClick: regenerate }, [icon('arrows-clockwise'), T().again]),
    el('button', { type: 'button', onClick: addProtocolCard }, [icon('file-text'), T().protocolBtn]),
    el('button', { type: 'button', onClick: addConsultCard }, [icon('headset'), T().consultBtn]),
  ]);
}

function renderError(item) {
  const key = ERROR_TEXT[item.code];
  const body = key ? T()[key] : item.code === 'network_error' ? T().errNetwork : item.message || '';
  return el('div', { class: 'error' }, [
    icon('warning-diamond'),
    el('div', { class: 'error-text' }, [
      el('span', { class: 'error-title', text: T().errTitle }),
      el('span', { class: 'error-body', text: body }),
      el('span', { class: 'error-code', text: item.code }),
      el('button', { type: 'button', onClick: retryLast }, [icon('arrows-clockwise'), T().retry]),
    ]),
  ]);
}

// Сноска ведёт к своему фрагменту ниже. Модель ставит в тексте идентификатор
// фрагмента; какие из них подтверждены, решил сервер — здесь остаётся только
// пронумеровать подтверждённые и убрать всё остальное.
const CITATION = /\[([^\[\]]+:[^\[\]]+:\d+:\d+)\]|\[(\d+)\]/g;

// Модель возвращает Markdown, а поле схемы — строка, поэтому переносы
// приезжают литеральными «\n». Приводим к простому тексту.
function plainText(raw) {
  return String(raw || '')
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, ' ')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/(^|[^\w])\*(.+?)\*(?!\w)/g, '$1$2')
    .replace(/^[ \t]*[*+][ \t]+/gm, '— ')
    .replace(/^[ \t]*#+[ \t]*/gm, '')
    .replace(/\n{3,}/g, '\n\n');
}

function renderAnswerText(item) {
  const node = el('div', { class: 'bot-text' });
  const sources = item.sources || [];
  const byId = new Map(sources.map((s, i) => [s.id, i]));
  const text = plainText(item.content);
  let cursor = 0;
  let match;
  CITATION.lastIndex = 0;
  while ((match = CITATION.exec(text)) !== null) {
    node.appendChild(document.createTextNode(text.slice(cursor, match.index)));
    cursor = match.index + match[0].length;
    const index = match[1] !== undefined ? byId.get(match[1]) : Number(match[2]) - 1;
    const source = index === undefined || index < 0 ? null : sources[index];
    if (!source) continue;  // ссылка в никуда: не показываем вовсе
    node.appendChild(el('a', {
      class: 'footnote',
      href: '#src-' + source.id,
      title: source.document_title + ' — ' + source.location,
      text: String(index + 1),
    }));
  }
  node.appendChild(document.createTextNode(text.slice(cursor)));
  return node;
}

function renderAssistant(item) {
  const body = [];

  if (item.local) body.push(el('span', { class: 'local-note', text: T().localCardNote }));

  if (item.streaming) {
    const text = el('div', { class: 'bot-text', id: 'streaming-text', text: item.content });
    text.appendChild(el('span', { class: 'caret' }));
    body.push(text);
  } else {
    body.push(renderAnswerText(item));
  }

  if (item.broken) {
    body.push(el('span', { class: 'incomplete', text: T().incomplete }));
    body.push(el('div', { class: 'error' }, [
      icon('warning-diamond'),
      el('div', { class: 'error-text' }, [
        el('span', { class: 'error-title', text: T().brokenTitle }),
        el('span', { class: 'error-body', text: T().brokenBody }),
        el('button', { type: 'button', onClick: regenerate }, [icon('arrows-clockwise'), T().retry]),
      ]),
    ]));
  } else if (item.stopped) {
    body.push(el('span', { class: 'incomplete', text: T().stoppedNote }));
  }

  const links = item.links || [];
  if (links.length) {
    body.push(el('div', { class: 'links' },
      links.map((l) => el('a', { href: l.href, target: '_blank', rel: 'noopener noreferrer' }, [icon('arrow-up-right'), l.label]))
    ));
  }

  // У оборванного ответа не показываем ничего, что придаёт ему вид законченного.
  if (item.done && !item.broken) {
    if (item.grounded === false) body.push(renderNotFound());
    if (item.conflicts && item.conflicts.length) body.push(renderConflicts(item.conflicts));
    if (item.sources && item.sources.length) body.push(renderSources(item.sources));
    if (item.support && item.support.length) body.push(renderSupport(item.support));
    if (item.questions && item.questions.length) body.push(renderQuestions(item.questions));
    if (item.escalate || item.local) body.push(renderEscalate());
    if (!item.local) body.push(renderActions());
  }

  return el('div', { class: 'bot' }, [
    el('span', { class: 'bot-avatar' }, [mark(14)]),
    el('div', { class: 'bot-body' }, body),
  ]);
}

function renderChips() {
  const asked = thread().filter((m) => m.role === 'user').map((m) => m.content.toLowerCase());
  const rest = TOPICS[state.lang].filter((t) => !asked.includes(t.q.toLowerCase())).slice(0, 3);
  if (!rest.length) return null;
  return el('div', { class: 'chips' }, [
    el('span', { class: 'chips-label', text: T().chipsLabel }),
    el('div', { class: 'chips-row' },
      rest.map((t) => el('button', { type: 'button', text: t.q, onClick: () => ask(t.q) }))
    ),
  ]);
}

function renderHistory() {
  const list = document.getElementById('history-list');
  list.textContent = '';
  const named = state.chats.filter((c) => c.title);
  if (!named.length) {
    list.appendChild(el('div', { class: 'side-empty', text: T().historyEmpty }));
    return;
  }
  for (const chat of named.slice().reverse()) {
    list.appendChild(
      el('button', {
        class: 'side-item',
        type: 'button',
        'aria-current': chat.id === state.activeId ? 'true' : 'false',
        onClick: () => { if (state.streaming) return; state.activeId = chat.id; state.stick = true; render(); },
      }, [
        el('div', { class: 'side-item-title', text: chat.title }),
        el('div', { class: 'side-item-meta', text: chat.time }),
      ])
    );
  }
}

function render() {
  const col = document.getElementById('col');
  col.textContent = '';
  const items = thread();

  if (!items.length) col.appendChild(renderGreeting());

  for (const item of items) {
    if (item.error) { col.appendChild(el('div', { class: 'msg' }, [renderError(item)])); continue; }
    if (item.role === 'user') {
      col.appendChild(el('div', { class: 'msg' }, [el('div', { class: 'bubble-user', text: item.content })]));
    } else if (item.role === 'assistant') {
      col.appendChild(el('div', { class: 'msg' }, [renderAssistant(item)]));
    }
  }

  if (items.length && !state.streaming) {
    const chips = renderChips();
    if (chips) col.appendChild(chips);
  }

  document.getElementById('send').hidden = state.streaming;
  document.getElementById('stop').hidden = !state.streaming;
  renderHistory();
  scrollThread();
}

function scrollThread() {
  const box = document.getElementById('thread');
  if (state.stick !== false) box.scrollTop = box.scrollHeight;
}

// ── статические подписи и переключатели ───────────────────
function applyStatic() {
  document.documentElement.lang = state.lang;

  for (const node of document.querySelectorAll('[data-t]')) {
    node.textContent = T()[node.getAttribute('data-t')] || '';
  }
  for (const node of document.querySelectorAll('[data-icon]')) {
    node.replaceChildren(icon(node.getAttribute('data-icon')));
  }

  document.getElementById('brand-mark').replaceChildren(mark(18));
  document.getElementById('settings-lang').textContent = T().langNative;
  renderLanguages();

  const newBtn = document.getElementById('new-chat');
  newBtn.replaceChildren(icon('plus'), document.createTextNode(T().newChat));

  document.getElementById('send').replaceChildren(icon('paper-plane-right'));
  document.getElementById('stop').replaceChildren(icon('stop'));

  const input = document.getElementById('input');
  input.placeholder = T().placeholder;
  input.setAttribute('aria-label', T().placeholder);


  paintStatus();
}

// Языки: доступные переключаются, будущие показаны как «скоро», чтобы было
// видно направление продукта, но не создавалось ложное обещание.
const LANGUAGES = [
  { code: 'ru', label: 'Русский', native: 'Русский', ready: true },
  { code: 'uz', label: 'Узбекский', native: 'Oʻzbekcha', ready: true },
  { code: 'en', label: 'Английский', native: 'English', ready: true },
  { code: 'ar', label: 'Арабский', native: 'العربية', ready: false },
];

function renderLanguages() {
  const list = document.getElementById('lang-list');
  list.replaceChildren(...LANGUAGES.map((lang) => {
    const active = lang.code === state.lang;
    const row = el('button', {
      class: 'lang-row' + (lang.ready ? '' : ' soon'),
      type: 'button',
      disabled: !lang.ready,
      'aria-pressed': active ? 'true' : 'false',
    }, [
      el('span', { class: 'lang-label', text: lang.label }),
      el('span', { class: 'lang-native', text: lang.native }),
      lang.ready
        ? (active ? el('span', { class: 'lang-check' }, [icon('check', 'icon')]) : null)
        : el('span', { class: 'lang-soon', text: T().soon }),
    ]);
    if (lang.ready) row.addEventListener('click', () => switchLanguage(lang.code));
    return row;
  }));
}

function switchLanguage(code) {
  if (code === state.lang || state.streaming) return;
  state.lang = code;
  if (activeChat() && activeChat().title) newChat();
  toggleSettings(false);
  applyStatic();
  render();
}

function toggleSettings(open) {
  const panel = document.getElementById('settings-panel');
  const next = open === undefined ? panel.hidden : open;
  panel.hidden = !next;
  document.getElementById('settings-toggle').setAttribute('aria-expanded', next ? 'true' : 'false');
}

function init() {
  newChat();
  applyStatic();
  render();

  document.getElementById('new-chat').addEventListener('click', () => {
    if (state.streaming) stopStream();
    const chat = activeChat();
    if (chat && !chat.title) return;   // текущий диалог ещё пуст
    newChat();
    state.stick = true;
    render();
  });

  document.getElementById('send').addEventListener('click', () => ask(document.getElementById('input').value));
  document.getElementById('stop').addEventListener('click', stopStream);

  const input = document.getElementById('input');
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      ask(input.value);
    }
  });

  document.getElementById('settings-toggle').addEventListener('click', () => toggleSettings());
  document.addEventListener('click', (e) => {
    const panel = document.getElementById('settings-panel');
    if (panel.hidden) return;
    if (panel.contains(e.target) || document.getElementById('settings-toggle').contains(e.target)) return;
    toggleSettings(false);
  });

  document.getElementById('thread').addEventListener('scroll', (e) => {
    const box = e.currentTarget;
    state.stick = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
  }, { passive: true });

  checkReady();
  setInterval(checkReady, 30000);
}

document.addEventListener('DOMContentLoaded', init);
