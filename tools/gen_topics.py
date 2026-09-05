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

QUESTIONS = {
    "placenta-accreta": {
        "icon": "drop",
        "ru": "Врастание и предлежание плаценты — что оценить при подозрении?",
        "uz": "Platsentaning oʻsib kirishi va oldinda yotishi — nimani baholash kerak?",
        "en": "Placenta accreta and praevia — what should I assess on suspicion?",
    },
    "multiple-pregnancy": {
        "icon": "baby",
        "ru": "Монохориальная двойня: как строить наблюдение?",
        "uz": "Monoxorial egizak: kuzatuvni qanday qurish kerak?",
        "en": "Monochorionic twins: how should monitoring be structured?",
    },
    "perineal-tears": {
        "icon": "first-aid-kit",
        "ru": "Разрывы промежности: классификация и тактика восстановления",
        "uz": "Oraliq yorilishlari: tasnifi va tiklash taktikasi",
        "en": "Perineal tears: classification and repair approach",
    },
    "female-infertility": {
        "icon": "test-tube",
        "ru": "Женское бесплодие: с чего начинать обследование пары?",
        "uz": "Ayollar bepushtligi: juftni tekshirishni nimadan boshlash kerak?",
        "en": "Female infertility: where does the couple's workup start?",
    },
    "bartholin-gland": {
        "icon": "heartbeat",
        "ru": "Болезни бартолиновой железы: когда показано дренирование?",
        "uz": "Bartolin bezi kasalliklari: drenaj qachon koʻrsatilgan?",
        "en": "Bartholin gland disease: when is drainage indicated?",
    },
    "cervicitis-vaginitis": {
        "icon": "sun",
        "ru": "Воспаление шейки матки и влагалища: план обследования",
        "uz": "Bachadon boʻyni va vagina yalligʻlanishi: tekshiruv rejasi",
        "en": "Cervicitis and vaginitis: the examination plan",
    },
}

LANGUAGES = ("ru", "uz", "en")


def main() -> None:
    documents = [d for d in load(MANIFEST_PATH) if d.level is EvidenceLevel.BASE]
    missing = [d.id for d in documents if d.id not in QUESTIONS]
    if missing:
        raise SystemExit(f"в корпусе есть документы без вопроса: {', '.join(missing)}")

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
    print(f"тем на язык: {len(documents)} · записано: {out}")


if __name__ == "__main__":
    main()
