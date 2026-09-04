// Выгружает данные артборда «Чат-бот центра» (проект Claude Design
// bf1a1126-2a4e-4ca5-b627-e3a6c4e4790e) в app/static/data.js.
//
//   node tools/sync_design.mjs <путь-к-Чат-бот-центра.dc.html> [выходной-файл]
//
// Переносятся словари ru/uz/en, шесть курируемых тем (вопрос, значок, ключевые
// слова, признаки тревоги, ссылки) и подборки клинических руководств.
// Канонические ответы макета НЕ переносятся: ответы даёт живая модель.
//
// Поверх макета накладываются правки, зафиксированные изменением add-web-ui:
// честные подписи источников и признаков тревоги, отделение локального контента
// интерфейса от вывода модели, клиентская история и состояния потока. Они живут
// в EXTRA ниже, поэтому повторная выгрузка их не теряет.

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const [srcArg, outArg] = process.argv.slice(2);
if (!srcArg) {
  console.error('использование: node tools/sync_design.mjs <артборд.dc.html> [выходной-файл]');
  process.exit(1);
}
const SRC = path.resolve(srcArg);
const OUT = path.resolve(outArg ?? 'app/static/data.js');
const src = fs.readFileSync(SRC, 'utf8');

function slice(startMarker, endMarker) {
  const a = src.indexOf(startMarker);
  if (a < 0) throw new Error('not found: ' + startMarker);
  const b = src.indexOf(endMarker, a);
  if (b < 0) throw new Error('end not found for ' + startMarker);
  const chunk = src.slice(a + startMarker.length, b);
  const last = Math.max(chunk.lastIndexOf('};'), chunk.lastIndexOf('];'));
  return chunk.slice(0, last + 1);
}

const L      = eval('({' + slice('  L = {', '  GUIDES = [') + ')');
const GUIDES = eval('([' + slice('  GUIDES = [', '  // per-block source map') + ')');
const QA     = eval('({' + slice('  QA = {', '  componentDidUpdate()') + ')');

// Строки, добавленные при переносе: они фиксируют решения изменения add-web-ui —
// честную подпись панели руководств, отделение локального контента от вывода
// модели, клиентскую историю и состояния потока.
const EXTRA = {
  ru: {
    guidesNote: 'Это не источники ответа: модель отвечает без ссылок на документы. Сверяйте пороги с действующим национальным протоколом центра.',
    flagsSource: "Источник — действующий национальный клинический протокол центра, не ответ модели. Актуальная редакция публикуется на сайте центра:",
    localCardNote: 'Справка интерфейса, не ответ модели',
    historyEmpty: 'Пока пусто. Диалоги этой вкладки появятся здесь.',
    historyNote: 'Только в этой вкладке: сервер диалоги не хранит.',
    stChecking: 'Проверка соединения с моделью',
    stReady: 'Поддержка решения врача · не ставит диагноз',
    stDown: 'Локальная модель недоступна',
    stoppedNote: 'Ответ остановлен врачом, он неполный.',
    brokenTitle: 'Генерация оборвалась',
    brokenBody: 'Поток прервался, не дойдя до конца. Ответ неполный — не опирайтесь на него.',
    errTitle: 'Запрос не выполнен',
    errUnavailable: 'LM Studio не отвечает. Проверьте, запущен ли локальный сервер и загружена ли модель.',
    errTimeout: 'Модель не ответила за отведённое время. Попробуйте сократить вопрос или повторить.',
    errLlm: 'Модель вернула ошибку или пустой ответ.',
    errValidation: 'Запрос не прошёл проверку: вопрос пуст или слишком длинный.',
    errNetwork: 'Сервис недоступен из браузера. Проверьте, запущен ли API.',
    retry: 'Повторить',
    incomplete: 'неполный ответ',
    modelLangNote: 'Меняется только язык интерфейса. Модель отвечает на языке вопроса.',
  },
  uz: {
    guidesNote: 'Bular javob manbalari emas: model hujjatlarga havolasiz javob beradi. Chegaralarni markazning amaldagi milliy protokoli bilan solishtiring.',
    flagsSource: "Manba — markazning amaldagi milliy klinik protokoli, model javobi emas. Joriy tahriri markaz saytida chop etiladi:",
    localCardNote: 'Interfeys ma’lumoti, model javobi emas',
    historyEmpty: 'Hozircha bo‘sh. Shu vkladka dialoglari shu yerda ko‘rinadi.',
    historyNote: 'Faqat shu vkladkada: server dialoglarni saqlamaydi.',
    stChecking: 'Model bilan aloqa tekshirilmoqda',
    stReady: 'Shifokor qaroriga yordam · tashxis qo‘ymaydi',
    stDown: 'Lokal model mavjud emas',
    stoppedNote: 'Javob shifokor tomonidan to‘xtatildi, u to‘liq emas.',
    brokenTitle: 'Generatsiya uzildi',
    brokenBody: 'Oqim oxiriga yetmay uzildi. Javob to‘liq emas — unga tayanmang.',
    errTitle: 'So‘rov bajarilmadi',
    errUnavailable: 'LM Studio javob bermayapti. Lokal server ishga tushganini va model yuklanganini tekshiring.',
    errTimeout: 'Model belgilangan vaqtda javob bermadi. Savolni qisqartiring yoki qayta urinib ko‘ring.',
    errLlm: 'Model xatolik yoki bo‘sh javob qaytardi.',
    errValidation: 'So‘rov tekshiruvdan o‘tmadi: savol bo‘sh yoki juda uzun.',
    errNetwork: 'Xizmat brauzerdan mavjud emas. API ishga tushganini tekshiring.',
    retry: 'Qayta urinish',
    incomplete: 'to‘liq bo‘lmagan javob',
    modelLangNote: 'Faqat interfeys tili o‘zgaradi. Model savol tilida javob beradi.',
  },
  en: {
    guidesNote: 'These are not the sources of the answer: the model replies without citing documents. Verify every threshold against the centre’s current national protocol.',
    flagsSource: "Source — the centre's current national clinical protocol, not the model's answer. The current revision is published on the centre's site:",
    localCardNote: 'Interface reference, not model output',
    historyEmpty: 'Empty so far. Conversations from this tab will appear here.',
    historyNote: 'This tab only: the server keeps no conversations.',
    stChecking: 'Checking the connection to the model',
    stReady: 'Decision support · does not diagnose',
    stDown: 'Local model unavailable',
    stoppedNote: 'The answer was stopped by the clinician and is incomplete.',
    brokenTitle: 'Generation broke off',
    brokenBody: 'The stream ended before completion. The answer is incomplete — do not rely on it.',
    errTitle: 'Request failed',
    errUnavailable: 'LM Studio is not responding. Check that the local server is running and a model is loaded.',
    errTimeout: 'The model did not answer in time. Try a shorter question or repeat the request.',
    errLlm: 'The model returned an error or an empty answer.',
    errValidation: 'The request failed validation: the question is empty or too long.',
    errNetwork: 'The service is unreachable from the browser. Check that the API is running.',
    retry: 'Retry',
    incomplete: 'incomplete answer',
    modelLangNote: 'Only the interface language changes. The model answers in the language of the question.',
  },
};

// В макете узбекская ссылка на протоколы вела в корень сайта; действующий
// раздел — /fan-va-talim/protokollar-va-standartlar (проверено на сайте центра).
L.uz.protocolsHref = 'https://uzaig.uz/fan-va-talim/protokollar-va-standartlar';

const i18n = {};
for (const lang of ['ru', 'uz', 'en']) {
  const { history, ...rest } = L[lang];   // выдуманная история макета не переносится
  i18n[lang] = { ...rest, ...EXTRA[lang] };
}

const topics = {};
for (const lang of ['ru', 'uz', 'en']) {
  topics[lang] = QA[lang].map((x, i) => ({
    id: i,
    q: x.q,
    icon: x.icon.replace(/^ph-/, ''),
    keywords: x.k,
    flags: x.flags || [],
    links: (x.links || []).map(([label, href]) => ({ label, href })),
    escalate: !!x.escalate,
  }));
}

const out = `// СГЕНЕРИРОВАНО из артборда Claude Design «Чат-бот центра» — правьте макет, не этот файл.
// Канонические ответы макета намеренно не перенесены: ответы даёт живая модель.
const I18N = ${JSON.stringify(i18n, null, 2)};

const TOPICS = ${JSON.stringify(topics, null, 2)};

const GUIDES = ${JSON.stringify(GUIDES, null, 2)};
`;
fs.writeFileSync(OUT, out);
console.log('записано:', OUT);
console.log('topics per lang:', topics.ru.length, topics.uz.length, topics.en.length);
console.log('guides groups:', GUIDES.length);
console.log('flags ru:', topics.ru.map(t => t.flags.length).join(','));
console.log('flags uz:', topics.uz.map(t => t.flags.length).join(','));
console.log('flags en:', topics.en.map(t => t.flags.length).join(','));
console.log('i18n keys:', Object.keys(i18n.ru).length);
