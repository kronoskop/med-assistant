"""Предложения, в которых модель говорит, что в фрагментах ответа нет.

Маленькая модель пишет «сведений об этом во фрагментах нет» и всё равно ставит
ссылку. Ссылка из такого предложения не подтверждает ответ: подтверждать нечего.
"""

import re

_ABSENCE = re.compile(
    r"(отсутству\w*|нет\s+(?:сведений|информации|данных|указаний)"
    r"|не\s+(?:содерж\w*|привод\w*|указ\w*|упомина\w*|описан\w*|найден\w*)|не\s+нашл\w*)"
    r"[^.!?]{0,80}(фрагмент\w*|документ\w*|материал\w*)"
    r"|(фрагмент\w*|документ\w*|протокол\w*|материал\w*)[^.!?]{0,80}"
    r"(отсутству\w*|\bнет\b|не\s+(?:содерж\w*|привод\w*|указ\w*|упомина\w*|описан\w*|даю\w*))"
    r"|(not|no)\b[^.!?]{0,60}\b(provided|contain\w*|mention\w*|found|available|includ\w*|specif\w*)"
    r"[^.!?]{0,60}\b(fragment|document|text|source)s?"
    r"|(fragment|document|source)s?\b[^.!?]{0,60}\b(do(es)? not|don't|doesn't)\b"
    r"|(fragment\w*|hujjat\w*|matn\w*)[^.!?]{0,80}(yoʻq|yo'q|keltirilmagan|mavjud\s+emas|berilmagan)",
    re.IGNORECASE,
)


def is_absence(sentence: str) -> bool:
    return bool(_ABSENCE.search(sentence))


_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_MARKER = re.compile(r"\[([^\[\]]+:[^\[\]]+:\d+:\d+)\]")


def _sentences(text: str) -> list[str]:
    """Предложения с их ссылками: ссылка после точки («…г/л. [2]») относится к
    предыдущему предложению."""
    out: list[str] = []
    for piece in _SENTENCE_END.split(text or ""):
        if out and not _MARKER.sub("", piece).strip(" .,;:"):
            out[-1] += " " + piece
        else:
            out.append(piece)
    return out


def without_absence(text: str) -> str:
    """Ответ без предложений «во фрагментах этого нет»."""
    return " ".join(s for s in _sentences(text) if not is_absence(s))


def drop_absence_citations(claimed: list[str], text: str) -> list[str]:
    """Убирает ссылки, которые стоят только в предложениях «этого нет»."""
    kept = set(_MARKER.findall(without_absence(text)))
    absent = set(_MARKER.findall(text)) - kept
    return [i for i in claimed if i not in absent]


def strip_absence_markers(text: str) -> str:
    """Снимает ссылки с предложений «этого нет», остальное не трогает."""
    return " ".join(
        _MARKER.sub("", s) if is_absence(s) else s for s in _sentences(text)
    )
