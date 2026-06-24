"""将棋学習アプリ バックエンド (FastAPI)。

起動: uvicorn app.main:app --reload --port 8000
初回起動時にテーブル作成とサンプル問題の投入を行う。
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .routers import openings, stats, time_attack, tsume
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_if_empty()
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


@app.get("/api/health")
def health():
    return {"status": "ok"}
