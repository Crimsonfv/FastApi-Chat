import anthropic
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import json
from decimal import Decimal
import datetime
import uuid

from .config import settings
from .models import Usuario, MedallaOlimpica, TerminoExcluido, ConfiguracionPrompt
from .schemas import ChatRequest, ChatResponse

# Configurar logging más detallado
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== LOGS DE DIAGNÓSTICO ==========
def log_anthropic_config():
    """Diagnosticar configuración de Anthropic"""
    print("\n🔍 === DIAGNÓSTICO ANTHROPIC ===")
    print(f"API Key configurada: {'✅ SÍ' if settings.anthropic_api_key else '❌ NO'}")
    if settings.anthropic_api_key:
        print(f"API Key (primeros 20 chars): {settings.anthropic_api_key[:20]}...")
        print(f"API Key (últimos 10 chars): ...{settings.anthropic_api_key[-10:]}")
        print(f"Longitud total: {len(settings.anthropic_api_key)} caracteres")
    print(f"Modelo configurado: {settings.anthropic_model}")
    print("================================\n")

# Llamar al diagnóstico al importar el módulo
log_anthropic_config()

def safe_json_serializer(obj):
    """
    Safe JSON serializer for complex data types
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    elif isinstance(obj, uuid.UUID):
        return str(obj)
    elif hasattr(obj, 'isoformat'):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# Cliente de Anthropic con logs
try:
    print("🔄 Intentando crear cliente de Anthropic...")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    print("✅ Cliente de Anthropic creado exitosamente")
except Exception as e:
    print(f"❌ Error al crear cliente de Anthropic: {e}")
    client = None

# Estructura de la tabla principal (basada en tu ExtraerCSV_Olimpiadas.py)
ESTRUCTURA_TABLA_OLIMPICA = """
TABLA medallas_olimpicas - Contiene datos de MEDALLISTAS olímpicos de verano 1976-2008
id              SERIAL PRIMARY KEY
city            VARCHAR(100)     - Ciudad donde se realizaron las olimpiadas (ej: Montreal, Moscow, Los Angeles, Seoul, Barcelona, Atlanta, Sydney, Athens, Beijing)
year            INTEGER          - Año de las olimpiadas (1976, 1980, 1984, 1988, 1992, 1996, 2000, 2004, 2008)
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

INFORMACIÓN IMPORTANTE:
- Cada fila representa un medallista (oro, plata o bronce)
- El campo 'city' contiene las ciudades anfitrionas de los Juegos Olímpicos
- El periodo de datos es 1976-2008 (Juegos Olímpicos de Verano únicamente)
- Para consultas sobre ciudades repetidas, usar GROUP BY city con COUNT(DISTINCT year)
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
    return """Eres un asistente especializado en análisis de datos olímpicos de verano (1976-2008). 
    Tienes acceso a información completa sobre medallistas, ciudades anfitrionas, países, deportes y estadísticas olímpicas.
    Proporciona respuestas precisas y profesionales. Puedes responder sobre:
    - Ciudades que han organizado múltiples Juegos Olímpicos
    - Medallistas y sus logros
    - Estadísticas por países, deportes y años
    - Análisis comparativos entre olimpiadas
    La base de datos contiene todas las medallas otorgadas en los Juegos Olímpicos de Verano desde Montreal 1976 hasta Beijing 2008."""

def obtener_terminos_excluidos(db: Session, usuario: Usuario) -> List[str]:
    """
    Obtener términos excluidos del usuario (Criterio E)
    """
    print(f"\n🔍 === CONSULTANDO TÉRMINOS EXCLUIDOS EN BD ===")
    print(f"Buscando términos para usuario_id: {usuario.id}")
    
    terminos = db.query(TerminoExcluido).filter(
        TerminoExcluido.id_usuario == usuario.id,
        TerminoExcluido.activo == True
    ).all()
    
    print(f"Términos encontrados en BD: {len(terminos)}")
    for termino in terminos:
        print(f"  - ID: {termino.id}, Término: '{termino.termino}', Activo: {termino.activo}")
    
    resultado = [termino.termino.lower() for termino in terminos]
    print(f"Lista final retornada: {resultado}")
    print("==========================================\n")
    
    return resultado

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

def filtrar_resultados_por_terminos_excluidos(resultados_sql: List[Dict], terminos_excluidos: List[str]) -> List[Dict]:
    """
    Filtrar resultados SQL removiendo filas que contengan términos excluidos (Criterio E)
    """
    print(f"\n🔒 === FUNCIÓN FILTRAR_RESULTADOS LLAMADA ===")
    print(f"Función filtrar_resultados_por_terminos_excluidos() EJECUTÁNDOSE")
    print(f"Recibido - resultados_sql: {len(resultados_sql) if resultados_sql else 0} filas")
    print(f"Recibido - terminos_excluidos: {terminos_excluidos}")
    
    if not terminos_excluidos or not resultados_sql:
        print(f"⚠️ SALIDA TEMPRANA: terminos_excluidos={bool(terminos_excluidos)}, resultados_sql={bool(resultados_sql)}")
        print("===================================\n")
        return resultados_sql
    
    print(f"🔍 PROCESANDO FILTRADO:")
    print(f"  - Resultados originales: {len(resultados_sql)} filas")
    print(f"  - Términos a excluir: {terminos_excluidos}")
    
    resultados_filtrados = []
    filas_removidas = 0
    filas_procesadas = 0
    
    for fila_index, fila in enumerate(resultados_sql):
        filas_procesadas += 1
        fila_contiene_termino_excluido = False
        
        # Debug: Mostrar contenido de las primeras filas
        if fila_index < 3:
            print(f"\n  🔍 Examinando fila {fila_index}: {fila}")
        
        for columna, valor in fila.items():
            if valor is None:
                continue
                
            # Convertir valor a string para búsqueda
            valor_str = str(valor).lower()
            
            # Verificar cada término excluido
            for termino in terminos_excluidos:
                termino_lower = termino.lower().strip()
                if termino_lower and termino_lower in valor_str:
                    print(f"    🚫 MATCH ENCONTRADO en fila {fila_index}:")
                    print(f"       Término: '{termino}' → Valor: '{valor}' (columna: {columna})")
                    fila_contiene_termino_excluido = True
                    break
            
            if fila_contiene_termino_excluido:
                break
        
        # Solo agregar la fila si no contiene términos excluidos
        if not fila_contiene_termino_excluido:
            resultados_filtrados.append(fila)
            if fila_index < 3:
                print(f"    ✅ Fila {fila_index} INCLUIDA (no contiene términos excluidos)")
        else:
            filas_removidas += 1
            if fila_index < 10:  # Mostrar las primeras 10 filas removidas
                print(f"    ❌ Fila {fila_index} REMOVIDA")
    
    print(f"\n📊 RESUMEN DEL FILTRADO:")
    print(f"  - Filas procesadas: {filas_procesadas}")
    print(f"  - Filas incluidas: {len(resultados_filtrados)}")
    print(f"  - Filas removidas: {filas_removidas}")
    print(f"  - Términos que causaron filtrado: {terminos_excluidos}")
    print("===================================\n")
    
    return resultados_filtrados

def obtener_consulta_sql(pregunta: str, prompt_contexto: str, historial_conversacion: List[Dict] = None, terminos_excluidos: List[str] = None) -> str:
    """
    Generar consulta SQL usando Claude (basado en ejemploProfe.py)
    """
    print(f"\n🤖 === LLAMADA A ANTHROPIC ===")
    print(f"Pregunta recibida: {pregunta}")
    print(f"Modelo a usar: {settings.anthropic_model}")
    
    # Verificar cliente
    if client is None:
        raise Exception("Cliente de Anthropic no inicializado")
    
    # Construir contexto de conversación si existe
    contexto_conversacion = ""
    if historial_conversacion and len(historial_conversacion) > 0:
        contexto_conversacion = "\n\nCONTEXTO DE CONVERSACIÓN PREVIA:\n"
        for mensaje in historial_conversacion:
            if mensaje["rol"] == "user":
                contexto_conversacion += f"Usuario preguntó: \"{mensaje['contenido']}\"\n"
            elif mensaje["rol"] == "assistant":
                # Truncar solo si es extremadamente largo, pero preservar más contexto
                contenido_assistant = mensaje['contenido']
                if len(contenido_assistant) > 800:
                    contenido_assistant = contenido_assistant[:800] + "..."
                contexto_conversacion += f"Asistente respondió: \"{contenido_assistant}\"\n"
                if mensaje.get("consulta_sql"):
                    contexto_conversacion += f"SQL ejecutado: {mensaje['consulta_sql']}\n"
        contexto_conversacion += "\nFIN DEL CONTEXTO PREVIO\n"
    
    # Construir sección de términos excluidos si existen
    seccion_terminos_excluidos = ""
    if terminos_excluidos and len(terminos_excluidos) > 0:
        terminos_formateados = ", ".join([f"'{termino}'" for termino in terminos_excluidos])
        seccion_terminos_excluidos = f"""
TÉRMINOS EXCLUIDOS POR EL USUARIO:
El usuario ha especificado que NO desea ver resultados que contengan los siguientes términos: {terminos_formateados}

INSTRUCCIONES CRÍTICAS PARA FILTRADO:
- DEBES excluir automáticamente de los resultados SQL cualquier fila que contenga estos términos excluidos
- Los términos pueden aparecer en cualquier campo (país, atleta, ciudad, deporte, etc.)
- Maneja variaciones del término (mayúsculas/minúsculas, espacios, plurales, sinónimos comunes)
- Usa condiciones WHERE con NOT ILIKE para excluir estos términos
- Para múltiples términos excluidos, usa AND para combinar todas las exclusiones
- Ejemplo: WHERE country NOT ILIKE '%término1%' AND athlete NOT ILIKE '%término2%' AND sport NOT ILIKE '%término3%'
- Aplica las exclusiones a TODAS las columnas relevantes donde estos términos podrían aparecer

"""
    
    prompt = f"""{prompt_contexto}

Dada la siguiente estructura de tabla:
{ESTRUCTURA_TABLA_OLIMPICA}
{contexto_conversacion}{seccion_terminos_excluidos}
Y la siguiente consulta en lenguaje natural:
"{pregunta}"

Genera una consulta SQL para PostgreSQL que responda la pregunta del usuario. Sigue estas pautas:

0. La tabla se llama medallas_olimpicas.
0.1. IMPORTANTE: Si hay contexto de conversación previa, usa esa información para interpretar referencias como "el país anterior", "ese atleta", "la medalla mencionada", etc.
0.2. Las referencias contextuales deben resolverse usando la información del historial de conversación.
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
15. CRÍTICO para PostgreSQL: En STRING_AGG con DISTINCT, el ORDER BY debe usar las mismas columnas que DISTINCT.
    - ✅ Correcto: STRING_AGG(DISTINCT sport, ', ' ORDER BY sport)
    - ❌ Incorrecto: STRING_AGG(DISTINCT sport, ', ' ORDER BY year)
    - ✅ Alternativa: STRING_AGG(DISTINCT CONCAT(year, ' - ', city), ', ' ORDER BY CONCAT(year, ' - ', city))
16. Para evitar errores de agregación con DISTINCT:
    - Si necesitas ordenar por una columna diferente, inclúyela en la expresión DISTINCT
    - O usa subconsultas para ordenamiento complejo
    - O omite ORDER BY en STRING_AGG si no es esencial

ESPECIAL - CONSULTAS SOBRE CIUDADES OLÍMPICAS:
17. Para preguntas sobre ciudades que se repiten o ciudades anfitrionas múltiples:
    - Usa la columna 'city' que contiene las ciudades donde se realizaron las olimpiadas
    - Para encontrar ciudades repetidas: GROUP BY city HAVING COUNT(DISTINCT year) > 1
    - Para listar todas las ediciones: incluye year y city en los resultados
    - Ejemplos de consultas típicas de ciudades:
      * "ciudades que se repiten" → SELECT city, COUNT(DISTINCT year) as veces, STRING_AGG(DISTINCT year::text, ', ' ORDER BY year::text) as años FROM medallas_olimpicas GROUP BY city HAVING COUNT(DISTINCT year) > 1
      * "ciudades anfitrionas" → SELECT DISTINCT city, year FROM medallas_olimpicas ORDER BY year
      * "cuántas veces una ciudad específica" → WHERE city ILIKE '%ciudad%' GROUP BY city, year

Responde solo con la consulta SQL, sin agregar nada más."""

    try:
        print("🔄 Enviando request a Anthropic...")
        
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
        
        print("✅ Respuesta recibida de Anthropic")
        sql_query = message.content[0].text.strip()
        print(f"SQL generado: {sql_query}")
        
        # Limpiar la respuesta en caso de que incluya texto extra
        if "```sql" in sql_query:
            sql_query = sql_query.split("```sql")[1].split("```")[0].strip()
        elif "```" in sql_query:
            sql_query = sql_query.split("```")[1].strip()
            
        return sql_query
        
    except anthropic.APIError as e:
        print(f"❌ Error de API de Anthropic: {e}")
        print(f"Tipo de error: {type(e)}")
        print(f"Código de estado: {getattr(e, 'status_code', 'N/A')}")
        raise Exception(f"Error de API de Anthropic: {str(e)}")
    except anthropic.AuthenticationError as e:
        print(f"❌ Error de autenticación Anthropic: {e}")
        print("🔍 Verificar API key...")
        raise Exception(f"Error de autenticación Anthropic: {str(e)}")
    except Exception as e:
        print(f"❌ Error general al llamar Anthropic: {e}")
        print(f"Tipo de error: {type(e)}")
        logger.error(f"Error al generar SQL con Claude: {e}")
        raise Exception(f"Error al generar consulta SQL: {str(e)}")

def ejecutar_sql(db: Session, sql_query: str) -> List[Dict]:
    """
    Ejecutar consulta SQL en PostgreSQL con manejo de errores y rollback
    """
    try:
        # Iniciar transacción
        logger.info(f"Ejecutando SQL: {sql_query}")
        
        result = db.execute(text(sql_query))
        
        # Convertir resultado a lista de diccionarios
        columns = result.keys()
        rows = result.fetchall()
        
        resultados = []
        for row in rows:
            row_dict = {}
            for i, column in enumerate(columns):
                value = row[i]
                # Convertir tipos especiales para JSON serialization
                if value is None:
                    row_dict[column] = None
                elif isinstance(value, Decimal):
                    # Fix: Convert Decimal to float for JSON serialization
                    row_dict[column] = float(value)
                elif isinstance(value, (datetime.datetime, datetime.date)):
                    # Convert datetime objects to ISO format string
                    row_dict[column] = value.isoformat()
                elif hasattr(value, 'isoformat'):  # Other datetime-like objects
                    row_dict[column] = value.isoformat()
                else:
                    row_dict[column] = value
            resultados.append(row_dict)
            
        logger.info(f"SQL ejecutado exitosamente. Resultados: {len(resultados)} filas")
        return resultados
        
    except Exception as e:
        # Rollback automático en caso de error
        try:
            db.rollback()
            logger.info("Rollback ejecutado correctamente")
        except Exception as rollback_error:
            logger.error(f"Error en rollback: {rollback_error}")
        
        # Clasificar tipos de errores para mejor manejo
        error_message = str(e).lower()
        
        if "invalidcolumnreference" in error_message or "order by expressions must appear" in error_message:
            logger.error(f"Error de sintaxis PostgreSQL en STRING_AGG/DISTINCT: {e}")
            raise Exception("Error de sintaxis SQL: Las expresiones ORDER BY en agregaciones con DISTINCT deben aparecer en la lista de argumentos")
        elif "syntax error" in error_message:
            logger.error(f"Error de sintaxis SQL: {e}")
            raise Exception(f"Error de sintaxis en la consulta SQL: {str(e)}")
        elif "column" in error_message and "does not exist" in error_message:
            logger.error(f"Error de columna inexistente: {e}")
            raise Exception(f"Error: Columna inexistente en la consulta: {str(e)}")
        else:
            logger.error(f"Error general al ejecutar SQL: {e}")
            raise Exception(f"Error en la consulta: {str(e)}")

def generar_respuesta_final(resultados_sql: List[Dict], pregunta: str, prompt_contexto: str, historial_conversacion: List[Dict] = None) -> str:
    """
    Generar respuesta natural usando Claude (basado en ejemploProfe.py)
    """
    print(f"\n🤖 === GENERANDO RESPUESTA FINAL ===")
    
    # Construir contexto de conversación si existe
    contexto_conversacion = ""
    if historial_conversacion and len(historial_conversacion) > 0:
        contexto_conversacion = "\n\nCONTEXTO DE CONVERSACIÓN PREVIA:\n"
        for mensaje in historial_conversacion:
            if mensaje["rol"] == "user":
                contexto_conversacion += f"Usuario preguntó: \"{mensaje['contenido']}\"\n"
            elif mensaje["rol"] == "assistant":
                # Truncar solo si es extremadamente largo, pero preservar más contexto
                contenido_assistant = mensaje['contenido']
                if len(contenido_assistant) > 800:
                    contenido_assistant = contenido_assistant[:800] + "..."
                contexto_conversacion += f"Asistente respondió: \"{contenido_assistant}\"\n"
        contexto_conversacion += "\nFIN DEL CONTEXTO PREVIO\n"
    
    prompt = f"""{prompt_contexto}

{contexto_conversacion}

Dada la siguiente pregunta:
"{pregunta}"

Y los siguientes resultados de la consulta SQL:
{json.dumps(resultados_sql, indent=2, ensure_ascii=False, default=safe_json_serializer)}

Genera una respuesta en lenguaje natural, entendible para un usuario interesado en datos olímpicos con las siguientes reglas:

1. Responde directamente sin hacer mención a SQL u otros términos técnicos.
1.1. IMPORTANTE: Si hay contexto de conversación previa, refiérete a él de manera natural cuando sea relevante (ej: "Como mencionamos antes sobre Chile...", "Siguiendo con el tema anterior...").
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
        print("🔄 Generando respuesta natural...")
        
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
        
        print("✅ Respuesta natural generada")
        return message.content[0].text.strip()
        
    except Exception as e:
        logger.error(f"Error al generar respuesta con Claude: {e}")
        raise Exception(f"Error al generar respuesta: {str(e)}")

def procesar_consulta_chat(
    db: Session, 
    usuario: Usuario, 
    pregunta: str,
    historial_conversacion: List[Dict] = None,
    contexto: str = "deportivo"
) -> Dict[str, Any]:
    """
    Función principal para procesar consulta del chat (Criterios A + D + E + F)
    """
    try:
        print(f"\n🎯 === PROCESANDO CONSULTA ===")
        print(f"Usuario: {usuario.username}")
        print(f"Pregunta: {pregunta}")
        
        # 1. Obtener configuración de prompt por contexto (Criterio F)
        prompt_contexto = obtener_prompt_contexto(db, contexto)
        
        # 2. Obtener términos excluidos del usuario (Criterio E)
        terminos_excluidos = obtener_terminos_excluidos(db, usuario)
        print(f"\n🔒 === DEBUG TÉRMINOS EXCLUIDOS ===")
        print(f"Usuario ID: {usuario.id}")
        print(f"Usuario: {usuario.username}")
        print(f"Términos excluidos obtenidos: {terminos_excluidos}")
        print(f"Cantidad de términos: {len(terminos_excluidos)}")
        print("=====================================\n")
        
        # 3. Los términos excluidos ahora se manejan directamente en la generación de SQL
        # No es necesario filtrar la pregunta previamente
        print(f"📝 Pregunta original: '{pregunta}'")
        print(f"🎯 Términos excluidos se integrarán en SQL: {terminos_excluidos}")
        
        # 4. Generar SQL con Claude (Criterio A + D) - incluyendo historial para contexto y términos excluidos
        sql_query = obtener_consulta_sql(pregunta, prompt_contexto, historial_conversacion, terminos_excluidos)
        
        # 5. Ejecutar SQL (Criterio D)
        resultados_sql = ejecutar_sql(db, sql_query)
        print(f"\n📊 === DEBUG RESULTADOS SQL ===")
        print(f"Resultados SQL sin filtrar: {len(resultados_sql)} filas")
        if resultados_sql:
            print(f"Primera fila de ejemplo: {resultados_sql[0]}")
            # Buscar específicamente Brazil/Brasil en los resultados
            brasil_found = []
            for i, fila in enumerate(resultados_sql[:10]):  # Solo primeras 10 filas
                for key, value in fila.items():
                    if value and 'brazil' in str(value).lower():
                        brasil_found.append(f"Fila {i}, columna '{key}': {value}")
            if brasil_found:
                print(f"🚨 BRAZIL ENCONTRADO EN RESULTADOS SQL:")
                for found in brasil_found:
                    print(f"  - {found}")
        print("===============================\n")
        
        # 6. Los términos excluidos ahora se manejan directamente en la generación de SQL
        # No es necesario filtrar post-SQL ya que el AI genera SQL con exclusiones integradas
        print(f"\n✅ === FILTRADO INTEGRADO EN SQL ===")
        print(f"Términos excluidos manejados por AI en SQL: {terminos_excluidos}")
        print(f"Resultados SQL ya filtrados: {len(resultados_sql)}")
        print("=====================================\n")
        
        # 7. Generar respuesta natural con Claude (Criterio A) - incluyendo historial para contexto
        respuesta_final = generar_respuesta_final(resultados_sql, pregunta, prompt_contexto, historial_conversacion)
        
        # 8. Preparar datos de contexto para modal (Criterio G)
        datos_contexto = {
            "total_resultados": len(resultados_sql),
            "muestra_datos": resultados_sql[:5] if resultados_sql else [],
            "sql_ejecutado": sql_query,
            "terminos_excluidos_aplicados": len(terminos_excluidos) if terminos_excluidos else 0
        }
        
        print("✅ Consulta procesada exitosamente")
        
        return {
            "respuesta": respuesta_final,
            "consulta_sql": sql_query,
            "datos_contexto": datos_contexto,
            "error": False
        }
        
    except Exception as e:
        logger.error(f"Error en procesamiento de chat: {e}")
        print(f"❌ Error en procesamiento: {e}")
        return {
            "respuesta": f"Ocurrió un error al procesar tu consulta: {str(e)}",
            "consulta_sql": None,
            "datos_contexto": None,
            "error": True
        }