"""将棋学習アプリ バックエンド (FastAPI)。

起動: uvicorn app.main:app --reload --port 8000
初回起動時にテーブル作成とサンプル問題の投入を行う。
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .next_move_database import NextMoveDatabaseUnavailable, get_next_move_connection, next_move_db_path
from .routers import book, next_move, openings, stats, time_attack, tsume
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_if_empty()
    try:
        next_move_conn = get_next_move_connection()
        next_move_conn.close()
        logging.getLogger(__name__).info("次の一手専用DBを認識しました: %s", next_move_db_path())
    except NextMoveDatabaseUnavailable as exc:
        logging.getLogger(__name__).warning("%s", exc)
    yield


app = FastAPI(title="Shogi Learning API", lifespan=lifespan)

# ローカル個人利用前提。Vite 開発サーバーからのアクセスを許可する。
cors_origins = os.environ.get(
    "SHOGI_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tsume.router)
app.include_router(time_attack.router)
app.include_router(stats.router)
app.include_router(openings.router)
app.include_router(book.router)
app.include_router(next_move.router)

@app.exception_handler(HTTPException)
async def structured_http_error(_, exc):
    from fastapi.responses import JSONResponse
    if isinstance(exc.detail, dict) and set(exc.detail) >= {"detail", "code"}:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/api/health")
def health():
    return {"status": "ok"}
