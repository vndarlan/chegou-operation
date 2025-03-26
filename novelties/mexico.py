import streamlit as st
import time
import pandas as pd
import datetime
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.support.ui import Select
import logging
import traceback
from io import StringIO
import sys
import platform
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Importa as funções de conexão com banco de dados com tratamento de erro
try:
    from db_connection import (
        init_database, 
        save_execution_results, 
        load_schedule_config, 
        save_schedule_config, 
        get_execution_history,
        is_railway
    )
except ImportError:
    # Fallback sem banco de dados
    def init_database(): return None
    def save_execution_results(results): return None
    def load_schedule_config(): return {"is_enabled": False, "interval_hours": 6, "start_time": "08:00", "end_time": "20:00", "last_run": None}
    def save_schedule_config(config): return None
    def get_execution_history(start_date, end_date): return pd.DataFrame()
    def is_railway(): return "RAILWAY_ENVIRONMENT" in os.environ

# Configurações padrão - Credenciais removidas do frontend conforme solicitado
DEFAULT_CREDENTIALS = {
    "email": "viniciuschegouoperacional@gmail.com",
    "password": "Viniciuschegou@1"
}

# Título e descrição
st.title("Automação de Novelties Dropi")
st.markdown("""
Este aplicativo automatiza o processamento de novelties na plataforma Dropi.
A automação é executada diretamente e você pode acompanhar o progresso em tempo real.
""")

# Inicializa o banco de dados
init_database()

# Verificar e instalar dependências
def check_dependencies():
    try:
        # No Railway, não verificamos o Chrome
        if is_railway():
            st.sidebar.success("🚂 Executando no Railway com PostgreSQL")
            return True
            
        # Verificar o sistema operacional
        system = platform.system()
        st.sidebar.info(f"Sistema Operacional: {system}")
        
        # Verificar se o Chrome está instalado
        if system == "Windows":
            chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
            chrome_path_alt = "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
            if os.path.exists(chrome_path) or os.path.exists(chrome_path_alt):
                st.sidebar.success("✅ Google Chrome detectado")
            else:
                st.sidebar.error("❌ Google Chrome não encontrado. Por favor, instale-o.")
        elif system == "Darwin":  # macOS
            if os.path.exists("/Applications/Google Chrome.app"):
                st.sidebar.success("✅ Google Chrome detectado")
            else:
                st.sidebar.error("❌ Google Chrome não encontrado. Por favor, instale-o.")
        elif system == "Linux":
            chrome_exists = os.system("which google-chrome > /dev/null 2>&1") == 0
            if chrome_exists:
                st.sidebar.success("✅ Google Chrome detectado")
            else:
                st.sidebar.error("❌ Google Chrome não encontrado. Por favor, instale-o.")
        
        # Verificar módulos Python
        required_modules = ["selenium", "webdriver_manager", "pandas", "apscheduler"]
        if is_railway():
            required_modules.append("psycopg2")
            
        missing_modules = []
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                missing_modules.append(module)
        
        if missing_modules:
            st.sidebar.error(f"❌ Módulos faltando: {', '.join(missing_modules)}")
            st.sidebar.info("Execute: pip install " + " ".join(missing_modules))
        else:
            st.sidebar.success("✅ Todos os módulos Python necessários estão instalados")
        
        # Informação sobre ambiente
        if is_railway():
            st.sidebar.success("🚂 Executando no Railway com PostgreSQL")
        else:
            st.sidebar.info("💻 Executando localmente com SQLite")
        
        return len(missing_modules) == 0
    except Exception as e:
        st.sidebar.error(f"Erro ao verificar dependências: {str(e)}")
        return False

# Inicializa o estado da sessão para armazenar logs
if 'log_output' not in st.session_state:
    st.session_state.log_output = StringIO()
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'progress' not in st.session_state:
    st.session_state.progress = 0
if 'total_items' not in st.session_state:
    st.session_state.total_items = 0
if 'processed_items' not in st.session_state:
    st.session_state.processed_items = 0
if 'success_count' not in st.session_state:
    st.session_state.success_count = 0
if 'failed_count' not in st.session_state:
    st.session_state.failed_count = 0
if 'report' not in st.session_state:
    st.session_state.report = None
if 'log_messages' not in st.session_state:
    st.session_state.log_messages = []
if 'error_messages' not in st.session_state:
    st.session_state.error_messages = []
if 'has_chromedriver' not in st.session_state:
    st.session_state.has_chromedriver = False
if 'automation_step' not in st.session_state:
    st.session_state.automation_step = 'idle'  # Estados: idle, setup, login, navigate, configure, process, complete
if 'driver' not in st.session_state:
    st.session_state.driver = None
if 'current_row_index' not in st.session_state:
    st.session_state.current_row_index = 0
if 'rows' not in st.session_state:
    st.session_state.rows = []
if 'failed_items' not in st.session_state:
    st.session_state.failed_items = []
if 'closed_tabs' not in st.session_state:
    st.session_state.closed_tabs = 0
if 'found_pagination' not in st.session_state:
    st.session_state.found_pagination = False
if 'start_time' not in st.session_state:
    st.session_state.start_time = None
if 'scheduler' not in st.session_state:
    st.session_state.scheduler = BackgroundScheduler()
    st.session_state.scheduler.start()

# Sidebar com informações
st.sidebar.title("Configuração")

# No Railway sempre usamos headless, em local podemos escolher
if is_railway():
    use_headless = True
else:
    use_headless = st.sidebar.checkbox("Modo Headless", value=True, 
                                help="Se marcado, o navegador não será exibido na tela. Desmarque para depuração.")

# Verificar dependências
dependencies_ok = check_dependencies()

# Tentar instalar o ChromeDriver apenas se não estivermos no Railway
if dependencies_ok and not st.session_state.has_chromedriver and not is_railway():
    with st.sidebar:
        with st.spinner("Instalando ChromeDriver..."):
            try:
                # Tenta instalar o ChromeDriver
                driver_path = ChromeDriverManager().install()
                st.session_state.has_chromedriver = True
                st.sidebar.success(f"✅ ChromeDriver instalado em: {driver_path}")
            except Exception as e:
                st.sidebar.error(f"❌ Erro ao instalar ChromeDriver: {str(e)}")
                st.sidebar.info("Por favor, instale manualmente o ChromeDriver compatível com sua versão do Chrome")
elif is_railway():
    # No Railway, assumimos que o ChromeDriver está disponível através do Dockerfile
    st.session_state.has_chromedriver = True

# Configuração de logging para o Streamlit
class StreamlitHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        st.session_state.log_output.write(log_entry + '\n')
        
        # Adiciona à lista de mensagens para exibição em tempo real
        log_type = "info"
        if record.levelno >= logging.ERROR:
            log_type = "error"
            # Adiciona erros à lista específica de erros
            st.session_state.error_messages.append({
                "type": "error",
                "message": log_entry
            })
        elif record.levelno >= logging.WARNING:
            log_type = "warning"
            
        st.session_state.log_messages.append({
            "type": log_type,
            "message": log_entry
        })

logger = logging.getLogger("dropi_automation")
logger.setLevel(logging.INFO)
# Limpa handlers existentes para evitar duplicação
if logger.handlers:
    logger.handlers = []
handler = StreamlitHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Carrega configurações de agendamento
schedule_config = load_schedule_config()

# Interface do usuário
tab1, tab2, tab3 = st.tabs(["Execução Manual", "Agendamento", "Histórico"])

with tab1:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Removido o formulário com credenciais
        if st.button("Iniciar Automação Manual"):
            if st.session_state.is_running:
                st.warning("Automação já está em execução.")
            elif not dependencies_ok:
                st.error("Não é possível iniciar a automação. Verifique as dependências no painel lateral.")
            elif not st.session_state.has_chromedriver:
                st.error("ChromeDriver não instalado. Verifique o painel lateral.")
            else:
                # Inicia a automação diretamente (sem thread)
                st.session_state.is_running = True
                st.session_state.log_output = StringIO()  # Limpa o log anterior
                st.session_state.log_messages = []  # Limpa as mensagens de log
                st.session_state.error_messages = []  # Limpa as mensagens de erro
                st.session_state.progress = 0
                st.session_state.total_items = 0
                st.session_state.processed_items = 0
                st.session_state.success_count = 0
                st.session_state.failed_count = 0
                st.session_state.report = None
                st.session_state.automation_step = 'setup'
                st.session_state.current_row_index = 0
                st.session_state.rows = []
                st.session_state.failed_items = []
                st.session_state.closed_tabs = 0
                st.session_state.found_pagination = False
                st.session_state.email = DEFAULT_CREDENTIALS["email"]
                st.session_state.password = DEFAULT_CREDENTIALS["password"]
                st.session_state.use_headless = use_headless
                st.session_state.start_time = time.time()
                st.success("Iniciando automação... Aguarde.")
                st.rerun()
    
    with col2:
        st.subheader("Status")
        
        # Exibe o status atual
        if st.session_state.is_running:
            status = st.info("✅ Automação em execução...")
            
            # Botão para parar a automação
            if st.button("Parar Automação"):
                st.session_state.is_running = False
                
                # Fecha o navegador se estiver aberto
                if st.session_state.driver:
                    try:
                        st.session_state.driver.quit()
                    except:
                        pass
                    st.session_state.driver = None
                    
                st.warning("Automação interrompida pelo usuário.")
                st.rerun()
        else:
            if st.session_state.report:
                status = st.success("✅ Automação concluída!")
            elif st.session_state.processed_items > 0:
                status = st.warning("⚠️ Automação interrompida.")
            else:
                status = st.info("⏸️ Aguardando início da automação.")
        
        # Exibe estatísticas
        st.metric("Novelties Processadas", st.session_state.processed_items)
        st.metric("Sucesso", st.session_state.success_count)
        st.metric("Falhas", st.session_state.failed_count)
    
    # Barra de progresso
    if st.session_state.total_items > 0:
        st.progress(st.session_state.progress)
        st.caption(f"Progresso: {st.session_state.processed_items}/{st.session_state.total_items} items")
    
    # Exibe apenas erros, não o log completo
    if st.session_state.error_messages:
        st.subheader("Erros Detectados")
        for error in st.session_state.error_messages[-10:]:  # Mostra apenas os 10 últimos erros
            st.error(error["message"])
    
    # Se houver um relatório, exibe-o
    if st.session_state.report and not st.session_state.is_running:
        st.subheader("Relatório de Execução")
        
        report = st.session_state.report
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Processado", report.get("total_processados", 0))
        with col2:
            st.metric("Total Falhas", report.get("total_falhas", 0))
        with col3:
            st.metric("Guias Fechadas", report.get("guias_fechadas", 0))
        
        # Se houver falhas, exibe os detalhes
        if report.get("total_falhas", 0) > 0:
            st.subheader("Detalhes das Falhas")
            
            # Cria um DataFrame com os itens que falharam
            failures_df = pd.DataFrame(report.get("itens_com_falha", []))
            st.dataframe(failures_df)

with tab2:
    st.subheader("Configuração de Automação Automática")
    
    # Campo para ativar/desativar automação agendada
    is_auto_enabled = st.toggle("Ativar Automação Automática", value=schedule_config["is_enabled"])
    
    # Configuração do intervalo de execução
    col1, col2 = st.columns(2)
    with col1:
        interval_hours = st.number_input("Intervalo de Execução (horas)", 
                                         min_value=1, max_value=24, 
                                         value=schedule_config["interval_hours"])
    
    # Configuração de horário de funcionamento
    col1, col2 = st.columns(2)
    with col1:
        start_time = st.time_input("Horário de Início", 
                                  value=datetime.datetime.strptime(schedule_config["start_time"], "%H:%M").time())
    with col2:
        end_time = st.time_input("Horário de Término", 
                               value=datetime.datetime.strptime(schedule_config["end_time"], "%H:%M").time())
    
    # Salvar configurações
    if st.button("Salvar Configurações de Agendamento"):
        new_config = {
            "is_enabled": is_auto_enabled,
            "interval_hours": interval_hours,
            "start_time": start_time.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
            "last_run": schedule_config.get("last_run")
        }
        
        save_schedule_config(new_config)
        
        # Atualiza o agendador
        if is_auto_enabled:
            # Remove todos os jobs existentes
            for job in st.session_state.scheduler.get_jobs():
                job.remove()
            
            # Adiciona o novo job
            st.session_state.scheduler.add_job(
                lambda: st.session_state.update({"trigger_automation": True}),
                IntervalTrigger(hours=interval_hours),
                id='automation_job'
            )
            
            st.success(f"✅ Automação agendada a cada {interval_hours} horas entre {start_time} e {end_time}")
        else:
            # Remove todos os jobs
            for job in st.session_state.scheduler.get_jobs():
                job.remove()
            st.info("❌ Automação automática desativada")
        
        st.rerun()
    
    # Exibe a última execução
    if schedule_config.get("last_run"):
        st.info(f"Última execução automática: {schedule_config['last_run']}")

with tab3:
    st.subheader("Histórico de Execuções")
    
    # Filtro de data
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Data Inicial", value=datetime.date.today() - datetime.timedelta(days=7))
    with col2:
        end_date = st.date_input("Data Final", value=datetime.date.today())
    
    # Botão para carregar dados
    if st.button("Carregar Histórico"):
        # Ajusta datas para incluir o dia inteiro
        start_datetime = datetime.datetime.combine(start_date, datetime.time.min)
        end_datetime = datetime.datetime.combine(end_date, datetime.time.max)
        
        # Usa a função importada que lida com ambos os bancos de dados
        history_df = get_execution_history(start_datetime, end_datetime)
        
        if len(history_df) > 0:
            # Formata os dados para exibição
            history_df['execution_date'] = pd.to_datetime(history_df['execution_date'])
            history_df['data'] = history_df['execution_date'].dt.date
            history_df['hora'] = history_df['execution_date'].dt.time
            history_df['tempo_execucao'] = history_df['execution_time'].apply(lambda x: f"{x:.2f} segundos")
            
            # Exibe o dataframe formatado
            st.dataframe(
                history_df[['data', 'hora', 'total_processed', 'successful', 'failed', 'tempo_execucao']],
                column_config={
                    'data': 'Data',
                    'hora': 'Hora',
                    'total_processed': 'Total Processado',
                    'successful': 'Sucessos',
                    'failed': 'Falhas',
                    'tempo_execucao': 'Tempo de Execução'
                },
                height=400
            )
            
            # Gráfico de resultados por dia
            st.subheader("Resultados por Dia")
            daily_stats = history_df.groupby('data').agg({
                'successful': 'sum',
                'failed': 'sum'
            }).reset_index()
            
            # Converte para formato adequado para gráfico
            chart_data = pd.DataFrame({
                'data': daily_stats['data'],
                'Sucessos': daily_stats['successful'],
                'Falhas': daily_stats['failed']
            })
            
            st.bar_chart(chart_data.set_index('data'))
        else:
            st.info("Nenhum dado encontrado para o período selecionado.")

# Rodapé
st.markdown("---")
st.caption("Automação Dropi Novelties © 2025")

# Função main a ser chamada pelo iniciar.py
def main():
    # Título e descrição
    st.title("Automação de Novelties Dropi")
    st.markdown("""
    Este aplicativo automatiza o processamento de novelties na plataforma Dropi.
    A automação é executada diretamente e você pode acompanhar o progresso em tempo real.
    """)

    # Inicializa o banco de dados
    init_database()

    # Inicializa o estado da sessão para armazenar logs
    if 'log_output' not in st.session_state:
        st.session_state.log_output = StringIO()
    if 'is_running' not in st.session_state:
        st.session_state.is_running = False
    if 'progress' not in st.session_state:
        st.session_state.progress = 0
    if 'total_items' not in st.session_state:
        st.session_state.total_items = 0
    if 'processed_items' not in st.session_state:
        st.session_state.processed_items = 0
    if 'success_count' not in st.session_state:
        st.session_state.success_count = 0
    if 'failed_count' not in st.session_state:
        st.session_state.failed_count = 0
    if 'report' not in st.session_state:
        st.session_state.report = None
    if 'log_messages' not in st.session_state:
        st.session_state.log_messages = []
    if 'error_messages' not in st.session_state:
        st.session_state.error_messages = []
    if 'has_chromedriver' not in st.session_state:
        st.session_state.has_chromedriver = is_railway()  # No Railway, assumimos que ChromeDriver está disponível
    if 'automation_step' not in st.session_state:
        st.session_state.automation_step = 'idle'
    if 'driver' not in st.session_state:
        st.session_state.driver = None
    if 'current_row_index' not in st.session_state:
        st.session_state.current_row_index = 0
    if 'rows' not in st.session_state:
        st.session_state.rows = []
    if 'failed_items' not in st.session_state:
        st.session_state.failed_items = []
    if 'closed_tabs' not in st.session_state:
        st.session_state.closed_tabs = 0
    if 'found_pagination' not in st.session_state:
        st.session_state.found_pagination = False
    if 'start_time' not in st.session_state:
        st.session_state.start_time = None
    if 'scheduler' not in st.session_state:
        st.session_state.scheduler = BackgroundScheduler()
        st.session_state.scheduler.start()

    # Verificar dependências
    dependencies_ok = check_dependencies()

    # Tentar instalar o ChromeDriver apenas se não estivermos no Railway
    if dependencies_ok and not st.session_state.has_chromedriver and not is_railway():
        with st.sidebar:
            with st.spinner("Instalando ChromeDriver..."):
                try:
                    # Tenta instalar o ChromeDriver
                    driver_path = ChromeDriverManager().install()
                    st.session_state.has_chromedriver = True
                    st.sidebar.success(f"✅ ChromeDriver instalado em: {driver_path}")
                except Exception as e:
                    st.sidebar.error(f"❌ Erro ao instalar ChromeDriver: {str(e)}")
                    st.sidebar.info("Por favor, instale manualmente o ChromeDriver compatível com sua versão do Chrome")
    elif is_railway():
        # No Railway, assumimos que o ChromeDriver está disponível através do Dockerfile
        st.session_state.has_chromedriver = True

    # Sidebar com informações
    st.sidebar.title("Configuração")

    # No Railway sempre usamos headless, em local podemos escolher
    if is_railway():
        st.session_state.use_headless = True
    else:
        st.session_state.use_headless = st.sidebar.checkbox("Modo Headless", value=True, 
                                    help="Se marcado, o navegador não será exibido na tela. Desmarque para depuração.")

    # Interface do usuário
    tab1, tab2, tab3 = st.tabs(["Execução Manual", "Agendamento", "Histórico"])

    with tab1:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Removido o formulário com credenciais
            if st.button("Iniciar Automação Manual"):
                if st.session_state.is_running:
                    st.warning("Automação já está em execução.")
                elif not dependencies_ok and not is_railway():
                    st.error("Não é possível iniciar a automação. Verifique as dependências no painel lateral.")
                elif not st.session_state.has_chromedriver and not is_railway():
                    st.error("ChromeDriver não instalado. Verifique o painel lateral.")
                else:
                    # Inicia a automação diretamente (sem thread)
                    st.session_state.is_running = True
                    st.session_state.log_output = StringIO()  # Limpa o log anterior
                    st.session_state.log_messages = []  # Limpa as mensagens de log
                    st.session_state.error_messages = []  # Limpa as mensagens de erro
                    st.session_state.progress = 0
                    st.session_state.total_items = 0
                    st.session_state.processed_items = 0
                    st.session_state.success_count = 0
                    st.session_state.failed_count = 0
                    st.session_state.report = None
                    st.session_state.automation_step = 'setup'
                    st.session_state.current_row_index = 0
                    st.session_state.rows = []
                    st.session_state.failed_items = []
                    st.session_state.closed_tabs = 0
                    st.session_state.found_pagination = False
                    st.session_state.email = DEFAULT_CREDENTIALS["email"]
                    st.session_state.password = DEFAULT_CREDENTIALS["password"]
                    st.session_state.start_time = time.time()
                    st.success("Iniciando automação... Aguarde.")
                    st.rerun()
        
        with col2:
            st.subheader("Status")
            
            # Exibe o status atual
            if st.session_state.is_running:
                status = st.info("✅ Automação em execução...")
                
                # Botão para parar a automação
                if st.button("Parar Automação"):
                    st.session_state.is_running = False
                    
                    # Fecha o navegador se estiver aberto
                    if st.session_state.driver:
                        try:
                            st.session_state.driver.quit()
                        except:
                            pass
                        st.session_state.driver = None
                        
                    st.warning("Automação interrompida pelo usuário.")
                    st.rerun()
            else:
                if st.session_state.report:
                    status = st.success("✅ Automação concluída!")
                elif st.session_state.processed_items > 0:
                    status = st.warning("⚠️ Automação interrompida.")
                else:
                    status = st.info("⏸️ Aguardando início da automação.")
            
            # Exibe estatísticas
            st.metric("Novelties Processadas", st.session_state.processed_items)
            st.metric("Sucesso", st.session_state.success_count)
            st.metric("Falhas", st.session_state.failed_count)
        
        # Barra de progresso
        if st.session_state.total_items > 0:
            st.progress(st.session_state.progress)
            st.caption(f"Progresso: {st.session_state.processed_items}/{st.session_state.total_items} items")
        
        # Exibe apenas erros, não o log completo
        if st.session_state.error_messages:
            st.subheader("Erros Detectados")
            for error in st.session_state.error_messages[-10:]:  # Mostra apenas os 10 últimos erros
                st.error(error["message"])
        
        # Se houver um relatório, exibe-o
        if st.session_state.report and not st.session_state.is_running:
            st.subheader("Relatório de Execução")
            
            report = st.session_state.report
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Processado", report.get("total_processados", 0))
            with col2:
                st.metric("Total Falhas", report.get("total_falhas", 0))
            with col3:
                st.metric("Guias Fechadas", report.get("guias_fechadas", 0))
            
            # Se houver falhas, exibe os detalhes
            if report.get("total_falhas", 0) > 0:
                st.subheader("Detalhes das Falhas")
                
                # Cria um DataFrame com os itens que falharam
                failures_df = pd.DataFrame(report.get("itens_com_falha", []))
                st.dataframe(failures_df)

    with tab2:
        st.subheader("Configuração de Automação Automática")
        
        # Carrega configurações de agendamento
        schedule_config = load_schedule_config()
        
        # Campo para ativar/desativar automação agendada
        is_auto_enabled = st.toggle("Ativar Automação Automática", value=schedule_config["is_enabled"])
        
        # Configuração do intervalo de execução
        col1, col2 = st.columns(2)
        with col1:
            interval_hours = st.number_input("Intervalo de Execução (horas)", 
                                            min_value=1, max_value=24, 
                                            value=schedule_config["interval_hours"])
        
        # Configuração de horário de funcionamento
        col1, col2 = st.columns(2)
        with col1:
            start_time = st.time_input("Horário de Início", 
                                    value=datetime.datetime.strptime(schedule_config["start_time"], "%H:%M").time())
        with col2:
            end_time = st.time_input("Horário de Término", 
                                value=datetime.datetime.strptime(schedule_config["end_time"], "%H:%M").time())
        
        # Salvar configurações
        if st.button("Salvar Configurações de Agendamento"):
            new_config = {
                "is_enabled": is_auto_enabled,
                "interval_hours": interval_hours,
                "start_time": start_time.strftime("%H:%M"),
                "end_time": end_time.strftime("%H:%M"),
                "last_run": schedule_config.get("last_run")
            }
            
            save_schedule_config(new_config)
            
            # Atualiza o agendador
            if is_auto_enabled:
                # Remove todos os jobs existentes
                for job in st.session_state.scheduler.get_jobs():
                    job.remove()
                
                # Adiciona o novo job
                st.session_state.scheduler.add_job(
                    lambda: st.session_state.update({"trigger_automation": True}),
                    IntervalTrigger(hours=interval_hours),
                    id='automation_job'
                )
                
                st.success(f"✅ Automação agendada a cada {interval_hours} horas entre {start_time} e {end_time}")
            else:
                # Remove todos os jobs
                for job in st.session_state.scheduler.get_jobs():
                    job.remove()
                st.info("❌ Automação automática desativada")
            
            st.rerun()
        
        # Exibe a última execução
        if schedule_config.get("last_run"):
            st.info(f"Última execução automática: {schedule_config['last_run']}")

    with tab3:
        st.subheader("Histórico de Execuções")
        
        # Filtro de data
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Data Inicial", value=datetime.date.today() - datetime.timedelta(days=7))
        with col2:
            end_date = st.date_input("Data Final", value=datetime.date.today())
        
        # Botão para carregar dados
        if st.button("Carregar Histórico"):
            # Ajusta datas para incluir o dia inteiro
            start_datetime = datetime.datetime.combine(start_date, datetime.time.min)
            end_datetime = datetime.datetime.combine(end_date, datetime.time.max)
            
            # Usa a função importada que lida com ambos os bancos de dados
            history_df = get_execution_history(start_datetime, end_datetime)
            
            if len(history_df) > 0:
                # Formata os dados para exibição
                history_df['execution_date'] = pd.to_datetime(history_df['execution_date'])
                history_df['data'] = history_df['execution_date'].dt.date
                history_df['hora'] = history_df['execution_date'].dt.time
                history_df['tempo_execucao'] = history_df['execution_time'].apply(lambda x: f"{x:.2f} segundos")
                
                # Exibe o dataframe formatado
                st.dataframe(
                    history_df[['data', 'hora', 'total_processed', 'successful', 'failed', 'tempo_execucao']],
                    column_config={
                        'data': 'Data',
                        'hora': 'Hora',
                        'total_processed': 'Total Processado',
                        'successful': 'Sucessos',
                        'failed': 'Falhas',
                        'tempo_execucao': 'Tempo de Execução'
                    },
                    height=400
                )
                
                # Gráfico de resultados por dia
                st.subheader("Resultados por Dia")
                daily_stats = history_df.groupby('data').agg({
                    'successful': 'sum',
                    'failed': 'sum'
                }).reset_index()
                
                # Converte para formato adequado para gráfico
                chart_data = pd.DataFrame({
                    'data': daily_stats['data'],
                    'Sucessos': daily_stats['successful'],
                    'Falhas': daily_stats['failed']
                })
                
                st.bar_chart(chart_data.set_index('data'))
            else:
                st.info("Nenhum dado encontrado para o período selecionado.")
                
    # Rodapé
    st.markdown("---")
    st.caption("Automação Dropi Novelties © 2025")

# Funções de automação (adaptadas para serem executadas passo a passo)
def setup_driver():
    """Configura o driver do Selenium."""
    logger.info("Iniciando configuração do driver Chrome...")
    
    chrome_options = Options()
    
    # Sempre use headless no Railway ou se configurado localmente
    if is_railway() or st.session_state.use_headless:
        logger.info("Modo headless ativado")
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
    else:
        logger.info("Modo headless desativado - navegador será visível")
    
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Adiciona algumas flags básicas que ajudam com a estabilidade
    chrome_options.add_argument("--disable-extensions")
    
    try:
        # Dentro do Railway, usamos uma abordagem mais simples para iniciar o Chrome
        if is_railway():
            logger.info("Inicializando o driver Chrome no Railway...")
            # No ambiente Railway, o Chrome está instalado no sistema
            driver = webdriver.Chrome(options=chrome_options)
        else:
            # Localmente, continue usando o webdriver_manager
            logger.info("Inicializando o driver Chrome localmente...")
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            
        logger.info("Driver do Chrome iniciado com sucesso")
        st.session_state.driver = driver
        return True
    except Exception as e:
        logger.error(f"Erro ao configurar o driver Chrome: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def login():
    """Função de login super robusta."""
    try:
        driver = st.session_state.driver
        
        # Abre o site em uma nova janela maximizada
        driver.maximize_window()
        
        # Navega para a página de login
        logger.info("Navegando para a página de login...")
        driver.get("https://app.dropi.mx/")
        time.sleep(5)  # Espera fixa de 5 segundos
        
        # Tira screenshot para análise
        driver.save_screenshot("login_page.png")
        logger.info("Screenshot da página salvo como login_page.png")
        
        # Inspeciona a página e loga a estrutura HTML para análise
        logger.info("Analisando estrutura da página de login...")
        html = driver.page_source
        logger.info(f"Título da página: {driver.title}")
        logger.info(f"URL atual: {driver.current_url}")
        
        # Tenta encontrar os campos usando diferentes métodos
        
        # MÉTODO 1: Tenta encontrar os campos por XPath direto
        try:
            logger.info("Tentando encontrar campos por XPath...")
            
            # Lista todos os inputs para depuração
            inputs = driver.find_elements(By.TAG_NAME, 'input')
            logger.info(f"Total de campos input encontrados: {len(inputs)}")
            for i, inp in enumerate(inputs):
                input_type = inp.get_attribute('type')
                input_id = inp.get_attribute('id')
                input_name = inp.get_attribute('name')
                logger.info(f"Input #{i}: tipo={input_type}, id={input_id}, name={input_name}")
            
            # Tenta localizar o campo de email/usuário - tentando diferentes atributos
            email_field = None
            
            # Tenta por tipo "email"
            try:
                email_field = driver.find_element(By.XPATH, "//input[@type='email']")
                logger.info("Campo de email encontrado por type='email'")
            except:
                pass
                
            # Tenta por tipo "text"
            if not email_field:
                try:
                    email_field = driver.find_element(By.XPATH, "//input[@type='text']")
                    logger.info("Campo de email encontrado por type='text'")
                except:
                    pass
            
            # Tenta pelo primeiro input
            if not email_field and len(inputs) > 0:
                email_field = inputs[0]
                logger.info("Usando primeiro campo input encontrado para email")
            
            # Se encontrou o campo de email, preenche
            if email_field:
                email_field.clear()
                email_field.send_keys(st.session_state.email)
                logger.info(f"Email preenchido: {st.session_state.email}")
            else:
                raise Exception("Não foi possível encontrar o campo de email")
            
            # Procura o campo de senha
            password_field = None
            
            # Tenta por tipo "password"
            try:
                password_field = driver.find_element(By.XPATH, "//input[@type='password']")
                logger.info("Campo de senha encontrado por type='password'")
            except:
                pass
            
            # Tenta usando o segundo input
            if not password_field and len(inputs) > 1:
                password_field = inputs[1]
                logger.info("Usando segundo campo input encontrado para senha")
            
            # Se encontrou o campo de senha, preenche
            if password_field:
                password_field.clear()
                password_field.send_keys(st.session_state.password)
                logger.info("Senha preenchida")
            else:
                raise Exception("Não foi possível encontrar o campo de senha")
            
            # Lista todos os botões para depuração
            buttons = driver.find_elements(By.TAG_NAME, 'button')
            logger.info(f"Total de botões encontrados: {len(buttons)}")
            for i, btn in enumerate(buttons):
                btn_text = btn.text
                btn_type = btn.get_attribute('type')
                logger.info(f"Botão #{i}: texto='{btn_text}', tipo={btn_type}")
            
            # Procura o botão de login
            login_button = None
            
            # Tenta por tipo "submit"
            try:
                login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
                logger.info("Botão de login encontrado por type='submit'")
            except:
                pass
            
            # Tenta por texto
            if not login_button:
                for btn in buttons:
                    if "iniciar" in btn.text.lower() or "login" in btn.text.lower() or "entrar" in btn.text.lower():
                        login_button = btn
                        logger.info(f"Botão de login encontrado pelo texto: '{btn.text}'")
                        break
            
            # Se não encontrou por texto específico, usa o primeiro botão
            if not login_button and len(buttons) > 0:
                login_button = buttons[0]
                logger.info("Usando primeiro botão encontrado para login")
            
            # Se encontrou o botão, clica
            if login_button:
                login_button.click()
                logger.info("Clicado no botão de login")
            else:
                raise Exception("Não foi possível encontrar o botão de login")
            
            # Aguarda a navegação
            time.sleep(8)
            
            # Tira screenshot após o login
            driver.save_screenshot("after_login.png")
            logger.info("Screenshot após login salvo como after_login.png")
            
            # Verifica se o login foi bem-sucedido
            current_url = driver.current_url
            logger.info(f"URL após tentativa de login: {current_url}")
            
            # Tenta encontrar elementos que aparecem após login bem-sucedido
            menu_items = driver.find_elements(By.TAG_NAME, 'a')
            for item in menu_items:
                logger.info(f"Item de menu encontrado: '{item.text}'")
                if "dashboard" in item.text.lower() or "orders" in item.text.lower():
                    logger.info(f"Item de menu confirmando login: '{item.text}'")
                    return True
            
            # Se não encontrou elementos claros de login, verifica se estamos na URL de dashboard
            if "dashboard" in current_url or "orders" in current_url:
                logger.info("Login confirmado pela URL")
                return True
            
            # Se chegou aqui, o login pode ter falhado
            logger.warning("Não foi possível confirmar se o login foi bem-sucedido. Tentando continuar mesmo assim.")
            return True
            
        except Exception as e:
            logger.error(f"Erro no método 1: {str(e)}")
            # Continua para o próximo método
        
        # MÉTODO 2: Tenta navegar diretamente para a página de Orders
        logger.info("Tentando método alternativo: navegação direta...")
        try:
            driver.get("https://app.dropi.mx/orders")
            time.sleep(5)
            driver.save_screenshot("direct_orders.png")
            
            # Verifica se fomos redirecionados para login ou se estamos na página de orders
            current_url = driver.current_url
            logger.info(f"URL após navegação direta: {current_url}")
            
            if "orders" in current_url and "login" not in current_url:
                logger.info("Navegação direta bem-sucedida!")
                return True
            else:
                logger.warning("Navegação direta falhou, redirecionado para login")
        except:
            logger.error("Erro ao tentar navegação direta")
        
        logger.error("Todos os métodos de login falharam")
        return False
        
    except Exception as e:
        logger.error(f"Erro geral no login: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def navigate_to_novelties():
    """Navega até a página de novelties."""
    try:
        driver = st.session_state.driver
        
        # Verifica se já estamos na dashboard
        logger.info("Verificando a página atual...")
        current_url = driver.current_url
        logger.info(f"URL atual: {current_url}")
        
        # Clica em My Orders - usando JavaScript para maior confiabilidade
        logger.info("Tentando clicar em 'My Orders'...")
        try:
            # Primeiro tenta com JavaScript
            driver.execute_script("Array.from(document.querySelectorAll('a')).find(el => el.textContent.includes('My Orders')).click();")
            logger.info("Clicado em 'My Orders' via JavaScript")
        except:
            # Se falhar, tenta com Selenium normal
            try:
                my_orders_link = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'My Orders')]"))
                )
                my_orders_link.click()
                logger.info("Clicado em 'My Orders' via Selenium")
            except:
                logger.warning("Não foi possível clicar em 'My Orders', tentando abrir URL diretamente")
                # Se ainda falhar, tenta navegar diretamente para a URL
                driver.get("https://app.dropi.mx/orders")
                time.sleep(3)
        
        # Espera um pouco
        time.sleep(5)
        
        # Clica em Novelties - usando abordagem similar
        logger.info("Tentando clicar em 'Novelties'...")
        try:
            # Primeiro tenta com JavaScript
            driver.execute_script("Array.from(document.querySelectorAll('a')).find(el => el.textContent.includes('Novelties')).click();")
            logger.info("Clicado em 'Novelties' via JavaScript")
        except:
            # Se falhar, tenta com Selenium normal
            try:
                novelties_link = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Novelties')]"))
                )
                novelties_link.click()
                logger.info("Clicado em 'Novelties' via Selenium")
            except:
                logger.warning("Não foi possível clicar em 'Novelties', tentando abrir URL diretamente")
                # Se ainda falhar, tenta navegar diretamente para a URL
                driver.get("https://app.dropi.mx/novelties")
                time.sleep(3)
        
        # Espera mais um pouco
        time.sleep(5)
        
        # Tira screenshot para verificar
        try:
            driver.save_screenshot("novelties_page.png")
            logger.info("Screenshot da página de novelties salvo")
        except:
            pass
        
        # Espera até que a tabela de novelties seja carregada
        logger.info("Verificando se a tabela de novelties foi carregada...")
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//table"))
            )
            logger.info("Tabela de novelties encontrada!")
        except:
            logger.warning("Não foi possível encontrar a tabela, mas continuando...")
        
        return True
    except Exception as e:
        logger.error(f"Erro ao navegar até Novelties: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def configure_entries_display():
    """Configura para exibir 1000 entradas usando o elemento select identificado."""
    try:
        driver = st.session_state.driver
        # Rola até o final da página
        logger.info("Rolando até o final da página para verificar opções de exibição...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # Aguarda para verificar se a opção está presente
        
        # Tira screenshot
        try:
            driver.save_screenshot("page_bottom_before.png")
            logger.info("Screenshot do final da página salvo (antes)")
        except:
            pass
        
        # Procura especificamente pelo select com os atributos informados
        logger.info("Procurando elemento select específico conforme HTML fornecido...")
        
        entries_found = False
        try:
            # Método 1: Procura pelo elemento select específico
            select_elements = driver.find_elements(By.XPATH, "//select[@name='select' and @id='select' and contains(@class, 'custom-select')]")
            
            if not select_elements:
                # Método 2: Procura por qualquer select na página
                select_elements = driver.find_elements(By.XPATH, "//select[contains(@class, 'custom-select') or contains(@class, 'form-control')]")
            
            if not select_elements:
                # Método 3: Procura por qualquer select
                select_elements = driver.find_elements(By.TAG_NAME, "select")
            
            if select_elements:
                logger.info(f"Elemento select encontrado: {len(select_elements)} elementos")
                
                # Usa o primeiro select encontrado
                select_element = select_elements[0]
                
                # Tira screenshot antes de interagir com o select
                driver.save_screenshot("before_select_interaction.png")
                
                # Cria um objeto Select para manipular o elemento
                select = Select(select_element)
                
                # Verifica se há uma opção com valor "1000"
                options_text = [o.text for o in select.options]
                logger.info(f"Opções disponíveis no select: {options_text}")
                
                try:
                    # Primeiro tenta selecionar pelo texto visível "1000"
                    select.select_by_visible_text("1000")
                    logger.info("Selecionado '1000' pelo texto visível")
                    entries_found = True
                except Exception as e:
                    logger.info(f"Erro ao selecionar por texto visível: {str(e)}")
                    
                    try:
                        # Tenta selecionar pelo índice da opção que contém "1000"
                        for i, option in enumerate(select.options):
                            if "1000" in option.text or "1000" in option.get_attribute("value"):
                                select.select_by_index(i)
                                logger.info(f"Selecionado '1000' pelo índice {i}")
                                entries_found = True
                                break
                    except Exception as e:
                        logger.info(f"Erro ao selecionar por índice: {str(e)}")
                        
                        try:
                            # Último recurso: tenta selecionar qualquer valor que contenha "1000"
                            for value in ["4: 1000", "1000", "4"]:  # Tenta vários formatos possíveis
                                try:
                                    select.select_by_value(value)
                                    logger.info(f"Selecionado '1000' pelo valor '{value}'")
                                    entries_found = True
                                    break
                                except:
                                    continue
                        except Exception as e:
                            logger.info(f"Erro ao selecionar por valor: {str(e)}")
                
                # Tenta também usando JavaScript
                if not entries_found:
                    try:
                        logger.info("Tentando selecionar '1000' via JavaScript...")
                        # Encontra o valor que contém 1000
                        for option in select.options:
                            if "1000" in option.text:
                                value = option.get_attribute("value")
                                # Define o valor diretamente via JavaScript
                                driver.execute_script(f"arguments[0].value = '{value}';", select_element)
                                # Dispara evento de change para atualizar a UI
                                driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", select_element)
                                logger.info(f"Selecionado '1000' via JavaScript com valor '{value}'")
                                entries_found = True
                                break
                    except Exception as e:
                        logger.info(f"Erro ao selecionar via JavaScript: {str(e)}")
                
                # Tira screenshot após tentar selecionar
                driver.save_screenshot("after_select_interaction.png")
                
                if entries_found:
                    logger.info("Configurado para exibir 1000 entradas")
                    st.session_state.found_pagination = True
                    
                    # Aguarda o carregamento da tabela com mais entradas
                    logger.info("Aguardando carregamento da tabela com mais entradas...")
                    time.sleep(5)
                    
                    # ADICIONADO: Espera explícita para o carregamento da tabela
                    logger.info("Esperando explicitamente pelo carregamento das linhas da tabela...")
                    try:
                        # Espera até que haja pelo menos uma linha na tabela ou até 30 segundos
                        WebDriverWait(driver, 30).until(
                            lambda d: len(d.find_elements(By.XPATH, "//table/tbody/tr")) > 0
                        )
                        logger.info("Linhas da tabela carregadas com sucesso!")
                    except TimeoutException:
                        logger.warning("Timeout esperando pelas linhas da tabela. Verificando se há mensagem de 'Sem resultados'...")
                        # Verifica se existe uma mensagem de "Sem resultados" ou similar
                        try:
                            no_results = driver.find_element(By.XPATH, "//*[contains(text(), 'No hay resultados') or contains(text(), 'No data') or contains(text(), 'Sem resultados')]")
                            if no_results:
                                logger.info(f"Mensagem encontrada: '{no_results.text}' - A tabela realmente parece estar vazia.")
                        except:
                            # Vamos tentar um outro seletor para as linhas
                            logger.info("Tentando seletor alternativo para as linhas da tabela...")
            else:
                logger.warning("Não foi possível encontrar o elemento select")
        except Exception as e:
            logger.error(f"Erro ao configurar quantidade de entradas: {str(e)}")
            logger.error(traceback.format_exc())
        
        # Volta para o topo da página
        logger.info("Retornando ao topo da página...")
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        # Agora obtém todas as linhas da tabela
        logger.info("Contando linhas da tabela...")
        try:
            # MODIFICADO: Tenta diferentes XPaths para encontrar as linhas
            rows = driver.find_elements(By.XPATH, "//table/tbody/tr")
            
            # Se não encontrou linhas, tenta um seletor mais genérico
            if not rows:
                logger.info("Nenhuma linha encontrada com o seletor padrão, tentando seletor alternativo...")
                rows = driver.find_elements(By.XPATH, "//table//tr[position() > 1]")  # Ignora a primeira linha (cabeçalho)
            
            # Se ainda não encontrou, tenta outro seletor mais genérico
            if not rows:
                logger.info("Tentando outro seletor alternativo...")
                rows = driver.find_elements(By.CSS_SELECTOR, "table tr:not(:first-child)")
            
            # Se continua sem encontrar, tenta um último recurso
            if not rows:
                logger.info("Último recurso: capturando todas as linhas...")
                rows = driver.find_elements(By.TAG_NAME, "tr")
                # Filtra as linhas para remover possíveis cabeçalhos
                if len(rows) > 1:
                    rows = rows[1:]  # Remove a primeira linha, que provavelmente é o cabeçalho
            
            # Tira screenshot da tabela para análise
            driver.save_screenshot("table_after_loading.png")
            logger.info("Screenshot da tabela após carregamento salvo")
            
            st.session_state.rows = rows
            st.session_state.total_items = len(rows)
            logger.info(f"Total de {len(rows)} novelties encontradas para processar")
            
            # Se não encontrou nenhuma linha, tenta verificar se há mensagem indicando ausência de dados
            if len(rows) == 0:
                try:
                    page_text = driver.find_element(By.TAG_NAME, "body").text
                    logger.info(f"Texto da página: {page_text[:500]}...")  # Primeiros 500 caracteres
                    
                    # Verifica se há textos comuns que indicam ausência de dados
                    no_data_texts = ["No hay resultados", "No data available", "No records found", "Sem resultados"]
                    for text in no_data_texts:
                        if text in page_text:
                            logger.info(f"Mensagem encontrada: '{text}' - A tabela realmente parece estar vazia.")
                except:
                    pass
        except Exception as e:
            logger.error(f"Erro ao contar linhas da tabela: {str(e)}")
            logger.error(traceback.format_exc())
            logger.warning("Não foi possível contar as linhas da tabela. Usando valor padrão.")
            st.session_state.rows = []
            st.session_state.total_items = 0
        
        return True
    except Exception as e:
        logger.error(f"Erro ao configurar exibição de entradas: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def process_current_novelty():
    """Processa a novelty atual na lista."""
    try:
        driver = st.session_state.driver
        
        # Verifica se há rows para processar
        if not st.session_state.rows:
            logger.info("Nenhuma novidade encontrada na tabela")
            return True
        
        # Verifica se todas as rows já foram processadas
        if st.session_state.current_row_index >= len(st.session_state.rows):
            logger.info("Todas as novelties foram processadas")
            return True
        
        # Pega a row atual
        row = st.session_state.rows[st.session_state.current_row_index]
        
        try:
            # Obtém o ID da linha para referência em caso de erro
            try:
                row_id = row.find_elements(By.TAG_NAME, "td")[0].text
                logger.info(f"Processando novelty ID: {row_id} ({st.session_state.current_row_index+1}/{len(st.session_state.rows)})")
            except:
                row_id = f"Linha {st.session_state.current_row_index+1}"
                logger.info(f"Processando {row_id}/{len(st.session_state.rows)}")
            
            # Atualiza o progresso
            st.session_state.processed_items = st.session_state.current_row_index + 1
            st.session_state.progress = (st.session_state.current_row_index + 1) / len(st.session_state.rows)
            
            # Tirar screenshot antes de clicar no botão Save
            try:
                driver.save_screenshot(f"before_save_{row_id}.png")
                logger.info(f"Screenshot antes de salvar: before_save_{row_id}.png")
            except:
                pass
            
            # Clica no botão Save verde
            logger.info(f"Clicando no botão 'Save' para a novelty {row_id}...")
            save_button = row.find_element(By.XPATH, ".//button[contains(@class, 'btn-success')]")
            save_button.click()
            
            # Espera pelo popup
            time.sleep(3)
            
            # Tirar screenshot após clicar no botão Save
            try:
                driver.save_screenshot(f"after_save_{row_id}.png")
                logger.info(f"Screenshot após salvar: after_save_{row_id}.png")
            except:
                pass
            
            # Tenta diferentes métodos para encontrar e clicar no botão "Yes" ou "Sim"
            yes_clicked = False
            
            # Método 1: Procura por texto exato
            for text in ["Yes", "Sim", "YES", "SIM", "yes", "sim"]:
                try:
                    button = driver.find_element(By.XPATH, f"//button[contains(text(), '{text}')]")
                    logger.info(f"Botão com texto '{text}' encontrado, tentando clicar...")
                    driver.execute_script("arguments[0].scrollIntoView(true);", button)
                    driver.execute_script("arguments[0].click();", button)
                    logger.info(f"Clicado no botão com texto '{text}'")
                    yes_clicked = True
                    break
                except Exception as e:
                    logger.info(f"Não foi possível clicar no botão '{text}': {str(e)}")
                    continue
            
            # Método 2: Primeiro botão no modal-footer
            if not yes_clicked:
                try:
                    buttons = driver.find_elements(By.XPATH, "//div[contains(@class, 'modal-footer')]/button")
                    if buttons:
                        logger.info("Encontrado botão no modal-footer, tentando clicar...")
                        driver.execute_script("arguments[0].scrollIntoView(true);", buttons[0])
                        driver.execute_script("arguments[0].click();", buttons[0])
                        logger.info("Clicado no primeiro botão do modal-footer")
                        yes_clicked = True
                except Exception as e:
                    logger.info(f"Erro ao clicar no botão do modal-footer: {str(e)}")
            
            # Método 3: Qualquer botão primary ou success
            if not yes_clicked:
                try:
                    buttons = driver.find_elements(By.TAG_NAME, "button")
                    for button in buttons:
                        if button.is_displayed():
                            try:
                                button_class = button.get_attribute("class").lower()
                                if "primary" in button_class or "success" in button_class:
                                    logger.info(f"Encontrado botão com classe {button_class}, tentando clicar...")
                                    driver.execute_script("arguments[0].scrollIntoView(true);", button)
                                    driver.execute_script("arguments[0].click();", button)
                                    logger.info(f"Clicado em botão de classe: {button_class}")
                                    yes_clicked = True
                                    break
                            except Exception as e:
                                logger.info(f"Erro ao clicar no botão de classe {button_class}: {str(e)}")
                                continue
                except Exception as e:
                    logger.info(f"Erro ao procurar botões por classe: {str(e)}")
                    
            if not yes_clicked:
                logger.warning("Não foi possível clicar em 'Yes'/'Sim'. Tentando continuar...")
            
            # Espera após clicar no botão Yes
            time.sleep(3)
            
            # Tirar screenshot após clicar no botão Yes
            try:
                driver.save_screenshot(f"after_yes_{row_id}.png")
                logger.info(f"Screenshot após clicar em Yes: after_yes_{row_id}.png")
            except:
                pass
            
            # Agora vamos tentar encontrar o formulário ou os campos, mesmo sem esperar pelo modal completo
            logger.info("Procurando campos para preenchimento, mesmo sem modal completo...")
            
            # Primeiro tentamos capturar o endereço antes de procurar o formulário
            address = extract_address_from_page(driver)
            
            # Tenta várias estratégias para encontrar o formulário
            form_found = False
            form_modal = None
            
            # Estratégia 1: Procura pelo modal padrão com formulário
            try:
                logger.info("Tentando encontrar o modal com formulário (estratégia 1)...")
                form_modal = WebDriverWait(driver, 7).until(
                    EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'modal-body')]//form"))
                )
                logger.info("Formulário encontrado com sucesso (estratégia 1)")
                form_found = True
            except Exception as e:
                logger.info(f"Não foi possível encontrar o formulário padrão: {str(e)}")
            
            # Estratégia 2: Procura por qualquer modal visível
            if not form_found:
                try:
                    logger.info("Tentando encontrar qualquer modal visível (estratégia 2)...")
                    modal = WebDriverWait(driver, 5).until(
                        EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'modal') and @style='display: block;']"))
                    )
                    logger.info("Modal visível encontrado, procurando campos dentro dele...")
                    form_modal = modal
                    form_found = True
                except Exception as e:
                    logger.info(f"Não foi possível encontrar modal visível: {str(e)}")
            
            # Estratégia 3: Procura por campos input diretamente
            if not form_found:
                try:
                    logger.info("Tentando encontrar campos input diretamente (estratégia 3)...")
                    inputs = driver.find_elements(By.TAG_NAME, "input")
                    # Filtra apenas inputs visíveis
                    visible_inputs = [inp for inp in inputs if inp.is_displayed()]
                    if visible_inputs:
                        logger.info(f"Encontrados {len(visible_inputs)} inputs visíveis")
                        # Usa o documento inteiro como "form_modal"
                        form_modal = driver.find_element(By.TAG_NAME, "body")
                        form_found = True
                    else:
                        logger.warning("Nenhum input visível encontrado na página")
                except Exception as e:
                    logger.info(f"Erro ao procurar inputs: {str(e)}")
            
            # Se encontrou o formulário ou campos, tenta preencher
            if form_found and form_modal:
                logger.info("Formulário ou campos encontrados, preenchendo...")
                
                # Procura e preenche o campo Solución
                solution_filled = fill_solution_field(driver, form_modal, address)
                
                # Clica em Salvar/Guardar se o campo foi preenchido
                if solution_filled:
                    # Clica em Salvar/Guardar - tentando vários textos
                    save_clicked = click_save_button(driver)
                    
                    # Espera o modal fechar
                    logger.info("Aguardando fechamento do modal de edição...")
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.invisibility_of_element_located((By.XPATH, "//div[contains(@class, 'modal') and @style='display: block;']"))
                        )
                        logger.info("Modal fechou com sucesso")
                    except:
                        logger.warning("Modal de edição não fechou em 10 segundos, tentando fechar manualmente...")
                        try:
                            # Tenta forçar o fechamento clicando no X
                            close_buttons = driver.find_elements(By.XPATH, "//button[contains(@class, 'close') or contains(@class, 'btn-close')]")
                            for button in close_buttons:
                                if button.is_displayed():
                                    driver.execute_script("arguments[0].click();", button)
                                    logger.info("Fechando modal manualmente clicando no X")
                                    break
                        except Exception as e:
                            logger.warning(f"Não foi possível fechar o modal manualmente: {str(e)}")
                else:
                    logger.warning("O campo Solución não foi preenchido, mas tentando continuar...")
                    try:
                        # Tenta clicar em salvar mesmo assim
                        save_clicked = click_save_button(driver)
                    except:
                        pass
            else:
                logger.warning("Não foi possível encontrar o formulário ou campos para preencher")
                try:
                    # Tenta continuar mesmo sem encontrar o formulário, talvez não seja necessário preenchimento
                    logger.info("Tentando continuar sem preencher campos...")
                    
                    # Procura por botões de salvar na página
                    for save_text in ["Guardar", "Salvar", "Save", "GUARDAR", "SALVAR", "SAVE"]:
                        try:
                            save_form_button = driver.find_element(By.XPATH, f"//button[contains(text(), '{save_text}')]")
                            if save_form_button.is_displayed():
                                driver.execute_script("arguments[0].click();", save_form_button)
                                logger.info(f"Clicado no botão '{save_text}' sem preencher campos")
                                break
                        except:
                            continue
                except:
                    pass
            
            # Espera adicional após salvar (conforme solicitado na melhoria)
            time.sleep(5)
            
            # NOVO: Procura e clica no popup "OK" que aparece após salvar
            logger.info("Procurando popup de confirmação com botão OK...")
            try:
                # Tira screenshot do popup
                try:
                    driver.save_screenshot(f"popup_ok_{row_id}.png")
                    logger.info(f"Screenshot do popup OK: popup_ok_{row_id}.png")
                except:
                    pass
                
                # Tenta várias estratégias para encontrar e clicar no botão OK
                ok_clicked = False
                
                # Método 1: Botão com texto OK
                for text in ["OK", "Ok", "ok", "Aceptar", "Aceptar", "Aceitar", "aceitar"]:
                    try:
                        ok_buttons = driver.find_elements(By.XPATH, f"//button[contains(text(), '{text}')]")
                        for button in ok_buttons:
                            if button.is_displayed():
                                logger.info(f"Botão OK encontrado com texto '{text}', clicando...")
                                driver.execute_script("arguments[0].click();", button)
                                ok_clicked = True
                                break
                        if ok_clicked:
                            break
                    except Exception as e:
                        logger.info(f"Erro ao clicar no botão '{text}': {str(e)}")
                
                # Método 2: Qualquer botão em um modal visible
                if not ok_clicked:
                    try:
                        buttons = driver.find_elements(By.XPATH, "//div[contains(@class, 'modal') and @style='display: block;']//button")
                        for button in buttons:
                            if button.is_displayed():
                                logger.info(f"Botão encontrado em modal visível: '{button.text}', clicando...")
                                driver.execute_script("arguments[0].click();", button)
                                ok_clicked = True
                                break
                    except Exception as e:
                        logger.info(f"Erro ao clicar em botão de modal visível: {str(e)}")
                
                # Método 3: Qualquer botão de classe primary ou success
                if not ok_clicked:
                    try:
                        buttons = driver.find_elements(By.TAG_NAME, "button")
                        for button in buttons:
                            if button.is_displayed():
                                try:
                                    button_class = button.get_attribute("class").lower()
                                    if "primary" in button_class or "success" in button_class:
                                        logger.info(f"Botão OK encontrado por classe: '{button.text}', clicando...")
                                        driver.execute_script("arguments[0].click();", button)
                                        ok_clicked = True
                                        break
                                except:
                                    continue
                    except Exception as e:
                        logger.info(f"Erro ao procurar botão OK por classe: {str(e)}")
                
                if ok_clicked:
                    logger.info("Botão OK clicado com sucesso")
                    # Espera adicional após clicar em OK
                    time.sleep(2)
                else:
                    logger.warning("Não foi possível encontrar e clicar no botão OK, continuando mesmo assim")
            except Exception as e:
                logger.warning(f"Erro ao procurar popup OK: {str(e)}")
            
            # Verifica se há novas guias abertas
            check_and_close_tabs()
            
            # Incrementa contador de sucesso
            st.session_state.success_count += 1
            logger.info(f"Novelty {row_id} processada com sucesso!")
            
            # Pequena pausa entre processamentos
            time.sleep(1)
            
        except Exception as e:
            # Registra o erro
            error_msg = f"Erro ao processar novelty {row_id}: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            st.session_state.failed_items.append({"id": row_id, "error": str(e)})
            st.session_state.failed_count = len(st.session_state.failed_items)
            
            # Tratamento de erro conforme especificado
            handle_error(row, row_id)
        
        # Incrementa o índice para a próxima novelty
        st.session_state.current_row_index += 1
        
        # Verifica se todas as novelties foram processadas
        if st.session_state.current_row_index >= len(st.session_state.rows):
            logger.info("Todas as novelties foram processadas")
            generate_report()
            return True
        
        return False
            
    except Exception as e:
        logger.error(f"Erro geral ao processar novelty: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def extract_address_from_page(driver):
    """Extrai o endereço da página, independente do formulário estar presente ou não."""
    try:
        logger.info("Procurando endereço do cliente na página...")
        
        # Tira screenshot para análise
        try:
            driver.save_screenshot("page_for_address.png")
            logger.info("Screenshot para busca de endereço salvo")
        except:
            pass
        
        address = ""
        
        # Método 1: Procura pelo cabeçalho típico "ORDERS TO:"
        try:
            # Procura primeiro o nome do cliente, que normalmente está em destaque
            header_info = driver.find_elements(By.XPATH, "//*[contains(text(), 'ORDERS TO:')]")
            
            if header_info:
                # Pega o elemento que vem depois do "ORDERS TO:" que contém o endereço completo
                for element in header_info:
                    try:
                        # Tenta pegar o texto do elemento pai
                        parent = element.find_element(By.XPATH, "./..")
                        parent_text = parent.text
                        logger.info(f"Texto no elemento pai de ORDERS TO: {parent_text}")
                        
                        # Se encontrou o texto, procura pelo endereço (geralmente após o nome)
                        lines = parent_text.split('\n')
                        if len(lines) > 1:
                            for i, line in enumerate(lines):
                                if "ORDERS TO:" in line and i + 1 < len(lines):
                                    address = lines[i + 2]  # Pega duas linhas abaixo (nome, depois endereço)
                                    logger.info(f"Endereço encontrado após ORDERS TO:: {address}")
                                    return address
                    except:
                        pass
            
                # Método alternativo: tenta pegar o próximo irmão
                for element in header_info:
                    try:
                        next_sibling = element.find_element(By.XPATH, "./following-sibling::*[1]")
                        sibling_text = next_sibling.text
                        logger.info(f"Texto no elemento seguinte a ORDERS TO:: {sibling_text}")
                        
                        # Separa as linhas
                        lines = sibling_text.split('\n')
                        if len(lines) > 1:
                            address = lines[1]  # A segunda linha geralmente é o endereço
                            logger.info(f"Endereço capturado do irmão: {address}")
                            return address
                        else:
                            address = sibling_text
                            logger.info(f"Usando texto completo do irmão como endereço: {address}")
                            return address
                    except:
                        pass
        except Exception as e:
            logger.info(f"Erro ao buscar ORDERS TO:: {str(e)}")
        
        # Método 2: Procura por elementos de texto que contêm endereço
        if not address:
            try:
                for address_keyword in ["Avenida", "Calle", "Rua", "Carretera", "Street", "Av.", "Av ", "Calz"]:
                    address_elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{address_keyword}')]")
                    for element in address_elements:
                        try:
                            element_text = element.text
                            if len(element_text) > 10:  # Filtra textos muito curtos
                                address = element_text
                                logger.info(f"Endereço encontrado com keyword '{address_keyword}': {address}")
                                return address
                        except:
                            pass
            except Exception as e:
                logger.info(f"Erro ao buscar por palavras-chave de endereço: {str(e)}")
        
        # Método 3: Procura por campos específicos no formulário que já estejam preenchidos
        if not address:
            try:
                # Tenta encontrar campos "Dirección" já preenchidos
                direccion_elements = driver.find_elements(By.XPATH, "//label[contains(text(), 'Dirección') or contains(text(), 'dirección')]")
                for label in direccion_elements:
                    try:
                        # Tenta encontrar o input associado
                        input_id = label.get_attribute("for")
                        if input_id:
                            input_field = driver.find_element(By.ID, input_id)
                            address_value = input_field.get_attribute("value")
                            if address_value and len(address_value) > 10:
                                address = address_value
                                logger.info(f"Endereço encontrado em campo 'Dirección': {address}")
                                return address
                    except:
                        pass
            except Exception as e:
                logger.info(f"Erro ao buscar campos de direção preenchidos: {str(e)}")
        
        # Se não encontrou endereço, usa um valor padrão
        if not address:
            address = "Endereço de Entrega"
            logger.warning("Não foi possível encontrar endereço, usando valor padrão")
        
        return address
    except Exception as e:
        logger.error(f"Erro ao extrair endereço: {str(e)}")
        return "Endereço de Entrega"

def fill_solution_field(driver, form_modal, address):
    """Preenche especificamente o campo Solución com o endereço."""
    try:
        logger.info("Tentando preencher o campo Solución...")
        
        # Procura o campo de solução
        solution_fields = []
        
        # Método 1: Por label exata
        try:
            solution_labels = driver.find_elements(By.XPATH, "//label[contains(text(), 'Solución') or contains(text(), 'Solucion') or contains(text(), 'solución') or contains(text(), 'solucion')]")
            for label in solution_labels:
                if label.is_displayed():
                    logger.info(f"Label de solução encontrado: '{label.text}'")
                    
                    # Procura o campo de input associado ao label
                    input_id = label.get_attribute("for")
                    if input_id:
                        try:
                            solution_field = driver.find_element(By.ID, input_id)
                            if solution_field.is_displayed():
                                solution_fields.append(solution_field)
                                logger.info("Campo de solução encontrado pelo ID do label")
                        except:
                            pass
        except Exception as e:
            logger.info(f"Erro ao buscar label 'Solución': {str(e)}")
        
        # Método 2: Encontrar qualquer input visível próximo à label
        if not solution_fields:
            try:
                solution_labels = driver.find_elements(By.XPATH, "//*[contains(text(), 'Solución') or contains(text(), 'Solucion')]")
                for label in solution_labels:
                    if label.is_displayed():
                        try:
                            # Busca por inputs próximos ao label
                            parent = label.find_element(By.XPATH, "./..")
                            nearby_inputs = parent.find_elements(By.TAG_NAME, "input")
                            for input_field in nearby_inputs:
                                if input_field.is_displayed():
                                    solution_fields.append(input_field)
                                    logger.info("Campo de solução encontrado próximo ao label")
                                    break
                        except:
                            pass
            except Exception as e:
                logger.info(f"Erro ao buscar inputs próximos à label 'Solución': {str(e)}")
        
        # Método 3: Encontrar o primeiro input visível vazio na página
        if not solution_fields:
            try:
                inputs = form_modal.find_elements(By.TAG_NAME, "input")
                for input_field in inputs:
                    try:
                        if input_field.is_displayed() and not input_field.get_attribute("value"):
                            # Verifica se não é um campo de nome, telefone ou código postal
                            input_name = input_field.get_attribute("name") or ""
                            input_id = input_field.get_attribute("id") or ""
                            input_placeholder = input_field.get_attribute("placeholder") or ""
                            
                            # Ignora campos específicos
                            skip_keywords = ["name", "nombre", "phone", "telefono", "postal", "código", "address", "dirección"]
                            should_skip = False
                            
                            for keyword in skip_keywords:
                                if (keyword.lower() in input_name.lower() or 
                                    keyword.lower() in input_id.lower() or 
                                    keyword.lower() in input_placeholder.lower()):
                                    should_skip = True
                                    break
                            
                            if not should_skip:
                                solution_fields.append(input_field)
                                logger.info("Usando primeiro campo vazio disponível para solução")
                                break
                    except:
                        continue
            except Exception as e:
                logger.info(f"Erro ao buscar primeiro input vazio: {str(e)}")
        
        # Se encontrou algum campo para solução, preenche com o endereço
        if solution_fields:
            solution_field = solution_fields[0]
            
            # Verifica se o campo está vazio antes de preencher
            if not solution_field.get_attribute("value"):
                # Rola até o elemento
                driver.execute_script("arguments[0].scrollIntoView(true);", solution_field)
                time.sleep(0.5)
                
                # Limpa o campo e preenche com o endereço
                solution_field.clear()
                time.sleep(0.5)
                
                # Preenche usando JavaScript para maior confiabilidade
                driver.execute_script(f"arguments[0].value = '{address}';", solution_field)
                
                # Também tenta o método padrão
                solution_field.send_keys(address)
                
                logger.info(f"Campo Solución preenchido com o endereço: {address}")
                
                # Verifica se o preenchimento funcionou
                actual_value = solution_field.get_attribute("value")
                logger.info(f"Valor atual do campo após preenchimento: '{actual_value}'")
                
                return True
            else:
                logger.info("Campo Solución já está preenchido, não foi modificado")
                return True
        else:
            logger.warning("Não foi possível encontrar o campo Solución")
            return False
            
    except Exception as e:
        logger.error(f"Erro ao preencher campo Solución: {str(e)}")
        return False

def click_save_button(driver):
    """Tenta clicar no botão de salvar usando várias estratégias."""
    try:
        logger.info("Tentando clicar no botão de salvar...")
        save_clicked = False
        
        # Método 1: Procura por texto exato
        for save_text in ["Guardar", "Salvar", "Save", "GUARDAR", "SALVAR", "SAVE"]:
            try:
                save_buttons = driver.find_elements(By.XPATH, f"//button[contains(text(), '{save_text}')]")
                for button in save_buttons:
                    if button.is_displayed():
                        logger.info(f"Botão de salvar encontrado com texto '{save_text}', tentando clicar...")
                        driver.execute_script("arguments[0].scrollIntoView(true);", button)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", button)
                        logger.info(f"Clicado no botão '{save_text}'")
                        save_clicked = True
                        break
                if save_clicked:
                    break
            except Exception as e:
                logger.info(f"Erro ao clicar no botão '{save_text}': {str(e)}")
                continue
        
        # Método 2: Procura por botão de tipo submit
        if not save_clicked:
            try:
                submit_buttons = driver.find_elements(By.XPATH, "//button[@type='submit']")
                for button in submit_buttons:
                    if button.is_displayed():
                        logger.info("Botão de submit encontrado, tentando clicar...")
                        driver.execute_script("arguments[0].scrollIntoView(true);", button)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", button)
                        logger.info("Clicado no botão de submit")
                        save_clicked = True
                        break
            except Exception as e:
                logger.info(f"Erro ao clicar no botão de submit: {str(e)}")
        
        # Método 3: Procura por botões com classe indicativa de sucesso/primário
        if not save_clicked:
            try:
                buttons = driver.find_elements(By.TAG_NAME, "button")
                for button in buttons:
                    try:
                        if button.is_displayed():
                            button_class = button.get_attribute("class").lower()
                            if "primary" in button_class or "success" in button_class:
                                button_text = button.text.strip()
                                # Ignore os botões que claramente não são para salvar
                                if button_text.lower() not in ["no", "não", "cancel", "cancelar", "close", "fechar"]:
                                    logger.info(f"Botão com classe {button_class} encontrado: '{button_text}', tentando clicar...")
                                    driver.execute_script("arguments[0].scrollIntoView(true);", button)
                                    time.sleep(0.5)
                                    driver.execute_script("arguments[0].click();", button)
                                    logger.info(f"Clicado em botão: '{button_text}'")
                                    save_clicked = True
                                    break
                    except:
                        continue
            except Exception as e:
                logger.info(f"Erro ao procurar botões por classe: {str(e)}")
        
        if not save_clicked:
            logger.warning("Não foi possível encontrar e clicar no botão de salvar")
        
        return save_clicked
    except Exception as e:
        logger.error(f"Erro ao tentar clicar no botão de salvar: {str(e)}")
        return False

def fill_empty_fields(form_modal, row_id):
    """Função legada mantida para compatibilidade, agora usa as novas funções."""
    try:
        driver = st.session_state.driver
        address = extract_address_from_page(driver)
        return fill_solution_field(driver, form_modal, address)
    except Exception as e:
        logger.error(f"Erro ao preencher formulário: {str(e)}")
        return False

def extract_data_from_table(row_id):
    """Extrai dados da linha da tabela para uso no formulário."""
    try:
        driver = st.session_state.driver
        # Tenta encontrar a linha com o ID correspondente
        row = driver.find_element(By.XPATH, f"//table/tbody/tr[td[contains(text(), '{row_id}')]]")
        
        # Extrai os dados
        data = {}
        
        # Tenta obter o nome e telefone do cliente da coluna de dados
        try:
            data_col = row.find_elements(By.TAG_NAME, "td")[3]  # Ajuste o índice conforme necessário
            data_text = data_col.text
            
            # Extrai nome e telefone
            if "Phone:" in data_text:
                parts = data_text.split("Phone:")
                data["nome"] = parts[0].strip()
                data["telefone"] = parts[1].strip() if len(parts) > 1 else ""
            else:
                data["nome"] = data_text
                data["telefone"] = ""
            
            # Tenta encontrar o endereço na mesma coluna ou em outra
            try:
                address_col = row.find_elements(By.TAG_NAME, "td")[4]  # Ajuste o índice conforme necessário
                data["endereco"] = address_col.text.strip()
                data["endereco_completo"] = address_col.text.strip()
            except:
                data["endereco"] = ""
                data["endereco_completo"] = ""
            
        except:
            # Se não conseguir extrair, usa valores genéricos
            data["nome"] = "Nome do Cliente"
            data["endereco"] = "Endereço de Entrega"
            data["endereco_completo"] = "Endereço Completo de Entrega"
            data["telefone"] = "1234567890"
        
        return data
    except:
        # Se não conseguir encontrar a linha, retorna dados genéricos
        return {
            "nome": "Nome do Cliente",
            "endereco": "Endereço de Entrega",
            "endereco_completo": "Endereço Completo de Entrega",
            "telefone": "1234567890"
        }

def handle_error(row, row_id):
    """Trata erros conforme o protocolo especificado."""
    try:
        driver = st.session_state.driver
        logger.info(f"Iniciando tratamento de erro para novelty {row_id}...")
        
        # Tenta fechar qualquer modal/popup aberto
        try:
            logger.info("Tentando fechar popups abertos...")
            close_buttons = driver.find_elements(By.XPATH, "//button[contains(@class, 'close') or contains(@class, 'btn-close')]")
            for button in close_buttons:
                if button.is_displayed():
                    button.click()
                    time.sleep(0.5)
        except:
            pass
            
        # Clica novamente no botão Save
        try:
            logger.info(f"Tentando fluxo alternativo para novelty {row_id}...")
            logger.info("Clicando novamente no botão 'Save'...")
            save_button = row.find_element(By.XPATH, ".//button[contains(@class, 'btn-success')]")
            save_button.click()
            
            # Espera pelo popup e clica em "Não" desta vez
            logger.info("Procurando e clicando no botão 'Não' no popup...")
            nao_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Não')]"))
            )
            nao_button.click()
            
            # No segundo popup, clica em "Sim"
            logger.info("Procurando e clicando no botão 'Sim' no segundo popup...")
            sim_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Sim')]"))
            )
            sim_button.click()
            
            # Aguarda o modal fechar
            time.sleep(2)
            
            logger.info(f"Tratamento alternativo aplicado com sucesso para novelty {row_id}")
        except Exception as e:
            logger.error(f"Erro ao aplicar tratamento alternativo para novelty {row_id}: {str(e)}")
            
            # Tenta fechar todos os popups novamente
            try:
                logger.info("Tentando fechar todos os popups após falha no tratamento alternativo...")
                close_buttons = driver.find_elements(By.XPATH, "//button[contains(@class, 'close') or contains(@class, 'btn-close')]")
                for button in close_buttons:
                    if button.is_displayed():
                        button.click()
                        time.sleep(0.5)
            except:
                pass
        
        # Verifica se há novas guias abertas
        check_and_close_tabs()
            
    except Exception as e:
        logger.error(f"Erro ao tratar erro para novelty {row_id}: {str(e)}")

def check_and_close_tabs():
    """Verifica se há novas guias abertas e as fecha."""
    try:
        driver = st.session_state.driver
        # Obtém todas as guias
        handles = driver.window_handles
        
        # Se houver mais de uma guia, fecha as extras
        if len(handles) > 1:
            current_handle = driver.current_window_handle
            
            for handle in handles:
                if handle != current_handle:
                    driver.switch_to.window(handle)
                    driver.close()
                    st.session_state.closed_tabs += 1
            
            # Volta para a guia principal
            driver.switch_to.window(current_handle)
            logger.info(f"Fechadas {len(handles) - 1} guias extras")
    except Exception as e:
        logger.error(f"Erro ao verificar e fechar guias: {str(e)}")

def generate_report():
    """Gera um relatório da execução e salva no banco de dados."""
    # Calcula o tempo de execução
    execution_time = time.time() - st.session_state.start_time if st.session_state.start_time else 0
    
    # Adiciona data/hora da execução para salvar no banco
    execution_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_details = json.dumps(st.session_state.failed_items)
    
    report = {
        "execution_date": execution_date,
        "total_processados": st.session_state.success_count,
        "total_falhas": len(st.session_state.failed_items),
        "itens_com_falha": st.session_state.failed_items,
        "guias_fechadas": st.session_state.closed_tabs,
        "encontrou_paginacao": st.session_state.found_pagination,
        "execution_time": execution_time,
        "error_details": error_details
    }
    
    logger.info("======= RELATÓRIO DE EXECUÇÃO =======")
    logger.info(f"Total de novelties processadas com sucesso: {report['total_processados']}")
    logger.info(f"Total de novelties com falha: {report['total_falhas']}")
    logger.info(f"Total de guias fechadas durante o processo: {report['guias_fechadas']}")
    logger.info(f"Encontrou opção para filtrar 1000 itens: {'Sim' if report['encontrou_paginacao'] else 'Não'}")
    logger.info(f"Tempo de execução: {execution_time:.2f} segundos")
    
    if report['total_falhas'] > 0:
        logger.info("Detalhes dos itens com falha:")
        for item in report['itens_com_falha']:
            logger.info(f"  - ID: {item['id']}, Erro: {item['error']}")
            
    logger.info("=====================================")
    
    # Salva o relatório no banco de dados
    try:
        save_execution_results(report)
        logger.info("Relatório salvo no banco de dados com sucesso")
    except Exception as e:
        logger.error(f"Erro ao salvar relatório no banco de dados: {str(e)}")
    
    st.session_state.report = report

# Função para executar a automação agendada
def run_scheduled_automation():
    """Executa a automação de acordo com o agendamento."""
    # Verifica se já está em execução
    if st.session_state.is_running:
        logger.info("Automação já está em execução, ignorando chamada agendada")
        return
    
    # Verifica se estamos dentro do horário permitido
    now = datetime.datetime.now().time()
    config = load_schedule_config()
    
    start_time = datetime.datetime.strptime(config["start_time"], "%H:%M").time()
    end_time = datetime.datetime.strptime(config["end_time"], "%H:%M").time()
    
    if not (start_time <= now <= end_time):
        logger.info(f"Fora do horário permitido ({config['start_time']} - {config['end_time']}), ignorando chamada agendada")
        return
    
    logger.info("Iniciando automação agendada")
    
    # Inicia a automação
    st.session_state.is_running = True
    st.session_state.log_output = StringIO()
    st.session_state.log_messages = []
    st.session_state.error_messages = []
    st.session_state.progress = 0
    st.session_state.total_items = 0
    st.session_state.processed_items = 0
    st.session_state.success_count = 0
    st.session_state.failed_count = 0
    st.session_state.report = None
    st.session_state.automation_step = 'setup'
    st.session_state.current_row_index = 0
    st.session_state.rows = []
    st.session_state.failed_items = []
    st.session_state.closed_tabs = 0
    st.session_state.found_pagination = False
    st.session_state.email = DEFAULT_CREDENTIALS["email"]
    st.session_state.password = DEFAULT_CREDENTIALS["password"]
    st.session_state.use_headless = True  # Sempre headless para automação agendada
    st.session_state.start_time = time.time()
    
    # Atualiza o último horário de execução
    config["last_run"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_schedule_config(config)

# Verifica se uma automação foi agendada
if 'trigger_automation' in st.session_state and st.session_state.trigger_automation:
    st.session_state.trigger_automation = False
    run_scheduled_automation()

# Se este script for executado diretamente (não importado)
if __name__ == "__main__":
    main()

# Processamento da automação baseado no estado atual
if st.session_state.is_running:
    # Etapas da automação
    if st.session_state.automation_step == 'setup':
        if setup_driver():
            st.session_state.automation_step = 'login'
            st.rerun()
        else:
            st.session_state.is_running = False
            st.error("Falha ao configurar o driver Chrome")
    
    elif st.session_state.automation_step == 'login':
        if login():
            st.session_state.automation_step = 'navigate'
            st.rerun()
        else:
            st.session_state.is_running = False
            st.error("Falha no login")
    
    elif st.session_state.automation_step == 'navigate':
        if navigate_to_novelties():
            st.session_state.automation_step = 'configure'
            st.rerun()
        else:
            st.session_state.is_running = False
            st.error("Falha ao navegar até Novelties")
    
    elif st.session_state.automation_step == 'configure':
        if configure_entries_display():
            st.session_state.automation_step = 'process'
            st.rerun()
        else:
            st.session_state.is_running = False
            st.error("Falha ao configurar exibição de entradas")
    
    elif st.session_state.automation_step == 'process':
        # Processa uma novelty por vez e faz rerun para atualizar a interface
        all_done = process_current_novelty()
        if all_done:
            st.session_state.automation_step = 'complete'
            # Fecha o navegador no final
            logger.info("Fechando o navegador...")
            if st.session_state.driver:
                st.session_state.driver.quit()
                st.session_state.driver = None
            st.session_state.is_running = False
        st.rerun()
    
    elif st.session_state.automation_step == 'complete':
        st.session_state.is_running = False
        st.success("Automação concluída com sucesso!")