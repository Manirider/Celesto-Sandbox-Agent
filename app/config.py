import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://celesto_user:celesto_pass@postgres:5432/celesto_db"
    celesto_provider: str = "celesto_cloud"
    celesto_api_key: str = ""
    celesto_backend: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    api_port: int = 8080
    sandbox_timeout_s: int = 600


settings = Settings()

# Automatically sync celesto_api_key to os.environ if loaded from .env
if settings.celesto_api_key and not os.environ.get("CELESTO_API_KEY"):
    os.environ["CELESTO_API_KEY"] = settings.celesto_api_key
