from __future__ import annotations
from datetime import date, datetime
from hashlib import sha256
from typing import Any

def _to_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except Exception:
            pass
        try:
            d, m, y = v[:10].split("/")
            return date(int(y), int(m), int(d))
        except Exception:
            return None
    return None

def _hash_dict(payload: dict[str, Any]) -> str:
    import json

    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return sha256(blob).hexdigest()

def _pick_first(payload: dict[str, Any], keys: list[str]) -> Any:
    for k in keys:
        if k in payload and payload.get(k) not in (None, ""):
            return payload.get(k)
    return None