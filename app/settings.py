from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "dev"
    database_url: str

    sync_interval_minutes: int = 60

    who_don_url: str = "https://www.who.int/api/news/diseaseoutbreaknews"
    infodengue_alertcity_url: str = "https://info.dengue.mat.br/api/alertcity"

    infodengue_default_geocodes: str = "3304557"
    infodengue_default_diseases: str = "dengue"
    infodengue_default_ew_start: int = 1
    infodengue_default_ew_end: int = 53
    infodengue_default_ey_start: int = 2025
    infodengue_default_ey_end: int = 2026

    alert_cooldown_minutes: int = 720

    # ✅ OpenDataSUS
    opendatasus_sivep_srg_csv_url: str = ""
    opendatasus_sivep_srag_zip_url_2024: str | None = None

    # ✅ eSUS Notifica / OpenSearch
    esus_opensearch_base_url: str = "https://notifica-prd-es.saude.gov.br"
    esus_opensearch_user: str | None = None
    esus_opensearch_password: str | None = None
    esus_opensearch_timeout_seconds: int = 60
    esus_opensearch_page_size: int = 200
    esus_opensearch_max_pages: int = 20

    # ✅ DEMAS (Dados Abertos MS)
    demas_base_url: str = "https://apidadosabertos.saude.gov.br"
    demas_timeout_seconds: int = 60
    demas_limit: int = 20
    demas_sleep_seconds: float = 0.05
    demas_arboviroses_years: str = "2024,2025,2026"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()