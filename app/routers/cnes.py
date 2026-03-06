from __future__ import annotations
from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_, cast, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.settings import settings
from app.demas_models import DemasRaw

router = APIRouter(prefix="/cnes", tags=["CNES (DEMAS)"])

def _session_factory() -> async_sessionmaker[AsyncSession]:
    db_url = getattr(settings, "database_url", None) or getattr(settings, "DATABASE_URL", None)
    if not db_url:
        db_url = "postgresql+asyncpg://epi:epi@localhost:5432/epi_clipping"
    engine = create_async_engine(db_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)

def _json_text(payload_col, key: str):
    return payload_col.op("->>")(key)

@router.get("/estabelecimentos")
async def cnes_estabelecimentos(
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=200),
    uf: str | None = Query(None, description="UF (ex: SP, RJ)"),
    municipio_ibge: str | None = Query(None, description="Código IBGE do município (string)"),
    cnes: str | None = Query(None, description="Código CNES do estabelecimento"),
    nome: str | None = Query(None, description="Busca por nome (ilike)"),
    tipo: str | None = Query(None, description="Tipo/Natureza (depende do payload)"),
):
    """
    Consulta CNES diretamente do demas_raw (dataset=cnes_estabelecimentos).

    Observação: nomes dos campos variam entre APIs.
    Aqui fazemos 'best effort' tentando campos comuns:
      - uf: 'uf' / 'sg_uf' / 'UF'
      - municipio: 'municipio_ibge' / 'codigo_municipio' / 'co_municipio'
      - cnes: 'cnes' / 'codigo_cnes' / 'co_cnes'
      - nome: 'nome' / 'no_fantasia' / 'nome_fantasia' / 'razao_social'
    """
    offset = page * size
    sf = _session_factory()

    payload = cast(DemasRaw.payload, JSONB)

    conds = [DemasRaw.endpoint_name == "cnes_estabelecimentos"]

    if uf:
        uf = uf.strip().upper()
        conds.append(
            func.coalesce(
                _json_text(payload, "uf"),
                _json_text(payload, "sg_uf"),
                _json_text(payload, "UF"),
            )
            == uf
        )

    if municipio_ibge:
        municipio_ibge = municipio_ibge.strip()
        conds.append(
            func.coalesce(
                _json_text(payload, "municipio_ibge"),
                _json_text(payload, "codigo_municipio"),
                _json_text(payload, "co_municipio"),
                _json_text(payload, "CO_MUNICIPIO"),
            )
            == municipio_ibge
        )

    if cnes:
        cnes = cnes.strip()
        conds.append(
            func.coalesce(
                _json_text(payload, "cnes"),
                _json_text(payload, "codigo_cnes"),
                _json_text(payload, "co_cnes"),
                _json_text(payload, "CO_CNES"),
            )
            == cnes
        )

    if nome:
        nome = nome.strip()
        name_expr = func.coalesce(
            _json_text(payload, "nome"),
            _json_text(payload, "no_fantasia"),
            _json_text(payload, "nome_fantasia"),
            _json_text(payload, "razao_social"),
            _json_text(payload, "no_razao_social"),
        )
        conds.append(name_expr.ilike(f"%{nome}%"))

    if tipo:
        tipo = tipo.strip()
        tipo_expr = func.coalesce(
            _json_text(payload, "tipo"),
            _json_text(payload, "tp_unidade"),
            _json_text(payload, "natureza_juridica"),
            _json_text(payload, "tp_gestao"),
        )
        conds.append(tipo_expr == tipo)

    async with sf() as session:
        total = (
            await session.execute(
                select(func.count()).select_from(DemasRaw).where(and_(*conds))
            )
        ).scalar_one()

        q = (
            select(DemasRaw)
            .where(and_(*conds))
            .order_by(DemasRaw.id.desc())
            .offset(offset)
            .limit(size)
        )
        rows = (await session.execute(q)).scalars().all()

    def pick_name(p: dict) -> str | None:
        for k in ("nome", "no_fantasia", "nome_fantasia", "razao_social", "no_razao_social"):
            v = p.get(k)
            if v:
                return str(v)
        return None

    def pick_cnes(p: dict) -> str | None:
        for k in ("cnes", "codigo_cnes", "co_cnes", "CO_CNES"):
            v = p.get(k)
            if v:
                return str(v)
        return None

    items = []
    for r in rows:
        p = r.payload or {}
        items.append(
            {
                "id": r.id,
                "cnes": pick_cnes(p),
                "nome": pick_name(p),
                "uf": p.get("uf") or p.get("sg_uf") or p.get("UF"),
                "municipio_ibge": p.get("municipio_ibge") or p.get("codigo_municipio") or p.get("co_municipio") or p.get("CO_MUNICIPIO"),
                "collected_at": r.collected_at.isoformat() if r.collected_at else None,
                "payload": p,
            }
        )

    return {"page": page, "size": size, "total_items": int(total), "items": items}

@router.get("/estabelecimentos/{cnes}")
async def cnes_estabelecimento_detail(cnes: str):
    """
    Retorna o registro mais recente do CNES informado (payload completo).
    """
    cnes = cnes.strip()
    sf = _session_factory()
    payload = cast(DemasRaw.payload, JSONB)

    conds = [
        DemasRaw.endpoint_name == "cnes_estabelecimentos",
        func.coalesce(
            _json_text(payload, "cnes"),
            _json_text(payload, "codigo_cnes"),
            _json_text(payload, "co_cnes"),
            _json_text(payload, "CO_CNES"),
        )
        == cnes,
    ]

    async with sf() as session:
        q = (
            select(DemasRaw)
            .where(and_(*conds))
            .order_by(DemasRaw.id.desc())
            .limit(1)
        )
        r = (await session.execute(q)).scalars().first()

    if not r:
        return {"status_code": 404, "message": f"CNES {cnes} não encontrado no demas_raw (rode o sync do cnes)"}

    return {
        "status_code": 200,
        "item": {
            "id": r.id,
            "dataset": r.endpoint_name,
            "record_hash": r.record_hash,
            "collected_at": r.collected_at.isoformat() if r.collected_at else None,
            "payload": r.payload,
        },
    }

@router.get("/autocomplete")
async def cnes_autocomplete(
    q: str = Query(..., min_length=2, description="Parte do nome"),
    size: int = Query(15, ge=1, le=30),
):
    """
    Autocomplete simples: retorna CNES + nome (sem payload completo).
    """
    sf = _session_factory()
    payload = cast(DemasRaw.payload, JSONB)

    name_expr = func.coalesce(
        _json_text(payload, "nome"),
        _json_text(payload, "no_fantasia"),
        _json_text(payload, "nome_fantasia"),
        _json_text(payload, "razao_social"),
        _json_text(payload, "no_razao_social"),
    )

    cnes_expr = func.coalesce(
        _json_text(payload, "cnes"),
        _json_text(payload, "codigo_cnes"),
        _json_text(payload, "co_cnes"),
        _json_text(payload, "CO_CNES"),
    )

    conds = [
        DemasRaw.endpoint_name == "cnes_estabelecimentos",
        name_expr.ilike(f"%{q.strip()}%"),
    ]

    async with sf() as session:
        rows = (
            await session.execute(
                select(
                    cnes_expr.label("cnes"),
                    name_expr.label("nome"),
                    _json_text(payload, "uf").label("uf"),
                    _json_text(payload, "municipio_ibge").label("municipio_ibge"),
                )
                .where(and_(*conds))
                .limit(size)
            )
        ).all()

    return {
        "q": q,
        "size": size,
        "items": [{"cnes": r.cnes, "nome": r.nome, "uf": r.uf, "municipio_ibge": r.municipio_ibge} for r in rows if r.cnes],
    }