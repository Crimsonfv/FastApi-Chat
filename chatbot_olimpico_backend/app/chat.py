import anthropic
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import json

from .config import settings
from .models import Usuario, MedallaOlimpica, TerminoExcluido, ConfiguracionPrompt
from .schemas import ChatRequest, ChatResponse

# Configurar logging
logger = logging.getLogger(__name__)

# Cliente de Anthropic
client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# Estructura de la tabla principal (basada en tu ExtraerCSV_Olimpiadas.py)
ESTRUCTURA_TABLA_OLIMPICA = """
TABLA medallas_olimpicas
id              SERIAL PRIMARY KEY
city            VARCHAR(100)     - Ciudad olímpica
year            INTEGER          - Año de las olimpiadas  
sport           VARCHAR(100)     - Deporte
discipline      VARCHAR(100)     - Disciplina específica
event           VARCHAR(200)     - Evento específico
athlete         VARCHAR(200)     - Nombre original del atleta (formato: "APELLIDO, Nombre")
nombre          VARCHAR(100)     - Nombre procesado del atleta
apellido        VARCHAR(100)     - Apellido procesado del atleta  
nombre_completo VARCHAR(200)     - Nombre completo procesado ("Nombre Apellido")
gender          VARCHAR(10)      - Género del atleta
country_code    VARCHAR(10)      - Código del país
country         VARCHAR(100)     - Nombre del país
event_gender    VARCHAR(10)      - Género del evento
medal           VARCHAR(20)      - Tipo de medalla (Gold, Silver, Bronze)
created_at      TIMESTAMP        - Fecha de creación del registro
"""

def obtener_prompt_contexto(db: Session, contexto: str = "deportivo") -> str:
    """
    Obtener prompt personalizado por contexto (Criterio F)
    """
    config = db.query(ConfiguracionPrompt).filter(
        ConfiguracionPrompt.contexto == contexto,
        ConfiguracionPrompt.activo == True
    ).first()
    
    if config:
        return config.prompt_sistema
    
    # Prompt por defecto si no hay configuración
    return """Eres un asistente especializado en análisis de datos olímpicos. 
    Proporciona respuestas precisas y profesionales sobre medallas, atletas, 
    países y estadísticas olímpicas."""

def obtener_terminos_excluidos(db: Session, usuario: Usuario) -> List[str]:
    """
    Obtener términos excluidos del usuario (Criterio E)
    """
    terminos = db.query(TerminoExcluido).filter(
        TerminoExcluido.id_usuario == usuario.id,
        TerminoExcluido.activo == True
    ).all()
    
    return [termino.termino.lower() for termino in terminos]

def filtrar_pregunta_por_terminos_excluidos(pregunta: str, terminos_excluidos: List[str]) -> str:
    """
    Filtrar pregunta removiendo términos excluidos (Criterio E)
    """
    if not terminos_excluidos:
        return pregunta
    
    pregunta_filtrada = pregunta
    for termino in terminos_excluidos:
        pregunta_filtrada = pregunta_filtrada.replace(termino, "")
    
    # Limpiar espacios extra
    pregunta_filtrada = " ".join(pregunta_filtrada.split())
    return pregunta_filtrada

def obtener_consulta_sql(pregunta: str, prompt_contexto: str) -> str:
    """
    Generar consulta SQL usando Claude (basado en ejemploProfe.py)
    """
    prompt = f"""{prompt_contexto}

Dada la siguiente estructura de tabla:
{ESTRUCTURA_TABLA_OLIMPICA}

Y la siguiente consulta en lenguaje natural:
"{pregunta}"

Genera una consulta SQL para PostgreSQL que responda la pregunta del usuario. Sigue estas pautas:

0. La tabla se llama medallas_olimpicas.
1. Utiliza ILIKE para búsquedas de texto insensibles a mayúsculas/minúsculas.
2. Para búsquedas de nombres de atletas, puedes usar tanto 'athlete' (formato original) como 'nombre_completo' (formato procesado).
3. Al buscar nombres completos usa ILIKE con comodines %. Para búsquedas específicas usa AND entre nombres y apellidos.
4. Si la consulta puede devolver múltiples resultados, usa GROUP BY para agrupar resultados similares.
5. Incluye COUNT(*) o COUNT(DISTINCT...) cuando sea apropiado para contar resultados.
6. Usa COALESCE cuando sea necesario para manejar valores null.
7. Limita los resultados a 100 filas como máximo. Usa LIMIT 100.
8. Incluye ORDER BY para ordenar los resultados de manera lógica.
9. Para cálculos numéricos, usa funciones como MIN, MAX, AVG, SUM.
10. Para fechas usa funciones apropiadas de PostgreSQL.
11. En la respuesta incluye datos útiles para que el usuario tenga una respuesta clara.
12. IMPORTANTE: Solo genera consultas SELECT. No generes DDL (CREATE, DROP) o DML (INSERT, UPDATE, DELETE).
13. Para filtros por medallas usa: medal = 'Gold', medal = 'Silver', medal = 'Bronze'.
14. Para filtros por género usa: gender = 'Men' o gender = 'Women'.

Responde solo con la consulta SQL, sin agregar nada más."""

    try:
        message = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1000,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        sql_query = message.content[0].text.strip()
        
        # Limpiar la respuesta en caso de que incluya texto extra
        if "```sql" in sql_query:
            sql_query = sql_query.split("```sql")[1].split("```")[0].strip()
        elif "```" in sql_query:
            sql_query = sql_query.split("```")[1].strip()
            
        return sql_query
        
    except Exception as e:
        logger.error(f"Error al generar SQL con Claude: {e}")
        raise Exception(f"Error al generar consulta SQL: {str(e)}")

def ejecutar_sql(db: Session, sql_query: str) -> List[Dict]:
    """
    Ejecutar consulta SQL en PostgreSQL
    """
    try:
        result = db.execute(text(sql_query))
        
        # Convertir resultado a lista de diccionarios
        columns = result.keys()
        rows = result.fetchall()
        
        resultados = []
        for row in rows:
            row_dict = {}
            for i, column in enumerate(columns):
                value = row[i]
                # Convertir tipos especiales para JSON
                if hasattr(value, 'isoformat'):  # datetime
                    value = value.isoformat()
                row_dict[column] = value
            resultados.append(row_dict)
            
        return resultados
        
    except Exception as e:
        logger.error(f"Error al ejecutar SQL: {e}")
        raise Exception(f"Error en la consulta: {str(e)}")

def generar_respuesta_final(resultados_sql: List[Dict], pregunta: str, prompt_contexto: str) -> str:
    """
    Generar respuesta natural usando Claude (basado en ejemploProfe.py)
    """
    prompt = f"""{prompt_contexto}

Dada la siguiente pregunta:
"{pregunta}"

Y los siguientes resultados de la consulta SQL:
{json.dumps(resultados_sql, indent=2, ensure_ascii=False)}

Genera una respuesta en lenguaje natural, entendible para un usuario interesado en datos olímpicos con las siguientes reglas:

1. Responde directamente sin hacer mención a SQL u otros términos técnicos.
2. Usa un lenguaje claro, profesional, como si estuvieses conversando con el usuario.
3. Presenta la información de manera organizada y fácil de entender.
4. Si los datos son limitados, proporciona una respuesta con la información disponible.
5. Utiliza términos propios del ámbito deportivo y olímpico cuando sea posible.
6. Si la respuesta incluye números, formátealos de manera clara.
7. No agregues información que no esté explícitamente en los datos obtenidos.
8. Si no hay datos disponibles, indica amablemente que no se encontraron resultados.
9. No hagas supuestos ni agregues análisis a menos que se solicite.
10. Entrega el resultado de manera precisa y estructurada.
11. Los resultados son para una conversación tipo chat, no saludes ni te despidas.
12. IMPORTANTE: Nunca menciones detalles técnicos de la consulta.
13. Si hay muchos resultados, resume los más relevantes y menciona el total.

"""

    try:
        message = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1000,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        return message.content[0].text.strip()
        
    except Exception as e:
        logger.error(f"Error al generar respuesta con Claude: {e}")
        raise Exception(f"Error al generar respuesta: {str(e)}")

def procesar_consulta_chat(
    db: Session, 
    usuario: Usuario, 
    pregunta: str,
    contexto: str = "deportivo"
) -> Dict[str, Any]:
    """
    Función principal para procesar consulta del chat (Criterios A + D + E + F)
    """
    try:
        # 1. Obtener configuración de prompt por contexto (Criterio F)
        prompt_contexto = obtener_prompt_contexto(db, contexto)
        
        # 2. Obtener términos excluidos del usuario (Criterio E)
        terminos_excluidos = obtener_terminos_excluidos(db, usuario)
        
        # 3. Filtrar pregunta por términos excluidos (Criterio E)
        pregunta_filtrada = filtrar_pregunta_por_terminos_excluidos(pregunta, terminos_excluidos)
        
        if not pregunta_filtrada.strip():
            return {
                "respuesta": "La pregunta contiene solo términos excluidos. Por favor, reformula tu consulta.",
                "consulta_sql": None,
                "datos_contexto": None,
                "error": True
            }
        
        # 4. Generar SQL con Claude (Criterio A + D)
        sql_query = obtener_consulta_sql(pregunta_filtrada, prompt_contexto)
        
        # 5. Ejecutar SQL (Criterio D)
        resultados_sql = ejecutar_sql(db, sql_query)
        
        # 6. Generar respuesta natural con Claude (Criterio A)
        respuesta_final = generar_respuesta_final(resultados_sql, pregunta_filtrada, prompt_contexto)
        
        # 7. Preparar datos de contexto para modal (Criterio G)
        datos_contexto = {
            "total_resultados": len(resultados_sql),
            "muestra_datos": resultados_sql[:5] if resultados_sql else [],
            "sql_ejecutado": sql_query
        }
        
        return {
            "respuesta": respuesta_final,
            "consulta_sql": sql_query,
            "datos_contexto": datos_contexto,
            "error": False
        }
        
    except Exception as e:
        logger.error(f"Error en procesamiento de chat: {e}")
        return {
            "respuesta": f"Ocurrió un error al procesar tu consulta: {str(e)}",
            "consulta_sql": None,
            "datos_contexto": None,
            "error": True
        }