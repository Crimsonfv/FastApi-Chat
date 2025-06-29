import anthropic
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import json
from decimal import Decimal
import datetime
import uuid
import re

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

# Lista de patrones de consultas sensibles que deben ser rechazadas
PATRONES_CONSULTAS_SENSIBLES = [
    # Consultas sobre usuarios y passwords (más precisas)
    r'\b(user|usuario|users|usuarios|registered)\b.*(password|contraseña|pass|pwd|email|mail)',
    r'\b(password|contraseña|pass|pwd)\b.*(user|usuario|users|usuarios)',
    r'\b(show|list|dame|mostrar)\b.*(user|usuario|users|usuarios).*(password|email)',
    r'\b(registered|registrados?)\b.*\b(user|usuario|users|usuarios)\b',
    r'\b(login|sesion|session|auth)\b.*\b(data|datos|info|información)\b',
    
    # Consultas sobre estructura de base de datos
    r'\b(show|mostrar|ver|listar|dame|display|list|what)\b.*(table|tabla|tables|tablas|database|base)',
    r'\b(all|todas?)\b.*(table|tabla|tables|tablas)',
    r'\b(what|que|cuales?|which)\b.*\b(table|tabla|tables|tablas)\b.*\b(database|base|db)\b',
    r'\b(describe|desc|structure|estructura)\b.*\b(table|tabla|database|base)\b',
    # Consultas sobre columnas de la base de datos
    r'\b(what|que|cuales?|which)\b.*(column|columna|columns|columnas|field|campo|fields|campos)\b',
    r'\b(show|mostrar|ver|listar|dame|display|list)\b.*(column|columna|columns|columnas|field|campo|fields|campos)',
    r'\b(column|columna|columns|columnas)\b.*(database|base|table|tabla)',
    r'\b(structure|estructura|schema|esquema)\b.*(column|columna|table|tabla)',
    # Metadatos del sistema
    r'\bschema\b',
    r'\binformation_schema\b',
    r'\bpg_tables\b',
    r'\bpg_catalog\b',
    
    # Consultas sobre configuración del sistema
    r'\b(config|configuracion|configuration|settings|ajustes)\b',
    r'\b(admin|administrator|administrador)\b.*\b(data|datos|info|información)\b',
    r'\b(system|sistema)\b.*\b(info|información|data|datos)\b',
    
    # Consultas DDL/DML peligrosas
    r'\b(drop|delete|update|insert|create|alter|truncate)\b',
    r'\b(grant|revoke|permissions|permisos)\b',
    
    # Consultas sobre conversaciones y mensajes privados (más específicos)
    r'\b(conversaciones?|conversations?|message|mensaje|messages|mensajes|chat)\b.*\b(other users?|otros usuarios?|all users?|todos los usuarios|private|privados?)\b',
    r'\b(show|mostrar|ver|listar)\b.*\b(chat|conversaciones?|mensajes?)\b.*\b(user|usuario|private|privado)\b',
]

# Lista de nombres de tablas públicas permitidas
TABLAS_PUBLICAS_PERMITIDAS = [
    'medallas_olimpicas'
]

def es_consulta_deportiva_valida(pregunta: str) -> bool:
    """
    Detecta si una pregunta es una consulta válida sobre deportes/género que podría ser 
    incorrectamente bloqueada por los filtros de seguridad.
    """
    pregunta_lower = pregunta.lower()
    
    # Patrones que indican consultas deportivas legítimas sobre género
    patrones_deportivos_genero = [
        r'\b(deportes?|sport|sports)\b.*\b(mujeres|hombres|women|men|femenino|masculino|female|male|género|genero|gender)\b',
        r'\b(mujeres|hombres|women|men|femenino|masculino|female|male)\b.*\b(deportes?|sport|sports|medallas?|medals?)\b',
        r'\b(más medallas|more medals|mejores?|better)\b.*\b(mujeres|hombres|women|men)\b',
        r'\b(mujeres|women)\b.*\b(más|more|mejor|better)\b.*\b(hombres|men)\b',
        r'\b(hombres|men)\b.*\b(más|more|mejor|better)\b.*\b(mujeres|women)\b',
        r'\b(comparar|compare|diferencia|difference)\b.*\b(género|genero|gender|sexo)\b',
        r'\b(participación|participation)\b.*\b(género|genero|gender|mujeres|hombres|women|men)\b'
    ]
    
    for patron in patrones_deportivos_genero:
        if re.search(patron, pregunta_lower):
            print(f"✅ Consulta deportiva válida detectada (patrón: {patron})")
            return True
    
    return False

def detectar_consulta_sensible(pregunta: str) -> tuple[bool, str]:
    """
    Detecta si una consulta contiene patrones sensibles que deben ser rechazados.
    Retorna (es_sensible, mensaje_rechazo)
    """
    pregunta_lower = pregunta.lower()
    
    # PRIMERO: Verificar si es una consulta deportiva válida que debe ser permitida
    if es_consulta_deportiva_valida(pregunta):
        print(f"✅ Permitiendo consulta deportiva válida: {pregunta}")
        return False, ""
    
    # SEGUNDO: Verificar cada patrón sensible
    for patron in PATRONES_CONSULTAS_SENSIBLES:
        if re.search(patron, pregunta_lower, re.IGNORECASE):
            print(f"🚫 Consulta sensible detectada. Patrón: {patron}")
            print(f"🚫 Pregunta: {pregunta}")
            
            # Generar mensaje de rechazo apropiado según el tipo de consulta
            if re.search(r'\b(user|usuario|users|usuarios)\b.*\b(password|contraseña|pass|pwd|email|mail)\b', pregunta_lower):
                return True, "Lo siento, no puedo proporcionar información sobre usuarios registrados, contraseñas o datos de autenticación por motivos de seguridad."
            
            elif re.search(r'\b(table|tabla|tables|tablas|database|base|schema|column|columna|columns|columnas|field|campo|fields|campos|structure|estructura)\b', pregunta_lower):
                return True, "Solo puedo proporcionar información sobre los datos olímpicos disponibles en la tabla de medallistas. No tengo acceso a información sobre la estructura de la base de datos o sus columnas."
            
            elif re.search(r'\b(config|configuracion|admin|administrator|administrador|system|sistema)\b', pregunta_lower):
                return True, "No tengo acceso a información del sistema, configuración o datos administrativos. Solo puedo ayudarte con consultas sobre datos olímpicos."
            
            elif re.search(r'\b(conversaciones?|conversations?|message|mensaje|messages|mensajes|chat)\b', pregunta_lower):
                return True, "No puedo acceder a conversaciones o mensajes de otros usuarios por motivos de privacidad. Solo puedo ayudarte con datos olímpicos públicos."
            
            else:
                return True, "Lo siento, no puedo procesar esa consulta. Solo puedo ayudarte con información sobre medallistas olímpicos, países, deportes y estadísticas relacionadas con los Juegos Olímpicos de 1976-2008."
    
    return False, ""

def validar_respuesta_estructura_db(pregunta: str) -> tuple[bool, str]:
    """
    Detecta consultas sobre estructura de DB y proporciona respuesta controlada.
    """
    pregunta_lower = pregunta.lower()
    
    # Patrones específicos sobre tablas/estructura
    patrones_estructura = [
        r'\b(what|que|cuales?|which)\b.*\b(table|tabla|tables|tablas)\b',
        r'\b(show|mostrar|ver|listar)\b.*\b(table|tabla|tables|tablas)\b',
        r'\b(database|base)\b.*\b(structure|estructura|schema|esquema)\b'
    ]
    
    for patron in patrones_estructura:
        if re.search(patron, pregunta_lower):
            print(f"🔍 Consulta sobre estructura de DB detectada")
            mensaje_publico = """Tengo acceso únicamente a la tabla de medallistas olímpicos (medallas_olimpicas) que contiene información sobre:

- Medallistas de los Juegos Olímpicos de Verano 1976-2008
- Países participantes y sus códigos
- Deportes, disciplinas y eventos
- Tipos de medallas (oro, plata, bronce)
- Ciudades anfitrionas de las olimpiadas
- Género de atletas y eventos

¿Te gustaría consultar algún dato específico sobre medallistas olímpicos?"""
            
            return True, mensaje_publico
    
    return False, ""

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
    
    CONTEXTO HISTÓRICO CRÍTICO:
    - 1976-1988: Alemania estaba dividida en DOS países independientes:
      * Alemania Occidental ("West Germany") 
      * Alemania Oriental ("East Germany")
    - 1992-2008: Alemania reunificada compite como un solo país ("Germany")
    - NUNCA confundas "East Germany" (1976-1988) con "Germany" (1992-2008)
    
    Proporciona respuestas precisas y profesionales. Puedes responder sobre:
    - Ciudades que han organizado múltiples Juegos Olímpicos
    - Medallistas y sus logros
    - Estadísticas por países, deportes y años
    - Análisis comparativos entre olimpiadas, especialmente casos históricos como las dos Alemanias
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
    
    resultado = [termino.termino for termino in terminos]
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

INSTRUCCIONES CRÍTICAS PARA FILTRADO INTELIGENTE:
- DEBES excluir automáticamente de los resultados SQL cualquier fila que contenga estos términos excluidos
- Los términos pueden estar en español, pero la base de datos está en inglés con formato capitalizado
- DEBES reconocer automáticamente y traducir/adaptar los términos al formato real de la base de datos:

EJEMPLOS CRÍTICOS DE TRADUCCIONES QUE DEBES APLICAR OBLIGATORIAMENTE:

PAÍSES (español → inglés de la BD):
- "estados unidos" / "eeuu" / "usa" → "United States" (también "USA", "US")
- "brasil" → "Brazil" 
- "rusia" → "Russia" (también "Soviet Union" para datos históricos)
- "china" → "China"
- "alemania" → "Germany"
- "reino unido" / "gran bretaña" → "Great Britain"

GÉNEROS (español → inglés de la BD):
- "masculino" / "hombre" / "hombres" → "Men" (campo gender) y "M" (campo event_gender)
- "femenino" / "mujer" / "mujeres" → "Women" (campo gender) y "W" (campo event_gender)

DEPORTES (español → inglés de la BD):
- "natación" → "Aquatics" (también "Swimming")
- "atletismo" → "Athletics"
- "gimnasia" → "Gymnastics"

CIUDADES (español → inglés de la BD):
- "atenas" → "Athens"
- "pekín" / "pekin" → "Beijing"
- "moscú" / "moscu" → "Moscow"

⚠️ CRÍTICO: NO uses NUNCA los términos originales en español en el SQL.
✅ CORRECTO: WHERE gender NOT ILIKE '%Men%'
❌ INCORRECTO: WHERE gender NOT ILIKE '%masculino%'

⚠️ OBLIGATORIO: SIEMPRE traduce los términos excluidos a los valores EXACTOS de la base de datos antes de usarlos en WHERE.

REGLAS DE APLICACIÓN:
1. Analiza cada término excluido e identifica si es un país, género, deporte, ciudad o atleta
2. Traduce automáticamente del español al inglés según corresponda
3. Aplica las exclusiones a los campos relevantes de la base de datos:
   * Para países: country, country_code
   * Para géneros: gender, event_gender  
   * Para deportes: sport, discipline
   * Para ciudades: city
   * Para atletas: athlete, nombre, apellido, nombre_completo
4. Usa condiciones WHERE con NOT ILIKE para excluir estos términos
5. Para múltiples términos excluidos, usa AND para combinar todas las exclusiones
6. Considera variantes y sinónimos del mismo concepto
7. Ejemplo: Si el usuario excluye "estados unidos", el SQL debe incluir: 
   WHERE country NOT ILIKE '%United States%' AND country NOT ILIKE '%USA%' AND country NOT ILIKE '%US%'

"""
    
    prompt = f"""{prompt_contexto}

Dada la siguiente estructura de tabla:
{ESTRUCTURA_TABLA_OLIMPICA}
{contexto_conversacion}{seccion_terminos_excluidos}
Y la siguiente consulta en lenguaje natural:
"{pregunta}"

Genera una consulta SQL para PostgreSQL que responda la pregunta del usuario. Sigue estas pautas:

RESTRICCIONES DE SEGURIDAD CRÍTICAS:
- SOLO accede a la tabla medallas_olimpicas
- NO generes consultas sobre otras tablas del sistema
- NO uses information_schema, pg_tables, pg_catalog u otras tablas del sistema
- NO generes DDL (CREATE, DROP, ALTER) o DML (INSERT, UPDATE, DELETE)
- Si la pregunta solicita información no disponible en medallas_olimpicas, responde que esa información no está disponible

RESTRICCIÓN TEMPORAL CRÍTICA:
- Los datos cubren EXCLUSIVAMENTE el período 1976-2008 (9 ediciones olímpicas)
- NUNCA uses conocimiento externo de olimpiadas anteriores a 1976 o posteriores a 2008
- Si una consulta no tiene resultados, acepta que es correcto para este período limitado
- NO inventes ni asumas datos de otros períodos históricos

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
    - CRÍTICO: Los datos cubren SOLO 1976-2008 (9 ediciones) donde NINGUNA ciudad se repitió como sede
    - Ciudades del período: Montreal (1976), Moscow (1980), Los Angeles (1984), Seoul (1988), Barcelona (1992), Atlanta (1996), Sydney (2000), Athens (2004), Beijing (2008)
    - Para encontrar ciudades repetidas: GROUP BY city HAVING COUNT(DISTINCT year) > 1 (resultará VACÍO para este período)
    - IMPORTANTE: Si el resultado es vacío, NO inventes datos de otros períodos históricos
    - Para listar todas las ediciones: incluye year y city en los resultados
    - Si el usuario pregunta por ciudades repetidas, explica que en el período 1976-2008 no hay repeticiones
    - Ejemplos de consultas típicas de ciudades:
      * "ciudades que se repiten" → SELECT city, COUNT(DISTINCT year) as veces, STRING_AGG(DISTINCT year::text, ', ' ORDER BY year::text) as años FROM medallas_olimpicas GROUP BY city HAVING COUNT(DISTINCT year) > 1
      * "ciudades anfitrionas" → SELECT DISTINCT city, year FROM medallas_olimpicas ORDER BY year
      * "cuántas veces una ciudad específica" → WHERE city ILIKE '%ciudad%' GROUP BY city, year
    - Si no hay resultados para ciudades repetidas, es correcto: cada ciudad fue sede una sola vez en este período
    - NUNCA menciones años anteriores a 1976 o posteriores a 2008

ESPECIAL - CONSULTAS SOBRE DEPORTES Y PAÍSES:
18. Para consultas sobre países que ganaron medallas en deportes específicos:
    - Para natación/swimming: usar WHERE sport ILIKE '%Aquatics%' OR sport ILIKE '%Swimming%'
    - Para atletismo: WHERE sport ILIKE '%Athletics%'
    - Para gymnastia: WHERE sport ILIKE '%Gymnastics%'
    - Asegúrate de incluir GROUP BY country cuando pregunten por países
    - Ejemplo: "países con medallas de oro en natación" → SELECT country, COUNT(*) as gold_medals FROM medallas_olimpicas WHERE sport ILIKE '%Aquatics%' AND medal = 'Gold' GROUP BY country ORDER BY gold_medals DESC
    - SIEMPRE incluir WHERE clauses apropiadas para el deporte mencionado
    
19. Para consultas de género/participación:
    - Usa gender = 'Men' y gender = 'Women' (no 'Male'/'Female')
    - Para análisis temporales incluye year en GROUP BY
    - Para comparaciones por país incluye country en SELECT y GROUP BY

CRÍTICO - CONSULTAS DE MÁXIMOS POR GÉNERO:
19.1. Para preguntas sobre "máximo medallista masculino Y femenino" o similares:
    - NUNCA uses una sola consulta con LIMIT para ambos géneros
    - Debes generar consultas SEPARADAS usando UNION o CTEs (Common Table Expressions)
    - Ejemplo correcto para "máximo medallista de cada género":
    
    WITH ranked_athletes AS (
        SELECT 
            athlete, nombre_completo, gender, country,
            COUNT(*) as total_medallas,
            COUNT(CASE WHEN medal = 'Gold' THEN 1 END) as medallas_oro,
            STRING_AGG(DISTINCT sport, ', ' ORDER BY sport) as deportes,
            ROW_NUMBER() OVER (PARTITION BY gender ORDER BY COUNT(*) DESC) as rank_in_gender
        FROM medallas_olimpicas 
        WHERE gender IN ('Men', 'Women')
        GROUP BY athlete, nombre_completo, gender, country
    )
    SELECT * FROM ranked_athletes WHERE rank_in_gender = 1 ORDER BY gender;

19.2. Para consultas comparativas por género:
    - Usa PARTITION BY gender para obtener rankings dentro de cada género
    - Para "mejores de cada género": ROW_NUMBER() OVER (PARTITION BY gender ORDER BY criterio DESC)
    - Para "comparar hombres vs mujeres": usa CASE statements o subconsultas separadas
    - SIEMPRE asegúrate de obtener representación de ambos géneros cuando sea solicitado

19.3. Patrones de preguntas que requieren consultas separadas por categoría:
    - "máximo/mejor de cada..." → ROW_NUMBER() OVER (PARTITION BY categoria)
    - "quien es el... masculino y femenino" → separar por gender
    - "mejores de cada país/deporte/año" → PARTITION BY según la categoría
    - "comparar entre..." → subconsultas o CTEs separadas
    - NUNCA uses solo LIMIT cuando necesites representación de múltiples categorías

CRÍTICO - CONTEXTO HISTÓRICO DE ALEMANIA (1976-2008):
20. IMPORTANTE: Durante el período de datos (1976-2008), Alemania tuvo diferentes configuraciones:
    - 1976-1988: Existían DOS países alemanes independientes:
      * "West Germany" (Alemania Occidental/Federal) - código GER o FRG
      * "East Germany" (Alemania Oriental/Democrática) - código GDR o DDR
    - 1992-2008: Alemania REUNIFICADA como un solo país:
      * "Germany" (Alemania unificada) - código GER
    - NO hubo competencia olímpica en 1990 (año de reunificación)
    
21. Para consultas sobre "Alemania Oriental vs Occidental":
    - Alemania Occidental: 1976, 1980, 1984, 1988 (como "West Germany")
    - Alemania Oriental: 1976, 1980, 1984, 1988 (como "East Germany") 
    - Alemania Reunificada: 1992, 1996, 2000, 2004, 2008 (como "Germany")
    - NUNCA confundir "East Germany" con "Germany" de períodos posteriores
    - Para comparar ambas, usar: WHERE country IN ('West Germany', 'East Germany')
    
22. Consultas SQL correctas para Alemania:
    - Alemania Occidental: WHERE country = 'West Germany' AND year BETWEEN 1976 AND 1988
    - Alemania Oriental: WHERE country = 'East Germany' AND year BETWEEN 1976 AND 1988  
    - Alemania Unificada: WHERE country = 'Germany' AND year >= 1992
    - Comparación histórica: usar CASE statements para agrupar períodos correctamente

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
        
        # Clasificar tipos de errores SQL y crear excepciones específicas
        error_message = str(e).lower()
        
        logger.error(f"Error SQL detallado: {e}")
        
        # Crear excepción personalizada para manejo específico de errores SQL
        if "invalidcolumnreference" in error_message or "order by expressions must appear" in error_message:
            logger.error(f"Error de sintaxis PostgreSQL en STRING_AGG/DISTINCT: {e}")
            raise SQLSyntaxError("Complex aggregation query requires restructuring")
        elif "syntax error" in error_message:
            logger.error(f"Error de sintaxis SQL: {e}")
            raise SQLSyntaxError("Invalid SQL syntax generated")
        elif "column" in error_message and "does not exist" in error_message:
            logger.error(f"Error de columna inexistente: {e}")
            raise SQLSyntaxError("Column reference error in query")
        elif "relation" in error_message and "does not exist" in error_message:
            logger.error(f"Error de tabla inexistente: {e}")
            raise SQLSyntaxError("Table reference error in query")
        else:
            logger.error(f"Error general al ejecutar SQL: {e}")
            raise SQLExecutionError(f"Database query execution failed: {str(e)}")


# Excepciones personalizadas para manejo específico de errores SQL
class SQLSyntaxError(Exception):
    """Raised when there are SQL syntax or structure issues"""
    pass

class SQLExecutionError(Exception):
    """Raised when there are SQL execution issues"""
    pass

def deberia_tener_resultados(pregunta: str) -> bool:
    """
    Determina si una pregunta debería normalmente tener resultados en los datos olímpicos.
    Usado para detectar casos donde una consulta válida devuelve resultados vacíos inesperadamente.
    """
    pregunta_lower = pregunta.lower()
    
    # Excepciones: consultas que pueden válidamente devolver resultados vacíos
    excepciones_sin_resultados = [
        # Consultas sobre ciudades repetidas (no hay en el período 1976-2008)
        r'\b(ciudades?|cities?|city)\b.*\b(repetidas?|múltiples?|multiples?|más de una|more than once|repeated?)\b',
        r'\b(sede|host|hosting)\b.*\b(más de una|multiple|several|varias?)\b.*\b(olimpiadas?|olympics?)\b',
        r'\b(qué|what|cuáles?|which)\b.*\b(ciudades?|cities?)\b.*\b(han sido sede|hosted?)\b.*\b(más de|multiple|varias?)\b',
    ]
    
    for excepcion in excepciones_sin_resultados:
        if re.search(excepcion, pregunta_lower):
            print(f"🚫 Pregunta '{pregunta}' puede válidamente no tener resultados (excepción: {excepcion})")
            return False
    
    # Patrones que indican consultas que normalmente deberían tener resultados
    patrones_con_resultados = [
        # Consultas sobre deportes populares
        r'\b(swimming|natación|natacion|aquatics)\b.*\b(countries|países|paises|country)\b',
        r'\b(countries|países|paises)\b.*\b(gold|oro|medals|medallas)\b',
        r'\b(usa|united states|estados unidos)\b.*\b(medals|medallas)\b',
        r'\b(athletes|atletas)\b.*\b(medals|medallas)\b',
        
        # Deportes que definitivamente existen en los datos
        r'\b(athletics|atletismo|gymnastics|gimnasia|swimming|natación)\b',
        
        # Países que definitivamente existen
        r'\b(usa|united states|china|russia|germany|australia|brazil|brasil)\b',
        
        # Consultas sobre medallas que deberían tener resultados
        r'\b(gold|silver|bronze|oro|plata|bronce)\b.*\b(medals|medallas)\b',
        
        # Consultas temporales sobre años que están en nuestros datos
        r'\b(1976|1980|1984|1988|1992|1996|2000|2004|2008)\b',
        
        # Consultas sobre ciudades anfitrionas (todas las ciudades)
        r'\b(ciudades?|cities?)\b.*\b(anfitrionas?|host|hosting|sede)\b',
    ]
    
    for patron in patrones_con_resultados:
        if re.search(patron, pregunta_lower):
            print(f"🎯 Pregunta '{pregunta}' debería tener resultados (patrón: {patron})")
            return True
    
    return False


def obtener_consulta_sql_simplificada(pregunta: str, prompt_contexto: str) -> str:
    """
    Generar una consulta SQL simplificada como fallback para casos de error.
    Se enfoca en consultas básicas sin agregaciones complejas.
    """
    print(f"\n🔄 === GENERANDO CONSULTA SQL SIMPLIFICADA ===")
    print(f"Pregunta: {pregunta}")
    
    if not client:
        raise Exception("Cliente de Anthropic no disponible")
    
    # Prompt simplificado que evita consultas complejas
    prompt_simplificado = f"""
{prompt_contexto}

IMPORTANTE: Genera SOLO consultas SQL simples sin:
- UNION con ORDER BY
- Agregaciones complejas con DISTINCT y ORDER BY
- Subconsultas complejas

Datos disponibles en la tabla medallas_olimpicas:
- city: ciudad olímpica
- year: año de los juegos  
- sport: deporte
- discipline: disciplina
- event: evento específico
- athlete: nombre del atleta
- gender: género del atleta
- country_code: código de país
- country: nombre del país
- medal: tipo de medalla (Gold, Silver, Bronze)

Pregunta del usuario: {pregunta}

Genera una consulta SQL simple y directa que responda la pregunta:
"""

    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=500,  # Reducido para consultas más simples
            messages=[{
                "role": "user", 
                "content": prompt_simplificado
            }]
        )
        
        sql_query = response.content[0].text.strip()
        print(f"✅ SQL simplificado generado: {sql_query}")
        return sql_query
        
    except Exception as e:
        logger.error(f"Error generando SQL simplificado: {e}")
        # Consulta por defecto muy básica
        return "SELECT DISTINCT country, COUNT(*) as total_medals FROM medallas_olimpicas WHERE medal = 'Gold' GROUP BY country ORDER BY total_medals DESC LIMIT 10;"


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

RESTRICCIONES CRÍTICAS - SOLO DATOS 1976-2008:
7.1. NUNCA menciones años fuera del rango 1976-2008:
    - NO menciones olimpiadas de 1972 o anteriores
    - NO menciones olimpiadas de 2012 o posteriores
    - NO inventes datos de años futuros (2024, 2028, etc.)
7.2. Si una consulta no tiene resultados en el período 1976-2008:
    - Explica claramente que los datos cubren SOLO 1976-2008
    - Menciona que podrían existir casos en otros períodos no incluidos
    - NUNCA inventes o asumas datos de otros períodos
7.3. Para ciudades repetidas específicamente:
    - En el período 1976-2008 NO hay ciudades que se repitan como sede
    - Las ciudades fueron: Montreal (1976), Moscow (1980), Los Angeles (1984), Seoul (1988), Barcelona (1992), Atlanta (1996), Sydney (2000), Athens (2004), Beijing (2008)
    - Cada ciudad fue sede UNA SOLA VEZ en este período
10. Entrega el resultado de manera precisa y estructurada.
11. Los resultados son para una conversación tipo chat, no saludes ni te despidas.
12. IMPORTANTE: Nunca menciones detalles técnicos de la consulta.
13. Si hay muchos resultados, resume los más relevantes y menciona el total.

ESPECIAL - RESPUESTAS POR GÉNERO/CATEGORÍA:
14. Si la pregunta solicita información de ambos géneros (ej: "máximo masculino y femenino"):
    - SIEMPRE presenta ambos géneros claramente separados
    - Usa encabezados como "Máximo Medallista Masculino:" y "Máximo Medallista Femenino:"
    - Si los datos solo contienen un género, menciona que falta el otro
    - NUNCA asumas que los primeros resultados representan ambos géneros
15. Para consultas comparativas por categorías:
    - Organiza la respuesta por categoría (país, deporte, género, año, etc.)
    - Usa formato estructurado para facilitar la comparación
    - Menciona explícitamente si alguna categoría no tiene datos disponibles

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
        
        # 0. VALIDACIÓN DE SEGURIDAD - Detectar consultas sensibles
        es_sensible, mensaje_rechazo = detectar_consulta_sensible(pregunta)
        if es_sensible:
            print(f"🚫 CONSULTA RECHAZADA: {pregunta}")
            return {
                "respuesta": mensaje_rechazo,
                "consulta_sql": None,
                "datos_contexto": None,
                "error": False,
                "rechazada": True
            }
        
        # 0.1. VALIDACIÓN ESPECIAL - Consultas sobre estructura de DB
        es_estructura, respuesta_estructura = validar_respuesta_estructura_db(pregunta)
        if es_estructura:
            print(f"🔍 RESPUESTA CONTROLADA DE ESTRUCTURA DE DB")
            return {
                "respuesta": respuesta_estructura,
                "consulta_sql": None,
                "datos_contexto": None,
                "error": False,
                "rechazada": False
            }
        
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
        
        # 5. Ejecutar SQL (Criterio D) con manejo de errores específicos
        try:
            resultados_sql = ejecutar_sql(db, sql_query)
        except SQLSyntaxError as sql_error:
            # Error de sintaxis SQL - intentar consulta simplificada como fallback
            logger.warning(f"Error de sintaxis SQL, intentando fallback: {sql_error}")
            print(f"⚠️ Error SQL, intentando consulta simplificada...")
            
            try:
                # Generar una consulta más simple como fallback
                sql_query_fallback = obtener_consulta_sql_simplificada(pregunta, prompt_contexto)
                print(f"🔄 Intentando consulta simplificada: {sql_query_fallback}")
                resultados_sql = ejecutar_sql(db, sql_query_fallback)
                sql_query = sql_query_fallback  # Usar la consulta fallback para los datos de contexto
            except Exception as fallback_error:
                logger.error(f"Fallback también falló: {fallback_error}")
                # Si el fallback también falla, devolver mensaje amigable
                return {
                    "respuesta": "Lo siento, tuve dificultades técnicas procesando tu consulta sobre los datos olímpicos. ¿Podrías reformularla de manera más simple? Por ejemplo, puedes preguntarme sobre medallas por país, deporte específico, o año.",
                    "consulta_sql": None,
                    "datos_contexto": None,
                    "error": False,
                    "fallback_used": True
                }
        except SQLExecutionError as exec_error:
            logger.error(f"Error de ejecución SQL: {exec_error}")
            return {
                "respuesta": "Encontré un problema al acceder a los datos olímpicos. Por favor, intenta con una consulta diferente o más específica.",
                "consulta_sql": None,
                "datos_contexto": None,
                "error": False,
                "fallback_used": True
            }
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
        
        # 6. Verificar si resultados vacíos cuando deberían tener datos (mejora de consistencia)
        if len(resultados_sql) == 0 and deberia_tener_resultados(pregunta):
            print(f"⚠️ === RESULTADOS VACÍOS INESPERADOS ===")
            print(f"La consulta '{pregunta}' debería tener resultados pero no los tiene.")
            print("Intentando consulta simplificada como fallback...")
            
            try:
                # Intentar consulta simplificada para obtener al menos algunos datos
                sql_query_fallback = obtener_consulta_sql_simplificada(pregunta, prompt_contexto)
                print(f"🔄 Intentando consulta fallback: {sql_query_fallback}")
                resultados_sql_fallback = ejecutar_sql(db, sql_query_fallback)
                
                if len(resultados_sql_fallback) > 0:
                    print(f"✅ Fallback exitoso: {len(resultados_sql_fallback)} resultados encontrados")
                    resultados_sql = resultados_sql_fallback
                    sql_query = sql_query_fallback
                else:
                    print("❌ Fallback también devolvió resultados vacíos")
            except Exception as fallback_error:
                print(f"❌ Error en fallback para resultados vacíos: {fallback_error}")
        
        # 7. Los términos excluidos ahora se manejan directamente en la generación de SQL
        # No es necesario filtrar post-SQL ya que el AI genera SQL con exclusiones integradas
        print(f"\n✅ === FILTRADO INTEGRADO EN SQL ===")
        print(f"Términos excluidos manejados por AI en SQL: {terminos_excluidos}")
        print(f"Resultados SQL ya filtrados: {len(resultados_sql)}")
        print("=====================================\n")
        
        # 8. Generar respuesta natural con Claude (Criterio A) - incluyendo historial para contexto
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
        
        # Proporcionar mensaje amigable sin exponer detalles técnicos
        mensaje_error = "Lo siento, tuve dificultades procesando tu consulta sobre los datos olímpicos. "
        
        # Detectar tipos específicos de consulta para sugerir alternativas
        pregunta_lower = pregunta.lower()
        if any(palabra in pregunta_lower for palabra in ["countries", "países", "paises", "country"]):
            mensaje_error += "¿Podrías preguntarme de forma más específica sobre un país en particular o un deporte específico?"
        elif any(palabra in pregunta_lower for palabra in ["swimming", "natación", "natacion"]):
            mensaje_error += "¿Podrías preguntarme sobre nadadores específicos o medallas de natación de un país en particular?"
        elif any(palabra in pregunta_lower for palabra in ["female", "male", "men", "women", "género", "genero"]):
            mensaje_error += "¿Podrías preguntarme de forma más específica sobre atletas masculinos o femeninos en un deporte particular?"
        else:
            mensaje_error += "¿Podrías reformular tu pregunta de manera más simple? Por ejemplo: '¿Qué países ganaron más medallas de oro?' o '¿Cuántas medallas ganó Estados Unidos en natación?'"
        
        return {
            "respuesta": mensaje_error,
            "consulta_sql": None,
            "datos_contexto": None,
            "error": False,  # No marcar como error técnico
            "fallback_used": True
        }