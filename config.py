from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_port: int
    database_username: str
    app_debug_mode: bool
    class Config:
        env_file = ".env"

    
settings = Settings()