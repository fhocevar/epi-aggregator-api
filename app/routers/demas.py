from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter

from app.settings import settings
from app.collectors.demas.client import DemasClient
from app.collectors.demas.collector import DemasCollector

# se você já tem demas_service persistindo, vamos usar também:
from app.services.demas_service import DemasService

router = APIRouter(prefix="/demas", tags=["DEMAS (MS Dados Abertos)"])


def _collector() -> DemasCollector:
    client = DemasClient(
        base_url=getattr(settings, "demas_base_url", "https://apidadosabertos.saude.gov.br/v1"),
        timeout_seconds=getattr(settings, "demas_timeout_seconds", 60),
        token=getattr(settings, "demas_token", None),
        username=getattr(settings, "demas_username", None),
        password=getattr(settings, "demas_password", None),
    )
    return DemasCollector(client, page_size=getattr(settings, "demas_page_size", 1000))


@router.get("/health")
async def demas_health():
    """
    Só valida conectividade (não baixa base gigante).
    """
    col = _collector()
    rows = await col.collect_all(
        "/macrorregiao-e-regiao-de-saude/municipio",
        params={"page": 1, "size": 1},
    )
    return {"status": "ok", "sample_items": len(rows), "ts": datetime.now(timezone.utc).isoformat()}


@router.get("/arboviroses/{agravo}")
async def demas_arboviroses(agravo: str, page: int = 1, size: int = 50):
    """
    Visualizar rapidamente no Swagger:
      dengue | chikungunya | zikavirus
    """
    agravo = agravo.lower()
    allowed = {"dengue", "chikungunya", "zikavirus"}
    if agravo not in allowed:
        return {"status_code": 400, "message": f"agravo inválido. use: {sorted(allowed)}"}

    col = _collector()
    items = await col.collect_all(f"/arboviroses/{agravo}", params={"page": page, "size": size})
    return {"status_code": 200, "total_items": len(items), "items": items}


@router.get("/srag")
async def demas_srag(page: int = 1, size: int = 50):
    """
    Visualizar SRAG no Swagger.
    """
    col = _collector()
    items = await col.collect_all("/vigilancia-e-meio-ambiente/srag-2019-2026", params={"page": page, "size": size})
    return {"status_code": 200, "total_items": len(items), "items": items}


# Opcional: endpoint para disparar o sync (se seu demas_service já estiver ok)
@router.post("/sync/{dataset}")
async def demas_sync(dataset: str):
    """
    Dispara um sync manual (útil pra testar sem esperar scheduler).
    dataset: dengue | chikungunya | zika | srag
    """
    dataset = dataset.lower()
    mapping = {
        "dengue": ("/arboviroses/dengue", "dengue"),
        "chikungunya": ("/arboviroses/chikungunya", "chikungunya"),
        "zika": ("/arboviroses/zikavirus", "zika"),
        "srag": ("/vigilancia-e-meio-ambiente/srag-2019-2026", "srag"),
    }
    if dataset not in mapping:
        return {"status_code": 400, "message": f"dataset inválido. use: {sorted(mapping.keys())}"}

    path, disease = mapping[dataset]

    service = DemasService()
    result = await service.sync_dataset(path=path, disease=disease)
    return {"status_code": 200, "result": result}