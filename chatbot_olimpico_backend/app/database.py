from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import logging

from .config import settings

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear engine de SQLAlchemy
engine = create_engine(
    settings.database_url,
    echo=settings.debug,  # Log SQL queries en modo debug
    pool_pre_ping=True,   # Verificar conexión antes de usar
    pool_recycle=300,     # Reciclar conexiones cada 5 minutos
)

# Configurar SessionLocal
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para modelos
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """
    Dependencia de FastAPI para obtener sesión de base de datos.
    Se usa en los endpoints como: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Error en sesión de base de datos: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    """
    Inicializar la base de datos.
    Crear todas las tablas si no existen.
    """
    try:
        # Importar todos los modelos aquí para que SQLAlchemy los conozca
        from . import models  # Esto se agregará cuando creemos models.py
        
        # Crear todas las tablas
        Base.metadata.create_all(bind=engine)
        logger.info("Base de datos inicializada correctamente")
        
    except Exception as e:
        logger.error(f"Error al inicializar base de datos: {e}")
        raise

def test_connection():
    """
    Probar la conexión a la base de datos
    """
    try:
        db = SessionLocal()
        # Ejecutar una consulta simple
        db.execute(text("SELECT 1"))
        db.close()
        logger.info("Conexión a base de datos exitosa")
        return True
    except Exception as e:
        logger.error(f"Error de conexión a base de datos: {e}")
        return False