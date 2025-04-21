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
import datetime
import plotly.express as px
from db_connection import get_execution_history  # Certifique-se de importar esta função
try:
    from db_connection import is_railway
except ImportError:
    def is_railway():
        return "RAILWAY_ENVIRONMENT" in os.environ

# Importa as funções de conexão com banco de dados com tratamento de erro
try:
    from db_connection import (
        init_database, 
        save_execution_results, 
        is_railway
    )
except ImportError:
    # Fallback sem banco de dados
    def init_database(): return None
    def save_execution_results(results): return None
    def is_railway(): return "RAILWAY_ENVIRONMENT" in os.environ

# Configurações padrão - Credenciais removidas do frontend conforme solicitado
DEFAULT_CREDENTIALS = {
    "email": "viniciuschegouoperacional@gmail.com",
    "password": "Viniciuschegou@1"
}

# Título e descrição
st.markdown("<h1 style='text-align: center;'>🇲🇽</h1>", unsafe_allow_html=True)
st.markdown("""
<style>
    .stButton>button {
        border: none !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
    }
    .stButton>button:hover {
        background-color: #f0f0f0 !important;
    }
    .metric-container {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin: 5px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

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
        required_modules = ["selenium", "webdriver_manager", "pandas"]
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

tab1, tab2 = st.tabs(["Execução Manual", "Relatório"])

# --- Conteúdo da Aba 1: Execução Manual ---
with tab1:
    st.subheader("Execução Manual")

    # Botão para iniciar automação dentro de um formulário
    with st.form("automation_form"):
        submit_button = st.form_submit_button("Iniciar Automação", use_container_width=True)

        if not dependencies_ok or not st.session_state.has_chromedriver:
            st.warning("⚠️ Verificação de dependências falhou. Veja o painel lateral.")

        if submit_button:
            # Verifica se já não está rodando para evitar múltiplos cliques
            if not st.session_state.is_running:
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
                # Pega as credenciais padrão (ajuste se necessário)
                st.session_state.email = DEFAULT_CREDENTIALS["email"]
                st.session_state.password = DEFAULT_CREDENTIALS["password"]
                st.session_state.use_headless = use_headless # Usa a configuração da sidebar
                st.session_state.start_time = time.time()
                st.success("Iniciando automação... Aguarde.")
                st.rerun() # Recarrega para iniciar o processo
            else:
                st.warning("Automação já está em execução.")

    # Exibe o status atual - AGORA DENTRO DA TAB 1
    st.subheader("Status da Execução Atual")
    if st.session_state.is_running:
        st.info("✅ Automação em execução...")

        # Botão para parar a automação
        if st.button("Parar Automação"):
            st.session_state.is_running = False

            # Fecha o navegador se estiver aberto
            if st.session_state.driver:
                try:
                    st.session_state.driver.quit()
                except Exception as e:
                    logger.warning(f"Erro ao tentar fechar o driver: {e}")
                st.session_state.driver = None

            st.warning("Automação interrompida pelo usuário.")
            # Gera um relatório parcial se algo foi processado
            if st.session_state.processed_items > 0:
                 generate_report() # Gera relatório mesmo se interrompido
            st.rerun()
    else:
        # Mostra status apenas se uma automação foi iniciada ou concluída nesta sessão
        if st.session_state.start_time is not None:
            if st.session_state.report:
                st.success("✅ Automação concluída!")
            elif st.session_state.processed_items > 0 or st.session_state.failed_count > 0:
                 st.warning("⚠️ Automação interrompida ou finalizada com erros.")
            # Não mostra "Aguardando início" aqui, pois isso é implícito se não estiver rodando
        else:
            st.info("Clique em 'Iniciar Automação' para começar.")


    # Exibe estatísticas da execução atual - AGORA DENTRO DA TAB 1
    # Só mostra se a automação já rodou ou está rodando
    if st.session_state.start_time is not None:
        st.subheader("Estatísticas da Execução Atual")
        cols = st.columns(3)
        with cols[0]:
            st.metric("Novelties Processadas", st.session_state.processed_items)
        with cols[1]:
            st.metric("Sucesso", st.session_state.success_count)
        with cols[2]:
            st.metric("Falhas", st.session_state.failed_count)

        # Barra de progresso - AGORA DENTRO DA TAB 1
        if st.session_state.total_items > 0:
            st.progress(st.session_state.progress)
            st.caption(f"Progresso: {st.session_state.processed_items}/{st.session_state.total_items} items")
        elif st.session_state.is_running and st.session_state.automation_step not in ['idle', 'setup', 'login', 'navigate']:
             # Mostra barra indeterminada se estiver rodando mas ainda não contou itens
             st.progress(0)
             st.caption("Calculando itens...")


        # Exibe erros da execução atual - AGORA DENTRO DA TAB 1
        if st.session_state.error_messages:
            st.subheader("Erros Detectados na Execução Atual")
            # Mostra apenas os 10 últimos erros para não poluir muito
            for error in st.session_state.error_messages[-10:]:
                st.error(error["message"])

        st.markdown("<hr style='margin: 20px 0; border-top: 1px solid #ddd;'>", unsafe_allow_html=True)

        # Log completo da execução atual - AGORA DENTRO DA TAB 1
        if 'show_log' not in st.session_state:
            st.session_state.show_log = False

        show_log = st.checkbox("Mostrar Log Completo da Execução Atual", value=st.session_state.show_log)
        st.session_state.show_log = show_log

        if st.session_state.show_log:
            log_container = st.container(height=400) # Define altura fixa para o container do log
            log_container.text_area(
                "Log Completo",
                value=st.session_state.log_output.getvalue(),
                height=380, # Altura interna um pouco menor
                key="log_area" # Chave para evitar problemas de atualização
            )

        # Relatório da ÚLTIMA execução manual - AGORA DENTRO DA TAB 1
        # Exibe apenas se a automação NÃO estiver rodando e um relatório foi gerado
        if st.session_state.report and not st.session_state.is_running:
            st.subheader("Relatório da Última Execução")
            report = st.session_state.report

            exec_time_sec = report.get("execution_time", 0)
            exec_time_min = exec_time_sec / 60

            st.write(f"Data/Hora: {report.get('execution_date', 'N/A')}")
            st.write(f"Duração: {exec_time_min:.2f} minutos ({exec_time_sec:.2f} segundos)")
            st.write(f"Total Processado com Sucesso: {report.get('total_processados', 0)}")
            st.write(f"Total Falhas: {report.get('total_falhas', 0)}")
            st.write(f"Guias Extras Fechadas: {report.get('guias_fechadas', 0)}")
            st.write(f"Opção de 1000 itens encontrada: {'Sim' if report.get('encontrou_paginacao') else 'Não'}")

            if report.get("total_falhas", 0) > 0:
                st.subheader("Detalhes das Falhas da Última Execução")
                failures_df = pd.DataFrame(report.get("itens_com_falha", []))
                # Renomeia colunas para clareza
                failures_df.rename(columns={'id': 'ID/Linha da Novelty', 'error': 'Erro'}, inplace=True)
                st.dataframe(failures_df, use_container_width=True)

# --- Conteúdo da Aba 2: Relatório Histórico ---
with tab2:
    st.subheader("Relatório Histórico de Execuções")

    # Filtros de data
    col1, col2 = st.columns(2)
    with col1:
        # Define data inicial padrão como 30 dias atrás
        default_start_date = datetime.date.today() - datetime.timedelta(days=30)
        start_date = st.date_input("Data Inicial", value=default_start_date, key="report_start_date")
    with col2:
        # Data final padrão é hoje
        default_end_date = datetime.date.today()
        end_date = st.date_input("Data Final", value=default_end_date, key="report_end_date")

    # Converte as datas para o formato string YYYY-MM-DD para a query
    # Garante que a data final inclua o dia todo
    start_date_str = start_date.strftime("%Y-%m-%d")
    # Adiciona hora final para incluir todo o dia final na query
    end_date_str = end_date.strftime("%Y-%m-%d") + " 23:59:59"

    # Botão para atualizar o relatório
    if st.button("Atualizar Relatório Histórico", key="update_report_history"):
        try:
            # Busca os dados do banco ao clicar no botão
            st.session_state.filtered_data = get_execution_history(start_date_str, end_date_str)
            st.rerun() # Recarrega para mostrar os dados atualizados
        except Exception as e:
            st.error(f"Erro ao buscar histórico do banco de dados: {e}")
            st.session_state.filtered_data = pd.DataFrame() # Define como vazio em caso de erro

    # Inicializa a variável filtered_data se não existir
    if 'filtered_data' not in st.session_state:
         try:
            # Tenta carregar na primeira vez também
            st.session_state.filtered_data = get_execution_history(start_date_str, end_date_str)
         except Exception as e:
            st.error(f"Erro ao buscar histórico do banco de dados: {e}")
            st.session_state.filtered_data = pd.DataFrame()

    # Exibe os dados em formato de tabela
    if st.session_state.filtered_data is None or st.session_state.filtered_data.empty:
        st.info("Não há dados de execução para o período selecionado.")
    else:
        # Faz uma cópia para evitar modificar o estado original
        display_df = st.session_state.filtered_data.copy()

        # --- MODIFICAÇÃO: Converte tempo para minutos ---
        # Garante que a coluna de tempo seja numérica, tratando possíveis erros
        display_df['execution_time'] = pd.to_numeric(display_df['execution_time'], errors='coerce')
        # Remove linhas onde o tempo não pôde ser convertido
        display_df.dropna(subset=['execution_time'], inplace=True)
        # Calcula os minutos
        display_df['Tempo (minutos)'] = (display_df['execution_time'] / 60) #.round(2) Deixando sem arredondar para métrica média
        display_df['Tempo Formatado (min)'] = display_df['Tempo (minutos)'].apply(lambda x: f"{x:.2f}")

        # Converte e formata a data
        try:
            display_df['execution_date'] = pd.to_datetime(display_df['execution_date'])
            display_df['Data/Hora'] = display_df['execution_date'].dt.strftime('%d/%m/%Y %H:%M')
        except Exception as e:
            logger.warning(f"Erro ao formatar data do histórico: {e}")
            display_df['Data/Hora'] = display_df['execution_date'].astype(str) # Fallback para string

        # Renomeia colunas para português
        display_df.rename(columns={
            'successful': 'Sucessos',
            'failed': 'Falhas',
            # Mantendo a coluna original para cálculo, mas não exibindo
            # 'execution_time': 'Tempo Original (s)'
        }, inplace=True)

        # Define as colunas a serem exibidas
        # Exibe o tempo FORMATADO em minutos
        display_columns = ['Data/Hora', 'Sucessos', 'Falhas', 'Tempo Formatado (min)']

        st.dataframe(
            display_df[display_columns],
            use_container_width=True,
            # Oculta o índice do dataframe
            hide_index=True,
        )

        # Estatísticas agregadas para o período
        st.subheader("Totais para o Período Selecionado")
        # total_novelties = display_df['total_processed'].sum() # Coluna 'total_processed' não parece existir na query, usar Sucessos + Falhas
        total_success = display_df['Sucessos'].sum()
        total_failed = display_df['Falhas'].sum()
        total_processed_calc = total_success + total_failed
        # Calcula a média dos minutos
        avg_time_min = display_df['Tempo (minutos)'].mean() if not display_df['Tempo (minutos)'].empty else 0

        stats_cols = st.columns(4)
        with stats_cols[0]:
            st.metric("Total Processado", f"{total_processed_calc}")
        with stats_cols[1]:
            st.metric("Total Sucessos", f"{total_success}")
        with stats_cols[2]:
            st.metric("Total Falhas", f"{total_failed}")
        with stats_cols[3]:
            st.metric("Tempo Médio (min)", f"{avg_time_min:.2f}")


# Rodapé (fora das abas)
st.markdown("---")
st.caption("Automação Dropi Novelties © 2025")

# Funções de automação (adaptadas para serem executadas passo a passo)
def setup_driver():
    """Configura o driver do Selenium."""
    logger.info("Iniciando configuração do driver Chrome...")
    
    chrome_options = Options()
    
    # No Railway sempre use headless
    if is_railway() or st.session_state.use_headless:
        logger.info("Modo headless ativado")
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
    else:
        logger.info("Modo headless desativado - navegador será visível")
    
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    
    try:
        if is_railway():
            # No Railway, usa o Chrome já instalado pelo Dockerfile
            logger.info("Inicializando o driver Chrome no Railway...")
            service = Service()
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            # Localmente, usa o webdriver_manager
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
    """
    Processa a novelty atual na lista (st.session_state.rows).
    Retorna True se o processamento deve parar (concluído ou erro crítico).
    Retorna False se deve continuar para a próxima novelty.
    """
    driver = st.session_state.get('driver') # Pega o driver do estado da sessão
    if not driver:
        logger.error("Driver não encontrado no estado da sessão ao iniciar process_current_novelty. Interrompendo.")
        st.session_state.is_running = False
        generate_report() # Tenta gerar relatório antes de parar
        return True # Indica que parou

    rows = st.session_state.get('rows', [])
    total_items = len(rows)
    current_row_index = st.session_state.get('current_row_index', 0)

    # Verifica se há rows para processar
    if not rows:
        logger.info("Nenhuma novidade encontrada na tabela para processar.")
        generate_report() # Gera relatório mesmo sem itens
        # Garante fechamento do driver se não há itens
        if driver:
             try: driver.quit()
             except: pass
             st.session_state.driver = None
        return True # Indica que terminou

    # Verifica se todas as rows já foram processadas
    if current_row_index >= total_items:
        logger.info("Todas as novelties foram processadas.")
        generate_report() # Gera relatório final
        # Garante fechamento do driver ao concluir
        if driver:
             try: driver.quit()
             except: pass
             st.session_state.driver = None
        return True # Indica que terminou

    # Pega a row atual
    row = rows[current_row_index]
    row_id = f"Linha {current_row_index + 1}" # ID Padrão

    try:
        # Tenta obter um ID mais específico da primeira célula, se possível
        try:
            # Espera um pouco para a célula existir se a tabela carregou dinamicamente
            WebDriverWait(row, 2).until(EC.presence_of_element_located((By.TAG_NAME, "td")))
            first_cell = row.find_elements(By.TAG_NAME, "td")[0]
            row_id_text = first_cell.text.strip()
            if row_id_text: # Usa o texto da célula se não estiver vazio
                 row_id = row_id_text
            logger.info(f"Processando novelty ID: {row_id} ({current_row_index + 1}/{total_items})")
        except Exception as e_id:
            logger.warning(f"Não foi possível obter ID específico para linha {current_row_index + 1}: {e_id}. Usando ID genérico.")
            logger.info(f"Processando {row_id}/{total_items}")

        # Atualiza o progresso ANTES de tentar processar
        st.session_state.processed_items = current_row_index + 1
        if total_items > 0:
             st.session_state.progress = (current_row_index + 1) / total_items
        else:
             st.session_state.progress = 1.0 # Completo se não houver linhas

        # --- ETAPA: Esperar Modais Anteriores Fecharem ---
        try:
            logger.info(f"Aguardando desaparecimento de modais antes de processar {row_id}...")
            # Espera até 10 segundos pela invisibilidade de QUALQUER modal do ng-bootstrap
            WebDriverWait(driver, 10).until(
                EC.invisibility_of_element_located((By.TAG_NAME, "ngb-modal-window"))
            )
            logger.info("Nenhuma modal ativa detectada.")
        except TimeoutException:
            logger.warning(f"Modal ainda estava visível após 10s antes de processar {row_id}, tentando fechar ativamente...")
            # Tenta fechar ativamente qualquer modal residual
            try:
                modals = driver.find_elements(By.XPATH, "//ngb-modal-window[contains(@class, 'show')]")
                logger.info(f"Encontradas {len(modals)} modais visíveis residuais.")
                for modal in modals:
                    # Tenta clicar no botão de fechar (X) dentro da modal
                    try:
                        close_buttons = modal.find_elements(By.XPATH, ".//button[contains(@class, 'close') or contains(@aria-label, 'Close')]")
                        if close_buttons and close_buttons[0].is_displayed():
                            logger.info("Clicando no botão fechar (X) da modal residual...")
                            driver.execute_script("arguments[0].click();", close_buttons[0])
                            time.sleep(1.5) # Pausa maior após fechar
                            # Verifica se a modal realmente fechou
                            try:
                                WebDriverWait(driver, 3).until(EC.invisibility_of_element(modal))
                                logger.info("Modal residual fechada com sucesso.")
                            except TimeoutException:
                                logger.error("Modal residual não fechou após clique no X.")
                            break # Processa apenas a primeira modal encontrada
                    except NoSuchElementException:
                         logger.warning("Botão fechar (X) não encontrado na modal residual.")
                    except Exception as close_err_loop:
                         logger.error(f"Erro ao tentar fechar modal residual no loop: {close_err_loop}")
            except Exception as close_err:
                 logger.error(f"Erro geral ao tentar fechar modais residuais: {close_err}")
        except Exception as wait_err:
            logger.error(f"Erro inesperado ao aguardar modais fecharem: {wait_err}")


        # Encontra o botão Save verde na linha atual
        logger.info(f"Procurando botão 'Save' para a novelty {row_id}...")
        # Usa espera explícita para garantir que o botão exista na linha antes de interagir
        save_button = WebDriverWait(row, 5).until(
             EC.presence_of_element_located((By.XPATH, ".//button[contains(@class, 'btn-success')]"))
        )

        # --- MODIFICAÇÃO: Scroll e clique com JavaScript ---
        logger.info(f"Tentando clicar no botão 'Save' para {row_id} via JavaScript...")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", save_button) # Centraliza o botão
        time.sleep(0.7) # Pequena pausa após scroll
        # Tenta clicar repetidamente por um curto período se falhar
        click_attempts = 0
        while click_attempts < 3:
            try:
                driver.execute_script("arguments[0].click();", save_button)
                logger.info(f"Botão 'Save' para {row_id} clicado (tentativa {click_attempts+1}).")
                break # Sucesso, sai do loop
            except Exception as click_e:
                click_attempts += 1
                logger.warning(f"Tentativa {click_attempts} de clicar no botão Save falhou: {click_e}. Retentando em 0.5s...")
                if click_attempts >= 3:
                     logger.error("Falha ao clicar no botão Save após múltiplas tentativas.")
                     raise click_e # Relança a exceção se todas as tentativas falharem
                time.sleep(0.5)


        # Espera pelo popup (aumentar um pouco a espera pode ajudar)
        time.sleep(4) # Mantido 4 segundos

        # Tenta clicar no botão "Yes" ou "Sim"
        yes_clicked = False
        logger.info("Procurando botão 'Yes'/'Sim' no popup...")
        possible_yes_texts = ["Yes", "Sim"] # Prioriza estes
        for text in possible_yes_texts:
            try:
                # Espera explícita pelo botão ser clicável (XPATH mais específico para modais)
                xpath_yes = f"//ngb-modal-window[contains(@class, 'show')]//button[normalize-space()='{text}']"
                yes_button = WebDriverWait(driver, 7).until( EC.element_to_be_clickable((By.XPATH, xpath_yes)) )
                logger.info(f"Botão com texto '{text}' encontrado, tentando clicar...")
                driver.execute_script("arguments[0].scrollIntoView(true);", yes_button)
                driver.execute_script("arguments[0].click();", yes_button) # JS Click
                logger.info(f"Clicado no botão '{text}'")
                yes_clicked = True
                break # Sai do loop se clicou com sucesso
            except TimeoutException:
                logger.debug(f"Botão '{text}' não encontrado ou não clicável em 7 segundos.")
            except ElementClickInterceptedException as e:
                 logger.warning(f"Clique no botão '{text}' interceptado: {e}. Tentando próximo.")
            except Exception as e:
                logger.error(f"Erro inesperado ao tentar clicar no botão '{text}': {e}")

        # Se não clicou via texto, tenta outras estratégias (modal-footer, classe)
        if not yes_clicked:
            logger.warning("Não foi possível clicar em 'Yes'/'Sim' pelo texto. Tentando estratégias alternativas...")
            try:
                 # Tenta pelo primeiro botão dentro do rodapé da modal visível
                 xpath_footer_btn = "//ngb-modal-window[contains(@class, 'show')]//div[contains(@class, 'modal-footer')]//button"
                 footer_buttons = WebDriverWait(driver, 3).until(EC.presence_of_all_elements_located((By.XPATH, xpath_footer_btn)))
                 if footer_buttons:
                     logger.info("Tentando clicar no primeiro botão do modal-footer...")
                     first_button = footer_buttons[0]
                     if first_button.is_displayed() and first_button.is_enabled():
                         driver.execute_script("arguments[0].click();", first_button)
                         logger.info(f"Clicado no primeiro botão do modal-footer (texto: '{first_button.text}')")
                         yes_clicked = True
                     else:
                          logger.warning("Primeiro botão do footer não está clicável.")
                 else:
                     logger.debug("Nenhum botão encontrado no modal-footer.")
            except TimeoutException:
                logger.debug("Nenhum botão encontrado no modal-footer em 3 segundos.")
            except Exception as e_footer:
                logger.error(f"Erro ao tentar clicar botão do modal-footer: {e_footer}")

        if not yes_clicked:
             logger.error("Falha crítica: Não foi possível clicar no botão 'Yes'/'Sim' ou equivalente.")
             # Decide se deve continuar ou parar - por ora, vamos tentar continuar, mas logando como erro grave.


        # Espera após clicar no botão Yes (ou tentar clicar)
        time.sleep(4) # Mantido 4 segundos

        # Tenta encontrar o formulário, extrair endereço, preencher e salvar
        logger.info("Procurando formulário e preenchendo dados...")
        address = extract_address_from_page(driver) # Tenta extrair endereço
        form_modal = None
        form_found = False
        try:
            # Tenta encontrar o formulário dentro de uma modal visível OU diretamente no body
            xpath_form = "//ngb-modal-window[contains(@class, 'show')]//form | //body//form[.//label[contains(text(), 'Solución')]]"
            form_modal = WebDriverWait(driver, 7).until( EC.visibility_of_element_located((By.XPATH, xpath_form)) )
            logger.info("Formulário encontrado dentro de modal ou body.")
            form_found = True
        except TimeoutException:
             logger.warning("Formulário não encontrado em modal/body visível em 7s.")
        except Exception as e_form:
             logger.error(f"Erro ao procurar formulário: {e_form}")


        if form_found and form_modal:
            solution_filled = fill_solution_field(driver, form_modal, address)
            if solution_filled:
                save_clicked = click_save_button(driver) # Tenta clicar em Salvar/Guardar
                if save_clicked:
                    logger.info("Botão Salvar/Guardar do formulário clicado.")
                    time.sleep(5) # Mantido 5 segundos
                else:
                    logger.warning("Não foi possível clicar no botão Salvar/Guardar do formulário.")
            else:
                logger.warning("Campo Solución não foi preenchido. Tentando salvar mesmo assim...")
                save_clicked = click_save_button(driver)
                if save_clicked: time.sleep(5)
        else:
            logger.error("Não foi possível encontrar o formulário para preencher. Pulando preenchimento.")
            # Mesmo sem formulário, pode haver um popup de confirmação, então continuamos


        # Espera e clica no popup "OK" final
        logger.info("Procurando popup de confirmação final com botão OK/Aceptar...")
        ok_clicked = False
        try:
            # Espera explícita pelo botão OK ser clicável em QUALQUER modal visível
            xpath_ok = "//ngb-modal-window[contains(@class, 'show')]//button[normalize-space()='OK' or normalize-space()='Ok' or normalize-space()='Aceptar']"
            ok_button = WebDriverWait(driver, 10).until( EC.element_to_be_clickable((By.XPATH, xpath_ok)) )
            logger.info(f"Botão '{ok_button.text}' encontrado, clicando...")
            driver.execute_script("arguments[0].click();", ok_button) # JS Click
            ok_clicked = True
            logger.info("Botão OK/Aceptar clicado com sucesso.")
            time.sleep(2.5) # Aumenta um pouco a pausa após clicar OK
            # Espera a modal do OK fechar
            WebDriverWait(driver, 5).until(EC.invisibility_of_element(ok_button))
            logger.info("Modal de confirmação OK fechada.")
        except TimeoutException:
            logger.warning("Não foi possível encontrar/clicar no botão OK/Aceptar OU modal não fechou em tempo.")
            # Tenta fechar qualquer modal residual como fallback
            try:
                modals = driver.find_elements(By.XPATH, "//ngb-modal-window[contains(@class, 'show')]")
                if modals:
                    close_buttons = modals[0].find_elements(By.XPATH, ".//button[contains(@class, 'close') or contains(@aria-label, 'Close')]")
                    if close_buttons and close_buttons[0].is_displayed():
                        driver.execute_script("arguments[0].click();", close_buttons[0])
                        logger.info("Modal residual fechada via botão X após falha no OK.")
                        time.sleep(1)
            except Exception as close_err:
                logger.error(f"Erro ao tentar fechar modal residual após falha no OK: {close_err}")
        except Exception as e:
             logger.error(f"Erro inesperado ao procurar/clicar botão OK: {e}")


        # Verifica se há novas guias abertas
        check_and_close_tabs()

        # Incrementa contador de sucesso
        st.session_state.success_count += 1
        logger.info(f"Novelty {row_id} processada com SUCESSO!")

    except Exception as e:
        # --- BLOCO DE CAPTURA DE ERRO PRINCIPAL ---
        error_msg = f"Erro CRÍTICO ao processar novelty {row_id}: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc()) # Loga o traceback completo para depuração

        # Adiciona à lista de erros para exibição na UI
        st.session_state.error_messages.append({
            "type": "error",
            "message": error_msg # Mensagem para a UI
        })
        # Adiciona aos itens com falha para o relatório
        st.session_state.failed_items.append({"id": row_id, "error": str(e)})
        st.session_state.failed_count = len(st.session_state.failed_items)

        # Tenta tirar um screenshot da tela no momento do erro
        screenshot_filename = f"error_{row_id.replace(' ', '_').replace('/', '-')}_{datetime.datetime.now().strftime('%H%M%S')}.png"
        try:
            driver.save_screenshot(screenshot_filename)
            logger.info(f"Screenshot do erro salvo como: {screenshot_filename}")
        except Exception as ss_error:
            logger.error(f"Falha ao tirar screenshot do erro: {ss_error}")

        # Chama a função de tratamento de erro (fluxo alternativo, fechar modais)
        handle_error(row, row_id) # Passa a linha e o ID

        # --- FIM DO BLOCO DE CAPTURA DE ERRO ---

    # Incrementa o índice para a próxima novelty, INDEPENDENTE de sucesso ou falha no try/except principal
    st.session_state.current_row_index += 1
    next_index = st.session_state.current_row_index

    # Pequena pausa antes de ir para o próximo item ou finalizar
    time.sleep(1.5)

    # Verifica se foi a última novelty processada (usando o próximo índice)
    if next_index >= total_items:
        logger.info(f"Fim do processamento. Último índice processado: {current_row_index-1}. Total de itens: {total_items}.")
        # Gera relatório e fecha driver ANTES de retornar True
        generate_report()
        if driver:
             logger.info("Fechando o driver no final do processamento.")
             try:
                 driver.quit()
             except Exception as quit_e:
                 logger.error(f"Erro ao fechar driver no final: {quit_e}")
             st.session_state.driver = None
        return True # Indica que terminou
    else:
        # Ainda há itens, retorna False para indicar que deve continuar
        logger.debug(f"Indo para a próxima novelty (índice {next_index}).")
        return False # Continua o loop na próxima iteração do Streamlit
    
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

with tab2:
    st.subheader("Relatório de Execuções")
    
    # Filtros de data
    col1, col2 = st.columns(2)
    with col1:
        default_start_date = datetime.datetime.now() - datetime.timedelta(days=30)
        start_date = st.date_input("Data Inicial", value=default_start_date)
    with col2:
        end_date = st.date_input("Data Final", value=datetime.datetime.now())
    
    # Converte as datas para o formato string YYYY-MM-DD
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d") + " 23:59:59"
    
    # Botão para atualizar o relatório
    if st.button("Atualizar Relatório", key="update_report"):
        st.session_state.filtered_data = get_execution_history(start_date_str, end_date_str)
    
    # Inicializa a variável filtered_data
    if 'filtered_data' not in st.session_state:
        st.session_state.filtered_data = get_execution_history(start_date_str, end_date_str)
    
    # Exibe os dados em formato de tabela
    if st.session_state.filtered_data.empty:
        st.info("Não há dados de execução para o período selecionado.")
    else:
        # Formatação da tabela
        display_df = st.session_state.filtered_data.copy()
        display_df['execution_date'] = pd.to_datetime(display_df['execution_date'])
        display_df['data_execucao'] = display_df['execution_date'].dt.strftime('%d/%m/%Y %H:%M')
        
        # Renomeia colunas para português
        display_df.rename(columns={
            'total_processed': 'Total Processado',
            'successful': 'Sucessos',
            'failed': 'Falhas',
            'execution_time': 'Tempo (segundos)'
        }, inplace=True)
        
        # Exibe a tabela
        display_columns = ['data_execucao', 'Total Processado', 'Sucessos', 'Falhas', 'Tempo (segundos)']
        st.dataframe(display_df[display_columns], width=800)
        
        # Estatísticas
        total_novelties = display_df['Total Processado'].sum()
        total_success = display_df['Sucessos'].sum()
        total_failed = display_df['Falhas'].sum()
        avg_time = display_df['Tempo (segundos)'].mean()
        
        # Métricas
        stats_cols = st.columns(4)
        with stats_cols[0]:
            st.metric("Total de Novelties", f"{total_novelties}")
        with stats_cols[1]:
            st.metric("Total de Sucessos", f"{total_success}")
        with stats_cols[2]:
            st.metric("Total de Falhas", f"{total_failed}")
        with stats_cols[3]:
            st.metric("Tempo Médio (s)", f"{avg_time:.2f}")

# Processamento da automação baseado no estado atual
if st.session_state.is_running:
    current_step = st.session_state.get('automation_step', 'idle') # Pega o passo atual
    logger.info(f"--- Executando passo da automação: {current_step} ---")

    try:
        if current_step == 'setup':
            st.info("Passo 1/5: Configurando o navegador (driver)...")
            if setup_driver():
                logger.info("Driver configurado com sucesso.")
                st.session_state.automation_step = 'login'
                st.rerun() # Vai para o próximo passo
            else:
                logger.error("Falha crítica ao configurar o driver Chrome.")
                st.error("Falha ao configurar o driver Chrome. Verifique os logs e a instalação do Chrome/ChromeDriver (se local).")
                st.session_state.is_running = False
                st.rerun() # Para a execução e atualiza a UI

        elif current_step == 'login':
            st.info("Passo 2/5: Realizando login no Dropi...")
            if login():
                logger.info("Login realizado com sucesso.")
                st.session_state.automation_step = 'navigate'
                st.rerun() # Vai para o próximo passo
            else:
                logger.error("Falha crítica no login.")
                st.error("Falha no login. Verifique as credenciais e a estrutura da página de login.")
                # Tenta fechar o driver em caso de falha no login
                if st.session_state.driver:
                    try:
                        st.session_state.driver.quit()
                    except Exception as e:
                         logger.warning(f"Erro ao fechar driver após falha no login: {e}")
                    st.session_state.driver = None
                st.session_state.is_running = False
                st.rerun() # Para a execução e atualiza a UI

        elif current_step == 'navigate':
            st.info("Passo 3/5: Navegando até a página de Novelties...")
            if navigate_to_novelties():
                logger.info("Navegação para Novelties concluída.")
                st.session_state.automation_step = 'configure'
                st.rerun() # Vai para o próximo passo
            else:
                logger.error("Falha crítica ao navegar para Novelties.")
                st.error("Falha ao navegar até Novelties. Verifique a estrutura do menu/links.")
                if st.session_state.driver:
                    try:
                        st.session_state.driver.quit()
                    except Exception as e:
                         logger.warning(f"Erro ao fechar driver após falha na navegação: {e}")
                    st.session_state.driver = None
                st.session_state.is_running = False
                st.rerun() # Para a execução e atualiza a UI

        elif current_step == 'configure':
            st.info("Passo 4/5: Configurando exibição e buscando novelties...")
            if configure_entries_display():
                logger.info(f"Configuração concluída. Encontradas {st.session_state.total_items} novelties.")
                if st.session_state.total_items == 0:
                     logger.warning("Nenhuma novelty encontrada para processar.")
                     st.warning("Nenhuma novelty encontrada na tabela.")
                     st.session_state.automation_step = 'complete' # Pula para completo se não há itens
                else:
                     st.session_state.automation_step = 'process' # Inicia processamento
                st.rerun() # Vai para o próximo passo (processar ou completar)
            else:
                logger.error("Falha crítica ao configurar exibição ou buscar novelties.")
                st.error("Falha ao configurar exibição de 1000 itens ou ao buscar linhas da tabela.")
                if st.session_state.driver:
                    try:
                        st.session_state.driver.quit()
                    except Exception as e:
                         logger.warning(f"Erro ao fechar driver após falha na configuração: {e}")
                    st.session_state.driver = None
                st.session_state.is_running = False
                st.rerun() # Para a execução e atualiza a UI

        elif current_step == 'process':
            st.info(f"Passo 5/5: Processando novelty {st.session_state.current_row_index + 1} de {st.session_state.total_items}...")
            # Processa UMA novelty por vez e retorna True se acabou, False se continua
            all_done = process_current_novelty()

            if all_done:
                # Se process_current_novelty retornou True, significa que terminou (ou houve erro crítico)
                logger.info("Processamento de todas as novelties concluído ou interrompido.")
                st.session_state.automation_step = 'complete'
                # O fechamento do driver e a geração do relatório agora acontecem DENTRO de process_current_novelty ou no passo 'complete'
            # Sempre faz rerun para atualizar a UI ou ir para o próximo item/passo 'complete'
            st.rerun()

        elif current_step == 'complete':
            logger.info("--- Automação concluída ---")
            st.success("Automação finalizada!")
            # Garante que o driver seja fechado se ainda estiver aberto
            if st.session_state.driver:
                logger.info("Fechando o navegador (garantia final)...")
                try:
                    st.session_state.driver.quit()
                    st.session_state.driver = None
                except Exception as e:
                    logger.error(f"Erro ao fechar o driver na etapa 'complete': {e}")
                    st.session_state.driver = None # Garante que seja None
            # Garante que o relatório seja gerado se ainda não foi
            if not st.session_state.report:
                 generate_report()
            st.session_state.is_running = False # Marca como não rodando
            st.rerun() # Atualiza a UI final

        else:
            # Estado inválido, interrompe
            logger.error(f"Estado de automação inválido: {current_step}")
            st.error(f"Erro interno: Estado de automação desconhecido '{current_step}'.")
            if st.session_state.driver:
                try:
                    st.session_state.driver.quit()
                except Exception as e:
                     logger.warning(f"Erro ao fechar driver em estado inválido: {e}")
                st.session_state.driver = None
            st.session_state.is_running = False
            st.rerun()

    except Exception as global_e:
        # Captura qualquer erro não tratado nos passos
        logger.error(f"Erro global não capturado durante a automação no passo {current_step}: {global_e}")
        logger.error(traceback.format_exc())
        st.error(f"Ocorreu um erro inesperado: {global_e}")
        # Tenta fechar o driver
        if st.session_state.driver:
            try:
                st.session_state.driver.quit()
            except Exception as e:
                 logger.warning(f"Erro ao fechar driver após erro global: {e}")
            st.session_state.driver = None
        st.session_state.is_running = False
        # Tenta gerar um relatório parcial
        generate_report()
        st.rerun() # Para a execução e atualiza a UI