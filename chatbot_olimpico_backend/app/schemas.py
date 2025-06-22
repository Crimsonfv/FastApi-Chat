from pydantic import BaseModel, EmailStr, validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum

# Enums para valores fijos
class RolUsuario(str, Enum):
    USER = "user"
    ADMIN = "admin"

class RolMensaje(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"

class TipoMedalla(str, Enum):
    GOLD = "Gold"
    SILVER = "Silver"
    BRONZE = "Bronze"

# ==================== SCHEMAS DE AUTENTICACIÓN ====================

class UsuarioBase(BaseModel):
    username: str
    email: EmailStr
    rol: RolUsuario = RolUsuario.USER

class UsuarioCreate(UsuarioBase):
    password: str
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('La contraseña debe tener al menos 6 caracteres')
        return v

class UsuarioLogin(BaseModel):
    username: str
    password: str

class UsuarioUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    rol: Optional[RolUsuario] = None
    activo: Optional[bool] = None

class UsuarioResponse(UsuarioBase):
    id: int
    fecha_registro: datetime
    activo: bool
    
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UsuarioResponse

# ==================== SCHEMAS DE CONVERSACIONES ====================

class ConversacionBase(BaseModel):
    titulo: Optional[str] = None

class ConversacionCreate(ConversacionBase):
    pass

class ConversacionResponse(ConversacionBase):
    id: int
    id_usuario: int
    fecha_inicio: datetime
    fecha_ultima_actividad: datetime
    activa: bool
    
    model_config = ConfigDict(from_attributes=True)

class MensajeBase(BaseModel):
    contenido: str
    rol: RolMensaje

class MensajeCreate(BaseModel):
    contenido: str
    rol: RolMensaje
    consulta_sql: Optional[str] = None

class MensajeResponse(MensajeBase):
    id: int
    id_conversacion: int
    consulta_sql: Optional[str] = None
    timestamp: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ConversacionConMensajes(ConversacionResponse):
    mensajes: List[MensajeResponse] = []

# ==================== SCHEMAS DE CHAT ====================

class ChatRequest(BaseModel):
    pregunta: str
    id_conversacion: Optional[int] = None

class ChatResponse(BaseModel):
    respuesta: str
    consulta_sql: Optional[str] = None
    id_conversacion: int
    id_mensaje: int
    datos_contexto: Optional[dict] = None  # Para Criterio G - detalles modal

# ==================== SCHEMAS DE TÉRMINOS EXCLUIDOS ====================

class TerminoExcluidoBase(BaseModel):
    termino: str

class TerminoExcluidoCreate(TerminoExcluidoBase):
    pass

class TerminoExcluidoResponse(TerminoExcluidoBase):
    id: int
    id_usuario: int
    activo: bool
    fecha_creacion: datetime
    
    model_config = ConfigDict(from_attributes=True)

# ==================== SCHEMAS DE CONFIGURACIÓN PROMPT ====================

class ConfiguracionPromptBase(BaseModel):
    contexto: str
    prompt_sistema: str

class ConfiguracionPromptCreate(ConfiguracionPromptBase):
    pass

class ConfiguracionPromptUpdate(BaseModel):
    contexto: Optional[str] = None
    prompt_sistema: Optional[str] = None
    activo: Optional[bool] = None

class ConfiguracionPromptResponse(ConfiguracionPromptBase):
    id: int
    creado_por: int
    fecha_modificacion: datetime
    activo: bool
    
    model_config = ConfigDict(from_attributes=True)

# ==================== SCHEMAS DE DATOS OLÍMPICOS ====================

class MedallaOlimpicaResponse(BaseModel):
    id: int
    city: str
    year: int
    sport: str
    discipline: str
    event: str
    athlete: str
    nombre: Optional[str]
    apellido: Optional[str]
    nombre_completo: Optional[str]
    gender: str
    country_code: str
    country: str
    event_gender: str
    medal: str
    
    model_config = ConfigDict(from_attributes=True)

# ==================== SCHEMAS COMUNES ====================

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None

class SuccessResponse(BaseModel):
    message: str
    data: Optional[dict] = None

class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    size: int
    pages: int