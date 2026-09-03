import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.llm import ensure_structured_output, get_llm
from app.routers import router
from app.schemas import AppError, ErrorBody

access_logger = logging.getLogger("app.access")
startup_logger = logging.getLogger("app.startup")


def create_app() -> FastAPI:
    application = FastAPI(
        title="med-assistant",
        description="HTTP API медицинского ИИ-ассистента",
        lifespan=_lifespan,
    )
    application.include_router(router)
    application.add_exception_handler(AppError, _app_error_handler)
    application.add_exception_handler(RequestValidationError, _validation_handler)
    application.add_exception_handler(StarletteHTTPException, _http_handler)
    application.middleware("http")(_access_log)
    return application


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await _check_model_on_startup(app)
    yield


async def _check_model_on_startup(app: FastAPI) -> None:
    """Несовместимую модель обнаруживает администратор при запуске, а не врач
    ошибкой на свой первый вопрос.

    Недоступная LM Studio запуску не мешает: это штатное состояние, его
    описывает `GET /ready`, и сервер модели может подняться позже.
    """
    try:
        provider = app.dependency_overrides.get(get_llm, get_llm)
        await ensure_structured_output(provider())
    except AppError as exc:
        if exc.code == "model_incompatible":
            raise RuntimeError(exc.message) from exc
        startup_logger.warning(
            "LM Studio недоступна при запуске (%s): проверка модели отложена до /ready",
            exc.code,
        )


async def _access_log(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    access_logger.info(
        "%s %s %s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorBody(code=exc.code, message=exc.message).model_dump(),
    )


async def _validation_handler(
    _request: Request,
    _exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=ErrorBody(
            code="validation_error",
            message="Ошибка валидации запроса",
        ).model_dump(),
    )


async def _http_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == 404 else "http_error"
    message = "Не найдено" if exc.status_code == 404 else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorBody(code=code, message=message).model_dump(),
    )


app = create_app()
