from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_port: int
    database_username: str
    app_debug_mode: bool
    database_password: str
    database_hostname: str
    database_name: str
    class Config:
        env_file = ".env" # has to be called env_file 

    
settings = Settings()