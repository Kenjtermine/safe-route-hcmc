from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Đọc cấu hình từ biến môi trường (docker compose truyền vào) hoặc file .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    log_level: str = "info"
    # Mặc định dùng khi chạy backend trực tiếp trên máy (không qua Docker)
    database_url: str = "postgresql://saferoute:change_me@localhost:5432/saferoute"


settings = Settings()
