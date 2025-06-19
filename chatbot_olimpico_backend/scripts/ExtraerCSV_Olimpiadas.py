import os
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

# Configuración de la conexión a PostgreSQL
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'crimson',
    'password': 'Inacap.2025',
    'database': 'Evaluacion-3'
}

def cargar_datos_olimpicos():
    """Carga datos desde CSV de olimpiadas a las tablas en PostgreSQL"""
    conn = None
    cursor = None
    try:
        # Verificar que el archivo existe
        csv_path = 'Summer-Olympic-medals-1976-to-2008.csv'
        if not os.path.exists(csv_path):
            print(f"Error: No se encuentra el archivo {csv_path}")
            return False
            
        # Leer el archivo CSV con detección automática de formato
        try:
            print(f"Intentando cargar archivo CSV: {csv_path}")
            
            # Detectar encoding del archivo primero
            import chardet
            with open(csv_path, 'rb') as f:
                raw_data = f.read(10000)  # Leer primeros 10KB para detectar encoding
                encoding_info = chardet.detect(raw_data)
                encoding_detectado = encoding_info['encoding']
                confianza = encoding_info['confidence']
            
            print(f"Encoding detectado: {encoding_detectado} (confianza: {confianza:.2f})")
            
            # Lista de encodings a probar (empezando por el detectado)
            encodings_a_probar = [encoding_detectado, 'utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'utf-16']
            
            # Analizar las primeras líneas para detectar el separador
            primera_linea = None
            encoding_exitoso = None
            
            for encoding in encodings_a_probar:
                try:
                    with open(csv_path, 'r', encoding=encoding) as f:
                        primera_linea = f.readline().strip()
                        segunda_linea = f.readline().strip()
                    encoding_exitoso = encoding
                    break
                except UnicodeDecodeError:
                    continue
            
            if not primera_linea:
                print("❌ No se pudo leer las primeras líneas con ningún encoding")
                return False
            
            print(f"✅ Archivo leído con encoding: {encoding_exitoso}")
            print(f"Primera línea: {primera_linea}")
            
            # Detectar separador
            separadores = [',', ';', '\t', '|']
            separador_detectado = ','
            max_campos = 0
            
            for sep in separadores:
                campos = len(primera_linea.split(sep))
                if campos > max_campos:
                    max_campos = campos
                    separador_detectado = sep
            
            print(f"Separador detectado: '{separador_detectado}' ({max_campos} campos)")
            
            # Intentar leer el CSV completo
            try:
                df = pd.read_csv(csv_path, 
                               sep=separador_detectado, 
                               encoding=encoding_exitoso,
                               on_bad_lines='skip',
                               skipinitialspace=True,
                               quotechar='"',
                               escapechar='\\')
                print(f"✅ CSV leído exitosamente")
            except Exception as e:
                print(f"❌ Error al leer CSV: {e}")
                # Último intento con configuración más permisiva
                try:
                    df = pd.read_csv(csv_path, 
                                   sep=separador_detectado, 
                                   encoding=encoding_exitoso,
                                   on_bad_lines='skip',
                                   skipinitialspace=True,
                                   quoting=3,  # QUOTE_NONE
                                   engine='python')  # Motor Python más tolerante
                    print(f"✅ CSV leído con configuración permisiva")
                except Exception as e2:
                    print(f"❌ Error final: {e2}")
                    return False
                
        except ImportError:
            print("❌ Módulo 'chardet' no encontrado. Instalando...")
            print("Ejecuta: pip install chardet")
            return False
        except Exception as e:
            print(f"Error al leer archivo CSV: {e}")
            return False
            
        print(f"CSV leído correctamente. Columnas encontradas: {df.columns.tolist()}")
        print(f"Total de registros en el CSV: {len(df)}")
        
        # Mostrar un vistazo de los datos
        print("\nMuestra de datos del CSV:")
        print(df.head(3))
        
        # Conectar a PostgreSQL
        print("\nConectando a la base de datos PostgreSQL...")
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Crear tablas si no existen
        crear_tablas_olimpicas(cursor, conn)
        
        # Procesar y cargar datos en las tablas
        cargar_datos_en_tablas(cursor, conn, df)
        
        print("Datos cargados exitosamente a la base de datos")
        return True
            
    except Exception as e:
        print(f"Error al cargar datos: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def crear_tablas_olimpicas(cursor, conn):
    """Crea las tablas necesarias para el sistema olímpico"""
    print("Creando tablas para dataset olímpico...")
    
    # 1. Tabla principal de medallas olímpicas (datos del CSV)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS medallas_olimpicas (
        id SERIAL PRIMARY KEY,
        city VARCHAR(100) NOT NULL,
        year INTEGER NOT NULL,
        sport VARCHAR(100) NOT NULL,
        discipline VARCHAR(100) NOT NULL,
        event VARCHAR(200) NOT NULL,
        athlete VARCHAR(200) NOT NULL,  -- Original: "KÖHLER, Christa"
        nombre VARCHAR(100),            -- Procesado: "Christa"
        apellido VARCHAR(100),          -- Procesado: "Köhler"  
        nombre_completo VARCHAR(200),   -- Procesado: "Christa Köhler"
        gender VARCHAR(10) NOT NULL,
        country_code VARCHAR(10) NOT NULL,
        country VARCHAR(100) NOT NULL,
        event_gender VARCHAR(10) NOT NULL,
        medal VARCHAR(20) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Tabla de usuarios para autenticación (Criterio C)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        rol VARCHAR(20) NOT NULL DEFAULT 'user', -- 'user' o 'admin'
        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        activo BOOLEAN DEFAULT TRUE
    )
    """)
    
    # 3. Tabla para almacenar conversaciones (Criterio B)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversaciones (
        id SERIAL PRIMARY KEY,
        id_usuario INTEGER NOT NULL,
        titulo VARCHAR(200),
        fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_ultima_actividad TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        activa BOOLEAN DEFAULT TRUE,
        FOREIGN KEY (id_usuario) REFERENCES usuarios(id) ON DELETE CASCADE
    )
    """)

    # 4. Tabla para mensajes de conversaciones (Criterio B)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mensajes (
        id SERIAL PRIMARY KEY,
        id_conversacion INTEGER NOT NULL,
        rol VARCHAR(20) NOT NULL, -- 'user' o 'assistant'
        contenido TEXT NOT NULL,
        consulta_sql TEXT, -- Opcional, para guardar la SQL generada
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (id_conversacion) REFERENCES conversaciones(id) ON DELETE CASCADE
    )
    """)
    
    # 5. Tabla de términos excluidos por usuario (Criterio E)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS terminos_excluidos (
        id SERIAL PRIMARY KEY,
        id_usuario INTEGER NOT NULL,
        termino VARCHAR(100) NOT NULL,
        activo BOOLEAN DEFAULT TRUE,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (id_usuario) REFERENCES usuarios(id) ON DELETE CASCADE
    )
    """)
    
    # 6. Tabla de configuraciones de prompt para administradores (Criterio F)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configuraciones_prompt (
        id SERIAL PRIMARY KEY,
        contexto VARCHAR(100) NOT NULL, -- 'deportivo', 'paises', 'atletas', etc.
        prompt_sistema TEXT NOT NULL,
        creado_por INTEGER NOT NULL, -- Solo administradores
        fecha_modificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        activo BOOLEAN DEFAULT TRUE,
        FOREIGN KEY (creado_por) REFERENCES usuarios(id)
    )
    """)
    
    # Crear índices para mejorar rendimiento
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_medallas_year ON medallas_olimpicas(year)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_medallas_country ON medallas_olimpicas(country)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_medallas_sport ON medallas_olimpicas(sport)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_medallas_athlete ON medallas_olimpicas(athlete)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_medallas_nombre_completo ON medallas_olimpicas(nombre_completo)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_medallas_apellido ON medallas_olimpicas(apellido)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversaciones_usuario ON conversaciones(id_usuario)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mensajes_conversacion ON mensajes(id_conversacion)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_terminos_usuario ON terminos_excluidos(id_usuario)")
    
    conn.commit()
    print("Tablas creadas correctamente")

def procesar_nombre_atleta(nombre_original):
    """
    Procesa el nombre del atleta del formato 'APELLIDO, Nombre' a formato separado
    
    Input: 'KÖHLER, Christa'
    Output: {
        'nombre': 'Christa',
        'apellido': 'Köhler', 
        'nombre_completo': 'Christa Köhler'
    }
    """
    try:
        nombre_original = str(nombre_original).strip()
        
        if ',' in nombre_original:
            # Formato: "APELLIDO, Nombre"
            partes = nombre_original.split(',', 1)
            apellido_raw = partes[0].strip()
            nombre_raw = partes[1].strip() if len(partes) > 1 else ''
            
            # Normalizar formato: Title Case
            apellido = apellido_raw.title()
            nombre = nombre_raw.title()
            
            # Crear nombre completo en orden natural
            if nombre:
                nombre_completo = f"{nombre} {apellido}".strip()
            else:
                nombre_completo = apellido
                
        else:
            # Si no hay coma, asumir que es solo un nombre
            nombre_completo = nombre_original.title()
            partes_nombre = nombre_completo.split()
            
            if len(partes_nombre) >= 2:
                nombre = ' '.join(partes_nombre[:-1])
                apellido = partes_nombre[-1]
            else:
                nombre = partes_nombre[0] if partes_nombre else ''
                apellido = ''
            
            nombre_completo = nombre_original.title()
        
        return {
            'nombre': nombre,
            'apellido': apellido,
            'nombre_completo': nombre_completo
        }
        
    except Exception as e:
        # En caso de error, devolver valores por defecto
        return {
            'nombre': '',
            'apellido': '',
            'nombre_completo': str(nombre_original).title()
        }


def cargar_datos_en_tablas(cursor, conn, df):
    """Carga los datos del CSV en la tabla principal"""
    print("Procesando y cargando datos olímpicos...")
    
    # Limpiar datos y verificar columnas esperadas
    columnas_esperadas = ['City', 'Year', 'Sport', 'Discipline', 'Event', 
                         'Athlete', 'Gender', 'Country_Code', 'Country', 
                         'Event_gender', 'Medal']
    
    # Verificar que todas las columnas están presentes
    columnas_faltantes = [col for col in columnas_esperadas if col not in df.columns]
    if columnas_faltantes:
        print(f"Error: Faltan las columnas: {columnas_faltantes}")
        return False
    
    # Limpiar datos nulos
    df = df.dropna(subset=columnas_esperadas)
    
    registros_procesados = 0
    registros_insertados = 0
    total_registros = len(df)
    nombres_ejemplos = []
    
    print(f"Iniciando inserción de {total_registros} registros...")
    print("🔄 Procesando nombres de atletas (ejemplos):")
    
    for _, row in df.iterrows():
        try:
            registros_procesados += 1
            if registros_procesados % 500 == 0:
                print(f"Procesando registro {registros_procesados}/{total_registros}...")
            
            # Extraer datos de la fila
            city = str(row['City']).strip()
            year = int(row['Year'])
            sport = str(row['Sport']).strip()
            discipline = str(row['Discipline']).strip()
            event = str(row['Event']).strip()
            athlete_original = str(row['Athlete']).strip()
            gender = str(row['Gender']).strip()
            country_code = str(row['Country_Code']).strip()
            country = str(row['Country']).strip()
            event_gender = str(row['Event_gender']).strip()
            medal = str(row['Medal']).strip()
            
            # Procesar nombre del atleta
            nombre_procesado = procesar_nombre_atleta(athlete_original)
            nombre = nombre_procesado['nombre']
            apellido = nombre_procesado['apellido']
            nombre_completo = nombre_procesado['nombre_completo']
            
            # Mostrar ejemplos de procesamiento (primeros 5)
            if len(nombres_ejemplos) < 5:
                nombres_ejemplos.append(f"  '{athlete_original}' → '{nombre_completo}'")
                if len(nombres_ejemplos) == 5:
                    for ejemplo in nombres_ejemplos:
                        print(ejemplo)
            
            # Verificar datos obligatorios
            if not all([city, year, sport, discipline, event, athlete_original, 
                       gender, country_code, country, event_gender, medal]):
                continue
                
            # Insertar en tabla principal
            cursor.execute("""
                INSERT INTO medallas_olimpicas (
                    city, year, sport, discipline, event, athlete,
                    nombre, apellido, nombre_completo,
                    gender, country_code, country, event_gender, medal
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                city, year, sport, discipline, event, athlete_original,
                nombre, apellido, nombre_completo,
                gender, country_code, country, event_gender, medal
            ))
            
            registros_insertados += 1
            
            # Commit cada 500 registros para mejor rendimiento
            if registros_insertados % 500 == 0:
                conn.commit()
                
        except Exception as e:
            print(f"Error al procesar registro {registros_procesados}: {e}")
            continue
    
    # Commit final
    conn.commit()
    print(f"✅ Cargados exitosamente {registros_insertados} de {total_registros} registros")

def crear_usuario_admin_inicial(cursor, conn):
    """Crea un usuario administrador inicial si no existe"""
    try:
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'admin'")
        admin_count = cursor.fetchone()[0]
        
        if admin_count == 0:
            # Crear usuario admin inicial (en producción usa hash real)
            cursor.execute("""
                INSERT INTO usuarios (username, email, password_hash, rol)
                VALUES (%s, %s, %s, %s)
            """, ('admin', 'admin@olimpiadas.com', 'admin123_hash', 'admin'))
            
            conn.commit()
            print("✅ Usuario administrador inicial creado: admin/admin123_hash")
        else:
            print("ℹ️  Ya existe al menos un usuario administrador")
            
    except Exception as e:
        print(f"Error al crear usuario admin: {e}")

if __name__ == "__main__":
    print("🏅 Iniciando proceso de carga de datos olímpicos...")
    print("📋 Datos: Olimpiadas de Verano 1976-2008 (Solo medallistas)")
    
    # Cargar datos
    if cargar_datos_olimpicos():
        print("\n🎯 Proceso completado exitosamente")
        print("\n📊 Estructura creada:")
        print("  ✅ medallas_olimpicas - Datos principales del CSV")
        print("      - athlete: Nombre original ('KÖHLER, Christa')")
        print("      - nombre: Nombre procesado ('Christa')")
        print("      - apellido: Apellido procesado ('Köhler')")
        print("      - nombre_completo: Formato natural ('Christa Köhler')")
        print("  ✅ usuarios - Sistema de autenticación") 
        print("  ✅ conversaciones - Historial de chats")
        print("  ✅ mensajes - Mensajes individuales")
        print("  ✅ terminos_excluidos - Filtros por usuario")
        print("  ✅ configuraciones_prompt - Prompts de admin")
        
        # Crear admin inicial
        try:
            import psycopg2
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            crear_usuario_admin_inicial(cursor, conn)
            cursor.close()
            conn.close()
        except:
            pass
            
    else:
        print("❌ Error en el proceso de carga")