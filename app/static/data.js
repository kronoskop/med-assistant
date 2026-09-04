// СГЕНЕРИРОВАНО из артборда Claude Design «Чат-бот центра» — правьте макет, не этот файл.
// Канонические ответы макета намеренно не перенесены: ответы даёт живая модель.
const I18N = {
  "ru": {
    "orgShort": "ГУ «РСНПМЦЗМиР»",
    "orgSub": "Центр здоровья матери и ребёнка",
    "newChat": "Новый вопрос",
    "historyLabel": "История консультаций",
    "whoami": "Врач акушер-гинеколог · филиал",
    "sourceNote": "Ориентиры — национальные протоколы центра и рекомендации ВОЗ",
    "privacyNote": "Не вводите ФИО и идентификаторы пациента",
    "botName": "Клинический справочный ассистент",
    "botStatus": "Поддержка решения врача · не ставит диагноз",
    "protoNote": "прототип · цвета подобраны приближённо",
    "dDense": "Плотно",
    "dAiry": "Свободно",
    "greetTitle": "О каком клиническом вопросе речь?",
    "greetBody": "Опишите случай без персональных данных: срок гестации, значимый анамнез, объективные данные. Дам ориентиры по критериям, порогам и признакам тревоги. Диагноз, назначение и объём обследования остаются за вами.",
    "chipsLabel": "Ещё вопросы",
    "placeholder": "Например: 32 недели, АД 158/104, протеинурия — что оценить в первую очередь?",
    "disclaimer": "Ответы носят справочный характер и поддерживают решение врача: это не диагноз и не назначение. Пороговые значения сверяйте с действующим национальным клиническим протоколом.",
    "again": "Переспросить",
    "protocolBtn": "Где сверить",
    "consultBtn": "Консультация центра",
    "verifySource": "Проверить источник",
    "guidesTitle": "Клинические руководства",
    "guidesNote": "Это не источники ответа: модель отвечает без ссылок на документы. Сверяйте пороги с действующим национальным протоколом центра.",
    "srcWho": "ВОЗ",
    "srcAap": "AAP",
    "srcLocal": "РСНПМЦЗМиР",
    "localGuideTitle": "Национальные клинические протоколы и стандарты центра",
    "protocolsHref": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty",
    "flagsTitle": "Признаки тревоги",
    "flagsNote": "При любом из признаков — немедленная переоценка на месте и решение о переводе на более высокий уровень помощи.",
    "escalateTitle": "Консультация специалиста центра",
    "escalateBody": "Если случай выходит за рамки уровня вашего учреждения, профильную консультацию можно запросить в центре. Выберите направление — сориентирую, к какому подразделению относится вопрос.",
    "escalateCall": "Позвонить в центр",
    "protocolsLink": "Протоколы и стандарты",
    "consults": [
      "Акушерский блок",
      "Фетальная медицина",
      "Неонатология и реанимация",
      "Гинекология"
    ],
    "protocolMsg": "Где сверить эти пороги?",
    "protocolBody": "Опорные документы центра — раздел «Протоколы и стандарты»: центр разрабатывает национальные клинические протоколы и стандарты диагностики и лечения в сфере охраны материнства и детства.\n\nЧто уточнить именно там\n— действующую редакцию протокола по вашему вопросу\n— пороговые значения, принятые в республике, если они отличаются от международных\n— порядок направления и уровни оказания помощи\n\nПо вопросам обучения и повышения квалификации — раздел «Наука и образование».",
    "consultMsg": "Нужна консультация специалиста центра",
    "consultBody": "Профильную консультацию можно запросить в центре — это головное учреждение службы охраны материнства и детства, с акушерским, гинекологическим, неонатальным и реанимационно-анестезиологическим блоками.\n\nЧто подготовить к звонку\n— срок гестации и краткую формулировку случая\n— витальные показатели и значимые лабораторные данные\n— уже выполненные исследования и текущую терапию\n— уровень вашего учреждения и возможности транспортировки",
    "flagsSource": "Источник — действующий национальный клинический протокол центра, не ответ модели. Актуальная редакция публикуется на сайте центра:",
    "localCardNote": "Справка интерфейса, не ответ модели",
    "historyEmpty": "Пока пусто. Диалоги этой вкладки появятся здесь.",
    "historyNote": "Только в этой вкладке: сервер диалоги не хранит.",
    "stChecking": "Проверка соединения с моделью",
    "stReady": "Поддержка решения врача · не ставит диагноз",
    "stDown": "Локальная модель недоступна",
    "stoppedNote": "Ответ остановлен врачом, он неполный.",
    "brokenTitle": "Генерация оборвалась",
    "brokenBody": "Поток прервался, не дойдя до конца. Ответ неполный — не опирайтесь на него.",
    "errTitle": "Запрос не выполнен",
    "errUnavailable": "LM Studio не отвечает. Проверьте, запущен ли локальный сервер и загружена ли модель.",
    "errTimeout": "Модель не ответила за отведённое время. Попробуйте сократить вопрос или повторить.",
    "errLlm": "Модель вернула ошибку или пустой ответ.",
    "errValidation": "Запрос не прошёл проверку: вопрос пуст или слишком длинный.",
    "errNetwork": "Сервис недоступен из браузера. Проверьте, запущен ли API.",
    "retry": "Повторить",
    "incomplete": "неполный ответ",
    "modelLangNote": "Меняется только язык интерфейса. Модель отвечает на языке вопроса."
  },
  "uz": {
    "orgShort": "DM «RIAITMMOʻM»",
    "orgSub": "Ona va bola salomatligi markazi",
    "newChat": "Yangi savol",
    "historyLabel": "Konsultatsiyalar tarixi",
    "whoami": "Akusher-ginekolog · filial",
    "sourceNote": "Asos — markaz milliy protokollari va JSST tavsiyalari",
    "privacyNote": "Bemorning F.I.Sh. va identifikatorlarini kiritmang",
    "botName": "Klinik maʼlumot assistenti",
    "botStatus": "Shifokor qaroriga yordam · tashxis qo‘ymaydi",
    "protoNote": "prototip · ranglar taqriban tanlangan",
    "dDense": "Zich",
    "dAiry": "Erkin",
    "greetTitle": "Qanday klinik savol bo‘yicha yordam kerak?",
    "greetBody": "Holatni shaxsiy ma’lumotlarsiz yozing: gestatsiya muddati, muhim anamnez, obyektiv ko‘rsatkichlar. Mezonlar, chegaralar va xavf belgilari bo‘yicha yo‘naltiraman. Tashxis, tayinlash va tekshiruv hajmi sizda qoladi.",
    "chipsLabel": "Yana savollar",
    "placeholder": "Masalan: 32 hafta, AQB 158/104, proteinuriya — birinchi navbatda nimani baholash kerak?",
    "disclaimer": "Javoblar maʼlumot tarzida bo‘lib, shifokor qaroriga yordam beradi: bu tashxis ham, tayinlash ham emas. Chegaraviy qiymatlarni amaldagi milliy klinik protokol bilan solishtiring.",
    "again": "Qayta so‘rash",
    "protocolBtn": "Qayerdan solishtirish",
    "consultBtn": "Markaz konsultatsiyasi",
    "verifySource": "Manbani tekshirish",
    "guidesTitle": "Klinik qo‘llanmalar",
    "guidesNote": "Bular javob manbalari emas: model hujjatlarga havolasiz javob beradi. Chegaralarni markazning amaldagi milliy protokoli bilan solishtiring.",
    "srcWho": "JSST",
    "srcAap": "AAP",
    "srcLocal": "RIAITMMOʻM",
    "localGuideTitle": "Markazning milliy klinik protokollari va standartlari",
    "protocolsHref": "https://uzaig.uz/fan-va-talim/protokollar-va-standartlar",
    "flagsTitle": "Xavf belgilari",
    "flagsNote": "Belgilardan biri bo‘lsa — joyida darhol qayta baholash va yuqori darajali yordamga o‘tkazish bo‘yicha qaror.",
    "escalateTitle": "Markaz mutaxassisi konsultatsiyasi",
    "escalateBody": "Holat muassasangiz darajasidan chiqsa, markazdan yo‘naltirilgan konsultatsiya so‘rash mumkin. Yo‘nalishni tanlang — savol qaysi bo‘limga tegishli ekanini aytaman.",
    "escalateCall": "Markazga qo‘ng‘iroq",
    "protocolsLink": "Protokollar va standartlar",
    "consults": [
      "Akusherlik bloki",
      "Fetal meditsina",
      "Neonatologiya va reanimatsiya",
      "Ginekologiya"
    ],
    "protocolMsg": "Bu chegaralarni qayerdan solishtiraman?",
    "protocolBody": "Markazning asosiy hujjatlari — «Protokollar va standartlar» bo‘limi: markaz onalik va bolalikni muhofaza qilish sohasida milliy klinik protokollar hamda diagnostika va davolash standartlarini ishlab chiqadi.\n\nAynan shu yerda aniqlanadigan jihatlar\n— savolingizga tegishli protokolning amaldagi tahriri\n— respublikada qabul qilingan chegaraviy qiymatlar, agar ular xalqaro qiymatlardan farq qilsa\n— yo‘naltirish tartibi va yordam darajalari\n\nTa’lim va malaka oshirish bo‘yicha — «Ilm va ta’lim» bo‘limi.",
    "consultMsg": "Markaz mutaxassisi konsultatsiyasi kerak",
    "consultBody": "Yo‘naltirilgan konsultatsiyani markazdan so‘rash mumkin — bu onalik va bolalikni muhofaza qilish xizmatining bosh muassasasi bo‘lib, akusherlik, ginekologiya, neonatal va reanimatsiya-anesteziologiya bloklariga ega.\n\nQo‘ng‘iroqqa nimalarni tayyorlash kerak\n— gestatsiya muddati va holatning qisqa ta’rifi\n— vital ko‘rsatkichlar va muhim laboratoriya ma’lumotlari\n— bajarilgan tekshiruvlar va hozirgi terapiya\n— muassasangiz darajasi va transportirovka imkoniyatlari",
    "flagsSource": "Manba — markazning amaldagi milliy klinik protokoli, model javobi emas. Joriy tahriri markaz saytida chop etiladi:",
    "localCardNote": "Interfeys ma’lumoti, model javobi emas",
    "historyEmpty": "Hozircha bo‘sh. Shu vkladka dialoglari shu yerda ko‘rinadi.",
    "historyNote": "Faqat shu vkladkada: server dialoglarni saqlamaydi.",
    "stChecking": "Model bilan aloqa tekshirilmoqda",
    "stReady": "Shifokor qaroriga yordam · tashxis qo‘ymaydi",
    "stDown": "Lokal model mavjud emas",
    "stoppedNote": "Javob shifokor tomonidan to‘xtatildi, u to‘liq emas.",
    "brokenTitle": "Generatsiya uzildi",
    "brokenBody": "Oqim oxiriga yetmay uzildi. Javob to‘liq emas — unga tayanmang.",
    "errTitle": "So‘rov bajarilmadi",
    "errUnavailable": "LM Studio javob bermayapti. Lokal server ishga tushganini va model yuklanganini tekshiring.",
    "errTimeout": "Model belgilangan vaqtda javob bermadi. Savolni qisqartiring yoki qayta urinib ko‘ring.",
    "errLlm": "Model xatolik yoki bo‘sh javob qaytardi.",
    "errValidation": "So‘rov tekshiruvdan o‘tmadi: savol bo‘sh yoki juda uzun.",
    "errNetwork": "Xizmat brauzerdan mavjud emas. API ishga tushganini tekshiring.",
    "retry": "Qayta urinish",
    "incomplete": "to‘liq bo‘lmagan javob",
    "modelLangNote": "Faqat interfeys tili o‘zgaradi. Model savol tilida javob beradi."
  },
  "en": {
    "orgShort": "RSSPMC MCH",
    "orgSub": "Mother and Child Health Centre",
    "newChat": "New question",
    "historyLabel": "Consultation history",
    "whoami": "Obstetrician-gynaecologist · branch",
    "sourceNote": "Anchored in the centre's national protocols and WHO guidance",
    "privacyNote": "Do not enter patient names or identifiers",
    "botName": "Clinical reference assistant",
    "botStatus": "Decision support · does not diagnose",
    "protoNote": "prototype · colours approximated",
    "dDense": "Dense",
    "dAiry": "Airy",
    "greetTitle": "What is the clinical question?",
    "greetBody": "Describe the case without personal data: gestational age, relevant history, objective findings. I'll point you to criteria, thresholds and warning signs. Diagnosis, prescribing and the extent of workup remain yours.",
    "chipsLabel": "More questions",
    "placeholder": "e.g. 32 weeks, BP 158/104, proteinuria — what should I assess first?",
    "disclaimer": "Answers are reference information supporting the clinician's decision: not a diagnosis and not a prescription. Verify every threshold against the current national clinical protocol.",
    "again": "Ask again",
    "protocolBtn": "Where to verify",
    "consultBtn": "Centre consultation",
    "verifySource": "Verify the source",
    "guidesTitle": "Clinical guidelines",
    "guidesNote": "These are not the sources of the answer: the model replies without citing documents. Verify every threshold against the centre’s current national protocol.",
    "srcWho": "WHO",
    "srcAap": "AAP",
    "srcLocal": "RSSPMC MCH",
    "localGuideTitle": "The centre's national clinical protocols and standards",
    "protocolsHref": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty",
    "flagsTitle": "Warning signs",
    "flagsNote": "Any one of these warrants immediate reassessment at the bedside and a decision on transfer to a higher level of care.",
    "escalateTitle": "Consultation with a centre specialist",
    "escalateBody": "If the case exceeds your facility's level, a specialist consultation can be requested from the centre. Pick a direction and I'll point you to the right unit.",
    "escalateCall": "Call the centre",
    "protocolsLink": "Protocols and standards",
    "consults": [
      "Obstetric block",
      "Fetal medicine",
      "Neonatology and intensive care",
      "Gynaecology"
    ],
    "protocolMsg": "Where do I verify these thresholds?",
    "protocolBody": "The centre's reference documents sit in the “Protocols and standards” section: the centre develops national clinical protocols and standards of diagnosis and treatment in maternal and child health.\n\nWhat to confirm there\n— the current revision of the protocol covering your question\n— threshold values adopted in the republic, where they differ from international ones\n— referral procedure and levels of care\n\nFor training and professional development, see “Science and education”.",
    "consultMsg": "I need a consultation with a centre specialist",
    "consultBody": "A specialist consultation can be requested from the centre — the lead institution of the maternal and child health service, with obstetric, gynaecological, neonatal and intensive care/anaesthesiology blocks.\n\nWhat to have ready for the call\n— gestational age and a short statement of the case\n— vital signs and the relevant laboratory results\n— investigations already done and current therapy\n— your facility's level and transport options",
    "flagsSource": "Source — the centre's current national clinical protocol, not the model's answer. The current revision is published on the centre's site:",
    "localCardNote": "Interface reference, not model output",
    "historyEmpty": "Empty so far. Conversations from this tab will appear here.",
    "historyNote": "This tab only: the server keeps no conversations.",
    "stChecking": "Checking the connection to the model",
    "stReady": "Decision support · does not diagnose",
    "stDown": "Local model unavailable",
    "stoppedNote": "The answer was stopped by the clinician and is incomplete.",
    "brokenTitle": "Generation broke off",
    "brokenBody": "The stream ended before completion. The answer is incomplete — do not rely on it.",
    "errTitle": "Request failed",
    "errUnavailable": "LM Studio is not responding. Check that the local server is running and a model is loaded.",
    "errTimeout": "The model did not answer in time. Try a shorter question or repeat the request.",
    "errLlm": "The model returned an error or an empty answer.",
    "errValidation": "The request failed validation: the question is empty or too long.",
    "errNetwork": "The service is unreachable from the browser. Check that the API is running.",
    "retry": "Retry",
    "incomplete": "incomplete answer",
    "modelLangNote": "Only the interface language changes. The model answers in the language of the question."
  }
};

const TOPICS = {
  "ru": [
    {
      "id": 0,
      "q": "Беременная с АД 158/104 и протеинурией — что оценить в первую очередь?",
      "icon": "heartbeat",
      "keywords": [
        "преэклампси",
        "гипертен",
        "ад ",
        "давлени",
        "протеинур",
        "эклампси"
      ],
      "flags": [
        "АД ≥160/110, не отвечающее на терапию",
        "Головная боль, зрительные нарушения, боль в эпигастрии",
        "Тромбоциты <100×10⁹/л, рост креатинина, АЛТ/АСТ выше нормы вдвое",
        "Отёк лёгких, олигурия, судороги",
        "Признаки страдания плода или отслойки"
      ],
      "links": [
        {
          "label": "Протоколы и стандарты",
          "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
        },
        {
          "label": "Акушерский блок",
          "href": "https://uzaig.uz/ru/klinika/statsionar/akusherskij-blok"
        }
      ],
      "escalate": true
    },
    {
      "id": 1,
      "q": "Какие пороги анемии у беременной и когда нужна парентеральная терапия?",
      "icon": "drop",
      "keywords": [
        "анеми",
        "гемоглобин",
        "hb",
        "железо",
        "ферритин"
      ],
      "flags": [
        "Гемоглобин ниже 70 г/л или симптомная анемия",
        "Признаки декомпенсации: тахикардия покоя, одышка, гипотензия",
        "Продолжающаяся кровопотеря",
        "Отсутствие ответа на терапию через 2–4 недели"
      ],
      "links": [
        {
          "label": "Протоколы и стандарты",
          "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
        },
        {
          "label": "Лаборатория",
          "href": "https://uzaig.uz/ru/klinika/nauchno-konsultativnaya-poliklinika-semya-i-brak/laboratoriya"
        }
      ],
      "escalate": false
    },
    {
      "id": 2,
      "q": "В какие сроки проводится скрининг плода и что входит в каждый этап?",
      "icon": "baby",
      "keywords": [
        "скрининг",
        "срок",
        "нед",
        "птгт",
        "хромосом",
        "порок"
      ],
      "flags": [
        "Высокий расчётный риск хромосомной патологии",
        "Выявленные структурные аномалии плода",
        "Срок за пределами окна скрининга — тактика меняется",
        "Отягощённый семейный или акушерский анамнез"
      ],
      "links": [
        {
          "label": "Отдел скрининга матери и ребёнка",
          "href": "https://uzaig.uz/ru/klinika/otdel-skrininga-materi-i-rebenka"
        },
        {
          "label": "Фетальная медицина",
          "href": "https://uzaig.uz/ru/klinika/nauchno-konsultativnaya-poliklinika-semya-i-brak/fetalnaya-meditsina"
        }
      ],
      "escalate": true
    },
    {
      "id": 3,
      "q": "Как трактовать пероральный глюкозотолерантный тест при беременности?",
      "icon": "test-tube",
      "keywords": [
        "гсд",
        "диабет",
        "глюкоз",
        "ттг",
        "огтт",
        "сахар"
      ],
      "flags": [
        "Гликемия натощак на уровне манифестного диабета",
        "Кетонурия или симптомы гипергликемии",
        "Макросомия или полигидрамнион по УЗИ",
        "Отсутствие контроля на диетотерапии"
      ],
      "links": [
        {
          "label": "Протоколы и стандарты",
          "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
        },
        {
          "label": "Приём беременных",
          "href": "https://uzaig.uz/ru/klinika/nauchno-konsultativnaya-poliklinika-semya-i-brak/priem-beremennykh-i-ginekologicheskikh-patsientov"
        }
      ],
      "escalate": false
    },
    {
      "id": 4,
      "q": "Послеродовое кровотечение: как структурировать первые действия и поиск причины?",
      "icon": "first-aid-kit",
      "keywords": [
        "кровотечен",
        "прк",
        "послеродов",
        "атони",
        "транексам"
      ],
      "flags": [
        "Кровопотеря продолжается несмотря на утеротоники",
        "Нестабильная гемодинамика, шоковый индекс растёт",
        "Подозрение на разрыв матки или инверсию",
        "Признаки коагулопатии",
        "Учреждение без возможностей хирургического гемостаза и трансфузии"
      ],
      "links": [
        {
          "label": "Акушерский блок",
          "href": "https://uzaig.uz/ru/klinika/statsionar/akusherskij-blok"
        },
        {
          "label": "Реанимационно-анестезиологический блок",
          "href": "https://uzaig.uz/ru/klinika/statsionar/reanimatsionno-anesteziologicheskij-blok"
        }
      ],
      "escalate": true
    },
    {
      "id": 5,
      "q": "Желтуха новорождённого: когда это тревожно и что оценивать?",
      "icon": "sun",
      "keywords": [
        "желтух",
        "билирубин",
        "новорожд",
        "фототерап"
      ],
      "flags": [
        "Желтуха в первые 24 часа",
        "Билирубин выше порога обменного переливания",
        "Вялость, отказ от кормления, гипотония, пронзительный крик",
        "Быстрый прирост билирубина на фототерапии",
        "Недоношенность или гемолитическая болезнь"
      ],
      "links": [
        {
          "label": "Неонатальный блок",
          "href": "https://uzaig.uz/ru/klinika/statsionar/neonatalnyj-blok"
        },
        {
          "label": "Протоколы и стандарты",
          "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
        }
      ],
      "escalate": true
    }
  ],
  "uz": [
    {
      "id": 0,
      "q": "Homiladorda AQB 158/104 va proteinuriya — birinchi navbatda nimani baholash kerak?",
      "icon": "heartbeat",
      "keywords": [
        "preeklampsi",
        "gipertenz",
        "aqb",
        "bosim",
        "proteinur",
        "eklampsi"
      ],
      "flags": [
        "Terapiyaga javob bermaydigan AQB ≥160/110",
        "Bosh og‘rigʻi, ko‘rish buzilishi, epigastriy og‘rigʻi",
        "Trombotsitlar <100×10⁹/l, kreatinin oshishi, ALT/AST ikki barobar yuqori",
        "O‘pka shishi, oliguriya, tirishishlar",
        "Homila azob chekishi yoki platsenta ko‘chishi belgilari"
      ],
      "links": [
        {
          "label": "Protokollar va standartlar",
          "href": "https://uzaig.uz/oz/"
        },
        {
          "label": "Akusherlik bloki",
          "href": "https://uzaig.uz/oz/"
        }
      ],
      "escalate": true
    },
    {
      "id": 1,
      "q": "Homiladorda anemiya chegaralari qanday va parenteral terapiya qachon kerak?",
      "icon": "drop",
      "keywords": [
        "anemi",
        "gemoglobin",
        "hb",
        "temir",
        "ferritin"
      ],
      "flags": [
        "Gemoglobin 70 g/l dan past yoki simptomli anemiya",
        "Dekompensatsiya belgilari: tinch holatda taxikardiya, hansirash, gipotenziya",
        "Davom etayotgan qon ketishi",
        "2–4 hafta ichida terapiyaga javob yo‘qligi"
      ],
      "links": [
        {
          "label": "Protokollar va standartlar",
          "href": "https://uzaig.uz/oz/"
        },
        {
          "label": "Laboratoriya",
          "href": "https://uzaig.uz/oz/"
        }
      ],
      "escalate": false
    },
    {
      "id": 2,
      "q": "Homila skriningi qaysi muddatlarda o‘tkaziladi va har bir bosqichga nimalar kiradi?",
      "icon": "baby",
      "keywords": [
        "skrining",
        "muddat",
        "hafta",
        "xromosom",
        "nuqson"
      ],
      "flags": [
        "Xromosoma patologiyasining yuqori hisoblangan xavfi",
        "Aniqlangan struktur anomaliyalar",
        "Muddat skrining oynasidan tashqarida — taktika o‘zgaradi",
        "Og‘irlashgan oilaviy yoki akusherlik anamnezi"
      ],
      "links": [
        {
          "label": "Ona va bola skriningi bo‘limi",
          "href": "https://uzaig.uz/oz/"
        },
        {
          "label": "Fetal meditsina",
          "href": "https://uzaig.uz/oz/"
        }
      ],
      "escalate": true
    },
    {
      "id": 3,
      "q": "Homiladorlikda oral glyukoza tolerantlik testini qanday izohlash kerak?",
      "icon": "test-tube",
      "keywords": [
        "qandli",
        "diabet",
        "glyukoz",
        "ogtt",
        "shakar"
      ],
      "flags": [
        "Nahordagi glikemiya manifest diabet darajasida",
        "Ketonuriya yoki giperglikemiya simptomlari",
        "UTT bo‘yicha makrosomiya yoki poligidramnion",
        "Dietoterapiyada nazorat yo‘qligi"
      ],
      "links": [
        {
          "label": "Protokollar va standartlar",
          "href": "https://uzaig.uz/oz/"
        },
        {
          "label": "Homiladorlar qabuli",
          "href": "https://uzaig.uz/oz/"
        }
      ],
      "escalate": false
    },
    {
      "id": 4,
      "q": "Tug‘ruqdan keyingi qon ketishi: birinchi harakatlar va sabab izlashni qanday tuzish kerak?",
      "icon": "first-aid-kit",
      "keywords": [
        "qon ketish",
        "tug‘ruqdan keyin",
        "atoni",
        "traneksam"
      ],
      "flags": [
        "Uterotoniklarga qaramay qon ketishi davom etmoqda",
        "Beqaror gemodinamika, shok indeksi oshmoqda",
        "Bachadon yorilishi yoki inversiyasiga shubha",
        "Koagulopatiya belgilari",
        "Jarrohlik gemostazi va transfuziya imkoni yo‘q muassasa"
      ],
      "links": [
        {
          "label": "Akusherlik bloki",
          "href": "https://uzaig.uz/oz/"
        },
        {
          "label": "Reanimatsiya-anesteziologiya bloki",
          "href": "https://uzaig.uz/oz/"
        }
      ],
      "escalate": true
    },
    {
      "id": 5,
      "q": "Yangi tug‘ilganda sariqlik: qachon xavfli va nimani baholash kerak?",
      "icon": "sun",
      "keywords": [
        "sarig‘",
        "sarik",
        "bilirubin",
        "yangi tug‘ilgan",
        "fototerap"
      ],
      "flags": [
        "Birinchi 24 soatdagi sariqlik",
        "Almashtirib quyish chegarasidan yuqori bilirubin",
        "Holsizlik, ovqatdan bosh tortish, gipotoniya, o‘tkir yig‘i",
        "Fototerapiyada bilirubinning tez oshishi",
        "Muddatidan oldin tug‘ilish yoki gemolitik kasallik"
      ],
      "links": [
        {
          "label": "Neonatal blok",
          "href": "https://uzaig.uz/oz/"
        },
        {
          "label": "Protokollar va standartlar",
          "href": "https://uzaig.uz/oz/"
        }
      ],
      "escalate": true
    }
  ],
  "en": [
    {
      "id": 0,
      "q": "Pregnant patient, BP 158/104 with proteinuria — what should I assess first?",
      "icon": "heartbeat",
      "keywords": [
        "preeclampsia",
        "pre-eclampsia",
        "hypertens",
        "blood pressure",
        "bp ",
        "proteinuria",
        "eclampsia"
      ],
      "flags": [
        "BP ≥160/110 not responding to treatment",
        "Headache, visual disturbance, epigastric pain",
        "Platelets <100×10⁹/L, rising creatinine, transaminases twice normal",
        "Pulmonary oedema, oliguria, seizures",
        "Signs of fetal compromise or abruption"
      ],
      "links": [
        {
          "label": "Protocols and standards",
          "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
        },
        {
          "label": "Obstetric block",
          "href": "https://uzaig.uz/ru/klinika/statsionar/akusherskij-blok"
        }
      ],
      "escalate": true
    },
    {
      "id": 1,
      "q": "What are the anaemia thresholds in pregnancy, and when is parenteral iron indicated?",
      "icon": "drop",
      "keywords": [
        "anaemia",
        "anemia",
        "haemoglobin",
        "hemoglobin",
        "hb",
        "iron",
        "ferritin"
      ],
      "flags": [
        "Haemoglobin below 70 g/L or symptomatic anaemia",
        "Decompensation: resting tachycardia, dyspnoea, hypotension",
        "Continuing blood loss",
        "No response to therapy after 2–4 weeks"
      ],
      "links": [
        {
          "label": "Protocols and standards",
          "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
        },
        {
          "label": "Laboratory",
          "href": "https://uzaig.uz/ru/klinika/nauchno-konsultativnaya-poliklinika-semya-i-brak/laboratoriya"
        }
      ],
      "escalate": false
    },
    {
      "id": 2,
      "q": "What are the fetal screening windows, and what does each stage include?",
      "icon": "baby",
      "keywords": [
        "screening",
        "window",
        "weeks",
        "chromosom",
        "malformation",
        "nuchal"
      ],
      "flags": [
        "High calculated risk of chromosomal abnormality",
        "Structural fetal anomaly identified",
        "Gestational age outside the screening window — management changes",
        "Significant family or obstetric history"
      ],
      "links": [
        {
          "label": "Mother and child screening",
          "href": "https://uzaig.uz/ru/klinika/otdel-skrininga-materi-i-rebenka"
        },
        {
          "label": "Fetal medicine",
          "href": "https://uzaig.uz/ru/klinika/nauchno-konsultativnaya-poliklinika-semya-i-brak/fetalnaya-meditsina"
        }
      ],
      "escalate": true
    },
    {
      "id": 3,
      "q": "How do I interpret the oral glucose tolerance test in pregnancy?",
      "icon": "test-tube",
      "keywords": [
        "gdm",
        "gestational diabetes",
        "glucose",
        "ogtt",
        "sugar"
      ],
      "flags": [
        "Fasting glucose at overt-diabetes level",
        "Ketonuria or symptoms of hyperglycaemia",
        "Macrosomia or polyhydramnios on ultrasound",
        "No control achieved on dietary therapy"
      ],
      "links": [
        {
          "label": "Protocols and standards",
          "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
        },
        {
          "label": "Antenatal appointments",
          "href": "https://uzaig.uz/ru/klinika/nauchno-konsultativnaya-poliklinika-semya-i-brak/priem-beremennykh-i-ginekologicheskikh-patsientov"
        }
      ],
      "escalate": false
    },
    {
      "id": 4,
      "q": "Postpartum haemorrhage: how should I structure the first actions and the search for a cause?",
      "icon": "first-aid-kit",
      "keywords": [
        "postpartum haemorrhage",
        "postpartum hemorrhage",
        "pph",
        "bleeding",
        "atony",
        "tranexamic"
      ],
      "flags": [
        "Bleeding continues despite uterotonics",
        "Unstable haemodynamics, rising shock index",
        "Suspected uterine rupture or inversion",
        "Signs of coagulopathy",
        "Facility without surgical haemostasis or transfusion capability"
      ],
      "links": [
        {
          "label": "Obstetric block",
          "href": "https://uzaig.uz/ru/klinika/statsionar/akusherskij-blok"
        },
        {
          "label": "Intensive care and anaesthesiology",
          "href": "https://uzaig.uz/ru/klinika/statsionar/reanimatsionno-anesteziologicheskij-blok"
        }
      ],
      "escalate": true
    },
    {
      "id": 5,
      "q": "Neonatal jaundice: when is it concerning and what should I assess?",
      "icon": "sun",
      "keywords": [
        "jaundice",
        "bilirubin",
        "neonat",
        "phototherapy"
      ],
      "flags": [
        "Jaundice within the first 24 hours",
        "Bilirubin above the exchange transfusion threshold",
        "Lethargy, poor feeding, hypotonia, high-pitched cry",
        "Rapid bilirubin rise despite phototherapy",
        "Prematurity or haemolytic disease"
      ],
      "links": [
        {
          "label": "Neonatal block",
          "href": "https://uzaig.uz/ru/klinika/statsionar/neonatalnyj-blok"
        },
        {
          "label": "Protocols and standards",
          "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
        }
      ],
      "escalate": true
    }
  ]
};

const GUIDES = [
  [
    {
      "t": "WHO recommendations for prevention and treatment of pre-eclampsia and eclampsia",
      "src": "who",
      "y": 2011,
      "href": "https://www.who.int/publications/i/item/9789241548335"
    },
    {
      "t": "WHO recommendations on antiplatelet agents for the prevention of pre-eclampsia",
      "src": "who",
      "y": 2021,
      "href": "https://www.who.int/publications/i/item/9789240037540"
    },
    {
      "t": "",
      "src": "local",
      "y": "",
      "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
    }
  ],
  [
    {
      "t": "Guideline on haemoglobin cutoffs to define anaemia in individuals and populations",
      "src": "who",
      "y": 2024,
      "href": "https://www.who.int/publications/i/item/9789240088542"
    },
    {
      "t": "WHO recommendations on antenatal care for a positive pregnancy experience",
      "src": "who",
      "y": 2016,
      "href": "https://www.ncbi.nlm.nih.gov/books/NBK409108/"
    },
    {
      "t": "",
      "src": "local",
      "y": "",
      "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
    }
  ],
  [
    {
      "t": "WHO recommendations on antenatal care for a positive pregnancy experience — maternal and fetal assessment",
      "src": "who",
      "y": 2016,
      "href": "https://www.ncbi.nlm.nih.gov/books/NBK409108/"
    },
    {
      "t": "WHO antenatal care recommendations — highlights and key messages",
      "src": "who",
      "y": 2018,
      "href": "https://www.who.int/publications/i/item/WHO-RHR-18.02"
    },
    {
      "t": "",
      "src": "local",
      "y": "",
      "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
    }
  ],
  [
    {
      "t": "Diagnostic criteria and classification of hyperglycaemia first detected in pregnancy",
      "src": "who",
      "y": 2013,
      "href": "https://apps.who.int/iris/handle/10665/85975"
    },
    {
      "t": "Hyperglycaemia first detected in pregnancy — recommendations chapter",
      "src": "who",
      "y": 2013,
      "href": "https://www.ncbi.nlm.nih.gov/books/NBK169023/"
    },
    {
      "t": "",
      "src": "local",
      "y": "",
      "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
    }
  ],
  [
    {
      "t": "Consolidated guidelines for the prevention, diagnosis and treatment of postpartum haemorrhage",
      "src": "who",
      "y": 2025,
      "href": "https://www.ncbi.nlm.nih.gov/books/NBK619236/"
    },
    {
      "t": "WHO recommendations for the prevention and treatment of postpartum haemorrhage",
      "src": "who",
      "y": 2012,
      "href": "https://www.who.int/publications/i/item/9789241548502"
    },
    {
      "t": "WHO recommendations: uterotonics for the prevention of postpartum haemorrhage",
      "src": "who",
      "y": 2018,
      "href": "https://www.who.int/publications-detail-redirect/9789241550420"
    }
  ],
  [
    {
      "t": "Clinical Practice Guideline Revision: Management of Hyperbilirubinemia in the Newborn Infant 35 or More Weeks of Gestation",
      "src": "aap",
      "y": 2022,
      "href": "https://publications.aap.org/pediatrics/article/150/3/e2022058859/188726/Clinical-Practice-Guideline-Revision-Management-of"
    },
    {
      "t": "AAP hyperbilirubinemia clinical resources and thresholds",
      "src": "aap",
      "y": 2022,
      "href": "https://www.aap.org/en/patient-care/hyperbilirubinemia/"
    },
    {
      "t": "",
      "src": "local",
      "y": "",
      "href": "https://uzaig.uz/ru/nauka-i-obrazovanie/protokoly-i-standarty"
    }
  ]
];
