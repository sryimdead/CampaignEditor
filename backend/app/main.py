import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  регистрирует таблицы в Base.metadata
from .config import get_settings
from .db import Base, engine
from .routers import campaign_offers, campaigns, creator


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    app = FastAPI(title="Keitaro Campaign Editor", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(campaigns.router)
    app.include_router(creator.router)
    app.include_router(campaign_offers.router)

    @app.get("/api/health", tags=["system"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
