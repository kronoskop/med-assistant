from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter()

STATIC_DIR = Path(__file__).parent / "static"

# Явный список отдаваемых файлов вместо StaticFiles-mount: mount перехватывает
# любой путь под своим префиксом и отвечает собственной текстовой 404-й,
# ломая JSON-контракт ошибок.
ASSETS: dict[str, str] = {
    "app.js": "text/javascript; charset=utf-8",
    "data.js": "text/javascript; charset=utf-8",
    "topics.js": "text/javascript; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
}


@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Корень ведёт в интерфейс: врач открывает адрес сервиса, а не `/ui`."""
    return RedirectResponse("/ui", status_code=307)


@router.get("/ui", include_in_schema=False)
async def ui_index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        media_type="text/html; charset=utf-8",
    )


@router.get("/ui/{name}", include_in_schema=False)
async def ui_asset(name: str) -> FileResponse:
    media_type = ASSETS.get(name)
    if media_type is None:
        raise HTTPException(status_code=404)
    return FileResponse(STATIC_DIR / name, media_type=media_type)
