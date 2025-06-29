from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime
import logging

# Imports locales
from .config import settings
from .database import get_db, test_connection, init_db
from .models import Usuario, TerminoExcluido, ConfiguracionPrompt
from .schemas import (
    # Auth schemas
    UsuarioCreate, UsuarioLogin, UsuarioResponse, UsuarioUpdate, Token,
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
    """Eliminar conversación y todos sus mensajes permanentemente"""
    eliminar_conversacion(db, current_user, conversacion_id)
    return SuccessResponse(message="Conversación y todos sus mensajes eliminados permanentemente")

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

# Admin - User Management
@app.get("/admin/users", response_model=List[UsuarioResponse])
async def listar_usuarios(
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Listar todos los usuarios (solo admin)"""
    usuarios = db.query(Usuario).all()
    return [UsuarioResponse.model_validate(u) for u in usuarios]

@app.get("/admin/users/{user_id}", response_model=UsuarioResponse)
async def obtener_usuario_admin(
    user_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Obtener detalles de un usuario (solo admin)"""
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    return UsuarioResponse.model_validate(usuario)

@app.put("/admin/users/{user_id}", response_model=UsuarioResponse)
async def actualizar_usuario_admin(
    user_id: int,
    user_update: UsuarioUpdate,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Actualizar usuario (solo admin)"""
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    # Verificar que no sea otro admin (los administradores no pueden editar otros administradores)
    if usuario.rol == "admin" and usuario.id != current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para editar otros administradores"
        )
    
    # Verificar que no esté intentando cambiar su propio rol
    if user_update.rol is not None and usuario.id == current_admin.id and usuario.rol != user_update.rol:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes cambiar tu propio rol"
        )
    
    # Actualizar campos permitidos
    if user_update.username is not None:
        # Verificar que el nuevo username no exista
        existing = db.query(Usuario).filter(
            Usuario.username == user_update.username,
            Usuario.id != user_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El username ya está en uso"
            )
        usuario.username = user_update.username
    
    if user_update.email is not None:
        # Verificar que el nuevo email no exista
        existing = db.query(Usuario).filter(
            Usuario.email == user_update.email,
            Usuario.id != user_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El email ya está en uso"
            )
        usuario.email = user_update.email
    
    if user_update.rol is not None:
        usuario.rol = user_update.rol
    
    if user_update.activo is not None:
        usuario.activo = user_update.activo
    
    db.commit()
    db.refresh(usuario)
    return UsuarioResponse.model_validate(usuario)

@app.delete("/admin/users/{user_id}", response_model=SuccessResponse)
async def eliminar_usuario_admin(
    user_id: int,
    hard_delete: bool = False,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Eliminar usuario (solo admin)"""
    if user_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propia cuenta"
        )
    
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    # Verificar que no sea admin (los administradores no pueden eliminar otros administradores)
    if usuario.rol == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para eliminar otros administradores"
        )
    
    try:
        if hard_delete:
            # Hard delete: eliminar permanentemente usuario y todas sus relaciones
            # Gracias a cascade="all, delete-orphan" en los modelos, esto eliminará:
            # - Todas las conversaciones del usuario
            # - Todos los mensajes de esas conversaciones
            # - Todos los términos excluidos del usuario
            
            # Primero obtener estadísticas antes de eliminar para el mensaje de respuesta
            from .models import Conversacion, Mensaje, TerminoExcluido
            
            conversaciones_count = db.query(Conversacion).filter(
                Conversacion.id_usuario == user_id
            ).count()
            
            mensajes_count = db.query(Mensaje).join(Conversacion).filter(
                Conversacion.id_usuario == user_id
            ).count()
            
            terminos_count = db.query(TerminoExcluido).filter(
                TerminoExcluido.id_usuario == user_id
            ).count()
            
            # Eliminar usuario (cascade se encarga del resto)
            db.delete(usuario)
            db.commit()
            
            return SuccessResponse(
                message=f"Usuario '{usuario.username}' eliminado permanentemente junto con {conversaciones_count} conversaciones, {mensajes_count} mensajes y {terminos_count} términos excluidos"
            )
        else:
            # Soft delete: desactivar usuario (mantiene datos para auditoría)
            usuario.activo = False
            db.commit()
            return SuccessResponse(message=f"Usuario '{usuario.username}' desactivado (soft delete)")
            
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar usuario: {str(e)}"
        )

@app.patch("/admin/users/{user_id}/activate", response_model=UsuarioResponse)
async def activar_usuario_admin(
    user_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Reactivar usuario desactivado (solo admin)"""
    if user_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes reactivar tu propia cuenta desde este endpoint"
        )
    
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    if usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario ya está activo"
        )
    
    try:
        # Reactivar usuario
        usuario.activo = True
        db.commit()
        db.refresh(usuario)
        
        return UsuarioResponse.model_validate(usuario)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al reactivar usuario: {str(e)}"
        )

@app.patch("/admin/users/{user_id}/deactivate", response_model=UsuarioResponse)
async def desactivar_usuario_admin(
    user_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Desactivar usuario activo (solo admin)"""
    if user_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta"
        )
    
    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario ya está inactivo"
        )
    
    # Verificar que no sea admin (los administradores no pueden desactivar otros administradores)
    if usuario.rol == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para desactivar otros administradores"
        )
    
    try:
        # Desactivar usuario
        usuario.activo = False
        db.commit()
        db.refresh(usuario)
        
        return UsuarioResponse.model_validate(usuario)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al desactivar usuario: {str(e)}"
        )

# Admin - Conversation Management
@app.get("/admin/conversations")
async def listar_todas_conversaciones(
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Listar todas las conversaciones (solo admin)"""
    from .models import Conversacion
    
    query = db.query(Conversacion).join(Usuario)
    
    if user_id:
        query = query.filter(Conversacion.id_usuario == user_id)
    
    conversaciones = query.offset(skip).limit(limit).all()
    
    result = []
    for conv in conversaciones:
        result.append({
            "id": conv.id,
            "titulo": conv.titulo,
            "fecha_inicio": conv.fecha_inicio,
            "fecha_ultima_actividad": conv.fecha_ultima_actividad,
            "activa": conv.activa,
            "usuario": {
                "id": conv.usuario.id,
                "username": conv.usuario.username,
                "email": conv.usuario.email
            }
        })
    
    return result

@app.get("/admin/conversations/{conversation_id}")
async def obtener_conversacion_admin(
    conversation_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Obtener conversación específica con mensajes (solo admin)"""
    from .models import Conversacion, Mensaje
    
    conversacion = db.query(Conversacion).filter(
        Conversacion.id == conversation_id
    ).first()
    
    if not conversacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada"
        )
    
    mensajes = db.query(Mensaje).filter(
        Mensaje.id_conversacion == conversation_id
    ).order_by(Mensaje.timestamp).all()
    
    return {
        "id": conversacion.id,
        "titulo": conversacion.titulo,
        "fecha_inicio": conversacion.fecha_inicio,
        "fecha_ultima_actividad": conversacion.fecha_ultima_actividad,
        "activa": conversacion.activa,
        "usuario": {
            "id": conversacion.usuario.id,
            "username": conversacion.usuario.username,
            "email": conversacion.usuario.email
        },
        "mensajes": [
            {
                "id": mensaje.id,
                "rol": mensaje.rol,
                "contenido": mensaje.contenido,
                "consulta_sql": mensaje.consulta_sql,
                "timestamp": mensaje.timestamp
            }
            for mensaje in mensajes
        ]
    }

@app.patch("/admin/conversations/{conversation_id}/deactivate", response_model=SuccessResponse)
async def desactivar_conversacion_admin(
    conversation_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Desactivar conversación (solo admin)"""
    from .models import Conversacion
    
    conversacion = db.query(Conversacion).filter(
        Conversacion.id == conversation_id
    ).first()
    
    if not conversacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada"
        )
    
    try:
        # Soft delete: marcar como inactiva
        conversacion.activa = False
        db.commit()
        
        return SuccessResponse(
            message=f"Conversación '{conversacion.titulo or conversation_id}' desactivada exitosamente"
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al desactivar conversación: {str(e)}"
        )

@app.patch("/admin/conversations/{conversation_id}/activate", response_model=SuccessResponse)
async def activar_conversacion_admin(
    conversation_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Reactivar conversación (solo admin)"""
    from .models import Conversacion
    
    conversacion = db.query(Conversacion).filter(
        Conversacion.id == conversation_id
    ).first()
    
    if not conversacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada"
        )
    
    if conversacion.activa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La conversación ya está activa"
        )
    
    try:
        # Reactivar conversación
        conversacion.activa = True
        db.commit()
        
        return SuccessResponse(
            message=f"Conversación '{conversacion.titulo or conversation_id}' reactivada exitosamente"
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al reactivar conversación: {str(e)}"
        )

@app.delete("/admin/conversations/{conversation_id}", response_model=SuccessResponse)
async def eliminar_conversacion_admin(
    conversation_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Eliminar conversación y todos sus mensajes permanentemente (solo admin)"""
    from .models import Conversacion, Mensaje
    
    conversacion = db.query(Conversacion).filter(
        Conversacion.id == conversation_id
    ).first()
    
    if not conversacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada"
        )
    
    try:
        # Obtener estadísticas antes de eliminar para el mensaje de respuesta
        mensajes_count = db.query(Mensaje).filter(
            Mensaje.id_conversacion == conversation_id
        ).count()
        
        titulo = conversacion.titulo or f"Conversación {conversation_id}"
        
        # Hard delete: eliminar permanentemente conversación y todos sus mensajes
        # Gracias a cascade="all, delete-orphan" en el modelo Conversacion,
        # esto eliminará automáticamente todos los mensajes asociados
        db.delete(conversacion)
        db.commit()
        
        return SuccessResponse(
            message=f"Conversación '{titulo}' eliminada permanentemente junto con {mensajes_count} mensajes"
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar conversación: {str(e)}"
        )

# Admin - Excluded Terms Management  
@app.get("/admin/excluded-terms")
async def listar_todos_terminos_excluidos(
    user_id: Optional[int] = None,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Listar términos excluidos de todos los usuarios (solo admin)"""
    # Cambiar para mostrar tanto activos como inactivos para admin
    query = db.query(TerminoExcluido).join(Usuario)
    
    if user_id:
        query = query.filter(TerminoExcluido.id_usuario == user_id)
    
    terminos = query.all()
    
    result = []
    for termino in terminos:
        result.append({
            "id": termino.id,
            "termino": termino.termino,
            "activo": termino.activo,  # Añadir campo activo
            "fecha_creacion": termino.fecha_creacion,
            "usuario": {
                "id": termino.usuario.id,
                "username": termino.usuario.username,
                "email": termino.usuario.email
            }
        })
    
    return result

@app.patch("/admin/excluded-terms/{term_id}/deactivate", response_model=SuccessResponse)
async def desactivar_termino_excluido_admin(
    term_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Desactivar término excluido (solo admin)"""
    termino = db.query(TerminoExcluido).filter(TerminoExcluido.id == term_id).first()
    
    if not termino:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Término no encontrado"
        )
    
    try:
        # Soft delete: marcar como inactivo
        termino.activo = False
        db.commit()
        
        return SuccessResponse(
            message=f"Término '{termino.termino}' desactivado exitosamente"
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al desactivar término: {str(e)}"
        )

@app.patch("/admin/excluded-terms/{term_id}/activate", response_model=SuccessResponse)
async def activar_termino_excluido_admin(
    term_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Reactivar término excluido (solo admin)"""
    termino = db.query(TerminoExcluido).filter(TerminoExcluido.id == term_id).first()
    
    if not termino:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Término no encontrado"
        )
    
    if termino.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El término ya está activo"
        )
    
    try:
        # Reactivar término: marcar como activo
        termino.activo = True
        db.commit()
        
        return SuccessResponse(
            message=f"Término '{termino.termino}' reactivado exitosamente"
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al reactivar término: {str(e)}"
        )

@app.delete("/admin/excluded-terms/{term_id}", response_model=SuccessResponse)
async def eliminar_termino_excluido_admin(
    term_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Eliminar término excluido permanentemente (solo admin)"""
    termino = db.query(TerminoExcluido).filter(TerminoExcluido.id == term_id).first()
    
    if not termino:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Término no encontrado"
        )
    
    try:
        # Obtener información para el mensaje de respuesta
        termino_texto = termino.termino
        usuario_username = termino.usuario.username
        
        # Hard delete: eliminar permanentemente de la base de datos
        db.delete(termino)
        db.commit()
        
        return SuccessResponse(
            message=f"Término '{termino_texto}' del usuario '{usuario_username}' eliminado permanentemente"
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar término: {str(e)}"
        )

@app.get("/admin/prompts", response_model=List[ConfiguracionPromptResponse])
async def listar_configuraciones_prompt(
    include_inactive: bool = False,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Listar configuraciones de prompt (solo admin)"""
    query = db.query(ConfiguracionPrompt)
    
    if not include_inactive:
        # Solo configuraciones activas por defecto
        query = query.filter(ConfiguracionPrompt.activo == True)
    
    configs = query.all()
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

@app.patch("/admin/prompts/{config_id}/activate", response_model=ConfiguracionPromptResponse)
async def activar_configuracion_prompt(
    config_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Reactivar configuración de prompt desactivada (solo admin)"""
    db_config = db.query(ConfiguracionPrompt).filter(
        ConfiguracionPrompt.id == config_id
    ).first()
    
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuración de prompt no encontrada"
        )
    
    if db_config.activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La configuración ya está activa"
        )
    
    try:
        # Reactivar configuración
        db_config.activo = True
        db_config.fecha_modificacion = datetime.utcnow()
        db.commit()
        db.refresh(db_config)
        
        return ConfiguracionPromptResponse.model_validate(db_config)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al reactivar configuración de prompt: {str(e)}"
        )

@app.delete("/admin/prompts/{config_id}", response_model=SuccessResponse)
async def eliminar_configuracion_prompt(
    config_id: int,
    current_admin: Usuario = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Eliminar configuración de prompt permanentemente (solo admin)"""
    db_config = db.query(ConfiguracionPrompt).filter(
        ConfiguracionPrompt.id == config_id
    ).first()
    
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuración de prompt no encontrada"
        )
    
    try:
        # Obtener información para el mensaje de respuesta
        contexto = db_config.contexto
        
        # Hard delete: eliminar permanentemente de la base de datos
        db.delete(db_config)
        db.commit()
        
        return SuccessResponse(
            message=f"Configuración de prompt '{contexto}' eliminada permanentemente"
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar configuración de prompt: {str(e)}"
        )

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