import os
import sqlite3
import psycopg2
from psycopg2 import sql
import pandas as pd

# Verifica se estamos rodando no Railway (presença da variável DATABASE_URL)
def is_railway():
    return os.environ.get('DATABASE_URL') is not None

# Função para obter conexão com o banco de dados apropriado
def get_db_connection():
    """Retorna uma conexão com o banco de dados (PostgreSQL no Railway, SQLite localmente)"""
    if is_railway():
        # Conecta ao PostgreSQL no Railway
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    else:
        # Conecta ao SQLite local
        conn = sqlite3.connect('dropi_automation.db')
    
    return conn

# Inicializa o banco de dados
def init_database():
    """Inicializa o banco de dados (PostgreSQL ou SQLite)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Cria tabelas com sintaxe compatível com ambos os bancos
    if is_railway():
        # Tabelas para PostgreSQL
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS execution_history (
            id SERIAL PRIMARY KEY,
            execution_date TIMESTAMP,
            total_processed INTEGER,
            successful INTEGER,
            failed INTEGER,
            error_details TEXT,
            execution_time REAL
        )
        ''')
        
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
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS execution_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_date TEXT,
            total_processed INTEGER,
            successful INTEGER,
            failed INTEGER,
            error_details TEXT,
            execution_time REAL
        )
        ''')
        
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
    conn.close()

# Salva resultados da execução no banco de dados
def save_execution_results(results):
    """Salva os resultados de uma execução no banco de dados"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if is_railway():
        # PostgreSQL
        cursor.execute(
            '''
            INSERT INTO execution_history 
            (execution_date, total_processed, successful, failed, error_details, execution_time)
            VALUES (%s, %s, %s, %s, %s, %s)
            ''', 
            (
                results.get('execution_date'),
                results.get('total_processados', 0),
                results.get('total_processados', 0) - results.get('total_falhas', 0),
                results.get('total_falhas', 0),
                results.get('error_details'),
                results.get('execution_time', 0)
            )
        )
    else:
        # SQLite
        cursor.execute(
            '''
            INSERT INTO execution_history 
            (execution_date, total_processed, successful, failed, error_details, execution_time)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', 
            (
                results.get('execution_date'),
                results.get('total_processados', 0),
                results.get('total_processados', 0) - results.get('total_falhas', 0),
                results.get('total_falhas', 0),
                results.get('error_details'),
                results.get('execution_time', 0)
            )
        )
    
    conn.commit()
    conn.close()

# Carrega configuração de agendamento
def load_schedule_config():
    """Carrega a configuração de agendamento do banco de dados"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT is_enabled, interval_hours, start_time, end_time, last_run FROM schedule_config WHERE id = 1")
    result = cursor.fetchone()
    
    conn.close()
    
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

# Salva configuração de agendamento
def save_schedule_config(config):
    """Salva a configuração de agendamento no banco de dados"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if is_railway():
        # PostgreSQL
        cursor.execute(
            '''
            UPDATE schedule_config
            SET is_enabled = %s, interval_hours = %s, start_time = %s, end_time = %s, last_run = %s
            WHERE id = 1
            ''', 
            (
                config["is_enabled"],
                config["interval_hours"],
                config["start_time"],
                config["end_time"],
                config.get("last_run")
            )
        )
    else:
        # SQLite
        cursor.execute(
            '''
            UPDATE schedule_config
            SET is_enabled = ?, interval_hours = ?, start_time = ?, end_time = ?, last_run = ?
            WHERE id = 1
            ''', 
            (
                int(config["is_enabled"]),
                config["interval_hours"],
                config["start_time"],
                config["end_time"],
                config.get("last_run")
            )
        )
    
    conn.commit()
    conn.close()

# Busca histórico de execuções
def get_execution_history(start_date, end_date):
    """Busca o histórico de execuções dentro de um período"""
    conn = get_db_connection()
    
    # Ajusta datas para incluir o dia inteiro
    # Diferentes entre PostgreSQL e SQLite
    if is_railway():
        # PostgreSQL usa formato de data diferente
        query = """
        SELECT execution_date, total_processed, successful, failed, execution_time
        FROM execution_history
        WHERE execution_date BETWEEN %s AND %s
        ORDER BY execution_date DESC
        """
        # Usando pandas com PostgreSQL
        df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    else:
        # SQLite
        query = f"""
        SELECT execution_date, total_processed, successful, failed, execution_time
        FROM execution_history
        WHERE execution_date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY execution_date DESC
        """
        # Usando pandas com SQLite
        df = pd.read_sql_query(query, conn)
    
    conn.close()
    return df