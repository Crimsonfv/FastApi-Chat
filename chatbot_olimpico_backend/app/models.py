from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

from .database import Base

class Usuario(Base):
    """
    Modelo para tabla usuarios (Criterio C - Autenticación)
    """
    __tablename__ = "usuarios"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(20), nullable=False, default="user")  # 'user' o 'admin'
    fecha_registro = Column(DateTime, default=func.now())
    activo = Column(Boolean, default=True)
    
    # Relaciones
    conversaciones = relationship("Conversacion", back_populates="usuario", cascade="all, delete-orphan")
    terminos_excluidos = relationship("TerminoExcluido", back_populates="usuario", cascade="all, delete-orphan")
    configuraciones_prompt = relationship("ConfiguracionPrompt", back_populates="creado_por_usuario")

class Conversacion(Base):
    """
    Modelo para tabla conversaciones (Criterio B - Almacenar conversaciones)
    """
    __tablename__ = "conversaciones"
    
    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    titulo = Column(String(200))
    fecha_inicio = Column(DateTime, default=func.now())
    fecha_ultima_actividad = Column(DateTime, default=func.now())
    activa = Column(Boolean, default=True)
    
    # Relaciones
    usuario = relationship("Usuario", back_populates="conversaciones")
    mensajes = relationship("Mensaje", back_populates="conversacion", cascade="all, delete-orphan")

class Mensaje(Base):
    """
    Modelo para tabla mensajes (Criterio B - Almacenar conversaciones)
    """
    __tablename__ = "mensajes"
    
    id = Column(Integer, primary_key=True, index=True)
    id_conversacion = Column(Integer, ForeignKey("conversaciones.id"), nullable=False)
    rol = Column(String(20), nullable=False)  # 'user' o 'assistant'
    contenido = Column(Text, nullable=False)
    consulta_sql = Column(Text)  # Opcional, para guardar la SQL generada
    timestamp = Column(DateTime, default=func.now())
    
    # Relaciones
    conversacion = relationship("Conversacion", back_populates="mensajes")

class MedallaOlimpica(Base):
    """
    Modelo para tabla medallas_olimpicas (Criterio D - Consultas complejas)
    """
    __tablename__ = "medallas_olimpicas"
    
    id = Column(Integer, primary_key=True, index=True)
    city = Column(String(100), nullable=False)
    year = Column(Integer, nullable=False, index=True)
    sport = Column(String(100), nullable=False, index=True)
    discipline = Column(String(100), nullable=False)
    event = Column(String(200), nullable=False)
    athlete = Column(String(200), nullable=False, index=True)  # Original: "KÖHLER, Christa"
    nombre = Column(String(100))  # Procesado: "Christa"
    apellido = Column(String(100), index=True)  # Procesado: "Köhler"
    nombre_completo = Column(String(200), index=True)  # Procesado: "Christa Köhler"
    gender = Column(String(10), nullable=False)
    country_code = Column(String(10), nullable=False)
    country = Column(String(100), nullable=False, index=True)
    event_gender = Column(String(10), nullable=False)
    medal = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=func.now())

class TerminoExcluido(Base):
    """
    Modelo para tabla terminos_excluidos (Criterio E - Términos excluidos)
    """
    __tablename__ = "terminos_excluidos"
    
    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    termino = Column(String(100), nullable=False)
    activo = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=func.now())
    
    # Relaciones
    usuario = relationship("Usuario", back_populates="terminos_excluidos")

class ConfiguracionPrompt(Base):
    """
    Modelo para tabla configuraciones_prompt (Criterio F - Prompts por contexto)
    """
    __tablename__ = "configuraciones_prompt"
    
    id = Column(Integer, primary_key=True, index=True)
    contexto = Column(String(100), nullable=False)  # 'deportivo', 'paises', 'atletas', etc.
    prompt_sistema = Column(Text, nullable=False)
    creado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha_modificacion = Column(DateTime, default=func.now())
    activo = Column(Boolean, default=True)
    
    # Relaciones
    creado_por_usuario = relationship("Usuario", back_populates="configuraciones_prompt")