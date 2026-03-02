from __future__ import annotations

from typing import Sequence, Mapping, Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert


def _chunked(seq: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _chunked_rows(rows: Sequence[Mapping[str, Any]], size: int) -> Iterable[list[Mapping[str, Any]]]:
    # garante list() para o SQLAlchemy/psycopg2 não sofrer com iteradores
    for i in range(0, len(rows), size):
        yield list(rows[i : i + size])


async def bulk_insert_on_conflict_do_nothing_chunked(
    session: AsyncSession,
    model_or_table,
    rows: Sequence[Mapping[str, Any]],
    *,
    chunk_size: int = 500,
    conflict_cols: list[str],
) -> int:
    """
    Insere em lotes e ignora duplicados no Postgres (ON CONFLICT DO NOTHING).
    Retorna total inserido (somando rowcount de cada chunk).
    """
    if not rows:
        return 0

    total_inserted = 0
    for chunk in _chunked_rows(list(rows), chunk_size):
        stmt = pg_insert(model_or_table).values(chunk)
        stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)
        result = await session.execute(stmt)
        total_inserted += int(getattr(result, "rowcount", 0) or 0)

    return total_inserted


async def bulk_insert_on_conflict_do_nothing_chunked_returning_count(
    session: AsyncSession,
    model_or_table,
    rows: Sequence[Mapping[str, Any]],
    *,
    chunk_size: int = 500,
    conflict_cols: list[str],
    returning_col=None,
) -> int:
    """
    Variante que usa RETURNING para contar inseridos com precisão.
    Útil quando rowcount não é confiável dependendo do driver/config.
    """
    if not rows:
        return 0

    inserted_total = 0
    for chunk in _chunked_rows(list(rows), chunk_size):
        stmt = pg_insert(model_or_table).values(chunk)
        stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)

        if returning_col is not None:
            stmt = stmt.returning(returning_col)
            res = await session.execute(stmt)
            inserted_total += len(res.scalars().all())
        else:
            res = await session.execute(stmt)
            inserted_total += int(getattr(res, "rowcount", 0) or 0)

    return inserted_total


async def save_raw_debug_find_bad_row_on_conflict(
    session: AsyncSession,
    model_or_table,
    rows: Sequence[Mapping[str, Any]],
    *,
    chunk_size: int = 200,
    conflict_cols: list[str],
) -> int:
    """
    Tenta inserir em lote com ON CONFLICT DO NOTHING.
    Se der erro, faz ROLLBACK (asyncpg deixa a transação abortada),
    e cai no modo 1-a-1 para identificar a row que quebra.

    Retorna quantidade inserida (rowcount somado por chunk quando bem-sucedido).
    """
    if not rows:
        return 0

    inserted_total = 0
    for chunk in _chunked_rows(list(rows), chunk_size):
        stmt = pg_insert(model_or_table).values(chunk)
        stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)

        try:
            res = await session.execute(stmt)
            inserted_total += int(getattr(res, "rowcount", 0) or 0)
            continue
        except Exception as bulk_exc:
            # 🔥 IMPORTANTÍSSIMO no asyncpg: a transação fica abortada após erro
            await session.rollback()

            # Agora sim dá pra executar comandos e descobrir a row ruim
            for i, row in enumerate(chunk):
                stmt1 = pg_insert(model_or_table).values([row])
                stmt1 = stmt1.on_conflict_do_nothing(index_elements=conflict_cols)
                try:
                    await session.execute(stmt1)
                except Exception as e:
                    # Aqui vai aparecer o ERRO REAL (tipo/constraint/json/etc)
                    raise RuntimeError(
                        f"Row inválida no chunk: index={i}, error={type(e).__name__}: {e}, row={dict(row)}"
                    ) from e

            # Se bulk falhou e 1-a-1 passou, normalmente é algo tipo "packet too large",
            # ou detalhe do driver; devolve o bulk_exc para investigação
            raise RuntimeError(
                f"Falha no insert em lote, mas não reproduziu no modo 1-a-1: {type(bulk_exc).__name__}: {bulk_exc}"
            ) from bulk_exc

    return inserted_total