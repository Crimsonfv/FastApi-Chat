import os
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Configuración de la aplicación
    app_name: str = "Chatbot Olímpico API"
    debug: bool = False
    version: str = "1.0.0"
    
    # Configuración de Base de Datos PostgreSQL
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "crimson"
    db_password: str = "Inacap.2025"
    db_name: str = "Evaluacion-3"
    
    # URL de conexión PostgreSQL para SQLAlchemy
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
    
    # Configuración de Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-20241022"
    
    # Configuración de JWT
    secret_key: str = "tu_clave_secreta_super_segura_cambiar_en_produccion"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # Configuración CORS (para React frontend)
    allowed_origins: list = ["http://localhost:3000", "http://localhost:8080"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings():
    return Settings()

# Instancia global de configuración
settings = get_settings()