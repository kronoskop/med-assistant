"""Собирает app/static/topics.js из манифеста корпуса.

Тема существует, только если под ней есть документ: идентификаторы берутся
из манифеста, поэтому список тем не может разойтись с корпусом молча.
Формулировки вопросов курируются здесь — они обращены к врачу, а не
пересказывают название документа.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.corpus.manifest import EvidenceLevel, load  # noqa: E402
from app.corpus.store import MANIFEST_PATH  # noqa: E402

# Тем на стартовом экране немного: это витрина, а не оглавление корпуса.
# Каждая обязана указывать на документ основы, но не каждый документ обязан
# попасть в витрину — иначе список станет нечитаемым.
QUESTIONS = {
    "mz-781": {
        "icon": "test-tube",
        "ru": "Гестационный сахарный диабет: пороги и тактика",
        "uz": "Gestatsion qandli diabet: chegaralar va taktika",
        "en": "Gestational diabetes: thresholds and management",
    },
    "mz-777": {
        "icon": "drop",
        "ru": "Ведение беременных с железодефицитной анемией",
        "uz": "Temir tanqisligi anemiyasi bilan homiladorlarni olib borish",
        "en": "Managing pregnancy with iron-deficiency anaemia",
    },
    "mz-779": {
        "icon": "baby",
        "ru": "Антенатальный уход: ведение беременных групп риска",
        "uz": "Antenatal parvarish: xavf guruhidagi homiladorlar",
        "en": "Antenatal care: managing high-risk pregnancies",
    },
    "mz-785": {
        "icon": "first-aid-kit",
        "ru": "Кесарево сечение: показания и подготовка",
        "uz": "Kesar kesish: koʻrsatmalar va tayyorgarlik",
        "en": "Caesarean section: indications and preparation",
    },
    "mz-806": {
        "icon": "heartbeat",
        "ru": "Сепсис и септический шок в акушерстве",
        "uz": "Akusherlikda sepsis va septik shok",
        "en": "Sepsis and septic shock in obstetrics",
    },
    "mz-808": {
        "icon": "sun",
        "ru": "Скрининг рака шейки матки: тактика ведения",
        "uz": "Bachadon boʻyni saratoni skriningi: olib borish taktikasi",
        "en": "Cervical cancer screening: management",
    },
}

LANGUAGES = ("ru", "uz", "en")


def main() -> None:
    known = {d.id: d for d in load(MANIFEST_PATH) if d.level is EvidenceLevel.BASE}
    unknown = [key for key in QUESTIONS if key not in known]
    if unknown:
        raise SystemExit(f"вопрос ссылается на документ вне основы: {', '.join(unknown)}")

    documents = [known[key] for key in QUESTIONS]
    topics = {lang: [] for lang in LANGUAGES}
    for number, document in enumerate(documents, start=1):
        entry = QUESTIONS[document.id]
        for lang in LANGUAGES:
            topics[lang].append(
                {
                    "documentId": document.id,
                    "number": f"{number:02d}",
                    "icon": entry["icon"],
                    "q": entry[lang],
                }
            )

    out = Path(__file__).resolve().parents[1] / "app" / "static" / "topics.js"
    out.write_text(
        "// СГЕНЕРИРОВАНО из app/corpus/documents.json — правьте манифест и tools/gen_topics.py.\n"
        "// Тема существует, только если под ней есть документ корпуса.\n"
        f"const TOPICS = {json.dumps(topics, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    print(f"тем на язык: {len(documents)} из {len(known)} документов основы · записано: {out}")


if __name__ == "__main__":
    main()
