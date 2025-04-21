import os
import sqlite3
import pandas as pd
from sqlalchemy import create_engine, text
import psycopg2
from psycopg2 import sql
import datetime

# Verifica se estamos rodando no Railway
def is_railway():
    return os.environ.get('RAILWAY_ENVIRONMENT') is not None

# Função para obter conexão SQLAlchemy com o banco de dados
def get_db_engine():
    """Retorna um engine SQLAlchemy para o banco de dados (PostgreSQL no Railway, SQLite localmente)"""
    if is_railway():
        # Conecta ao PostgreSQL no Railway
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            engine = create_engine(database_url)
        else:
            # Fallback se DATABASE_URL não estiver disponível
            user = os.environ.get('PGUSER', 'postgres')
            password = os.environ.get('PGPASSWORD', '')
            host = os.environ.get('PGHOST', 'localhost')
            port = os.environ.get('PGPORT', '5432')
            database = os.environ.get('PGDATABASE', 'railway')
            engine = create_engine(f'postgresql://{user}:{password}@{host}:{port}/{database}')
    else:
        # Conecta ao SQLite local
        engine = create_engine('sqlite:///dropi_automation.db')
    
    return engine

# Função para obter conexão direta com o banco (para casos onde SQLAlchemy não é usado)
def get_db_connection():
    """Retorna uma conexão direta com o banco de dados (PostgreSQL no Railway, SQLite localmente)"""
    if is_railway():
        # Conecta ao PostgreSQL no Railway
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            conn = psycopg2.connect(database_url)
        else:
            # Fallback se DATABASE_URL não estiver disponível
            conn = psycopg2.connect(
                user=os.environ.get('PGUSER', 'postgres'),
                password=os.environ.get('PGPASSWORD', ''),
                host=os.environ.get('PGHOST', 'localhost'),
                port=os.environ.get('PGPORT', '5432'),
                database=os.environ.get('PGDATABASE', 'railway')
            )
    else:
        # Conecta ao SQLite local
        conn = sqlite3.connect('dropi_automation.db')
    
    return conn

# Inicializa o banco de dados
def init_database():
    """Inicializa o banco de dados (PostgreSQL ou SQLite)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Cria tabelas com sintaxe compatível com ambos os bancos
        if is_railway():
            # Tabelas para PostgreSQL
            
            # Verifica se a tabela já existe
            cursor.execute("""
                SELECT EXISTS (
                   SELECT FROM information_schema.tables 
                   WHERE table_name = 'execution_history'
                )
            """)
            table_exists = cursor.fetchone()[0]
            
            # Se a tabela não existe, cria
            if not table_exists:
                cursor.execute('''
                CREATE TABLE execution_history (
                    id SERIAL PRIMARY KEY,
                    execution_date TIMESTAMP,
                    country VARCHAR(50) NOT NULL,
                    total_processed INTEGER,
                    successful INTEGER,
                    failed INTEGER,
                    error_details TEXT,
                    execution_time REAL
                )
                ''')
            else:
                # Se a tabela já existe, verifica se precisa adicionar a coluna country
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_name = 'execution_history' AND column_name = 'country'
                    )
                """)
                column_exists = cursor.fetchone()[0]
                
                # Se a coluna não existe, adiciona
                if not column_exists:
                    cursor.execute('''
                    ALTER TABLE execution_history
                    ADD COLUMN country VARCHAR(50) DEFAULT 'unknown' NOT NULL
                    ''')
            
            # Tabela de configuração
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule_config (
                id INTEGER PRIMARY KEY,
                is_enabled BOOLEAN,
                interval_hours INTEGER,
                start_time TEXT,
                end_time TEXT,
                last_run TIMESTAMP
            )
            ''')
            
            # Verifica se já existe configuração, se não, cria uma padrão
            cursor.execute("SELECT COUNT(*) FROM schedule_config")
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                INSERT INTO schedule_config (id, is_enabled, interval_hours, start_time, end_time, last_run)
                VALUES (1, false, 6, '08:00', '20:00', NULL)
                ''')
        else:
            # Tabelas para SQLite
            
            # Verificar se a tabela execution_history existe
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='execution_history';
            """)
            table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                # Criar tabela com campo country
                cursor.execute('''
                CREATE TABLE execution_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_date TEXT,
                    country TEXT NOT NULL,
                    total_processed INTEGER,
                    successful INTEGER,
                    failed INTEGER,
                    error_details TEXT,
                    execution_time REAL
                )
                ''')
            else:
                # Verificar se a coluna country existe
                try:
                    cursor.execute('SELECT country FROM execution_history LIMIT 1')
                except sqlite3.OperationalError:
                    # A coluna não existe, adiciona
                    cursor.execute('ALTER TABLE execution_history ADD COLUMN country TEXT DEFAULT "unknown" NOT NULL')
            
            # Tabela de configuração
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule_config (
                id INTEGER PRIMARY KEY,
                is_enabled INTEGER,
                interval_hours INTEGER,
                start_time TEXT,
                end_time TEXT,
                last_run TEXT
            )
            ''')
            
            # Verifica se já existe configuração, se não, cria uma padrão
            cursor.execute("SELECT COUNT(*) FROM schedule_config")
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                INSERT INTO schedule_config (is_enabled, interval_hours, start_time, end_time, last_run)
                VALUES (0, 6, '08:00', '20:00', NULL)
                ''')
        
        conn.commit()
    except Exception as e:
        print(f"Erro ao inicializar banco de dados: {str(e)}")
    finally:
        conn.close()

# Salva resultados da execução no banco de dados
def save_execution_results(results, country):
    """Salva os resultados de uma execução no banco de dados com o país"""
    try:
        # Usar SQLAlchemy para inserção de dados
        engine = get_db_engine()
        
        # Preparar dados para a inserção
        data = {
            "execution_date": results.get('execution_date', datetime.datetime.now()),
            "country": country,  # Novo campo para país
            "total_processed": results.get('total_processados', 0),
            "successful": results.get('total_processados', 0) - results.get('total_falhas', 0),
            "failed": results.get('total_falhas', 0),
            "error_details": results.get('error_details', ''),
            "execution_time": results.get('execution_time', 0)
        }
        
        # Criar consulta SQL
        query = """
            INSERT INTO execution_history 
            (execution_date, country, total_processed, successful, failed, error_details, execution_time)
            VALUES (:execution_date, :country, :total_processed, :successful, :failed, :error_details, :execution_time)
        """
        
        # Executar a inserção
        with engine.connect() as connection:
            connection.execute(text(query), data)
            connection.commit()
            
        return True
    except Exception as e:
        print(f"Erro ao salvar resultados da execução: {str(e)}")
        return False

# Carrega configuração de agendamento
def load_schedule_config():
    """Carrega a configuração de agendamento do banco de dados"""
    try:
        engine = get_db_engine()
        query = "SELECT is_enabled, interval_hours, start_time, end_time, last_run FROM schedule_config WHERE id = 1"
        
        with engine.connect() as connection:
            result = connection.execute(text(query)).fetchone()
        
        if result:
            return {
                "is_enabled": bool(result[0]),
                "interval_hours": result[1],
                "start_time": result[2],
                "end_time": result[3],
                "last_run": result[4]
            }
        return {
            "is_enabled": False,
            "interval_hours": 6,
            "start_time": "08:00",
            "end_time": "20:00",
            "last_run": None
        }
    except Exception as e:
        print(f"Erro ao carregar configuração de agendamento: {str(e)}")
        return {
            "is_enabled": False,
            "interval_hours": 6,
            "start_time": "08:00",
            "end_time": "20:00",
            "last_run": None
        }

# Salva configuração de agendamento
def save_schedule_config(config):
    """Salva a configuração de agendamento no banco de dados"""
    try:
        engine = get_db_engine()
        
        # Preparar dados para a atualização
        data = {
            "is_enabled": config["is_enabled"],
            "interval_hours": config["interval_hours"],
            "start_time": config["start_time"],
            "end_time": config["end_time"],
            "last_run": config.get("last_run")
        }
        
        # Criar consulta SQL
        query = """
            UPDATE schedule_config
            SET is_enabled = :is_enabled, 
                interval_hours = :interval_hours, 
                start_time = :start_time, 
                end_time = :end_time, 
                last_run = :last_run
            WHERE id = 1
        """
        
        # Executar a atualização
        with engine.connect() as connection:
            connection.execute(text(query), data)
            connection.commit()
            
        return True
    except Exception as e:
        print(f"Erro ao salvar configuração de agendamento: {str(e)}")
        return False

# Busca histórico de execuções, agora com filtro por país
def get_execution_history(start_date, end_date, country=None):
    """Busca o histórico de execuções dentro de um período, opcionalmente filtrado por país"""
    try:
        engine = get_db_engine()
        
        # Base da consulta SQL
        base_query = """
            SELECT execution_date, country, total_processed, successful, failed, execution_time
            FROM execution_history
            WHERE execution_date BETWEEN :start_date AND :end_date
        """
        
        # Adiciona filtro por país se especificado
        if country:
            base_query += " AND country = :country"
        
        # Adiciona ordenação
        base_query += " ORDER BY execution_date DESC"
        
        # Parâmetros da consulta
        params = {"start_date": start_date, "end_date": end_date}
        if country:
            params["country"] = country
        
        # Executar a consulta e carregar os resultados em um DataFrame
        df = pd.read_sql_query(sql=text(base_query), con=engine, params=params)
        
        return df
    except Exception as e:
        print(f"Erro ao buscar histórico de execuções: {str(e)}")
        # Retorna DataFrame vazio em caso de erro
        return pd.DataFrame(columns=['execution_date', 'country', 'total_processed', 'successful', 'failed', 'execution_time'])