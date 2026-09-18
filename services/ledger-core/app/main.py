from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.accounts import router as accounts_router
from app.api.reconciliation import router as reconciliation_router
from app.api.transactions import router as transactions_router
from app.config import get_settings
from app.infra.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


settings = get_settings()

app = FastAPI(
    title="PAYO Core Ledger",
    description=(
        "Double-entry, idempotent, exactly-once core banking ledger with a "
        "compliance screening gate and fiat/on-chain reconciliation API."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(accounts_router)
app.include_router(transactions_router)
app.include_router(reconciliation_router)


@app.get("/healthz", tags=["ops"])
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name, "env": settings.environment}
