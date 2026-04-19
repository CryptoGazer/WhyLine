from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str
    openai_api_key: str = ""
    jira_base_url: str = ""
    jira_token: str = ""
    log_level: str = "info"


settings = Settings()
