import httpx

async def fetch_who_dons(base_url: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.get(base_url, headers={"Accept": "application/json"})
        r.raise_for_status()

        try:
            data = r.json()
        except Exception:
            raise RuntimeError(
                f"WHO_DON_URL não retornou JSON. status={r.status_code} "
                f"content-type={r.headers.get('content-type')} body={r.text[:200]!r}"
            )

    if isinstance(data, dict) and "value" in data and isinstance(data["value"], list):
        return data["value"]
    if isinstance(data, list):
        return data
    return []