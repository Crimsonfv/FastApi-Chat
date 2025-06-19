import os
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List

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
    
    # Configuración de Anthropic - LEE DEL .ENV
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    
    # Configuración de JWT
    secret_key: str = "tu_clave_secreta_super_segura_cambiar_en_produccion"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # Configuración CORS (para React frontend)
    allowed_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080,http://127.0.0.1:3000,http://127.0.0.1:5173"
    
    @property
    def allowed_origins_list(self) -> List[str]:
        """Convertir string de CORS a lista"""
        return [origin.strip() for origin in self.allowed_origins.split(",")]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # Permitir variables de entorno que sobrescriban valores por defecto
        extra = "ignore"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Validación de API key de Anthropic
        if not self.anthropic_api_key:
            print("⚠️  WARNING: ANTHROPIC_API_KEY no está configurada")
            print("   Crea un archivo .env con: ANTHROPIC_API_KEY=tu_api_key")
        else:
            print("✅ Anthropic API Key configurada correctamente")

@lru_cache()
def get_settings():
    return Settings()

# Instancia global de configuración
settings = get_settings()

# Para debug - mostrar configuración (sin secrets)
def print_config():
    """Imprimir configuración actual (para debug)"""
    print("\n🔧 Configuración actual:")
    print(f"  App: {settings.app_name} v{settings.version}")
    print(f"  Debug: {settings.debug}")
    print(f"  Database: {settings.db_host}:{settings.db_port}/{settings.db_name}")
    print(f"  Anthropic Model: {settings.anthropic_model}")
    print(f"  API Key configurada: {'✅ Sí' if settings.anthropic_api_key else '❌ No'}")
    print(f"  CORS Origins: {settings.allowed_origins_list}")
    print(f"  JWT Expire: {settings.access_token_expire_minutes} min")
    print()

if __name__ == "__main__":
    # Test de configuración
    print_config()