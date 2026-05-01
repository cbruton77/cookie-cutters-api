from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Snowflake
    snowflake_account: str
    snowflake_user: str
    snowflake_password: str = ""
    snowflake_auth_method: str = "password"          # "password" or "keypair"
    snowflake_private_key_path: str = ""             # Path to .p8 file
    snowflake_private_key_base64: str = ""           # OR base64-encoded key for serverless
    snowflake_private_key_passphrase: str = ""       # If key is encrypted
    snowflake_warehouse: str
    snowflake_database: str
    snowflake_schema: str
    snowflake_role: str
    snowflake_pool_size: int = 5
    snowflake_pool_timeout: int = 30

    # Supabase Auth
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""

    # App
    app_env: str = "development"
    app_debug: bool = True
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
