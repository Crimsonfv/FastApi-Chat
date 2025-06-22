from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from fastapi import HTTPException, status
from datetime import datetime

from .models import Usuario, Conversacion, Mensaje
from .schemas import (
    ConversacionCreate, ConversacionResponse, ConversacionConMensajes,
    MensajeCreate, MensajeResponse, ChatRequest, ChatResponse
)
from .chat import procesar_consulta_chat

def crear_conversacion(db: Session, usuario: Usuario, conversacion: ConversacionCreate) -> ConversacionResponse:
    """
    Crear nueva conversación (Criterio B)
    """
    # Generar título automático si no se proporciona
    titulo = conversacion.titulo
    if not titulo:
        # Contar conversaciones del usuario para generar título
        count = db.query(Conversacion).filter(Conversacion.id_usuario == usuario.id).count()
        titulo = f"Conversación {count + 1}"
    
    db_conversacion = Conversacion(
        id_usuario=usuario.id,
        titulo=titulo
    )
    db.add(db_conversacion)
    db.commit()
    db.refresh(db_conversacion)
    
    return ConversacionResponse.model_validate(db_conversacion)

def obtener_conversaciones_usuario(db: Session, usuario: Usuario, skip: int = 0, limit: int = 100) -> List[ConversacionResponse]:
    """
    Obtener todas las conversaciones del usuario (Criterio B)
    Nota: Mantenemos el filtro activa=True para compatibilidad con conversaciones
    que pudieron haberse marcado como inactivas antes del cambio a hard delete
    """
    conversaciones = db.query(Conversacion).filter(
        Conversacion.id_usuario == usuario.id,
        Conversacion.activa == True
    ).order_by(desc(Conversacion.fecha_ultima_actividad)).offset(skip).limit(limit).all()
    
    return [ConversacionResponse.model_validate(conv) for conv in conversaciones]

def obtener_conversacion_con_mensajes(db: Session, usuario: Usuario, conversacion_id: int) -> ConversacionConMensajes:
    """
    Obtener conversación específica con todos sus mensajes (Criterio B)
    """
    conversacion = db.query(Conversacion).filter(
        Conversacion.id == conversacion_id,
        Conversacion.id_usuario == usuario.id,
        Conversacion.activa == True
    ).first()
    
    if not conversacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada"
        )
    
    # Obtener mensajes ordenados por timestamp
    mensajes = db.query(Mensaje).filter(
        Mensaje.id_conversacion == conversacion_id
    ).order_by(Mensaje.timestamp).all()
    
    return ConversacionConMensajes(
        id=conversacion.id,
        id_usuario=conversacion.id_usuario,
        titulo=conversacion.titulo,
        fecha_inicio=conversacion.fecha_inicio,
        fecha_ultima_actividad=conversacion.fecha_ultima_actividad,
        activa=conversacion.activa,
        mensajes=[MensajeResponse.model_validate(msg) for msg in mensajes]
    )

def eliminar_conversacion(db: Session, usuario: Usuario, conversacion_id: int) -> bool:
    """
    Eliminar conversación y todos sus mensajes permanentemente (hard delete) (Criterio B)
    """
    conversacion = db.query(Conversacion).filter(
        Conversacion.id == conversacion_id,
        Conversacion.id_usuario == usuario.id
    ).first()
    
    if not conversacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada"
        )
    
    try:
        # Hard delete: eliminar permanentemente la conversación y todos sus mensajes
        # Gracias a cascade="all, delete-orphan" en el modelo Conversacion,
        # esto eliminará automáticamente todos los mensajes asociados
        
        # Obtener estadísticas antes de eliminar para logging
        mensajes_count = db.query(Mensaje).filter(
            Mensaje.id_conversacion == conversacion_id
        ).count()
        
        # Eliminar conversación (cascade eliminará automáticamente los mensajes)
        db.delete(conversacion)
        db.commit()
        
        # Log para auditoría
        print(f"Conversación {conversacion_id} eliminada permanentemente junto con {mensajes_count} mensajes")
        
        return True
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar conversación: {str(e)}"
        )

def actualizar_titulo_conversacion(db: Session, usuario: Usuario, conversacion_id: int, nuevo_titulo: str) -> ConversacionResponse:
    """
    Actualizar título de conversación
    """
    conversacion = db.query(Conversacion).filter(
        Conversacion.id == conversacion_id,
        Conversacion.id_usuario == usuario.id,
        Conversacion.activa == True
    ).first()
    
    if not conversacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada"
        )
    
    conversacion.titulo = nuevo_titulo
    conversacion.fecha_ultima_actividad = datetime.utcnow()
    db.commit()
    db.refresh(conversacion)
    
    return ConversacionResponse.model_validate(conversacion)

def agregar_mensaje(db: Session, conversacion_id: int, mensaje: MensajeCreate) -> MensajeResponse:
    """
    Agregar mensaje a conversación
    """
    # Verificar que la conversación existe
    conversacion = db.query(Conversacion).filter(
        Conversacion.id == conversacion_id,
        Conversacion.activa == True
    ).first()
    
    if not conversacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada"
        )
    
    # Crear mensaje
    db_mensaje = Mensaje(
        id_conversacion=conversacion_id,
        rol=mensaje.rol,
        contenido=mensaje.contenido,
        consulta_sql=mensaje.consulta_sql
    )
    db.add(db_mensaje)
    
    # Actualizar fecha de última actividad de la conversación
    conversacion.fecha_ultima_actividad = datetime.utcnow()
    
    db.commit()
    db.refresh(db_mensaje)
    
    return MensajeResponse.model_validate(db_mensaje)

def obtener_historial_conversacion(db: Session, conversacion_id: int, limite: int = 10) -> List[Dict[str, Any]]:
    """
    Obtener historial reciente de una conversación para proporcionar contexto al AI.
    Retorna los últimos mensajes en formato simplificado.
    """
    mensajes = db.query(Mensaje).filter(
        Mensaje.id_conversacion == conversacion_id
    ).order_by(desc(Mensaje.timestamp)).limit(limite).all()
    
    # Invertir para tener orden cronológico (más antiguo primero)
    mensajes = mensajes[::-1]
    
    historial = []
    for mensaje in mensajes:
        historial.append({
            "rol": mensaje.rol,
            "contenido": mensaje.contenido,
            "timestamp": mensaje.timestamp.isoformat() if mensaje.timestamp else None,
            "consulta_sql": mensaje.consulta_sql
        })
    
    return historial

def procesar_mensaje_chat(db: Session, usuario: Usuario, chat_request: ChatRequest) -> ChatResponse:
    """
    Procesar mensaje de chat completo - integra chat.py con conversations.py (Criterio A + B + D)
    """
    conversacion_id = chat_request.id_conversacion
    
    # Si no hay conversación, crear una nueva
    if not conversacion_id:
        nueva_conversacion = crear_conversacion(
            db, 
            usuario, 
            ConversacionCreate(titulo=f"Chat sobre: {chat_request.pregunta[:50]}...")
        )
        conversacion_id = nueva_conversacion.id
    else:
        # Verificar que la conversación pertenece al usuario
        conversacion = db.query(Conversacion).filter(
            Conversacion.id == conversacion_id,
            Conversacion.id_usuario == usuario.id,
            Conversacion.activa == True
        ).first()
        
        if not conversacion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversación no encontrada"
            )
    
    # 1. Guardar mensaje del usuario
    mensaje_usuario = agregar_mensaje(
        db,
        conversacion_id,
        MensajeCreate(
            rol="user",
            contenido=chat_request.pregunta
        )
    )
    
    # 2. Obtener historial de conversación para contexto
    historial_conversacion = obtener_historial_conversacion(db, conversacion_id)
    
    # 3. Procesar consulta con IA incluyendo historial
    resultado_chat = procesar_consulta_chat(db, usuario, chat_request.pregunta, historial_conversacion)
    
    # 4. Guardar respuesta del asistente
    mensaje_asistente = agregar_mensaje(
        db,
        conversacion_id,
        MensajeCreate(
            rol="assistant",
            contenido=resultado_chat["respuesta"],
            consulta_sql=resultado_chat["consulta_sql"]
        )
    )
    
    # 5. Preparar respuesta
    return ChatResponse(
        respuesta=resultado_chat["respuesta"],
        consulta_sql=resultado_chat["consulta_sql"],
        id_conversacion=conversacion_id,
        id_mensaje=mensaje_asistente.id,
        datos_contexto=resultado_chat["datos_contexto"]
    )

def obtener_estadisticas_conversaciones(db: Session, usuario: Usuario) -> dict:
    """
    Obtener estadísticas de conversaciones del usuario
    """
    total_conversaciones = db.query(Conversacion).filter(
        Conversacion.id_usuario == usuario.id,
        Conversacion.activa == True
    ).count()
    
    total_mensajes = db.query(Mensaje).join(Conversacion).filter(
        Conversacion.id_usuario == usuario.id,
        Conversacion.activa == True
    ).count()
    
    conversacion_mas_reciente = db.query(Conversacion).filter(
        Conversacion.id_usuario == usuario.id,
        Conversacion.activa == True
    ).order_by(desc(Conversacion.fecha_ultima_actividad)).first()
    
    return {
        "total_conversaciones": total_conversaciones,
        "total_mensajes": total_mensajes,
        "fecha_ultima_actividad": conversacion_mas_reciente.fecha_ultima_actividad if conversacion_mas_reciente else None
    }