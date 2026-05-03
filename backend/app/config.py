"""Configuration for CPAP Analyzer backend."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "CPAP Analyzer"
    debug: bool = True

    # Database
    database_url: str = "sqlite:///./cpap.db"

    # File storage
    upload_dir: str = "./uploads"
    max_upload_size: int = 2 * 1024 * 1024 * 1024  # 2GB

    # OpenAI-compatible API
    openai_api_key: str = ""
    openai_base_url: str = "https://api.synthetic.new/openai/v1"
    openai_model: str = "hf:moonshotai/Kimi-K2.6"

    # Processing
    signal_downsample_1min: bool = True
    signal_downsample_5min: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    return Settings()
