import os
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.exceptions import LoginRequired
from app.routers import api_v1
from app.routers import finance_pages
from app.routers import web as web_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    os.makedirs("data", exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        from app.seed import seed_demo

        await seed_demo(session)
    yield


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    version="1.0.0",
    description="Versioned REST API under /api/v1 for mobile and integrations. Web UI uses session auth.",
)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")

app.include_router(web_router.router)
app.include_router(finance_pages.router)
app.include_router(api_v1.router, prefix="/api/v1")

_static = Path(__file__).resolve().parent / "static"
if _static.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")


@app.exception_handler(LoginRequired)
async def login_redirect(_request: Request, _exc: LoginRequired):
    return RedirectResponse(url="/login", status_code=302)


@app.get("/health")
async def health():
    return {"status": "ok"}
