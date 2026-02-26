from fastapi import FastAPI
from app.routers.epidemiologia import router as epi_router
from app.db import AsyncSessionLocal
from app.services.scheduler import build_scheduler
from app.routers.admin import router as admin_router
from app.routers.epidemiologia_v2 import router as epi_v2_router
from app.services.scheduler_v2 import build_scheduler_v2
from app.routers import datasus
from app.routers import demas
from app.routers import esus_notifica
from app.routers.cnes import router as cnes_router

app = FastAPI(title="API de Clipping Epidemiológico", version="0.1.0")
app.include_router(admin_router)
app.include_router(epi_router)
app.include_router(datasus.router)
app.include_router(demas.router)
app.include_router(esus_notifica.router)
app.include_router(cnes_router)

scheduler = None

@app.on_event("startup")
async def startup():
    global scheduler
    scheduler = build_scheduler(AsyncSessionLocal)
    scheduler.start()

@app.on_event("shutdown")
async def shutdown():
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)

@app.get("/health")
async def health():
    return {"status": "ok"}
