from __future__ import annotations

from typing import Sequence, Mapping, Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert


def _chunked(seq: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


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
    for chunk in _chunked(list(rows), chunk_size):
        stmt = pg_insert(model_or_table).values(list(chunk))
        stmt = stmt.on_conflict_do_nothing(index_elements=conflict_cols)
        result = await session.execute(stmt)
        total_inserted += int(getattr(result, "rowcount", 0) or 0)

    return total_inserted