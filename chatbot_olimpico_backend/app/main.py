from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from datetime import datetime
import logging

# Imports locales
from .config import settings
from .database import get_db, test_connection, init_db
from .models import Usuario, TerminoExcluido, ConfiguracionPrompt
from .schemas import (
    # Auth schemas
    UsuarioCreate, UsuarioLogin, UsuarioResponse, Token,
    # Conversation schemas  
    ConversacionCreate, ConversacionResponse, ConversacionConMensajes,
    # Chat schemas
    ChatRequest, ChatResponse,
    # Admin schemas
    ConfiguracionPromptCreate, ConfiguracionPromptResponse, ConfiguracionPromptUpdate,
    # Filter schemas
    TerminoExcluidoCreate, TerminoExcluidoResponse,
    # Common schemas
    SuccessResponse, ErrorResponse
)
from .auth import (
    create_user, login_user, get_current_user, get_current_admin_user
)
from .conversations import (
    crear_conversacion, obtener_conversaciones_usuario, 
    obtener_conversacion_con_mensajes, eliminar_conversacion,
    actualizar_titulo_conversacion, procesar_mensaje_chat,
    obtener_estadisticas_conversaciones
)

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="API Backend para Chatbot Olímpico con IA - Evaluación 3"
)

# Configurar CORS para React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",    # ✅ Puerto de Vite
        "http://127.0.0.1:3000", 
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],           # ✅ CRÍTICO: incluye OPTIONS
    allow_headers=["*"],
    expose_headers=["*"],
)

# ==================== EVENTOS DE INICIO ====================
@app.options("/auth/{path:path}")
async def auth_options_handler(path: str):
    """Manejar explícitamente OPTIONS para rutas de auth"""
    return {"message": "OK"}

@app.get("/debug/cors-info")
async def debug_cors_info():
    """Debug: verificar configuración CORS"""
    return {
        "cors_enabled": True,
        "backend_running": True,
        "timestamp": datetime.now().isoformat()
    }

@app.on_event("startup")
async def startup_event():
    """Inicializar aplicación"""
    logger.info("Iniciando aplicación...")
    
    # Probar conexión a BD
    if not test_connection():
        logger.error("Error de conexión a base de datos")
        raise Exception("No se puede conectar a la base de datos")
    
    # Inicializar BD (crear tablas si no existen)
    try:
        init_db()
        logger.info("Base de datos inicializada")
    except Exception as e:
        logger.error(f"Error al inicializar BD: {e}")
    
    logger.info("Aplicación iniciada correctamente")

# ==================== ENDPOINTS DE SALUD ====================

@app.get("/")
async def root():
    """Endpoint raíz"""
    return {
        "message": "Chatbot Olímpico API - Evaluación 3",
        "version": settings.version,
        "status": "running"
    }

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Verificar estado de la aplicación"""
    try:
        # Probar consulta simple
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "version": settings.version
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database error: {str(e)}"
        )

# ==================== ENDPOINTS DE AUTENTICACIÓN (Criterio C) ====================

@app.post("/auth/register", response_model=UsuarioResponse)
async def registrar_usuario(usuario: UsuarioCreate, db: Session = Depends(get_db)):
    """Registrar nuevo usuario"""
    try:
        db_user = create_user(db, usuario)
        return UsuarioResponse.model_validate(db_user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear usuario: {str(e)}"
        )

@app.post("/auth/login", response_model=Token)
async def login(user_login: UsuarioLogin, db: Session = Depends(get_db)):
    """Login de usuario"""
    return login_user(db, user_login)

@app.get("/auth/me", response_model=UsuarioResponse)
async def obtener_usuario_actual(current_user: Usuario = Depends(get_current_user)):
    """Obtener información del usuario actual"""
    return UsuarioResponse.model_validate(current_user)

# ==================== ENDPOINTS DE CONVERSACIONES (Criterio B) ====================

@app.post("/conversations", response_model=ConversacionResponse)
async def crear_nueva_conversacion(
    conversacion: ConversacionCreate,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crear nueva conversación"""
    return crear_conversacion(db, current_user, conversacion)

@app.get("/conversations", response_model=List[ConversacionResponse])
async def listar_conversaciones(
    skip: int = 0,
    limit: int = 100,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Listar conversaciones del usuario"""
    return obtener_conversaciones_usuario(db, current_user, skip, limit)

@app.get("/conversations/{conversacion_id}", response_model=ConversacionConMensajes)
async def obtener_conversacion(
    conversacion_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener conversación específica con mensajes"""
    return obtener_conversacion_con_mensajes(db, current_user, conversacion_id)

@app.delete("/conversations/{conversacion_id}", response_model=SuccessResponse)
async def eliminar_conversacion_endpoint(
    conversacion_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eliminar conversación"""
    eliminar_conversacion(db, current_user, conversacion_id)
    return SuccessResponse(message="Conversación eliminada exitosamente")

@app.put("/conversations/{conversacion_id}/title", response_model=ConversacionResponse)
async def actualizar_titulo(
    conversacion_id: int,
    nuevo_titulo: str,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Actualizar título de conversación"""
    return actualizar_titulo_conversacion(db, current_user, conversacion_id, nuevo_titulo)

@app.get("/conversations/stats/summary")
async def estadisticas_conversaciones(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener estadísticas de conversaciones del usuario"""
    return obtener_estadisticas_conversaciones(db, current_user)

# ==================== ENDPOINTS DE CHAT (Criterio A + D) ====================

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    chat_request: ChatRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Endpoint principal del chat con IA"""
    try:
        return procesar_mensaje_chat(db, current_user, chat_request)
    except Exception as e:
        logger.error(f"Error en chat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al procesar consulta: {str(e)}"
        )

# ==================== ENDPOINTS DE TÉRMINOS EXCLUIDOS (Criterio E) ====================

@app.get("/filters/excluded-terms", response_model=List[TerminoExcluidoResponse])
async def listar_terminos_excluidos(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Listar términos excluidos del usuario"""
    terminos = db.query(TerminoExcluido).filter(
        TerminoExcluido.id_usuario == current_user.id,
        TerminoExcluido.activo == True
    ).all()
    return [TerminoExcluidoResponse.model_validate(t) for t in terminos]

@app.post("/filters/excluded-terms", response_model=TerminoExcluidoResponse)
async def agregar_termino_excluido(
    termino: TerminoExcluidoCreate,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Agregar término excluido"""
    # Verificar si ya existe
    existe = db.query(TerminoExcluido).filter(
        TerminoExcluido.id_usuario == current_user.id,
        TerminoExcluido.termino == termino.termino.lower(),
        TerminoExcluido.activo == True
    ).first()
    
    if existe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El término ya está en la lista de excluidos"
        )
    
    db_termino = TerminoExcluido(
        id_usuario=current_user.id,
        termino=termino.termino.lower()
    )
    db.add(db_termino)
    db.commit()
    db.refresh(db_termino)
    return TerminoExcluidoResponse.model_validate(db_termino)

@app.delete("/filters/excluded-terms/{termino_id}", response_model=SuccessResponse)
async def eliminar_termino_excluido(
    termino_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eliminar término excluido"""
    termino = db.query(TerminoExcluido).filter(
        TerminoExcluido.id == termino_id,
        TerminoExcluido.id_usuario == current_user.id
    ).first()
    
    if not termino:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Término no encontrado"
        )
    
    termino.activo = False
    db.commit()
    return SuccessResponse(message="Término eliminado exitosamente")

# ==================== ENDPOINTS DE ADMINISTRACIÓN (Criterio F) ====================

@app.get("/admin/prompts", response_model=List[ConfiguracionPromptResponse])
async def listar_configuraciones_prompt(
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Listar configuraciones de prompt (solo admin)"""
    configs = db.query(ConfiguracionPrompt).filter(
        ConfiguracionPrompt.activo == True
    ).all()
    return [ConfiguracionPromptResponse.model_validate(c) for c in configs]

@app.post("/admin/prompts", response_model=ConfiguracionPromptResponse)
async def crear_configuracion_prompt(
    config: ConfiguracionPromptCreate,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Crear nueva configuración de prompt (solo admin)"""
    db_config = ConfiguracionPrompt(
        contexto=config.contexto,
        prompt_sistema=config.prompt_sistema,
        creado_por=current_admin.id
    )
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return ConfiguracionPromptResponse.model_validate(db_config)

@app.put("/admin/prompts/{config_id}", response_model=ConfiguracionPromptResponse)
async def actualizar_configuracion_prompt(
    config_id: int,
    config_update: ConfiguracionPromptUpdate,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Actualizar configuración de prompt (solo admin)"""
    db_config = db.query(ConfiguracionPrompt).filter(
        ConfiguracionPrompt.id == config_id
    ).first()
    
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuración no encontrada"
        )
    
    if config_update.contexto is not None:
        db_config.contexto = config_update.contexto
    if config_update.prompt_sistema is not None:
        db_config.prompt_sistema = config_update.prompt_sistema
    if config_update.activo is not None:
        db_config.activo = config_update.activo
    
    db_config.fecha_modificacion = datetime.utcnow()
    db.commit()
    db.refresh(db_config)
    return ConfiguracionPromptResponse.model_validate(db_config)

# ==================== ENDPOINTS DE DETALLES (Criterio G) ====================

@app.get("/data/details/{mensaje_id}")
async def obtener_detalles_contexto(
    mensaje_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obtener detalles contextuales para modal"""
    # Verificar que el mensaje pertenece al usuario
    from .models import Mensaje, Conversacion
    
    mensaje = db.query(Mensaje).join(Conversacion).filter(
        Mensaje.id == mensaje_id,
        Conversacion.id_usuario == current_user.id
    ).first()
    
    if not mensaje:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mensaje no encontrado"
        )
    
    # Si hay SQL, ejecutarla nuevamente para obtener datos frescos
    detalles = {
        "mensaje_id": mensaje_id,
        "consulta_sql": mensaje.consulta_sql,
        "timestamp": mensaje.timestamp,
        "datos_disponibles": False
    }
    
    if mensaje.consulta_sql:
        try:
            from .chat import ejecutar_sql
            resultados = ejecutar_sql(db, mensaje.consulta_sql)
            detalles["datos_disponibles"] = True
            detalles["total_resultados"] = len(resultados)
            detalles["muestra_datos"] = resultados[:10]  # Primeros 10 para modal
        except Exception as e:
            detalles["error"] = str(e)
    
    return detalles

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)