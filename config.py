from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_port: int
    database_username: str
    app_debug_mode: bool
    database_password: str
    database_hostname: str
    database_name: str
    redis_host: str = "localhost"
    redis_port: int = 6379

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}"
    
    class Config:
        env_file = ".env"

settings = Settings()