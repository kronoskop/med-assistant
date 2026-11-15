import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.absence import drop_absence_citations, strip_absence_markers, without_absence
from app.answer import (
    MarkerRewriter,
    RepeatGuard,
    confirmed_conflicts,
    confirmed_questions,
    confirmed_sources,
    doctor_words,
    last_question,
    numbered_to_ids,
    question_language,
    refusal_text,
    support_documents,
    weave_citations,
)
from app.corpus.service import Grounding, Retrieval, Retriever, get_retriever, render_fragments
from app.llm import Claims, LLMClient, cited_ids, ensure_structured_output, get_llm
from app.prompt import DISCLAIMER
from app.review.auth import current_user
from app.review.verified import Verified, VerifiedAnswers, get_verified_answers
from app.settings import get_settings
from app.schemas import UTF8JSONResponse, AppError, ChatMessage, ChatRequest, ChatResponse

router = APIRouter()

# Время по этапам — без текста запроса и ответа: по нему видно, где теряются
# секунды, а клинического содержания в нём нет.
timing_logger = logging.getLogger("app.timing")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(llm: LLMClient = Depends(get_llm)):
    try:
        await llm.ping()
        await ensure_structured_output(llm)
    except AppError as exc:
        return UTF8JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "code": exc.code,
                "message": exc.message,
            },
        )
    return {"status": "ready"}


@router.post("/api/v1/chat")
async def chat(
    body: ChatRequest,
    llm: LLMClient = Depends(get_llm),
    retriever: Retriever = Depends(get_retriever),
    verified_answers: VerifiedAnswers = Depends(get_verified_answers),
    _user: dict = Depends(current_user),
):
    started = time.perf_counter()
    question = last_question(body.messages)
    # Принятый медиками ответ отдаётся дословно, без поиска и без модели.
    # Только на первый вопрос диалога: смысл последующих зависит от предыстории.
    if sum(m.role == "user" for m in body.messages) == 1:
        verified = await asyncio.to_thread(verified_answers, question)
        if verified is not None:
            _log_timing(stream=body.stream, verified=verified.refinement_id, total_ms=_ms(started))
            if body.stream:
                return StreamingResponse(_sse_verified(verified), media_type="text/event-stream")
            return ChatResponse(
                message=ChatMessage(role="assistant", content=verified.text),
                disclaimer=DISCLAIMER,
                grounding="verified",
                verified=verified.payload(),
            )
    language = question_language(question)
    # Отбор синхронный (эмбеддинг — сетевой запрос): в отдельном потоке он не
    # останавливает обслуживание остальных врачей.
    retrieval = await asyncio.to_thread(retriever, question)
    retrieval_ms = _ms(started)

    # Без фрагментов основы модель не зовём вовсе: отказ формулирует сервер,
    # иначе ответ пришёл бы из памяти модели.
    if not retrieval.is_grounded:
        text = refusal_text(retrieval.status)
        if body.stream:
            return StreamingResponse(_sse_refusal(text, retrieval), media_type="text/event-stream")
        return _response(text, retrieval, [])

    fragments = render_fragments(retrieval.hits)
    said = doctor_words(body.messages)
    if body.stream:
        claims = Claims()
        chunks = await llm.start_chat_stream(body.messages, fragments, claims, language=language)
        timing = {"started": started, "retrieval_ms": retrieval_ms}
        return StreamingResponse(
            _sse(chunks, claims, retrieval, said, timing, retriever), media_type="text/event-stream"
        )

    answer = await llm.complete(body.messages, fragments, language=language)
    _log_timing(
        stream=False,
        retrieval_ms=retrieval_ms,
        total_ms=_ms(started),
        reasoning_chars=getattr(answer, "reasoning_chars", 0),
        answer_chars=len(answer.text),
    )
    with_ids = strip_absence_markers(numbered_to_ids(answer.text, retrieval.hits))
    woven, inline = weave_citations(with_ids, retrieval.hits)
    claimed = drop_absence_citations([s.id for s in inline] or list(answer.source_ids), with_ids)
    substance = without_absence(with_ids)
    attribution = "model"
    if not confirmed_sources(claimed, retrieval.hits):
        claimed, _ = await _attribute(retriever, without_absence(woven), retrieval)
        attribution = "similarity"
    elif _unsupported(await _support(retriever, substance, retrieval)):
        claimed = []
    _, grounded, _ = _settle(woven, retrieval, claimed)
    if not grounded:
        return _response(refusal_text(Grounding.NO_MATCH), retrieval, [])
    response = _response(woven, retrieval, claimed, answer.questions, answer.conflicts, said)
    response.attribution = attribution
    return response


async def _support(retriever: Retriever, text: str, retrieval: Retrieval) -> float | None:
    """Близость предложений со ссылками модели к их фрагментам (corpus.service.citation_support)."""
    support = getattr(retriever, "citation_support", None)
    if support is None:
        return None
    return await asyncio.to_thread(support, text, retrieval.hits)


def _unsupported(score: float | None) -> bool:
    """Ссылки модели есть, но сказанное на фрагменты не похоже: стих о море со
    ссылкой на протокол. Такой ответ не подтверждён."""
    threshold = get_settings().citation_min_support
    return score is not None and threshold > 0 and score < threshold


async def _attribute(retriever: Retriever, text: str, retrieval: Retrieval) -> tuple[list[str], float]:
    """Запасные сноски по близости предложений к фрагментам (см. corpus.service.attribute).
    Подменённый в тестах отборщик может их не уметь — тогда сносок нет."""
    attribute = getattr(retriever, "attribute", None)
    if attribute is None or not text.strip():
        return [], 0.0
    return await asyncio.to_thread(attribute, text, retrieval.hits)


def _response(text: str, retrieval: Retrieval, claimed, questions=(), conflicts=(), said: str = "") -> ChatResponse:
    """Уточнения приходят пустыми по умолчанию: к отказу их не добавляют —
    его смысл в том, что подтверждать нечего, и спрашивать не о чем."""
    sources, grounded, status = _settle(text, retrieval, claimed)
    return ChatResponse(
        message=ChatMessage(role="assistant", content=text),
        disclaimer=DISCLAIMER,
        grounded=grounded,
        grounding=status,
        sources=sources,
        support=support_documents(retrieval),
        questions=confirmed_questions(questions, retrieval.hits),
        conflicts=confirmed_conflicts(conflicts, said),
    )


def _settle(text: str, retrieval: Retrieval, claimed):
    """Заземлён ли ответ, решает не близость, а цитирование.

    Косинусная оценка не отделяет профильный вопрос от постороннего: у обоих
    она одинаковая. Судит модель, прочитавшая фрагменты: если она не сослалась
    ни на один, подтверждать нечего.
    """
    sources = confirmed_sources(claimed, retrieval.hits)
    if not retrieval.is_grounded:
        return sources, False, retrieval.status.value
    if not sources:
        return [], False, Grounding.NO_MATCH.value
    return sources, True, retrieval.status.value


def _sources_event(
    retrieval: Retrieval,
    claims: Claims,
    said: str = "",
    attribution: str = "model",
    attribution_score: float | None = None,
) -> str:
    sources, grounded, status = _settle("", retrieval, claims.source_ids)
    payload = {
        "grounded": grounded,
        "attribution": attribution,
        "attribution_score": attribution_score,
        # Ответ уже показан по мере генерации; не подтвердился — интерфейс
        # заменяет его этим отказом, как в ответе без потока.
        "refusal": None if grounded or not retrieval.is_grounded else refusal_text(Grounding.NO_MATCH),
        "grounding": status,
        "sources": [s.model_dump() for s in sources],
        "support": [d.model_dump() for d in support_documents(retrieval)],
        "questions": [q.model_dump() for q in confirmed_questions(claims.questions, retrieval.hits)],
        "conflicts": [c.model_dump() for c in confirmed_conflicts(claims.conflicts, said)],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _clarify_event(retrieval: Retrieval, claims: Claims, said: str = "") -> str:
    """Уточнения и противоречия, досчитанные после кадра со сносками."""
    payload = {
        "clarify": True,
        "questions": [q.model_dump() for q in confirmed_questions(claims.questions, retrieval.hits)],
        "conflicts": [c.model_dump() for c in confirmed_conflicts(claims.conflicts, said)],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _sse(
    chunks: AsyncIterator[str],
    claims: Claims,
    retrieval: Retrieval,
    said: str = "",
    timing: dict | None = None,
    retriever: Retriever | None = None,
) -> AsyncIterator[str]:
    first_ms = None
    answer_ms = None
    size = 0
    # Модель ссылается на номера фрагментов; врачу и проверке уходят идентификаторы.
    rewriter = MarkerRewriter(retrieval.hits)
    guard = RepeatGuard()
    shown: list[str] = []
    try:
        async for raw in chunks:
            text = rewriter.feed(raw)
            if not text:
                continue
            if first_ms is None and timing:
                first_ms = _ms(timing["started"])
            size += len(text)
            shown.append(text)
            yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
            if guard.feed(text):
                # Модель пошла по кругу: дальше будет тот же абзац до потолка длины.
                await chunks.aclose()
                break
        tail = rewriter.flush()
        if tail:
            shown.append(tail)
            yield f"data: {json.dumps({'text': tail}, ensure_ascii=False)}\n\n"
        answer = "".join(shown)
        claims.source_ids[:0] = [i for i in cited_ids(answer) if i not in claims.source_ids]
        # «Во фрагментах этого нет [2]» — ссылка есть, а опоры нет.
        claims.source_ids[:] = drop_absence_citations(claims.source_ids, answer)
        substance = without_absence(answer)
        attribution, attribution_best = "model", None
        if retriever is not None and not confirmed_sources(claims.source_ids, retrieval.hits):
            found, attribution_best = await _attribute(retriever, substance, retrieval)
            claims.source_ids.extend(found)
            attribution = "similarity"
        elif retriever is not None:
            attribution_best = await _support(retriever, substance, retrieval)
            if _unsupported(attribution_best):
                claims.source_ids.clear()
    except Exception as exc:  # noqa: BLE001 — любой сбой: кадр ошибки вместо обрыва
        # Обрыв посреди ответа: врач видит «ответ не завершён» (нет [DONE]), а в
        # журнале остаётся причина — код ошибки, без текста.
        code = exc.code if isinstance(exc, AppError) else type(exc).__name__
        cause = type(exc.__cause__ or exc).__name__
        timing_logger.warning("stream_failed code=%s cause=%s after_chars=%s", code, cause, size)
        yield f"data: {json.dumps({'error': code})}\n\n"
        return
    finally:
        # Врач закрыл вкладку или нажал «Стоп»: поток генерации закрывается
        # сразу, и LM Studio прекращает писать брошенный ответ.
        close = getattr(chunks, "aclose", None)
        if close is not None:
            await close()
    try:
        yield _sources_event(retrieval, claims, said, attribution, attribution_best)
        sources_ms = _ms(timing["started"]) if timing else None
        if await claims.settle():
            yield _clarify_event(retrieval, claims, said)
    finally:
        claims.abandon()  # врач ушёл до уточнений
    yield "data: [DONE]\n\n"
    if timing:
        answer_ms = _ms(timing["started"])
        _log_timing(
            stream=True,
            retrieval_ms=timing["retrieval_ms"],
            first_token_ms=first_ms,
            sources_ms=sources_ms,
            total_ms=answer_ms,
            clarify_ms=claims.clarify_ms,
            reasoning_chars=claims.reasoning_chars,
            answer_chars=size,
            markers=len(cited_ids(answer)),
            attribution=attribution,
            attribution_best=attribution_best,
        )


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _log_timing(**values) -> None:
    timing_logger.info(" ".join(f"{k}={v}" for k, v in values.items() if v is not None))


async def _sse_refusal(text: str, retrieval: Retrieval) -> AsyncIterator[str]:
    yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
    yield _sources_event(retrieval, Claims())
    yield "data: [DONE]\n\n"


async def _sse_verified(verified: Verified) -> AsyncIterator[str]:
    yield f"data: {json.dumps({'text': verified.text}, ensure_ascii=False)}\n\n"
    payload = {
        "grounded": True,
        "grounding": "verified",
        "verified": verified.payload(),
        "refusal": None,
        "sources": [],
        "support": [],
        "questions": [],
        "conflicts": [],
    }
    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
