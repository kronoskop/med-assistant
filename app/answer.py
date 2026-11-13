"""Сборка ответа чата: отбор фрагментов, проверка ссылок, отказ при пустоте.

Здесь проходит граница доверия: модель заявляет источники, а подтверждаются
только те, что действительно были отобраны.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.corpus.index import Hit
from app.corpus.service import Grounding, Retrieval
from app.prompt import REFUSAL_EMPTY_CORPUS, REFUSAL_NO_MATCH
from app.schemas import Clarification, Conflict, SourceFragment, SupportDocument

# Больше трёх уточнений врач не прочитает, а ассистент, требующий заполнить
# анкету, перестанет использоваться после второго раза.
MAX_QUESTIONS = 3


@dataclass(frozen=True)
class Grounded:
    retrieval: Retrieval
    fragments_prompt: str


def refusal_text(status: Grounding) -> str:
    return REFUSAL_EMPTY_CORPUS if status is Grounding.EMPTY_CORPUS else REFUSAL_NO_MATCH


def resolve_ref(raw: object, hits: tuple[Hit, ...]) -> Hit | None:
    """Фрагмент по ссылке модели: номеру из списка («2», «[2]») или идентификатору.

    Модели показываются номера: длинные идентификаторы вида
    `mz-777:ru:12:3` маленькая модель не переписывает и просто опускает.
    Номер вне списка — ссылка в никуда, её нет.
    """
    ref = str(raw or "").strip().strip("[]").strip()
    if ref.isdigit():
        index = int(ref) - 1
        return hits[index] if 0 <= index < len(hits) else None
    return next((hit for hit in hits if hit.fragment.id == ref), None)


def confirmed_sources(claimed: tuple[str, ...] | list[str], hits: tuple[Hit, ...]) -> list[SourceFragment]:
    """Оставляет только те ссылки, что указывают на реально отобранные фрагменты.

    Модель охотно ссылается на правдоподобные, но не существовавшие фрагменты;
    без этой сверки продукт получил бы фальшивую трассируемость.
    """
    sources: list[SourceFragment] = []
    seen: set[str] = set()
    for raw in claimed:
        hit = resolve_ref(raw, hits)
        if hit is None or hit.fragment.id in seen:
            continue
        seen.add(hit.fragment.id)
        sources.append(_source_fragment(hit))
    return sources


def _source_fragment(hit: Hit) -> SourceFragment:
    return SourceFragment(
        id=hit.fragment.id,
        document_id=hit.document.id,
        document_title=hit.document.title,
        origin=hit.document.origin,
        revision=hit.document.revision,
        language=hit.fragment.language,
        location=hit.fragment.location,
        text=hit.fragment.text,
        kind=hit.fragment.kind,
        url=_edition_url(hit),
    )


def confirmed_questions(claimed, hits: tuple[Hit, ...]) -> list[Clarification]:
    """Оставляет уточнения, опирающиеся на реально отобранные фрагменты.

    Уточнение — это утверждение «протокол требует это учитывать». Без фрагмента
    под ним оно превращается в догадку модели о том, что бывает важно, и
    наследует все её ошибки.
    """
    out: list[Clarification] = []
    seen: set[str] = set()
    for item in claimed:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        hit = resolve_ref(item.get("source"), hits)
        if not question or hit is None or question.casefold() in seen:
            continue
        seen.add(question.casefold())
        out.append(Clarification(question=question, source=_source_fragment(hit)))
        if len(out) == MAX_QUESTIONS:
            break
    return out


def doctor_words(messages) -> str:
    """Всё, что сказал врач. Ответы ассистента сюда не входят: противоречие
    ищется в сведениях о случае, а не в том, что модель успела написать."""
    return "\n".join(m.content for m in messages if m.role == "user")


def _comparable(text: str) -> str:
    """Приводит цитату к виду, в котором её можно искать в словах врача:
    пробелы схлопнуты, обрамляющие кавычки и знаки препинания сняты."""
    return re.sub(r"\s+", " ", text).strip(" .,;:!?—–-«»\"'").casefold()


def confirmed_conflicts(claimed, said: str = "") -> list[Conflict]:
    """Оставляет отметки, обе стороны которых врач действительно произнёс.

    Сторона — цитата из слов врача, и непроверенная цитата приписала бы ему то,
    чего он не говорил: та же фальшивая трассируемость, от которой защищены
    сноски. Отметка без обеих сторон вычёркивается — «данные противоречивы» без
    указания на что подрывает доверие ко всему ответу.
    """
    source = _comparable(said)
    out: list[Conflict] = []
    seen: set[tuple[str, str]] = set()
    for item in claimed:
        if not isinstance(item, dict):
            continue
        first = str(item.get("first") or "").strip()
        second = str(item.get("second") or "").strip()
        if not first or not second:
            continue
        left, right = _comparable(first), _comparable(second)
        # Вложенность — признак того, что модель сложила в одну отметку
        # предложение целиком и его же часть: сторон здесь не две, а одна.
        if left in right or right in left:
            continue
        if left not in source or right not in source:
            continue
        if (left, right) in seen or (right, left) in seen:
            continue
        seen.add((left, right))
        out.append(Conflict(first=first, second=second))
    return out


def _edition_url(hit: Hit) -> str | None:
    """Адрес той языковой редакции, из которой взят фрагмент."""
    edition = hit.document.edition(hit.fragment.language)
    return edition.url if edition else None


def support_documents(retrieval: Retrieval) -> list[SupportDocument]:
    out: list[SupportDocument] = []
    for document in retrieval.support:
        edition = document.editions[0]
        out.append(
            SupportDocument(
                document_id=document.id,
                title=document.title,
                origin=document.origin,
                revision=document.revision,
                url=edition.url,
            )
        )
    return out


_UZ_LATIN = re.compile(r"[og][ʻʼ‘’'`]|\b(va|uchun|bilan|qanday|qachon|nima|kerak|boʻl|bo'l|homilador|davolash|bemor)\b", re.IGNORECASE)


def question_language(text: str) -> str:
    """Язык вопроса врача: ru, uz (латиница) или en — чтобы прямо сказать
    модели, на каком языке отвечать. Кириллица считается русской: узбекские
    вопросы в демо пишутся латиницей."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "ru"
    cyrillic = sum("а" <= c.lower() <= "я" or c in "ёЁ" for c in letters)
    if cyrillic * 2 >= len(letters):
        return "ru"
    return "uz" if _UZ_LATIN.search(text) else "en"


def last_question(messages) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


# Ссылка внутри ответа: [document:язык:страница:порядок]
_MARKER = re.compile(r"\[([^\[\]]+:[^\[\]]+:\d+:\d+)\]")


def normalize_answer(text: str) -> str:
    """Приводит ответ к простому тексту.

    Модель возвращает разметку Markdown, а поле схемы — строка, поэтому
    переносы приезжают как литеральные «\\n». В ленте это выглядело как
    сломанный вывод: звёздочки и обратные слэши прямо в тексте.
    """
    out = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", " ")
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", out)          # жирный
    out = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", out)   # курсив
    out = re.sub(r"^\s*[*+]\s+", "— ", out, flags=re.M)   # маркеры списка
    out = re.sub(r"^\s*#+\s*", "", out, flags=re.M)       # заголовки
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


# Номера фрагментов в тексте модели: [2], [1, 3], [1; 3].
_NUMBERED = re.compile(r"\[\s*(\d{1,2}(?:\s*[,;]\s*\d{1,2})*)\s*\]")
# Сколько символов после «[» ждать закрывающую скобку, прежде чем отпустить текст.
_PENDING_LIMIT = 16


def numbered_to_ids(text: str, hits: tuple[Hit, ...]) -> str:
    """Переводит номера фрагментов в идентификаторы: дальше по стеку — и в
    интерфейсе — ссылка всегда идентификатор. Номер вне списка вычёркивается."""

    def replace(match: re.Match[str]) -> str:
        found = [resolve_ref(n, hits) for n in re.split(r"[,;]", match.group(1))]
        return "".join(f"[{hit.fragment.id}]" for hit in found if hit is not None)

    return _NUMBERED.sub(replace, text)


class MarkerRewriter:
    """`numbered_to_ids` для потока: номер может разрезаться между кусками,
    поэтому хвост с незакрытой «[» придерживается до следующего куска."""

    def __init__(self, hits: tuple[Hit, ...]) -> None:
        self.hits = hits
        self.pending = ""

    def feed(self, chunk: str) -> str:
        text = self.pending + chunk
        cut = text.rfind("[")
        if cut >= 0 and "]" not in text[cut:] and len(text) - cut <= _PENDING_LIMIT:
            text, self.pending = text[:cut], text[cut:]
        else:
            self.pending = ""
        return numbered_to_ids(text, self.hits)

    def flush(self) -> str:
        text, self.pending = self.pending, ""
        return numbered_to_ids(text, self.hits)


class RepeatGuard:
    """Замечает, что ответ пошёл по кругу: законченное предложение длиной от
    30 знаков слово в слово повторило уже написанное."""

    _END = re.compile(r"(?<=[.!?…])\s+")

    def __init__(self) -> None:
        self.checked = 0

    def repeated(self, text: str) -> bool:
        sentences = [_comparable(s) for s in self._END.split(text)[:-1]]  # последнее ещё пишется
        done = [s for s in sentences if len(s) >= 30]
        fresh = len(done) > self.checked
        self.checked = len(done)
        return fresh and done[-1] in done[:-1]


def weave_citations(text: str, hits: tuple[Hit, ...]) -> tuple[str, list[SourceFragment]]:
    """Заменяет идентификаторы в тексте на номера сносок.

    В ответе остаются только ссылки на реально отобранные фрагменты: выдуманный
    идентификатор вычёркивается вместе со скобками, иначе врач увидел бы сноску,
    ведущую в никуда. Нумерация — по первому появлению в тексте, чтобы номер
    сноски совпадал с порядком чтения.
    """
    by_id = {hit.fragment.id: hit for hit in hits}
    order: list[str] = []

    def replace(match: re.Match[str]) -> str:
        fragment_id = match.group(1)
        if fragment_id not in by_id:
            return ""  # ссылка в никуда: убираем вместе со скобками
        if fragment_id not in order:
            order.append(fragment_id)
        return f"[{order.index(fragment_id) + 1}]"

    woven = _MARKER.sub(replace, normalize_answer(text))
    woven = re.sub(r" +([.,;:])", r"\1", woven)
    woven = re.sub(r"[ \t]{2,}", " ", woven).strip()
    return woven, confirmed_sources(order, hits)
