import httpx

SEVERITY_ORDER = {"info": 1, "warning": 2, "high": 3, "critical": 4}

def _allowed(min_sev: str, sev: str) -> bool:
    return SEVERITY_ORDER.get(sev, 0) >= SEVERITY_ORDER.get(min_sev, 3)

def _match_filters(target, alert: dict) -> bool:
    if target.disease_filter and "in" in target.disease_filter:
        if alert["disease"] not in target.disease_filter["in"]:
            return False
    if target.geo_filter and "in" in target.geo_filter:
        if alert["geo_code"] not in target.geo_filter["in"]:
            return False
    return True

async def send_notification(target, alert: dict) -> None:
    if not _allowed(target.min_severity, alert["severity"]):
        return
    if not _match_filters(target, alert):
        return

    async with httpx.AsyncClient(timeout=20) as client:
        if target.target_type == "teams_webhook":
            # MessageCard simples
            payload = {
                "@type": "MessageCard",
                "@context": "https://schema.org/extensions",
                "summary": alert["title"],
                "themeColor": "FF0000" if alert["severity"] in ("high", "critical") else "FFA500",
                "title": f"[{alert['severity'].upper()}] {alert['title']}",
                "text": alert["message"],
                "sections": [
                    {
                        "facts": [
                            {"name": "Doença", "value": alert["disease"]},
                            {"name": "Geo", "value": alert["geo_code"]},
                            {"name": "Período", "value": f"SE {alert['epiweek']}/{alert['year']}"},
                        ]
                    }
                ],
            }
            await client.post(target.target_url, json=payload)
        else:
            # webhook genérico
            await client.post(target.target_url, json=alert)
