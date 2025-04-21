# db.py (ou db_connection.py)
import os
import sqlite3
import psycopg2
from psycopg2 import sql
import pandas as pd
import logging # Adicionar import de logging

logger = logging.getLogger(__name__) # Configurar logger para este módulo

# Verifica se estamos rodando no Railway (presença da variável DATABASE_URL)
def is_railway():
    return os.environ.get('RAILWAY_ENVIRONMENT') is not None

# Função para obter conexão com o banco de dados apropriado
def get_db_connection():
    """Retorna uma conexão com o banco de dados (PostgreSQL no Railway, SQLite localmente)"""
    conn = None # Inicializa conn como None
    try:
        if is_railway():
            # Conecta ao PostgreSQL no Railway
            db_url = os.environ.get('DATABASE_URL')
            if not db_url:
                logger.error("Variável de ambiente DATABASE_URL não definida no Railway.")
                raise ValueError("DATABASE_URL não encontrada.")
            logger.info("Conectando ao PostgreSQL no Railway...")
            conn = psycopg2.connect(db_url)
            logger.info("Conexão PostgreSQL estabelecida.")
        else:
            # Conecta ao SQLite local
            db_path = 'dropi_automation.db'
            logger.info(f"Conectando ao SQLite local em: {db_path}")
            conn = sqlite3.connect(db_path)
            logger.info("Conexão SQLite estabelecida.")
        return conn
    except (psycopg2.Error, sqlite3.Error, ValueError, Exception) as e:
         logger.error(f"Erro ao obter conexão com o banco de dados: {e}", exc_info=True)
         # Se conn foi parcialmente estabelecido, tenta fechar
         if conn:
             try: conn.close()
             except: pass
         raise # Relança a exceção para que o chamador saiba que falhou

# Inicializa o banco de dados
def init_database():
    """Inicializa o banco de dados (PostgreSQL ou SQLite)"""
    conn = None # Inicializa conn
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info("Inicializando/Verificando tabelas do banco de dados...")

        # --- MODIFICADO: Adiciona a coluna source_country ---
        history_table_sql = '''
        CREATE TABLE IF NOT EXISTS execution_history (
            id {serial_pk},
            execution_date {timestamp_type},
            total_processed INTEGER,
            successful INTEGER,
            failed INTEGER,
            error_details TEXT,
            execution_time REAL,
            source_country TEXT  -- Nova coluna para identificar a origem
        )
        '''

        schedule_table_sql = '''
        CREATE TABLE IF NOT EXISTS schedule_config (
            id {integer_pk},
            is_enabled {boolean_type},
            interval_hours INTEGER,
            start_time TEXT,
            end_time TEXT,
            last_run {timestamp_type}
        )
        '''

        if is_railway():
            logger.debug("Usando tipos de dados PostgreSQL.")
            cursor.execute(history_table_sql.format(serial_pk="SERIAL PRIMARY KEY", timestamp_type="TIMESTAMP"))
            cursor.execute(schedule_table_sql.format(integer_pk="INTEGER PRIMARY KEY", boolean_type="BOOLEAN", timestamp_type="TIMESTAMP"))
            # Verifica se a coluna nova já existe (para evitar erro em execuções repetidas)
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='execution_history' AND column_name='source_country'
            """)
            if not cursor.fetchone():
                logger.info("Adicionando coluna 'source_country' à tabela 'execution_history' (PostgreSQL)...")
                cursor.execute("ALTER TABLE execution_history ADD COLUMN source_country TEXT")

            # Verifica config padrão
            cursor.execute("SELECT COUNT(*) FROM schedule_config WHERE id = 1")
            if cursor.fetchone()[0] == 0:
                logger.info("Inserindo configuração de agendamento padrão (PostgreSQL).")
                cursor.execute('''
                INSERT INTO schedule_config (id, is_enabled, interval_hours, start_time, end_time, last_run)
                VALUES (1, false, 6, '08:00', '20:00', NULL)
                ''')
        else:
            logger.debug("Usando tipos de dados SQLite.")
            # SQLite não tem boolean nativo, usa INTEGER 0/1
            # SQLite também não tem ALTER TABLE ADD COLUMN IF NOT EXISTS nativamente fácil
            cursor.execute(history_table_sql.format(serial_pk="INTEGER PRIMARY KEY AUTOINCREMENT", timestamp_type="TEXT"))
            cursor.execute(schedule_table_sql.format(integer_pk="INTEGER PRIMARY KEY", boolean_type="INTEGER", timestamp_type="TEXT"))

            # Tenta adicionar a coluna (ignora erro se já existir - abordagem comum no SQLite)
            try:
                logger.info("Tentando adicionar coluna 'source_country' à tabela 'execution_history' (SQLite)...")
                cursor.execute("ALTER TABLE execution_history ADD COLUMN source_country TEXT")
                logger.info("Coluna 'source_country' adicionada ou já existia.")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    logger.warning("Coluna 'source_country' já existe (SQLite).")
                else:
                    logger.error(f"Erro ao adicionar coluna no SQLite: {e}")
                    raise # Relança outros erros

            # Verifica config padrão
            cursor.execute("SELECT COUNT(*) FROM schedule_config WHERE id = 1") # SQLite usa id auto-incrementado, mas podemos forçar o ID 1
            if cursor.fetchone()[0] == 0:
                 logger.info("Inserindo configuração de agendamento padrão (SQLite).")
                 # Para garantir id=1, podemos usar INSERT OR IGNORE ou especificar o id se a tabela estiver vazia
                 cursor.execute('''
                 INSERT INTO schedule_config (id, is_enabled, interval_hours, start_time, end_time, last_run)
                 VALUES (1, 0, 6, '08:00', '20:00', NULL)
                 ''')


        conn.commit()
        logger.info("Inicialização/Verificação do banco de dados concluída.")
    except Exception as e:
        logger.error(f"Erro durante a inicialização do banco de dados: {e}", exc_info=True)
        # Tenta reverter se algo deu errado durante a transação
        if conn:
            try: conn.rollback()
            except: pass
    finally:
        # Garante que a conexão seja fechada
        if conn:
            conn.close()
            logger.debug("Conexão com DB fechada após init.")

# Salva resultados da execução no banco de dados
# --- MODIFICADO: Adiciona parâmetro source_country ---
def save_execution_results(results, source_country):
    """Salva os resultados de uma execução no banco de dados, incluindo a origem."""
    conn = None
    if not source_country:
        logger.warning("Tentativa de salvar resultados sem source_country. Ignorando.")
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Salvando resultados da execução para '{source_country}'...")

        execution_date = results.get('execution_date')
        total_processed = results.get('total_processados', 0) # Mudado de total_processados para corresponder ao report
        total_falhas = results.get('total_falhas', 0)
        successful = total_processed - total_falhas # Calcula sucessos
        error_details = results.get('error_details', '[]') # Garante que seja uma string json válida
        execution_time = results.get('execution_time', 0)

        if is_railway():
            # PostgreSQL
            cursor.execute(
                '''
                INSERT INTO execution_history
                (execution_date, total_processed, successful, failed, error_details, execution_time, source_country)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''',
                (
                    execution_date,
                    total_processed,
                    successful,
                    total_falhas, # Usar total_falhas que veio do report
                    error_details,
                    execution_time,
                    source_country # Salva a origem
                )
            )
        else:
            # SQLite
            cursor.execute(
                '''
                INSERT INTO execution_history
                (execution_date, total_processed, successful, failed, error_details, execution_time, source_country)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    execution_date,
                    total_processed,
                    successful,
                    total_falhas, # Usar total_falhas
                    error_details,
                    execution_time,
                    source_country # Salva a origem
                )
            )

        conn.commit()
        logger.info(f"Resultados para '{source_country}' salvos com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao salvar resultados da execução para '{source_country}': {e}", exc_info=True)
        if conn:
            try: conn.rollback()
            except: pass
    finally:
        if conn:
            conn.close()
            logger.debug("Conexão com DB fechada após save_results.")


# Busca histórico de execuções
# --- MODIFICADO: Adiciona parâmetro country_filter ---
def get_execution_history(start_date, end_date, country_filter=None):
    """
    Busca o histórico de execuções dentro de um período.
    Opcionalmente filtra por país/origem se country_filter for fornecido.
    """
    conn = None
    try:
        conn = get_db_connection()
        logger.info(f"Buscando histórico de execução de {start_date} a {end_date}" + (f" para '{country_filter}'" if country_filter else ""))

        # Monta a query base
        base_query = """
        SELECT execution_date, total_processed, successful, failed, execution_time, source_country
        FROM execution_history
        WHERE execution_date BETWEEN {start_placeholder} AND {end_placeholder}
        """

        params = [start_date, end_date]

        # Adiciona filtro de país se fornecido
        if country_filter:
            base_query += " AND source_country = {country_placeholder}"
            params.append(country_filter)

        base_query += " ORDER BY execution_date DESC"

        # Ajusta placeholders para o tipo de banco
        if is_railway():
            # PostgreSQL usa %s
            query = base_query.format(start_placeholder="%s", end_placeholder="%s", country_placeholder="%s")
            logger.debug(f"Executando query PostgreSQL: {query} com params: {params}")
            df = pd.read_sql_query(query, conn, params=tuple(params)) # psycopg2 espera tupla
        else:
            # SQLite usa ?
            query = base_query.format(start_placeholder="?", end_placeholder="?", country_placeholder="?")
            logger.debug(f"Executando query SQLite: {query} com params: {params}")
            df = pd.read_sql_query(query, conn, params=params)

        logger.info(f"Histórico encontrado: {len(df)} registros.")
        return df
    except Exception as e:
        logger.error(f"Erro ao buscar histórico de execução: {e}", exc_info=True)
        return pd.DataFrame() # Retorna DataFrame vazio em caso de erro
    finally:
        if conn:
            conn.close()
            logger.debug("Conexão com DB fechada após get_history.")


# --- Funções load/save schedule_config (mantidas como antes) ---
def load_schedule_config():
    """Carrega a configuração de agendamento do banco de dados"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_enabled, interval_hours, start_time, end_time, last_run FROM schedule_config WHERE id = 1")
        result = cursor.fetchone()
        if result:
            return {
                "is_enabled": bool(result[0]), # Converte para boolean independentemente do DB
                "interval_hours": result[1],
                "start_time": result[2],
                "end_time": result[3],
                "last_run": result[4]
            }
    except Exception as e:
        logger.error(f"Erro ao carregar config de agendamento: {e}", exc_info=True)
    finally:
        if conn: conn.close()

    # Retorna padrão se não encontrar ou der erro
    return { "is_enabled": False, "interval_hours": 6, "start_time": "08:00", "end_time": "20:00", "last_run": None }

def save_schedule_config(config):
    """Salva a configuração de agendamento no banco de dados"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        is_enabled_value = config["is_enabled"] # Assume que já é boolean
        last_run_value = config.get("last_run")

        if is_railway():
            # PostgreSQL
            cursor.execute(
                '''
                UPDATE schedule_config
                SET is_enabled = %s, interval_hours = %s, start_time = %s, end_time = %s, last_run = %s
                WHERE id = 1
                ''',
                (
                    is_enabled_value,
                    config["interval_hours"],
                    config["start_time"],
                    config["end_time"],
                    last_run_value
                )
            )
        else:
            # SQLite (converte boolean para int)
            cursor.execute(
                '''
                UPDATE schedule_config
                SET is_enabled = ?, interval_hours = ?, start_time = ?, end_time = ?, last_run = ?
                WHERE id = 1
                ''',
                (
                    int(is_enabled_value), # Converte para 0 ou 1
                    config["interval_hours"],
                    config["start_time"],
                    config["end_time"],
                    last_run_value
                )
            )
        conn.commit()
        logger.info("Configuração de agendamento salva.")
    except Exception as e:
        logger.error(f"Erro ao salvar config de agendamento: {e}", exc_info=True)
        if conn:
            try: # Tenta fazer rollback
                logger.warning("Erro ao salvar config, tentando rollback...")
                conn.rollback()
                logger.info("Rollback realizado.")
            except Exception as rollback_e: # Captura erro DURANTE o rollback
                # Loga o erro do rollback mas continua para fechar a conexão
                logger.error(f"Erro durante o rollback da config: {rollback_e}", exc_info=True)
                # O 'pass' aqui é implícito, pois não há mais nada a fazer neste except
    finally:
        # Garante que a conexão seja fechada, independentemente de erros
        if conn:
            try:
                conn.close()
                logger.debug("Conexão DB fechada (save_schedule_config).")
            except Exception as close_e:
                 logger.error(f"Erro ao fechar conexão DB em save_schedule_config: {close_e}", exc_info=True)