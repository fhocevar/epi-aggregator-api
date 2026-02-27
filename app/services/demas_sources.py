# app/services/demas_sources.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemasSource:
    key: str
    url: str
    request_year: int | None = None
    normalize_events: bool = True


# ✅ Fontes S3 (fallback) — URLs
DEMAS_S3_SOURCES: list[DemasSource] = [
    DemasSource(
        key="sinan_dengue",
        url="https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR26.csv.zip",
        request_year=2026,
        normalize_events=True,
    ),
    DemasSource(
        key="sinan_chikungunya",
        url="https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Chikungunya/csv/CHIKBR26.csv.zip",
        request_year=2026,
        normalize_events=True,
    ),
    DemasSource(
        key="sinan_zika",
        url="https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Zikavirus/csv/ZIKABR26.csv.zip",
        request_year=2026,
        normalize_events=True,
    ),
    # Febre Amarela é CSV direto (não zip)
    DemasSource(
        key="sinan_febre_amarela",
        url="https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/Febre+Amarela/fa_casoshumanos_1994-2025.csv",
        request_year=2025,
        normalize_events=True,
    ),
    # CNES / Leitos — não são “eventos epi” (normalizar não é útil)
    DemasSource(
        key="cnes_estabelecimentos",
        url="https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_csv.zip",
        request_year=None,
        normalize_events=False,
    ),
    DemasSource(
        key="leitos_sus",
        url="https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/Leitos_SUS/Leitos_csv_2026.zip",
        request_year=2026,
        normalize_events=False,
    ),
]