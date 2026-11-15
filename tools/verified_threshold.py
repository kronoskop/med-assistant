"""Замер порога близости для принятых медиками ответов (VERIFIED_MIN_SCORE).

    uv run python tools/verified_threshold.py

Печатает близость вопроса к его перефразировкам (должны получать принятый
ответ) и к похожим, но другим вопросам (не должны). Порог ставится выше
самого близкого «другого» вопроса. Если перефразировки и другие вопросы не
разделяются, оставьте VERIFIED_MIN_SCORE=0 — только точное совпадение.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.corpus.embed import embed_query, model_id  # noqa: E402
from app.settings import get_settings  # noqa: E402

# (вопрос, перефразировки, похожие вопросы с другим ответом)
CASES = [
    (
        "Анемия у беременных: порог гемоглобина?",
        ["Какой порог гемоглобина при анемии у беременных?", "При каком гемоглобине ставят анемию беременной?",
         "анемия беременных порог гемоглобина"],
        ["Анемия у детей: порог гемоглобина?", "Анемия у беременных: порог ферритина?",
         "Анемия у беременных: лечение препаратами железа", "Анемия у беременных: порог гемоглобина во втором триместре?",
         "Гестационный диабет: порог глюкозы?"],
    ),
    (
        "Какая доза магния сульфата при тяжёлой преэклампсии?",
        ["Доза сульфата магния при тяжелой преэклампсии", "Сколько магния сульфата вводить при тяжёлой преэклампсии?"],
        ["Какая доза нифедипина при тяжёлой преэклампсии?", "Какая доза магния сульфата при эклампсии?",
         "Какая доза магния сульфата при лёгкой преэклампсии?"],
    ),
    (
        "Homilador ayollarda anemiya: gemoglobin chegarasi qanday?",
        ["Homiladorlarda anemiyada gemoglobin chegarasi qancha?"],
        ["Homilador ayollarda anemiya: davolash qanday?", "Bolalarda anemiya: gemoglobin chegarasi qanday?"],
    ),
    (
        "What is the hemoglobin threshold for anemia in pregnancy?",
        ["Hemoglobin cutoff for anaemia in pregnant women?"],
        ["What is the ferritin threshold for anemia in pregnancy?", "What is the hemoglobin threshold for anemia in children?"],
    ),
]


def main() -> None:
    settings = get_settings()
    print(f"Модель: {model_id(settings)}\n")
    same_scores, other_scores = [], []
    for question, same, other in CASES:
        base = embed_query(question, settings)[0]
        print(question)
        for label, group, bucket in (("тот же", same, same_scores), ("другой", other, other_scores)):
            for text in group:
                score = float(embed_query(text, settings)[0] @ base)
                bucket.append(score)
                print(f"  {score:.3f}  {label}  {text}")
        print()
    lowest_same, highest_other = min(same_scores), max(other_scores)
    print(f"Перефразировки: от {lowest_same:.3f}. Другие вопросы: до {highest_other:.3f}.")
    if highest_other < lowest_same:
        print(f"Разделяются. VERIFIED_MIN_SCORE={(lowest_same + highest_other) / 2:.3f}")
    else:
        caught = sum(s > highest_other for s in same_scores)
        print(
            f"Не разделяются. Безопасный порог VERIFIED_MIN_SCORE={highest_other + 0.005:.3f} "
            f"узнаёт {caught} из {len(same_scores)} перефразировок; либо оставьте 0."
        )


if __name__ == "__main__":
    main()
