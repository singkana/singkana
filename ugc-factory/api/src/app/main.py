from fastapi import FastAPI

from app.db import Base, engine
from app.routes.jobs import router as jobs_router

app = FastAPI(title="UGC Orchestrator API", version="0.1.0")

# v0: 起動時にテーブル作成（本番はalembic）
Base.metadata.create_all(bind=engine)

app.include_router(jobs_router)


@app.get("/health")
def health():
    return {"ok": True}

