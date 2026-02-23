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

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
