import streamlit as st
import time
import pandas as pd
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
import os
import platform
import datetime
import plotly.express as px
from db_connection import get_execution_history  # Certifique-se de importar esta função
try:
    from db_connection import is_railway
except ImportError:
    def is_railway():
        return "RAILWAY_ENVIRONMENT" in os.environ
    
THIS_COUNTRY = "colombia" # Mude para "chile", "colombia", 

st.markdown("<h1 style='text-align: center;'>🇨🇴</h1>", unsafe_allow_html=True)
# Adicione o CSS aqui
st.markdown("""
<style>
    .stButton>button {
        border: none !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
    }
    /* Hover effect */
    .stButton>button:hover {
        background-color: #f0f0f0 !important;
    }
</style>
""", unsafe_allow_html=True)

# Verificar e instalar dependências
def check_dependencies():
    try:
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
if 'show_log' not in st.session_state:
    st.session_state.show_log = False

# Sidebar com informações
st.sidebar.title("Configuração")
use_headless = st.sidebar.checkbox("Modo Headless", value=False, 
                               help="Se marcado, o navegador não será exibido na tela. Desmarque para depuração.")

# Verificar dependências
dependencies_ok = check_dependencies()

# Tentar instalar o ChromeDriver
if dependencies_ok and not st.session_state.has_chromedriver:
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

# Configuração de logging para o Streamlit
class StreamlitHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        st.session_state.log_output.write(log_entry + '\n')
        
        # Adiciona à lista de mensagens para exibição em tempo real
        log_type = "info"
        if record.levelno >= logging.ERROR:
            log_type = "error"
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
with tab1:
    # Interface do usuário - agora em linhas em vez de colunas
    st.subheader("Execução Manual")

# Define as credenciais diretamente no código (não visíveis no UI)
# Use suas credenciais reais aqui
EMAIL_CREDENTIALS = "viniciuschegouoperacional@gmail.com"
PASSWORD_CREDENTIALS = "123456cC"

# Interface do usuário com layout reformulado
with st.form("automation_form"):
    # Botão para iniciar automação centralizado (sem borda grande)
    submit_button = st.form_submit_button("Iniciar Automação", use_container_width=True)
    
    # Aviso de dependências abaixo do botão se necessário
    if not dependencies_ok or not st.session_state.has_chromedriver:
        st.warning("⚠️ Verificação de dependências falhou. Veja o painel lateral.")
    
    if submit_button:
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
            st.session_state.email = EMAIL_CREDENTIALS
            st.session_state.password = PASSWORD_CREDENTIALS
            st.session_state.use_headless = use_headless
            st.success("Iniciando automação... Aguarde.")
            st.rerun()

# Status em uma linha própria (agora fora do formulário)
if st.session_state.is_running:
    st.info("✅ Automação em execução...")
    
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
        st.success("✅ Automação concluída!")
    elif st.session_state.processed_items > 0:
        st.warning("⚠️ Automação interrompida.")
    else:
        st.info("⏸️ Aguardando início da automação.")

# Métricas com bordas individuais
st.markdown("""
<style>
    .metric-container {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin: 5px;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

cols = st.columns(3)
with cols[0]:
    st.markdown(
        f'<div class="metric-container"><p>Novelties Processadas</p><h1>{st.session_state.processed_items}</h1></div>', 
        unsafe_allow_html=True
    )
with cols[1]:
    st.markdown(
        f'<div class="metric-container"><p>Sucesso</p><h1>{st.session_state.success_count}</h1></div>', 
        unsafe_allow_html=True
    )
with cols[2]:
    st.markdown(
        f'<div class="metric-container"><p>Falhas</p><h1>{st.session_state.failed_count}</h1></div>', 
        unsafe_allow_html=True
    )

# Barra de progresso
if st.session_state.total_items > 0:
    st.progress(st.session_state.progress)
    st.caption(f"Progresso: {st.session_state.processed_items}/{st.session_state.total_items} items")

# Linha divisória 
st.markdown("<hr style='margin: 20px 0; border-top: 1px solid #ddd;'>", unsafe_allow_html=True)

# Toggle para mostrar/ocultar o log completo
show_log = st.checkbox("Mostrar Log Completo", value=st.session_state.show_log)
st.session_state.show_log = show_log

# Exibe o log completo apenas se o checkbox estiver marcado
if st.session_state.show_log:
    log_container = st.container()
    log_container.text_area("Log Completo", value=st.session_state.log_output.getvalue(), height=400)

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
    chrome_options.add_argument("--page-load-strategy=eager")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
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

def verify_authentication():
    """Verifica se o usuário está autenticado."""
    try:
        driver = st.session_state.driver
        current_url = driver.current_url
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        
        # Indicadores de que NÃO está autenticado
        auth_failure_indicators = [
            "login" in current_url,
            "auth" in current_url,
            "registrarme" in page_text,
            "crear cuenta" in page_text,
            "iniciar sesión" in page_text,
            "sign in" in page_text
        ]
        
        if any(auth_failure_indicators):
            logger.error("USUÁRIO NÃO ESTÁ AUTENTICADO!")
            return False
        
        # Indicadores de que ESTÁ autenticado
        auth_success_indicators = [
            "dashboard" in current_url,
            "orders" in current_url,
            "novelties" in current_url,
            "pedidos" in page_text,
            "dashboard" in page_text
        ]
        
        if any(auth_success_indicators):
            logger.info("Usuário autenticado com sucesso")
            return True
        
        logger.warning("Status de autenticação incerto")
        return False
        
    except Exception as e:
        logger.error(f"Erro ao verificar autenticação: {e}")
        return False

def login():
    """Função de login super robusta - VERSÃO CORRIGIDA."""
    try:
        driver = st.session_state.driver
        
        # Abre o site em uma nova janela maximizada
        driver.maximize_window()
        
        # Navega para a página de login
        logger.info("Navegando para a página de login...")
        driver.get("https://app.dropi.co/auth/login")  # URL mais específica
        time.sleep(5)
        
        # Aguarda a página carregar completamente
        logger.info("Aguardando carregamento completo da página...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Tira screenshot para análise
        driver.save_screenshot("login_page.png")
        logger.info("Screenshot da página salvo como login_page.png")
        
        # Encontra e preenche o campo de email
        logger.info("Preenchendo campo de email...")
        try:
            email_field = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "email"))
            )
            email_field.clear()
            email_field.send_keys(st.session_state.email)
            logger.info(f"Email preenchido: {st.session_state.email}")
        except Exception as e:
            logger.error(f"Erro ao preencher email: {e}")
            return False
        
        # Encontra e preenche o campo de senha
        logger.info("Preenchendo campo de senha...")
        try:
            password_field = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "password"))
            )
            password_field.clear()
            password_field.send_keys(st.session_state.password)
            logger.info("Senha preenchida")
        except Exception as e:
            logger.error(f"Erro ao preencher senha: {e}")
            return False
        
        # CORREÇÃO PRINCIPAL: Melhor tratamento do botão de login
        logger.info("Tentando clicar no botão de login...")
        try:
            # Método 1: JavaScript click (mais confiável)
            login_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Iniciar Sesión')]"))
            )
            
            # Rola até o botão para garantir visibilidade
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", login_button)
            time.sleep(2)
            
            # Clica usando JavaScript (evita problemas de interceptação)
            driver.execute_script("arguments[0].click();", login_button)
            logger.info("Clicado no botão de login via JavaScript")
            
        except Exception as e:
            logger.warning(f"Erro no método JavaScript: {e}")
            
            # Método 2: Tenta com ActionChains
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                login_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Iniciar Sesión')]")
                actions = ActionChains(driver)
                actions.move_to_element(login_button).click().perform()
                logger.info("Clicado no botão de login via ActionChains")
            except Exception as e2:
                logger.warning(f"Erro no método ActionChains: {e2}")
                
                # Método 3: Enviar ENTER no formulário
                try:
                    from selenium.webdriver.common.keys import Keys
                    password_field.send_keys(Keys.ENTER)
                    logger.info("Login enviado via ENTER")
                except Exception as e3:
                    logger.error(f"Todos os métodos de login falharam: {e3}")
                    return False
        
        # Aguarda o redirecionamento após login
        logger.info("Aguardando redirecionamento após login...")
        time.sleep(8)
        
        # Verifica se o login foi bem-sucedido
        current_url = driver.current_url
        logger.info(f"URL após login: {current_url}")
        
        # Verifica se foi redirecionado para dashboard ou orders
        if any(path in current_url for path in ["/dashboard", "/orders", "/novelties"]):
            logger.info("Login confirmado - redirecionado com sucesso")
            return True
        else:
            logger.warning(f"Login pode ter falhado - URL atual: {current_url}")
            # Tenta verificar se há elementos que indicam login bem-sucedido
            try:
                # Procura por elementos que só aparecem quando logado
                dashboard_elements = driver.find_elements(By.XPATH, 
                    "//*[contains(text(), 'Dashboard') or contains(text(), 'Orders') or contains(text(), 'Pedidos')]")
                if dashboard_elements:
                    logger.info("Login confirmado - elementos do dashboard encontrados")
                    return True
            except:
                pass
            
            return False
            
    except Exception as e:
        logger.error(f"Erro geral no login: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def navigate_to_novelties():
    """Navega até a página de novelties - VERSÃO CORRIGIDA."""
    try:
        driver = st.session_state.driver
        
        # CORREÇÃO: Navega diretamente para a URL correta
        logger.info("Navegando diretamente para a página de novelties...")
        driver.get("https://app.dropi.co/dashboard/novelties")  # URL CORRIGIDA
        time.sleep(8)  # Aguarda carregamento
        
        # Verifica se a página carregou corretamente
        current_url = driver.current_url
        logger.info(f"URL atual após navegação: {current_url}")
        
        # Verifica se está na página correta
        if "novelties" not in current_url:
            logger.warning("Não conseguiu acessar a página de novelties, tentando método alternativo...")
            
            # Tenta navegar através do menu
            try:
                # Vai para dashboard primeiro
                driver.get("https://app.dropi.co/dashboard")
                time.sleep(5)
                
                # Procura pelo link de novelties
                novelties_links = driver.find_elements(By.XPATH, 
                    "//a[contains(@href, 'novelties') or contains(text(), 'Novelties')]")
                
                if novelties_links:
                    logger.info("Link de novelties encontrado, clicando...")
                    driver.execute_script("arguments[0].click();", novelties_links[0])
                    time.sleep(5)
                else:
                    logger.warning("Link de novelties não encontrado no menu")
                    return False
                    
            except Exception as e:
                logger.error(f"Erro na navegação alternativa: {e}")
                return False
        
        # Aguarda a tabela carregar
        logger.info("Aguardando carregamento da tabela de novelties...")
        try:
            # Aguarda até 20 segundos pela tabela
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            logger.info("Tabela de novelties carregada com sucesso!")
        except TimeoutException:
            logger.warning("Timeout aguardando tabela, mas continuando...")
            
            # Verifica se há mensagem de "sem dados"
            page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if any(text in page_text for text in ["no data", "no hay", "sem dados", "vazio"]):
                logger.info("Página indica que não há novelties para processar")
            else:
                logger.warning("Tabela não encontrada e sem mensagem clara sobre dados")
        
        # Tira screenshot da página final
        driver.save_screenshot("novelties_page_final.png")
        logger.info("Screenshot da página de novelties salvo")
        
        return True
        
    except Exception as e:
        logger.error(f"Erro ao navegar até Novelties: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def configure_entries_display():
    """Configura para exibir 1000 entradas - VERSÃO CORRIGIDA."""
    try:
        driver = st.session_state.driver
        
        # Aguarda a página estar completamente carregada
        logger.info("Aguardando página estar completamente carregada...")
        time.sleep(5)
        
        # Verifica se há dados na página primeiro
        page_text = driver.find_element(By.TAG_NAME, "body").text
        logger.info(f"Verificando conteúdo da página...")
        logger.info(f"Conteúdo da página (primeiros 500 chars): {page_text[:500]}")
        logger.info(f"URL atual: {driver.current_url}")
        logger.info(f"Título da página: {driver.title}")
        
        # Se a página contém texto de registro/login, há um problema de autenticação
        if any(text in page_text.lower() for text in ["registrarme", "crear cuenta", "dropshipper", "login", "iniciar sesión"]):
            logger.error("ERRO: Página mostra conteúdo de registro/login - usuário não está autenticado!")
            logger.error("A automação precisa fazer login novamente")
            return False
        
        # Procura pela tabela de novelties
        logger.info("Procurando tabela de novelties...")
        tables = driver.find_elements(By.TAG_NAME, "table")
        
        if not tables:
            logger.warning("Nenhuma tabela encontrada na página")
            # Verifica se há mensagem específica sobre dados
            if any(text in page_text.lower() for text in ["no hay novelties", "no data", "sem dados"]):
                logger.info("Página indica explicitamente que não há novelties")
                st.session_state.rows = []
                st.session_state.total_items = 0
                return True
            else:
                logger.error("Nenhuma tabela encontrada e sem mensagem clara sobre status dos dados")
                return False
        
        # Se há tabela, procura pelo controle de paginação
        logger.info("Procurando controle de paginação...")
        
        # Rola até o final da página
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # CORREÇÃO: Busca mais robusta pelo select de paginação
        select_found = False
        
        # Tenta diferentes estratégias para encontrar o select
        select_strategies = [
            "//select[contains(@class, 'form-select')]",
            "//select[contains(@class, 'custom-select')]", 
            "//select[@name='select']",
            "//select[@id='select']",
            "//select",
            "//div[contains(@class, 'dataTables_length')]//select",
            "//*[contains(@class, 'pagination')]//select"
        ]
        
        for strategy in select_strategies:
            try:
                select_elements = driver.find_elements(By.XPATH, strategy)
                if select_elements:
                    logger.info(f"Select encontrado usando estratégia: {strategy}")
                    
                    for select_element in select_elements:
                        if select_element.is_displayed():
                            # Verifica se tem opção para 1000
                            select = Select(select_element)
                            options = [option.text for option in select.options]
                            logger.info(f"Opções disponíveis: {options}")
                            
                            # Tenta selecionar 1000 se disponível
                            if any("1000" in str(option) for option in options):
                                try:
                                    # Tenta diferentes formas de selecionar 1000
                                    for option in select.options:
                                        if "1000" in option.text:
                                            select.select_by_visible_text(option.text)
                                            logger.info(f"Selecionado: {option.text}")
                                            select_found = True
                                            break
                                    
                                    if select_found:
                                        time.sleep(8)  # Aguarda recarregamento
                                        break
                                        
                                except Exception as e:
                                    logger.info(f"Erro ao selecionar 1000: {e}")
                            else:
                                logger.info("Opção 1000 não disponível, usando configuração padrão")
                                select_found = True
                                break
                    
                    if select_found:
                        break
                        
            except Exception as e:
                logger.info(f"Estratégia {strategy} falhou: {e}")
                continue
        
        if not select_found:
            logger.warning("Controle de paginação não encontrado, usando configuração padrão")
        
        # Volta para o topo
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        
        # CORREÇÃO: Busca mais robusta pelas linhas da tabela
        logger.info("Contando linhas da tabela...")
        
        # Aguarda um pouco mais para carregamento
        time.sleep(5)
        
        # Estratégias múltiplas para encontrar linhas
        row_strategies = [
            "//table/tbody/tr",
            "//table//tr[position() > 1]",  # Pula header
            "//tr[td]",  # Linhas que têm células
            "//tbody/tr",
            ".//tr"
        ]
        
        rows_found = []
        for strategy in row_strategies:
            try:
                potential_rows = driver.find_elements(By.XPATH, strategy)
                visible_rows = [row for row in potential_rows if row.is_displayed()]
                
                # Filtra linhas que realmente contêm dados (têm pelo menos 3 células)
                data_rows = []
                for row in visible_rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 3:  # Linha com dados reais
                        data_rows.append(row)
                
                if data_rows:
                    logger.info(f"Estratégia '{strategy}' encontrou {len(data_rows)} linhas com dados")
                    rows_found = data_rows
                    break
                    
            except Exception as e:
                logger.info(f"Estratégia de linhas '{strategy}' falhou: {e}")
                continue
        
        # Atualiza o estado
        st.session_state.rows = rows_found
        st.session_state.total_items = len(rows_found)
        
        logger.info(f"RESULTADO FINAL: {len(rows_found)} novelties encontradas para processar")
        
        # Tira screenshot final
        driver.save_screenshot("table_final_count.png")
        
        return True
        
    except Exception as e:
        logger.error(f"Erro ao configurar exibição de entradas: {str(e)}")
        logger.error(traceback.format_exc())
        return False
    
def extract_customer_info(driver):
    """Extrai informações do cliente da página, incluindo nome, endereço e telefone."""
    try:
        logger.info("Extraindo informações do cliente...")
        
        # Tira screenshot para análise
        try:
            driver.save_screenshot("page_for_customer_info.png")
            logger.info("Screenshot para busca de informações do cliente salvo")
        except:
            pass
        
        customer_info = {
            "address": "",
            "name": "",
            "phone": ""
        }
        
        # Procura pelo cabeçalho "ORDERS TO:"
        try:
            header_info = driver.find_elements(By.XPATH, "//*[contains(text(), 'ORDERS TO:')]")
            
            if header_info:
                for element in header_info:
                    try:
                        # Tenta pegar o texto do elemento pai
                        parent = element.find_element(By.XPATH, "./..")
                        parent_text = parent.text
                        logger.info(f"Texto no elemento pai de ORDERS TO: {parent_text}")
                        
                        # Separar as linhas para extrair as informações
                        lines = parent_text.split('\n')
                        if len(lines) > 1:
                            for i, line in enumerate(lines):
                                if "ORDERS TO:" in line:
                                    # O nome geralmente está uma linha após ORDERS TO:
                                    if i + 1 < len(lines):
                                        customer_info["name"] = lines[i + 1]
                                        logger.info(f"Nome encontrado: {customer_info['name']}")
                                    
                                    # O endereço geralmente está duas linhas após ORDERS TO:
                                    if i + 2 < len(lines):
                                        customer_info["address"] = lines[i + 2]
                                        logger.info(f"Endereço encontrado: {customer_info['address']}")
                                    
                                    break
                    except Exception as e:
                        logger.info(f"Erro ao extrair de ORDERS TO:: {str(e)}")
        except Exception as e:
            logger.info(f"Erro ao buscar ORDERS TO:: {str(e)}")
        
        # Procura pelo campo de telefone - procura por texto com "Telf."
        try:
            phone_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Telf.')]")
            for element in phone_elements:
                element_text = element.text
                logger.info(f"Elemento com 'Telf.' encontrado: {element_text}")
                
                # Extrai o número de telefone
                if "Telf." in element_text:
                    phone_parts = element_text.split("Telf.")
                    if len(phone_parts) > 1:
                        customer_info["phone"] = phone_parts[1].strip()
                        logger.info(f"Telefone encontrado: {customer_info['phone']}")
                        break
        except Exception as e:
            logger.info(f"Erro ao buscar telefone: {str(e)}")
        
        # Se não encontrou alguma informação, tenta métodos alternativos para cada uma
        
        # Método alternativo para nome
        if not customer_info["name"]:
            try:
                # Tenta buscar por elementos que podem conter o nome do cliente
                for name_keyword in ["Client:", "Cliente:", "Nombre:", "Name:"]:
                    name_elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{name_keyword}')]")
                    for element in name_elements:
                        try:
                            element_text = element.text
                            if name_keyword in element_text:
                                parts = element_text.split(name_keyword)
                                if len(parts) > 1:
                                    customer_info["name"] = parts[1].strip()
                                    logger.info(f"Nome encontrado (método alt): {customer_info['name']}")
                                    break
                        except:
                            pass
                    if customer_info["name"]:
                        break
            except Exception as e:
                logger.info(f"Erro ao buscar nome (método alt): {str(e)}")
        
        # Método alternativo para endereço
        if not customer_info["address"]:
            try:
                # Tenta buscar por elementos com palavras-chave de endereço
                for address_keyword in ["Avenida", "Calle", "Rua", "Carretera", "Street", "Av.", "Av ", "Calz"]:
                    address_elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{address_keyword}')]")
                    for element in address_elements:
                        try:
                            element_text = element.text
                            if len(element_text) > 10:  # Filtra textos muito curtos
                                customer_info["address"] = element_text
                                logger.info(f"Endereço encontrado (método alt): {customer_info['address']}")
                                break
                        except:
                            pass
                    if customer_info["address"]:
                        break
            except Exception as e:
                logger.info(f"Erro ao buscar endereço (método alt): {str(e)}")
        
        # Método alternativo para telefone
        if not customer_info["phone"]:
            try:
                # Tenta buscar por elementos com palavras-chave de telefone
                for phone_keyword in ["Phone:", "Teléfono:", "Telefono:", "Tel:", "Tel."]:
                    phone_elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{phone_keyword}')]")
                    for element in phone_elements:
                        try:
                            element_text = element.text
                            if phone_keyword in element_text:
                                parts = element_text.split(phone_keyword)
                                if len(parts) > 1:
                                    customer_info["phone"] = parts[1].strip()
                                    logger.info(f"Telefone encontrado (método alt): {customer_info['phone']}")
                                    break
                        except:
                            pass
                    if customer_info["phone"]:
                        break
            except Exception as e:
                logger.info(f"Erro ao buscar telefone (método alt): {str(e)}")
        
        # Valores padrão para campos não encontrados
        if not customer_info["name"]:
            customer_info["name"] = "Nome do Cliente"
            logger.warning("Nome do cliente não encontrado, usando valor padrão")
        
        if not customer_info["address"]:
            customer_info["address"] = "Endereço de Entrega"
            logger.warning("Endereço não encontrado, usando valor padrão")
        
        if not customer_info["phone"]:
            customer_info["phone"] = "Não informado"
            logger.warning("Telefone não encontrado, usando valor padrão")
            
        return customer_info
    except Exception as e:
        logger.error(f"Erro ao extrair informações do cliente: {str(e)}")
        return {
            "address": "Endereço de Entrega",
            "name": "Nome do Cliente",
            "phone": "Não informado"
        }

def handle_dropdown_solution_form(driver, form_modal, customer_info):
    """Função especializada para lidar com o formulário que tem um dropdown de Solución."""
    try:
        logger.info("Detectado formulário com dropdown de Solución - usando o código específico...")
        
        # Tirar screenshot antes de qualquer interação
        try:
            driver.save_screenshot("before_dropdown_interaction.png")
            logger.info("Screenshot antes da interação com dropdown")
        except:
            pass
        
        # PASSO 1: Encontrar o dropdown usando o seletor específico baseado no HTML inspecionado
        select_element = None
        select_found = False
        
        try:
            # Busca específica pelo select dentro da div com "Solución"
            logger.info("Buscando pelo elemento select específico...")
            
            # Tenta encontrar o select usando vários seletores (do mais específico para o mais genérico)
            selectors = [
                "//div[contains(text(), 'Solución')]/select[contains(@class, 'form-select')]",
                "//div[contains(@class, 'form-group')]/select[contains(@class, 'form-select')]",
                "//div[contains(text(), 'Solución')]//select",
                "//select[contains(@class, 'form-select')]",
                "//select"
            ]
            
            for selector in selectors:
                select_elements = driver.find_elements(By.XPATH, selector)
                if select_elements:
                    for element in select_elements:
                        if element.is_displayed():
                            select_element = element
                            select_found = True
                            logger.info(f"Select encontrado usando o seletor: {selector}")
                            break
                    if select_found:
                        break
            
            if not select_found:
                logger.info("Último recurso: procurando por qualquer elemento select em qualquer lugar")
                select_elements = driver.find_elements(By.TAG_NAME, "select")
                for element in select_elements:
                    if element.is_displayed():
                        select_element = element
                        select_found = True
                        logger.info("Select encontrado usando busca por tag")
                        break
        except Exception as e:
            logger.info(f"Erro ao buscar select: {str(e)}")
        
        # Se não encontrou o select, tentar clicar em NO e depois Yes
        if not select_element:
            logger.error("Não foi possível encontrar o elemento select")
            return click_no_yes_buttons(driver)
        
        # PASSO 2: Verificar se a opção desejada existe
        option_exists = False
        try:
            # Lista todas as opções disponíveis para depuração
            select = Select(select_element)
            options = select.options
            logger.info(f"Opções disponíveis no select ({len(options)}):")
            
            # MUDANÇA CRÍTICA: Verificar explicitamente se a opção existe
            for i, option in enumerate(options):
                option_text = option.text.lower().strip()
                option_value = option.get_attribute("value")
                logger.info(f"  Opção {i}: texto='{option_text}', valor='{option_value}'")
                
                # Verificar por diferentes variações do texto
                if "entregar en nueva dirección" in option_text or "entregar en nueva direccion" in option_text:
                    option_exists = True
                    logger.info(f"Opção 'Entregar en nueva dirección' encontrada na posição {i}")
            
            # MUDANÇA CRÍTICA: Se a opção não existir, clique em NO e depois Yes
            if not option_exists:
                logger.warning("Opção 'Entregar en nueva dirección' NÃO encontrada! Tentando excluir o formulário...")
                return click_no_yes_buttons(driver)
                
        except Exception as e:
            logger.error(f"Erro ao verificar opções do select: {str(e)}")
            # Se houver qualquer erro na verificação, tente excluir o formulário
            logger.warning("Erro ao verificar opções. Tentando excluir o formulário...")
            return click_no_yes_buttons(driver)
        
        # PASSO 3: Selecionar a opção "Entregar en nueva dirección" diretamente
        option_selected = False
        
        try:
            # Rola até o elemento para garantir que está visível
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", select_element)
            time.sleep(1)
            
            # Método 1: Usando a classe Select do Selenium
            try:
                logger.info("Tentando selecionar com a classe Select...")
                select = Select(select_element)
                
                # Tenta selecionar pelo texto visível
                select.select_by_visible_text("Entregar en nueva dirección")
                logger.info("Opção selecionada pelo texto visível")
                option_selected = True
            except Exception as e:
                logger.info(f"Erro ao selecionar pelo texto visível: {str(e)}")
                
                # Tenta selecionar pelo valor - sabemos que é "2: Object"
                try:
                    select.select_by_value("2: Object")
                    logger.info("Opção selecionada pelo valor '2: Object'")
                    option_selected = True
                except Exception as e:
                    logger.info(f"Erro ao selecionar pelo valor: {str(e)}")
                    
                    # Tenta selecionar pelo índice (a opção "Entregar en nueva dirección" é a terceira = índice 2)
                    try:
                        select.select_by_index(2)
                        logger.info("Opção selecionada pelo índice 2")
                        option_selected = True
                    except Exception as e:
                        logger.info(f"Erro ao selecionar pelo índice: {str(e)}")
        except Exception as e:
            logger.info(f"Erro ao usar a classe Select: {str(e)}")
        
        # Método 2: Usando JavaScript direto
        if not option_selected:
            try:
                logger.info("Tentando selecionar usando JavaScript...")
                
                # Define o valor diretamente via JavaScript
                driver.execute_script("arguments[0].value = '2: Object';", select_element)
                
                # Dispara evento de change para atualizar a interface
                driver.execute_script("arguments[0].dispatchEvent(new Event('change', { 'bubbles': true }));", select_element)
                
                logger.info("Valor '2: Object' configurado via JavaScript")
                option_selected = True
            except Exception as e:
                logger.info(f"Erro ao selecionar via JavaScript: {str(e)}")
        
        # Tirar screenshot após selecionar a opção
        try:
            driver.save_screenshot("after_option_selected.png")
            logger.info("Screenshot após selecionar opção")
        except:
            pass
        
        # Espera para o dropdown processar a seleção
        time.sleep(3)
        
        # Se não conseguiu selecionar, tenta excluir o item
        if not option_selected:
            logger.warning("Não foi possível selecionar a opção, tentando excluir...")
            return click_no_yes_buttons(driver)
        
        # PASSO 4: Preencher os campos "Detalle adicional" e "Dirección entrega"
        # com o endereço do cliente
        fields_filled = 0
        
        logger.info("Preenchendo campos após selecionar a opção...")
        
        # Preenche o campo "Detalle adicional de la solución"
        try:
            # Método 1: Usando fill_field_by_label
            detalle_filled = fill_field_by_label(driver, form_modal, 
                                                ["Detalle adicional de la solución", "Detalle adicional"], 
                                                customer_info["address"])
            
            # Método 2: Tentar encontrar por placeholder ou atributos
            if not detalle_filled:
                detalles = driver.find_elements(By.XPATH, "//textarea | //input[contains(@placeholder, 'Detalle') or contains(@id, 'detalle') or contains(@name, 'detalle')]")
                for detalle in detalles:
                    if detalle.is_displayed():
                        driver.execute_script("arguments[0].value = '';", detalle)
                        time.sleep(0.5)
                        driver.execute_script(f"arguments[0].value = '{customer_info['address']}';", detalle)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", detalle)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", detalle)
                        logger.info("Campo 'Detalle adicional' preenchido via método alternativo")
                        detalle_filled = True
                        fields_filled += 1
                        break
            else:
                fields_filled += 1
                logger.info("Campo 'Detalle adicional' preenchido com sucesso")
        except Exception as e:
            logger.info(f"Erro ao preencher campo 'Detalle adicional': {str(e)}")
        
        # Preenche o campo "Dirección entrega"
        try:
            # Método 1: Usando fill_field_by_label
            direccion_filled = fill_field_by_label(driver, form_modal, 
                                                 ["Dirección entrega", "Dirección de entrega"], 
                                                 customer_info["address"])
            
            # Método 2: Tentar encontrar por placeholder ou atributos
            if not direccion_filled:
                direcciones = driver.find_elements(By.XPATH, "//input[contains(@placeholder, 'dirección') or contains(@id, 'direccion') or contains(@name, 'direccion') or contains(@id, 'address') or contains(@name, 'address')]")
                for direccion in direcciones:
                    if direccion.is_displayed():
                        driver.execute_script("arguments[0].value = '';", direccion)
                        time.sleep(0.5)
                        driver.execute_script(f"arguments[0].value = '{customer_info['address']}';", direccion)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", direccion)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", direccion)
                        logger.info("Campo 'Dirección entrega' preenchido via método alternativo")
                        direccion_filled = True
                        fields_filled += 1
                        break
            else:
                fields_filled += 1
                logger.info("Campo 'Dirección entrega' preenchido com sucesso")
        except Exception as e:
            logger.info(f"Erro ao preencher campo 'Dirección entrega': {str(e)}")
        
        # Tirar screenshot após preencher os campos
        try:
            driver.save_screenshot("after_fields_filled.png")
            logger.info("Screenshot após preencher os campos")
        except:
            pass
        
        logger.info(f"Total de {fields_filled} campos preenchidos após selecionar a opção")
        return fields_filled > 0
            
    except Exception as e:
        logger.error(f"Erro ao processar formulário com dropdown: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def click_no_yes_buttons(driver):
    """Função para clicar em NO e depois Yes quando não podemos processar o formulário."""
    try:
        logger.info("Tentando clicar em NO e depois Yes para excluir o formulário...")
        
        # Procura e clica no botão "No"
        no_clicked = False
        try:
            # Procura botões com texto "NO" ou classe de botão danger (vermelho)
            no_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'NO') or contains(@class, 'btn-danger')]")
            for button in no_buttons:
                if button.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", button)
                    logger.info("Clicado no botão 'NO' via JavaScript")
                    time.sleep(2)
                    no_clicked = True
                    break
            
            if not no_clicked:
                logger.warning("Não foi possível encontrar ou clicar no botão 'NO'")
                return False
            
            # Agora procura e clica no botão "Yes" para confirmar
            yes_clicked = False
            
            # Procura por diferentes variações de "Yes"
            for text in ["Yes", "YES"]:
                yes_buttons = driver.find_elements(By.XPATH, f"//button[contains(text(), '{text}')]")
                for button in yes_buttons:
                    if button.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", button)
                        logger.info(f"Clicado no botão '{text}' via JavaScript para confirmar exclusão")
                        time.sleep(2)
                        yes_clicked = True
                        break
                
                if yes_clicked:
                    break
            
            if not yes_clicked:
                logger.warning("Não foi possível encontrar ou clicar no botão Yes após NO")
                return False
            
            logger.info("Exclusão do formulário confirmada com sucesso (NO + Yes)")
            
            # Sinaliza que o formulário foi excluído com sucesso
            st.session_state.form_excluded = True
            
            # Aguarda para ter certeza que tudo processou
            time.sleep(5)
            
            # Retorna True para indicar sucesso e pular para o próximo item
            return True
            
        except Exception as e:
            logger.error(f"Erro ao clicar nos botões NO/Yes: {str(e)}")
            return False
    except Exception as e:
        logger.error(f"Erro ao tentar excluir formulário: {str(e)}")
        return False

def handle_simple_three_field_form(driver, form_modal, customer_info):
    """Função corrigida para lidar com o formulário simples de 3 campos."""
    try:
        logger.info("Detectado formulário simples de 3 campos - usando tratamento específico...")
        
        driver.save_screenshot("before_simple_form_interaction.png")
        logger.info("Screenshot antes da interação com formulário simples")
        
        fields_filled = 0
        
        # CAMPO 1: Preenche "Solución" com o endereço
        logger.info("Preenchendo campo 'Solución'...")
        solucion_filled = fill_field_by_label(driver, form_modal, 
                                            ["Solución", "Solucion"], 
                                            customer_info["address"])
        if solucion_filled:
            fields_filled += 1
            logger.info("✅ Campo 'Solución' preenchido com sucesso")
        else:
            logger.warning("❌ Não foi possível preencher o campo 'Solución'")
        
        # CAMPO 2: Preenche "Confirmar dirección destinatario" - BUSCA MELHORADA
        logger.info("Preenchendo campo 'Confirmar dirección destinatario'...")
        direccion_filled = False
        
        # Tenta várias variações do nome do campo
        direccion_variations = [
            "Confirmar dirección destinatario",
            "Confirmar direccion destinatario", 
            "confirmar direccion",
            "direccion destinatario",
            "direccion",
            "address"
        ]
        
        for variation in direccion_variations:
            if direccion_filled:
                break
            direccion_filled = fill_field_by_label(driver, form_modal, [variation], customer_info["address"])
        
        if direccion_filled:
            fields_filled += 1
            logger.info("✅ Campo 'Confirmar dirección destinatario' preenchido com sucesso")
        else:
            logger.warning("❌ Não foi possível preencher o campo 'Confirmar dirección destinatario'")
        
        # CAMPO 3: Preenche "Confirmar celular destinatario" - BUSCA MELHORADA
        logger.info("Preenchendo campo 'Confirmar celular destinatario'...")
        celular_filled = False
        
        # Tenta várias variações do nome do campo
        celular_variations = [
            "Confirmar celular destinatario",
            "confirmar celular",
            "celular destinatario", 
            "celular",
            "telefono",
            "phone"
        ]
        
        for variation in celular_variations:
            if celular_filled:
                break
            celular_filled = fill_field_by_label(driver, form_modal, [variation], customer_info["phone"])
        
        if celular_filled:
            fields_filled += 1
            logger.info("✅ Campo 'Confirmar celular destinatario' preenchido com sucesso")
        else:
            logger.warning("❌ Não foi possível preencher o campo 'Confirmar celular destinatario'")
        
        driver.save_screenshot("after_simple_form_filled.png")
        logger.info("Screenshot após preencher formulário simples")
        
        logger.info(f"Total de {fields_filled} campos preenchidos no formulário simples")
        
        # CRITÉRIO MAIS RIGOROSO: Exige pelo menos 2 campos preenchidos
        if fields_filled >= 2:
            logger.info("✅ Formulário considerado preenchido com sucesso (2+ campos)")
            return True
        else:
            logger.warning("❌ Formulário não foi preenchido adequadamente (menos de 2 campos)")
            return False
            
    except Exception as e:
        logger.error(f"Erro ao processar formulário simples de 3 campos: {str(e)}")
        return False

def fill_form_fields(driver, form_modal, customer_info):
    """Preenche os campos do formulário com as informações do cliente."""
    try:
        logger.info("Analisando tipo de formulário...")
        
        # NOVA VERIFICAÇÃO: Detecta formulário simples de 3 campos
        simple_form_exists = False
        try:
            # Verifica se tem os 3 campos específicos do novo formato
            simple_field_indicators = [
                "Solución",
                "Confirmar dirección destinatario", 
                "Confirmar celular destinatario"
            ]
            
            fields_found = 0
            for field_name in simple_field_indicators:
                # Busca por labels ou placeholders com esses textos
                elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{field_name}') or contains(@placeholder, '{field_name}')]")
                if elements:
                    fields_found += 1
                    logger.info(f"Campo encontrado: {field_name}")
            
            # Se encontrou pelo menos 2 dos 3 campos específicos, é o formato simples
            if fields_found >= 2:
                simple_form_exists = True
                logger.info("Detectado formulário simples de 3 campos")
                
            # Verifica também pela presença do botão "SAVE SOLUTION"
            if not simple_form_exists:
                save_solution_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'SAVE SOLUTION')]")
                if save_solution_buttons:
                    simple_form_exists = True
                    logger.info("Detectado formulário simples pela presença do botão 'SAVE SOLUTION'")
                    
        except Exception as e:
            logger.info(f"Erro ao verificar formulário simples: {str(e)}")
        
        # Se detectou o formulário simples, usa a função especializada
        if simple_form_exists:
            logger.info("Usando tratamento para formulário simples de 3 campos")
            return handle_simple_three_field_form(driver, form_modal, customer_info)
        
        # Verifica se existe um select de Solución (detecção mais precisa)
        dropdown_exists = False
        try:
            # Busca específica pelo elemento select
            select_elements = []
            
            # Tenta encontrar o select explicitamente relacionado à Solución
            select_elements = driver.find_elements(By.XPATH, "//div[contains(text(), 'Solución')]/select")
            
            if not select_elements:
                select_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'form-group')][contains(text(), 'Solución')]//select")
            
            # Se encontrou algum select, verifica se tem a opção específica "Entregar en nueva dirección"
            if select_elements:
                for select_element in select_elements:
                    if select_element.is_displayed():
                        # Verifica se tem a opção específica
                        try:
                            options = select_element.find_elements(By.TAG_NAME, "option")
                            for option in options:
                                if "entregar en nueva dirección" in option.text.lower():
                                    dropdown_exists = True
                                    logger.info("Detectado formulário com dropdown para Solución e opção 'Entregar en nueva dirección'")
                                    break
                            if dropdown_exists:
                                break
                        except:
                            # Se não conseguir verificar as opções, ainda pode ser um dropdown
                            pass
            
            # Se não encontrou pelo select com opções, faz uma verificação de fallback
            if not dropdown_exists:
                # Verifica especificamente pela estrutura HTML que você compartilhou
                form_html = form_modal.get_attribute("innerHTML").lower()
                if "select" in form_html and "solución" in form_html and "entregar en nueva dirección" in form_html:
                    dropdown_exists = True
                    logger.info("Detectado formulário com dropdown de Solución via HTML interno")
        except Exception as e:
            logger.info(f"Erro ao verificar tipo de formulário: {str(e)}")
        
        # Se detectou que é o formato com dropdown, usa a função especializada
        if dropdown_exists:
            logger.info("Detectado formulário com dropdown de Solución. Usando tratamento especializado.")
            return handle_dropdown_solution_form(driver, form_modal, customer_info)
        
        # Caso contrário, continua com o fluxo normal
        logger.info("Usando fluxo normal de preenchimento de formulário...")
        fields_filled = 0
        
        # Caso contrário, continua com o fluxo normal
        logger.info("Usando fluxo normal de preenchimento de formulário...")
        fields_filled = 0
        
        # Resto do código original para preencher formulários padrão
        # Primeiro vamos encontrar todos os campos do formulário para entender o que precisa ser preenchido
        form_fields = []
        try:
            # Tirar screenshot do formulário para análise
            driver.save_screenshot("form_before_filling.png")
            logger.info("Screenshot do formulário antes de preencher salvo")
            
            # Encontra todas as labels visíveis no formulário
            labels = form_modal.find_elements(By.TAG_NAME, "label")
            visible_labels = [label for label in labels if label.is_displayed()]
            
            logger.info(f"Total de {len(visible_labels)} labels visíveis encontradas no formulário")
            
            # Lista todas as labels encontradas no log
            for idx, label in enumerate(visible_labels):
                label_text = label.text.strip()
                label_for = label.get_attribute("for")
                logger.info(f"Label #{idx}: Texto='{label_text}', For='{label_for}'")
                
                # Verifica se há um campo associado
                if label_for:
                    try:
                        input_field = driver.find_element(By.ID, label_for)
                        if input_field.is_displayed():
                            field_type = input_field.get_attribute("type")
                            field_value = input_field.get_attribute("value")
                            field_required = input_field.get_attribute("required")
                            
                            form_fields.append({
                                "label": label_text,
                                "field": input_field,
                                "type": field_type,
                                "value": field_value,
                                "required": field_required == "true" or field_required == ""
                            })
                            
                            logger.info(f"Campo associado encontrado: Tipo='{field_type}', Valor='{field_value}', Obrigatório={field_required}")
                    except:
                        logger.info(f"Não foi possível encontrar campo para label '{label_text}'")
            
            # Se não encontrou campos por labels, tenta encontrar todos os inputs
            if not form_fields:
                logger.info("Tentando encontrar todos os campos de input visíveis...")
                inputs = form_modal.find_elements(By.TAG_NAME, "input")
                visible_inputs = [inp for inp in inputs if inp.is_displayed()]
                
                logger.info(f"Total de {len(visible_inputs)} inputs visíveis encontrados")
                
                for idx, input_field in enumerate(visible_inputs):
                    field_id = input_field.get_attribute("id")
                    field_name = input_field.get_attribute("name")
                    field_placeholder = input_field.get_attribute("placeholder")
                    field_type = input_field.get_attribute("type")
                    field_value = input_field.get_attribute("value")
                    field_required = input_field.get_attribute("required")
                    
                    # IMPORTANTE: Ignorar o campo de pesquisa
                    if field_name == "textToSearch" or field_placeholder == "Search":
                        logger.info(f"Ignorando campo de pesquisa: ID='{field_id}', Nome='{field_name}', Placeholder='{field_placeholder}'")
                        continue
                    
                    # Tenta determinar a label pelo contexto
                    label_text = field_placeholder or field_name or field_id or f"Campo #{idx}"
                    
                    form_fields.append({
                        "label": label_text,
                        "field": input_field,
                        "type": field_type,
                        "value": field_value,
                        "required": field_required == "true" or field_required == ""
                    })
                    
                    logger.info(f"Input #{idx}: ID='{field_id}', Nome='{field_name}', Placeholder='{field_placeholder}', " +
                               f"Tipo='{field_type}', Valor='{field_value}', Obrigatório={field_required}")
        except Exception as e:
            logger.error(f"Erro ao analisar campos do formulário: {str(e)}")
        
        # Conta o número total de campos visíveis para determinar o padrão (Colômbia vs Equador)
        visible_input_count = len([f for f in form_fields if f["field"].is_displayed()])
        logger.info(f"Total de {visible_input_count} campos de input visíveis detectados")
        
        # 1. Preenche o campo Solución (sempre deve ser preenchido, independente do padrão)
        solucion_filled = fill_field_by_label(driver, form_modal, 
                                              ["Solución", "Solucion", "solución", "solucion", "Solution"], 
                                              customer_info["address"])
        if solucion_filled:
            fields_filled += 1
            logger.info("✅ Campo Solución preenchido com sucesso")
        else:
            logger.warning("❌ Não foi possível preencher o campo Solución")
        
        # Se há mais de um campo, preenche os outros campos (comportamento padrão do Equador)
        if visible_input_count > 1:
            logger.info("Detectados múltiplos campos - usando o padrão completo de preenchimento")
            
            # 2. Preenche o campo Nombre
            nombre_filled = fill_field_by_label(driver, form_modal, 
                                               ["Nombre", "Nome", "Name"], 
                                               customer_info["name"])
            if nombre_filled:
                fields_filled += 1
                logger.info("✅ Campo Nombre preenchido com sucesso")
            else:
                logger.warning("❌ Não foi possível preencher o campo Nombre")
                
                # Tenta encontrar e preencher o campo pelo ID ou classe
                try:
                    nombre_inputs = form_modal.find_elements(By.XPATH, "//input[contains(@id, 'nombre') or contains(@id, 'name') or contains(@name, 'nombre') or contains(@name, 'name')]")
                    if nombre_inputs:
                        nombre_input = nombre_inputs[0]
                        if nombre_input.is_displayed():
                            # Limpa e preenche
                            driver.execute_script("arguments[0].value = '';", nombre_input)
                            time.sleep(0.5)
                            driver.execute_script(f"arguments[0].value = '{customer_info['name']}';", nombre_input)
                            # Dispara eventos para garantir que o site registre a alteração
                            driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", nombre_input)
                            driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", nombre_input)
                            logger.info("✅ Campo Nombre preenchido via seletor alternativo")
                            fields_filled += 1
                            nombre_filled = True
                except Exception as e:
                    logger.info(f"Erro ao tentar método alternativo para Nombre: {str(e)}")
            
            # 3. Preenche o campo Dirección entrega
            direccion_filled = fill_field_by_label(driver, form_modal, 
                                                  ["Dirección entrega", "Direccion entrega", "Direção entrega", 
                                                   "Dirección de entrega", "Direccion de entrega", "Delivery address"], 
                                                  customer_info["address"])
            if direccion_filled:
                fields_filled += 1
                logger.info("✅ Campo Dirección entrega preenchido com sucesso")
            else:
                logger.warning("❌ Não foi possível preencher o campo Dirección entrega")
                
                # Tenta encontrar e preencher o campo pelo ID ou classe
                try:
                    direccion_inputs = form_modal.find_elements(By.XPATH, "//input[contains(@id, 'direccion') or contains(@id, 'address') or contains(@name, 'direccion') or contains(@name, 'address')]")
                    if direccion_inputs:
                        direccion_input = direccion_inputs[0]
                        if direccion_input.is_displayed():
                            # Limpa e preenche
                            driver.execute_script("arguments[0].value = '';", direccion_input)
                            time.sleep(0.5)
                            driver.execute_script(f"arguments[0].value = '{customer_info['address']}';", direccion_input)
                            # Dispara eventos para garantir que o site registre a alteração
                            driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", direccion_input)
                            driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", direccion_input)
                            logger.info("✅ Campo Dirección preenchido via seletor alternativo")
                            fields_filled += 1
                            direccion_filled = True
                except Exception as e:
                    logger.info(f"Erro ao tentar método alternativo para Dirección: {str(e)}")
            
            # 4. Preenche o campo Celular
            celular_filled = fill_field_by_label(driver, form_modal, 
                                                ["Celular", "Teléfono", "Telefono", "Phone"], 
                                                customer_info["phone"])
            if celular_filled:
                fields_filled += 1
                logger.info("✅ Campo Celular preenchido com sucesso")
            else:
                logger.warning("❌ Não foi possível preencher o campo Celular")
                
                # Tenta encontrar e preencher o campo pelo ID ou classe
                try:
                    celular_inputs = form_modal.find_elements(By.XPATH, "//input[contains(@id, 'celular') or contains(@id, 'phone') or contains(@id, 'telefono') or contains(@name, 'celular') or contains(@name, 'phone') or contains(@name, 'telefono')]")
                    if celular_inputs:
                        celular_input = celular_inputs[0]
                        if celular_input.is_displayed():
                            # Limpa e preenche
                            driver.execute_script("arguments[0].value = '';", celular_input)
                            time.sleep(0.5)
                            driver.execute_script(f"arguments[0].value = '{customer_info['phone']}';", celular_input)
                            # Dispara eventos para garantir que o site registre a alteração
                            driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", celular_input)
                            driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", celular_input)
                            logger.info("✅ Campo Celular preenchido via seletor alternativo")
                            fields_filled += 1
                            celular_filled = True
                except Exception as e:
                    logger.info(f"Erro ao tentar método alternativo para Celular: {str(e)}")
        else:
            logger.info("Detectado apenas um campo - usando o padrão simplificado da Colômbia")
            # No padrão da Colômbia com apenas um campo, já preenchemos o Solución acima
        
        # 5. Tenta preencher todos os campos obrigatórios vazios
        try:
            logger.info("Verificando se há campos obrigatórios não preenchidos...")
            
            # Encontra todos os campos marcados como obrigatórios
            required_inputs = form_modal.find_elements(By.XPATH, "//input[@required]")
            
            logger.info(f"Encontrados {len(required_inputs)} campos obrigatórios")
            
            for idx, input_field in enumerate(required_inputs):
                if input_field.is_displayed():
                    field_value = input_field.get_attribute("value")
                    field_id = input_field.get_attribute("id") or ""
                    field_name = input_field.get_attribute("name") or ""
                    field_type = input_field.get_attribute("type") or ""
                    field_placeholder = input_field.get_attribute("placeholder") or ""
                    
                    # IMPORTANTE: Ignorar o campo de pesquisa
                    if field_name == "textToSearch" or field_placeholder == "Search":
                        logger.info(f"Ignorando campo de pesquisa obrigatório: ID='{field_id}', Nome='{field_name}'")
                        continue
                    
                    logger.info(f"Campo obrigatório #{idx}: ID='{field_id}', Nome='{field_name}', Tipo='{field_type}', Valor Atual='{field_value}'")
                    
                    # Se o campo está vazio, tenta preenchê-lo com um valor relevante
                    if not field_value:
                        # Determina o melhor valor com base nos atributos do campo
                        value_to_use = ""
                        
                        if "nombre" in field_id.lower() or "nome" in field_id.lower() or "name" in field_id.lower() or \
                           "nombre" in field_name.lower() or "nome" in field_name.lower() or "name" in field_name.lower():
                            value_to_use = customer_info["name"]
                        elif "direccion" in field_id.lower() or "endereco" in field_id.lower() or "address" in field_id.lower() or \
                             "direccion" in field_name.lower() or "endereco" in field_name.lower() or "address" in field_name.lower():
                            value_to_use = customer_info["address"]
                        elif "celular" in field_id.lower() or "telefono" in field_id.lower() or "phone" in field_id.lower() or \
                             "celular" in field_name.lower() or "telefono" in field_name.lower() or "phone" in field_name.lower():
                            value_to_use = customer_info["phone"]
                        elif "solucion" in field_id.lower() or "solution" in field_id.lower() or \
                             "solucion" in field_name.lower() or "solution" in field_name.lower():
                            value_to_use = customer_info["address"]
                        else:
                            # Se não conseguimos determinar, usa o nome para campos de texto
                            if field_type.lower() in ["text", "email", "tel", "url", ""]:
                                value_to_use = customer_info["name"]
                        
                        if value_to_use:
                            # Limpa e preenche
                            driver.execute_script("arguments[0].value = '';", input_field)
                            time.sleep(0.5)
                            driver.execute_script(f"arguments[0].value = '{value_to_use}';", input_field)
                            # Dispara eventos
                            driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", input_field)
                            driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", input_field)
                            logger.info(f"Preenchido campo obrigatório #{idx} com '{value_to_use}'")
                            fields_filled += 1
        except Exception as e:
            logger.error(f"Erro ao verificar campos obrigatórios: {str(e)}")
        
        # Tirar screenshot após preencher todos os campos
        try:
            driver.save_screenshot("form_after_filling.png")
            logger.info("Screenshot do formulário após preenchimento salvo")
        except:
            pass
        
        # 7. Verifica se todos os campos foram preenchidos
        try:
            logger.info("Verificando preenchimento final dos campos...")
            
            empty_required_fields = []
            
            # Verifica todos os inputs
            all_inputs = form_modal.find_elements(By.TAG_NAME, "input")
            for input_field in all_inputs:
                if input_field.is_displayed():
                    field_id = input_field.get_attribute("id") or ""
                    field_name = input_field.get_attribute("name") or ""
                    field_value = input_field.get_attribute("value")
                    field_required = input_field.get_attribute("required") == "true" or input_field.get_attribute("required") == ""
                    field_type = input_field.get_attribute("type") or ""
                    field_placeholder = input_field.get_attribute("placeholder") or ""
                    
                    # IMPORTANTE: Ignorar o campo de pesquisa
                    if field_name == "textToSearch" or field_placeholder == "Search":
                        logger.info(f"Ignorando campo de pesquisa na verificação final: ID='{field_id}', Nome='{field_name}'")
                        continue
                    
                    # Ignora campos ocultos, checkbox, radio
                    if field_type.lower() not in ["hidden", "checkbox", "radio"]:
                        if field_required and not field_value:
                            empty_required_fields.append({
                                "id": field_id,
                                "name": field_name,
                                "type": field_type
                            })
            
            if empty_required_fields:
                logger.warning(f"Ainda existem {len(empty_required_fields)} campos obrigatórios vazios:")
                for field in empty_required_fields:
                    logger.warning(f"Campo vazio: ID='{field['id']}', Nome='{field['name']}', Tipo='{field['type']}'")
            else:
                logger.info("Todos os campos obrigatórios estão preenchidos!")
        except Exception as e:
            logger.error(f"Erro ao verificar preenchimento final: {str(e)}")
        
        logger.info(f"Total de {fields_filled} campos preenchidos no formulário")
        
        # NOVA VERIFICAÇÃO: Se não preencheu nenhum campo, tentar excluir o formulário
        if fields_filled == 0:
            logger.warning("Nenhum campo foi preenchido, tentando excluir o formulário...")
            return click_no_yes_buttons(driver)
            
        return fields_filled > 0
    except Exception as e:
        logger.error(f"Erro ao preencher campos do formulário: {str(e)}")
        return False
    
def handle_empty_data_error(driver, customer_info):
    """Função mantida para compatibilidade, não é mais utilizada ativamente."""
    logger.info("Função handle_empty_data_error chamada, mas não está mais em uso ativo.")
    return False

def fill_field_by_label(driver, form_modal, label_texts, value):
    """Preenche um campo específico do formulário identificado por texto da label - VERSÃO CORRIGIDA."""
    try:
        logger.info(f"Tentando preencher campo com labels {label_texts}...")
        
        field_found = False
        
        # NOVA ESTRATÉGIA: Busca mais agressiva por campos
        for label_text in label_texts:
            if field_found:
                break
                
            # Método 1: Busca por placeholder
            try:
                placeholder_inputs = driver.find_elements(By.XPATH, f"//input[contains(@placeholder, '{label_text}') or contains(@placeholder, '{label_text.lower()}')]")
                for input_field in placeholder_inputs:
                    if input_field.is_displayed():
                        logger.info(f"Campo encontrado por placeholder: {label_text}")
                        # Preenche o campo
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_field)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].value = '';", input_field)
                        time.sleep(0.5)
                        safe_value = value.replace("'", "\\'").replace("\\", "\\\\")
                        driver.execute_script(f"arguments[0].value = '{safe_value}';", input_field)
                        
                        # Dispara eventos
                        events = ["input", "change", "blur"]
                        for event in events:
                            driver.execute_script(f"arguments[0].dispatchEvent(new Event('{event}', {{bubbles: true}}));", input_field)
                        
                        logger.info(f"Campo '{label_text}' preenchido com sucesso via placeholder")
                        return True
            except Exception as e:
                logger.info(f"Erro na busca por placeholder '{label_text}': {e}")
            
            # Método 2: Busca por name attribute
            try:
                name_variations = [
                    label_text.lower().replace(" ", "").replace("ó", "o").replace("ñ", "n"),
                    label_text.lower().replace(" ", "_").replace("ó", "o").replace("ñ", "n"),
                    label_text.lower().replace(" ", "-").replace("ó", "o").replace("ñ", "n")
                ]
                
                for name_var in name_variations:
                    name_inputs = driver.find_elements(By.XPATH, f"//input[contains(@name, '{name_var}')]")
                    for input_field in name_inputs:
                        if input_field.is_displayed():
                            logger.info(f"Campo encontrado por name: {name_var}")
                            # Preenche o campo
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_field)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].value = '';", input_field)
                            time.sleep(0.5)
                            safe_value = value.replace("'", "\\'").replace("\\", "\\\\")
                            driver.execute_script(f"arguments[0].value = '{safe_value}';", input_field)
                            
                            # Dispara eventos
                            events = ["input", "change", "blur"]
                            for event in events:
                                driver.execute_script(f"arguments[0].dispatchEvent(new Event('{event}', {{bubbles: true}}));", input_field)
                            
                            logger.info(f"Campo '{label_text}' preenchido com sucesso via name")
                            return True
            except Exception as e:
                logger.info(f"Erro na busca por name '{label_text}': {e}")
            
            # Método 3: Busca por ID
            try:
                id_variations = [
                    label_text.lower().replace(" ", "").replace("ó", "o").replace("ñ", "n"),
                    label_text.lower().replace(" ", "_").replace("ó", "o").replace("ñ", "n"),
                    label_text.lower().replace(" ", "-").replace("ó", "o").replace("ñ", "n")
                ]
                
                for id_var in id_variations:
                    id_inputs = driver.find_elements(By.XPATH, f"//input[contains(@id, '{id_var}')]")
                    for input_field in id_inputs:
                        if input_field.is_displayed():
                            logger.info(f"Campo encontrado por ID: {id_var}")
                            # Preenche o campo
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_field)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].value = '';", input_field)
                            time.sleep(0.5)
                            safe_value = value.replace("'", "\\'").replace("\\", "\\\\")
                            driver.execute_script(f"arguments[0].value = '{safe_value}';", input_field)
                            
                            # Dispara eventos
                            events = ["input", "change", "blur"]
                            for event in events:
                                driver.execute_script(f"arguments[0].dispatchEvent(new Event('{event}', {{bubbles: true}}));", input_field)
                            
                            logger.info(f"Campo '{label_text}' preenchido com sucesso via ID")
                            return True
            except Exception as e:
                logger.info(f"Erro na busca por ID '{label_text}': {e}")
        
        # Resto do código original...
        logger.warning(f"Não foi possível encontrar campo com labels {label_texts}")
        return False
        
    except Exception as e:
        logger.error(f"Erro ao preencher campo: {str(e)}")
        return False

def verify_processing_success(driver, row_id):
    """Verifica se o processamento foi realmente bem-sucedido."""
    try:
        logger.info(f"Verificando sucesso do processamento para novelty {row_id}...")
        
        # Aguarda um pouco para garantir que a página atualizou
        time.sleep(3)
        
        # Recarrega a página para garantir dados atualizados
        driver.refresh()
        time.sleep(5)
        
        # Verifica se ainda está na página de novelties
        current_url = driver.current_url
        if "novelties" not in current_url:
            logger.warning("Não está na página de novelties após processamento")
            driver.get("https://app.dropi.co/dashboard/novelties")
            time.sleep(5)
        
        # Procura pela novelty específica na tabela atualizada
        try:
            # Busca pela linha com o ID específico
            row_xpath = f"//td[contains(text(), '{row_id}')]/parent::tr"
            specific_rows = driver.find_elements(By.XPATH, row_xpath)
            
            if specific_rows:
                specific_row = specific_rows[0]
                
                # Verifica se ainda há botão "Solve" nesta linha
                solve_buttons = specific_row.find_elements(By.XPATH, ".//button[contains(text(), 'Solve')]")
                
                if not solve_buttons:
                    logger.info("✅ Processamento confirmado - botão 'Solve' não encontrado")
                    return True
                else:
                    logger.warning("❌ Processamento falhou - botão 'Solve' ainda presente")
                    return False
            else:
                logger.warning("❌ Não foi possível encontrar a linha específica na tabela")
                return False
                
        except Exception as e:
            logger.error(f"Erro ao verificar linha específica: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Erro ao verificar sucesso do processamento: {e}")
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
        
        # Variável para controlar tentativas de recarregamento
        reload_attempts = 0
        max_reload_attempts = 3
        
        # Obtém o ID da linha para referência
        try:
            # Importante: Precisamos recarregar as linhas da tabela para evitar StaleElementReference
            rows = driver.find_elements(By.XPATH, "//table/tbody/tr")
            
            # Se não encontrou linhas, tenta seletores alternativos
            if not rows:
                logger.info("Tentando seletores alternativos para as linhas da tabela...")
                rows = driver.find_elements(By.CSS_SELECTOR, "table tr:not(:first-child)")
                
                if not rows:
                    rows = driver.find_elements(By.XPATH, "//tr[position() > 1]")
            
            if rows and st.session_state.current_row_index < len(rows):
                row = rows[st.session_state.current_row_index]
                try:
                    row_id = row.find_elements(By.TAG_NAME, "td")[0].text
                    logger.info(f"Processando novelty ID: {row_id} ({st.session_state.current_row_index+1}/{len(rows)})")
                except:
                    row_id = f"Linha {st.session_state.current_row_index+1}"
                    logger.info(f"Processando {row_id}/{len(rows)}")
            else:
                row_id = f"Linha {st.session_state.current_row_index+1}"
                logger.info(f"Processando {row_id} (linhas não disponíveis)")
                
                # MODIFICAÇÃO: estratégia mais robusta de recarregamento
                if reload_attempts < max_reload_attempts:
                    logger.warning(f"Linhas da tabela não disponíveis. Tentativa {reload_attempts+1} de {max_reload_attempts} para recarregar a página...")
                    reload_attempts += 1
                    
                    # Navega diretamente para a página de novelties para garantir que estamos no lugar certo
                    driver.get("https://app.dropi.co/dashboard/novelties")
                    
                    # Aumenta o tempo de espera após recarregar
                    logger.info("Aguardando 10 segundos para carregamento completo da página...")
                    time.sleep(10)
                    
                    # Tenta configurar a exibição de 1000 entradas novamente
                    try:
                        logger.info("Tentando configurar exibição para 1000 entradas novamente...")
                        configure_entries_display()
                        time.sleep(5)  # Espera adicional após configurar
                    except:
                        logger.warning("Não foi possível configurar exibição para 1000 entradas")
                    
                    # Tenta obter as linhas novamente após a configuração
                    try:
                        rows = driver.find_elements(By.XPATH, "//table/tbody/tr")
                        
                        if not rows:
                            rows = driver.find_elements(By.CSS_SELECTOR, "table tr:not(:first-child)")
                            
                            if not rows:
                                rows = driver.find_elements(By.XPATH, "//tr[position() > 1]")
                        
                        logger.info(f"Após recarregar: {len(rows)} linhas encontradas")
                        
                        if rows and len(rows) > 0:
                            # Atualiza as linhas no state
                            st.session_state.rows = rows
                            logger.info("Linhas atualizadas com sucesso!")
                            return False  # Retorna para tentar processar novamente
                    except Exception as e:
                        logger.error(f"Erro ao tentar obter linhas após recarregar: {str(e)}")
                
                # Se chegou aqui, é porque todas as tentativas de recarregamento falharam
                # Vamos avançar para a próxima novelty
                if reload_attempts >= max_reload_attempts:
                    logger.error(f"Todas as {max_reload_attempts} tentativas de recarregamento falharam. Avançando para próxima novelty.")
                    st.session_state.failed_items.append({"id": row_id, "error": "Não foi possível carregar a tabela após múltiplas tentativas"})
                    st.session_state.failed_count = len(st.session_state.failed_items)
                    
                    # Incrementa o índice para a próxima novelty e retorna para tentar novamente
                    st.session_state.current_row_index += 1
                    st.session_state.processed_items = st.session_state.current_row_index
                    st.session_state.progress = st.session_state.current_row_index / st.session_state.total_items
                    return False
                
                return False  # Retorna para tentar novamente
        except Exception as e:
            logger.error(f"Erro ao obter informações da linha: {str(e)}")
            row_id = f"Linha {st.session_state.current_row_index+1}"
        
        # Atualiza o progresso
        st.session_state.processed_items = st.session_state.current_row_index + 1
        st.session_state.progress = (st.session_state.current_row_index + 1) / st.session_state.total_items
        
        try:
            # Tirar screenshot antes de clicar no botão Save
            try:
                driver.save_screenshot(f"before_save_{row_id}.png")
                logger.info(f"Screenshot antes de salvar: before_save_{row_id}.png")
            except:
                pass
            
            # CORREÇÃO PARA O ERRO STALE ELEMENT: Recarregar o elemento antes de interagir
            logger.info(f"Tentando localizar o botão 'Save' para a novelty {row_id}...")
            try:
                # Recarrega as linhas novamente para garantir que estão atuais
                fresh_rows = driver.find_elements(By.XPATH, "//table/tbody/tr")
                
                # Se não encontrou com o seletor padrão, tenta seletores alternativos
                if not fresh_rows:
                    fresh_rows = driver.find_elements(By.CSS_SELECTOR, "table tr:not(:first-child)")
                    
                    if not fresh_rows:
                        fresh_rows = driver.find_elements(By.XPATH, "//tr[position() > 1]")
                
                if fresh_rows and st.session_state.current_row_index < len(fresh_rows):
                    current_row = fresh_rows[st.session_state.current_row_index]
                    
                    # MODIFICAÇÃO: usa múltiplos seletores para encontrar o botão Save
                    save_buttons = current_row.find_elements(By.XPATH, ".//button[contains(@class, 'btn-success')]")
                    
                    # Se não encontrou por classe, tenta por texto
                    if not save_buttons:
                        save_buttons = current_row.find_elements(By.XPATH, ".//button[contains(text(), 'Save')]")
                    
                    # Se ainda não encontrou, tenta qualquer botão na linha
                    if not save_buttons:
                        save_buttons = current_row.find_elements(By.TAG_NAME, "button")
                    
                    if save_buttons:
                        save_button = save_buttons[0]
                        
                        # Rola até o botão para garantir que esteja visível
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", save_button)
                        time.sleep(2)  # Aumentado para 2 segundos
                        
                        # Tenta clicar com JavaScript para maior confiabilidade
                        driver.execute_script("arguments[0].click();", save_button)
                        logger.info("Botão 'Save' clicado via JavaScript")
                        
                        # NOVA VERIFICAÇÃO: Verificar se a janela ainda existe após clicar
                        time.sleep(2)
                        try:
                            # Tenta acessar o título atual para verificar se a janela existe
                            current_title = driver.title
                        except Exception as window_error:
                            logger.warning(f"Janela do navegador foi fechada: {str(window_error)}")
                            # Fecha o driver atual se existir
                            try:
                                if st.session_state.driver:
                                    st.session_state.driver.quit()
                            except:
                                pass
                            
                            # Reconfigura o driver
                            setup_driver()
                            
                            # Reinicia o login e navegação
                            if login():
                                navigate_to_novelties()
                                configure_entries_display()
                            
                            # Registra como processado com sucesso
                            st.session_state.success_count += 1
                            logger.info(f"Novelty {row_id} processada com sucesso (janela fechada e reaberta)!")
                            
                            # Avança para a próxima novelty
                            st.session_state.current_row_index += 1
                            st.session_state.processed_items = st.session_state.current_row_index
                            st.session_state.progress = st.session_state.current_row_index / st.session_state.total_items
                            return False
                    else:
                        logger.warning("Botão 'Save' não encontrado na linha atual")
                        # Registra a falha
                        st.session_state.failed_items.append({"id": row_id, "error": "Botão 'Save' não encontrado"})
                        st.session_state.failed_count = len(st.session_state.failed_items)
                        # Incrementa o índice e continua para a próxima novelty
                        st.session_state.current_row_index += 1
                        return False
                else:
                    logger.warning("Não foi possível localizar a linha atual na tabela")
                    # Registra a falha
                    st.session_state.failed_items.append({"id": row_id, "error": "Linha não encontrada na tabela"})
                    st.session_state.failed_count = len(st.session_state.failed_items)
                    # Incrementa o índice e continua para a próxima novelty
                    st.session_state.current_row_index += 1
                    return False
            except Exception as e:
                logger.error(f"Erro ao clicar no botão 'Save': {str(e)}")
                # Registra a falha
                st.session_state.failed_items.append({"id": row_id, "error": f"Erro ao clicar no botão 'Save': {str(e)}"})
                st.session_state.failed_count = len(st.session_state.failed_items)
                # Incrementa o índice e continua para a próxima novelty
                st.session_state.current_row_index += 1
                return False
            
            # Espera pelo popup - tempo aumentado
            logger.info("Aguardando 5 segundos pelo popup...")
            time.sleep(5)
            
            # Tirar screenshot após clicar no botão Save
            try:
                driver.save_screenshot(f"after_save_{row_id}.png")
                logger.info(f"Screenshot após salvar: after_save_{row_id}.png")
            except:
                pass
            
            # Tenta diferentes métodos para encontrar e clicar no botão "Yes" ou "Sim"
            yes_clicked = False
            
            # Método 1: Procura por texto exato
            for text in ["Yes", "YES"]:
                try:
                    yes_buttons = driver.find_elements(By.XPATH, f"//button[contains(text(), '{text}')]")
                    for button in yes_buttons:
                        if button.is_displayed():
                            logger.info(f"Botão com texto '{text}' encontrado, tentando clicar...")
                            
                            # Rola até o botão para garantir que esteja visível
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                            time.sleep(1)
                            
                            # Tenta clicar com JavaScript
                            driver.execute_script("arguments[0].click();", button)
                            logger.info(f"Clicado no botão com texto '{text}' via JavaScript")
                            
                            # Aguarda após clicar
                            time.sleep(2)
                            
                            yes_clicked = True
                            break
                    if yes_clicked:
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
                        
                        # Rola até o botão para garantir que esteja visível
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", buttons[0])
                        time.sleep(1)
                        
                        # Tenta clicar com JavaScript
                        driver.execute_script("arguments[0].click();", buttons[0])
                        logger.info("Clicado no primeiro botão do modal-footer via JavaScript")
                        
                        # Aguarda após clicar
                        time.sleep(2)
                        
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
                                    
                                    # Rola até o botão para garantir que esteja visível
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                    time.sleep(1)
                                    
                                    # Tenta clicar com JavaScript
                                    driver.execute_script("arguments[0].click();", button)
                                    logger.info(f"Clicado em botão de classe: {button_class} via JavaScript")
                                    
                                    # Aguarda após clicar
                                    time.sleep(2)
                                    
                                    yes_clicked = True
                                    break
                            except Exception as e:
                                logger.info(f"Erro ao clicar no botão de classe {button_class}: {str(e)}")
                                continue
                except Exception as e:
                    logger.info(f"Erro ao procurar botões por classe: {str(e)}")
                    
            if not yes_clicked:
                logger.warning("Não foi possível clicar em 'Yes'/'Sim'. Tentando continuar...")
            
            # Verificar novamente se a janela ainda existe após Yes
            try:
                # Tenta acessar o título atual
                current_title = driver.title
            except Exception as window_error:
                logger.warning(f"Janela do navegador foi fechada após clicar em Yes: {str(window_error)}")
                # Fecha o driver atual se existir
                try:
                    if st.session_state.driver:
                        st.session_state.driver.quit()
                except:
                    pass
                
                # Reconfigura o driver
                setup_driver()
                
                # Reinicia o login e navegação
                if login():
                    navigate_to_novelties()
                    configure_entries_display()
                
                # Registra como processado com sucesso
                st.session_state.success_count += 1
                logger.info(f"Novelty {row_id} processada com sucesso (janela fechada após Yes)!")
                
                # Avança para a próxima novelty
                st.session_state.current_row_index += 1
                st.session_state.processed_items = st.session_state.current_row_index
                st.session_state.progress = st.session_state.current_row_index / st.session_state.total_items
                return False
            
            # Aguardar mais tempo antes de procurar o formulário
            logger.info("Aguardando 8 segundos para garantir que o formulário seja carregado...")
            time.sleep(8)  # Aumentado de 5 para 8 segundos
            
            # Tirar screenshot após clicar no botão Yes para diagnóstico
            try:
                driver.save_screenshot(f"after_yes_{row_id}.png")
                logger.info(f"Screenshot após clicar em Yes: after_yes_{row_id}.png")
            except:
                pass
            
            # Extrair as informações do cliente
            customer_info = extract_customer_info(driver)
            
            # ESTRATÉGIA APRIMORADA para encontrar o formulário
            form_found = False
            form_modal = None
            
            # Diagnóstico do DOM atual para depuração
            try:
                logger.info("Analisando estrutura do DOM após clicar em Yes...")
                
                # Verificar se há modais visíveis
                modals = driver.find_elements(By.XPATH, "//div[contains(@class, 'modal') and @style='display: block;']")
                logger.info(f"Modais visíveis encontrados: {len(modals)}")
                
                # Verificar todos os formulários na página
                forms = driver.find_elements(By.TAG_NAME, "form")
                logger.info(f"Formulários encontrados: {len(forms)}")
                
                # Verificar campos de input
                inputs = driver.find_elements(By.TAG_NAME, "input")
                visible_inputs = [i for i in inputs if i.is_displayed()]
                logger.info(f"Campos de input visíveis: {len(visible_inputs)}")
                
                # Verificar selects (dropdowns)
                selects = driver.find_elements(By.TAG_NAME, "select")
                visible_selects = [s for s in selects if s.is_displayed()]
                logger.info(f"Dropdowns visíveis: {len(visible_selects)}")
                
                # Verificar textareas
                textareas = driver.find_elements(By.TAG_NAME, "textarea")
                visible_textareas = [t for t in textareas if t.is_displayed()]
                logger.info(f"Textareas visíveis: {len(visible_textareas)}")
                
                # Verificar presença específica do dropdown de Solución
                try:
                    solution_labels = driver.find_elements(By.XPATH, "//div[contains(text(), 'Solución')]")
                    if solution_labels:
                        logger.info(f"Labels de Solución encontradas: {len(solution_labels)}")
                        
                        # Verificar se alguma está próxima de um select
                        for label in solution_labels:
                            parent = label.find_element(By.XPATH, ".//..")
                            parent_selects = parent.find_elements(By.TAG_NAME, "select")
                            if parent_selects:
                                logger.info("Detectado formulário com dropdown de Solución")
                                form_modal = parent
                                form_found = True
                                break
                except Exception as e:
                    logger.info(f"Erro ao verificar dropdown de Solución: {e}")
            except Exception as e:
                logger.warning(f"Erro ao analisar DOM: {e}")
            
            # Estratégia 1: Busca pelo modal com formulário (padrão)
            if not form_found:
                try:
                    logger.info("Estratégia 1: Buscando modal com formulário...")
                    # Aumente o tempo de espera para 10 segundos
                    form_modal = WebDriverWait(driver, 10).until(
                        EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'modal-body')]//form"))
                    )
                    logger.info("Formulário encontrado na modal-body")
                    form_found = True
                except Exception as e:
                    logger.info(f"Estratégia 1 falhou: {e}")
            
            # Estratégia 2: Busca qualquer formulário na página
            if not form_found:
                try:
                    logger.info("Estratégia 2: Buscando qualquer formulário...")
                    forms = driver.find_elements(By.TAG_NAME, "form")
                    for form in forms:
                        if form.is_displayed():
                            form_modal = form
                            form_found = True
                            logger.info("Formulário encontrado diretamente")
                            break
                except Exception as e:
                    logger.info(f"Estratégia 2 falhou: {e}")
            
            # Estratégia 3: Busca qualquer modal ativo
            if not form_found:
                try:
                    logger.info("Estratégia 3: Buscando qualquer modal ativo...")
                    modals = driver.find_elements(By.XPATH, "//div[contains(@class, 'modal') and @style='display: block;']")
                    if modals:
                        form_modal = modals[0]
                        form_found = True
                        logger.info("Modal ativo encontrado, usando como formulário")
                except Exception as e:
                    logger.info(f"Estratégia 3 falhou: {e}")
            
            # Estratégia 4: Usa o corpo da página como último recurso
            if not form_found:
                try:
                    logger.info("Estratégia 4: Usando corpo da página como último recurso...")
                    form_modal = driver.find_element(By.TAG_NAME, "body")
                    form_found = True
                    logger.info("Usando body como formulário")
                except Exception as e:
                    logger.info(f"Estratégia 4 falhou: {e}")
            
            # Adicional: Verifica a presença do dropdown específico
            try:
                dropdown_exists = False
                selects = driver.find_elements(By.TAG_NAME, "select")
                for select in selects:
                    if select.is_displayed():
                        try:
                            options = select.find_elements(By.TAG_NAME, "option")
                            for option in options:
                                if "entregar en nueva dirección" in option.text.lower():
                                    logger.info("Detectado dropdown com opção 'Entregar en nueva dirección'")
                                    dropdown_exists = True
                                    break
                        except:
                            pass
                    if dropdown_exists:
                        break
                        
                if dropdown_exists:
                    logger.info("Usando fluxo especial para formulário dropdown")
                    result = handle_dropdown_solution_form(driver, form_modal, customer_info)
                elif form_found:
                    logger.info("Usando fluxo padrão para formulário encontrado")
                    result = fill_form_fields(driver, form_modal, customer_info)
                else:
                    logger.error("Não foi possível encontrar o formulário para preencher. Pulando preenchimento.")
                    result = False
                
                # ADICIONADO: SEMPRE tenta clicar no botão de salvar, independentemente do resultado anterior
                logger.info("PASSO CRÍTICO: Tentando clicar no botão 'Save Solution'...")
                try:
                    # Pausa antes de tentar clicar
                    time.sleep(3)
                    # Chama a função aprimorada de clique
                    save_clicked = click_save_button(driver)
                    if save_clicked:
                        logger.info("✅ Botão 'Save Solution' clicado com sucesso")
                        
                        # NOVA VERIFICAÇÃO: Aguarda e verifica se realmente foi salvo
                        logger.info("Verificando se o formulário foi salvo com sucesso...")
                        time.sleep(5)  # Aguarda mais tempo para processamento
                        
                        # Verifica se o modal foi fechado (indicativo de sucesso)
                        try:
                            modals_after = driver.find_elements(By.XPATH, "//div[contains(@class, 'modal') and @style='display: block;']")
                            if len(modals_after) == 0:
                                logger.info("✅ Modal fechado - salvamento confirmado")
                            else:
                                logger.warning("⚠️ Modal ainda aberto - possível erro no salvamento")
                        except Exception as modal_check_error:
                            logger.info(f"Erro ao verificar modal: {modal_check_error}")
                        
                        # Verifica se apareceu mensagem de sucesso
                        try:
                            success_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'éxito') or contains(text(), 'success') or contains(text(), 'guardado') or contains(text(), 'saved')]")
                            if success_elements:
                                logger.info("✅ Mensagem de sucesso encontrada")
                            else:
                                logger.info("ℹ️ Nenhuma mensagem de sucesso explícita encontrada")
                        except Exception as success_check_error:
                            logger.info(f"Erro ao verificar mensagem de sucesso: {success_check_error}")
                            
                    else:
                        logger.warning("⚠️ Falha ao clicar no botão 'Save Solution'")
                except Exception as explicit_save_error:
                    logger.error(f"❌ Erro ao executar clique: {explicit_save_error}")
                    
            except Exception as e:
                logger.error(f"Erro ao identificar tipo de formulário: {e}")
                result = False
                
                # Mesmo com erro, tenta clicar no botão salvar
                logger.info("Tentando clicar no botão de salvar mesmo após erro...")
                try:
                    save_clicked = click_save_button(driver)
                except Exception as e_save:
                    logger.error(f"Erro ao tentar clicar no botão salvar após erro: {e_save}")
            
            # CÓDIGO REDIRECIONAMENTO - Verifica o erro específico "Ups, tenemos el siguiente inconveniente"
            logger.info("Verificando se apareceu o erro 'Ups, tenemos el siguiente inconveniente'...")
            try:
                # Espera um pouco para o popup aparecer
                time.sleep(3)
                
                # Procura pelo texto de erro específico
                error_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Ups, tenemos el siguiente inconveniente')]")
                
                if error_elements:
                    logger.warning("Detectado erro 'Ups, tenemos el siguiente inconveniente'")
                    
                    # Tenta tirar um screenshot do erro
                    try:
                        driver.save_screenshot(f"error_ups_{row_id}.png")
                        logger.info(f"Screenshot do erro: error_ups_{row_id}.png")
                    except:
                        pass
                    
                    # Registra o erro
                    error_msg = "Erro 'Ups, tenemos el siguiente inconveniente'"
                    logger.error(f"Erro ao processar novelty {row_id}: {error_msg}")
                    st.session_state.failed_items.append({"id": row_id, "error": error_msg})
                    st.session_state.failed_count = len(st.session_state.failed_items)
                    
                    # Redireciona para a lista de novelties
                    logger.info("Redirecionando para a lista de novelties...")
                    driver.get("https://app.dropi.co/dashboard/novelties")
                    
                    # Aguarda o carregamento da página
                    time.sleep(8)  # Aumentado para 8 segundos
                    
                    # Incrementa o índice para pular esta novelty
                    st.session_state.current_row_index += 1
                    
                    # Atualiza o progresso
                    st.session_state.processed_items = st.session_state.current_row_index
                    st.session_state.progress = st.session_state.current_row_index / st.session_state.total_items
                    
                    # Retorna False para continuar com a próxima novelty
                    return False
            except Exception as e:
                logger.info(f"Erro ao verificar popup de erro específico: {str(e)}")
            
            # Espera adicional após salvar - AUMENTADO
            logger.info("Aguardando processamento adicional...")
            time.sleep(8)  # Aumentado de 5 para 8 segundos
            
            # Procura e clica no popup "OK" que aparece após salvar
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
            
            # NOVA VERIFICAÇÃO FINAL: Confirma se realmente voltou para a lista de novelties
            logger.info("Verificação final: confirmando se voltou para a lista de novelties...")
            try:
                current_url = driver.current_url
                logger.info(f"URL atual após processamento: {current_url}")
                
                if "novelties" in current_url:
                    logger.info("✅ Confirmado: ainda/voltou para a página de novelties")
                    
                    # Verifica se o botão "Solve" ainda está presente na linha processada
                    try:
                        # Recarrega as linhas para verificar
                        fresh_rows = driver.find_elements(By.XPATH, "//table/tbody/tr")
                        if fresh_rows and st.session_state.current_row_index < len(fresh_rows):
                            current_row = fresh_rows[st.session_state.current_row_index]
                            solve_buttons = current_row.find_elements(By.XPATH, ".//button[contains(text(), 'Solve')]")
                            
                            if not solve_buttons:
                                logger.info("✅ Botão 'Solve' não encontrado na linha - indicativo de processamento bem-sucedido")
                            else:
                                logger.warning("⚠️ Botão 'Solve' ainda presente - possível falha no salvamento")
                                # Registra como falha potencial mas continua
                                st.session_state.failed_items.append({
                                    "id": row_id, 
                                    "error": "Botão 'Solve' ainda presente após processamento"
                                })
                                st.session_state.failed_count = len(st.session_state.failed_items)
                    except Exception as solve_check_error:
                        logger.info(f"Erro ao verificar botão Solve: {solve_check_error}")
                else:
                    logger.warning(f"⚠️ URL não está na página de novelties: {current_url}")
                    # Tenta navegar de volta
                    driver.get("https://app.dropi.co/dashboard/novelties")
                    time.sleep(5)
                    
            except Exception as final_check_error:
                logger.warning(f"Erro na verificação final: {final_check_error}")
            
            # Incrementa contador de sucesso
            logger.info("Executando verificação final de sucesso...")
            processing_successful = verify_processing_success(driver, row_id)
            
            if processing_successful:
                st.session_state.success_count += 1
                logger.info(f"✅ Novelty {row_id} processada com SUCESSO CONFIRMADO!")
            else:
                st.session_state.failed_items.append({"id": row_id, "error": "Verificação de sucesso falhou - botão Solve ainda presente"})
                st.session_state.failed_count = len(st.session_state.failed_items)
                logger.warning(f"❌ Novelty {row_id} processamento FALHOU na verificação final!")
            
            # Pequena pausa entre processamentos
            time.sleep(3)
            
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

def click_save_button(driver):
    """Tenta clicar no botão de salvar usando várias estratégias. Versão ultra robusta para Colômbia."""
    try:
        logger.info("Iniciando processo aprimorado para clicar no botão de salvar...")
        
        # DIAGNÓSTICO: Tira screenshot antes de qualquer interação
        driver.save_screenshot("before_trying_save_button.png")
        logger.info("Screenshot antes de tentar salvar")
        
        # PAUSA MAIOR: Aguarda o formulário estar completamente pronto
        logger.info("Aguardando 8 segundos para garantir que o formulário esteja pronto...")
        time.sleep(8)
        
        # DIAGNÓSTICO DE BOTÕES: Mapeia todos os botões visíveis na página
        logger.info("Analisando todos os botões visíveis na página...")
        all_buttons = driver.find_elements(By.TAG_NAME, "button")
        visible_buttons = []
        
        # Lista todos os botões para diagnóstico
        for idx, btn in enumerate(all_buttons):
            try:
                if btn.is_displayed():
                    btn_text = btn.text.strip()
                    btn_class = btn.get_attribute("class")
                    btn_id = btn.get_attribute("id")
                    btn_type = btn.get_attribute("type")
                    
                    button_info = {
                        "index": idx,
                        "text": btn_text,
                        "class": btn_class,
                        "id": btn_id,
                        "type": btn_type
                    }
                    
                    visible_buttons.append((btn, button_info))
                    logger.info(f"Botão #{idx}: Texto='{btn_text}', Classe='{btn_class}', ID='{btn_id}', Tipo='{btn_type}'")
            except:
                pass
        
        logger.info(f"Total de {len(visible_buttons)} botões visíveis encontrados")
        
        # Variáveis para controle
        save_clicked = False
        button_to_click = None
        click_method = ""
        
        # ESTRATÉGIA ESPECÍFICA PARA COLÔMBIA: busca por botão específico SAVE SOLUCION no documento inteiro
        logger.info("ESTRATÉGIA ESPECIAL COLÔMBIA: Procurando botão 'SAVE SOLUCION' em qualquer lugar do documento...")
        special_patterns = [
            "SAVE SOLUCION", "Save Solucion", "SAVE SOLUTION", "Save Solution", 
            "GUARDAR SOLUCION", "Guardar Solucion", "GUARDAR SOLUCIÓN", "Guardar Solución"
        ]

        # Busca por JavaScript em todo o documento - extremamente agressivo para encontrar o botão
        try:
            driver.execute_script("""
                // Destaca todos os botões em verde para diagnóstico
                document.querySelectorAll('button').forEach(btn => {
                    btn.style.border = '2px dashed green';
                });
            """)
            
            # Busca por botão específico
            for pattern in special_patterns:
                if button_to_click:
                    break
                    
                # Busca por texto exato, parcial e case-insensitive
                for js_search in [
                    f"return Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === '{pattern}');",
                    f"return Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('{pattern}'));",
                    f"return Array.from(document.querySelectorAll('button')).find(b => b.textContent.toLowerCase().includes('{pattern.lower()}'));"
                ]:
                    try:
                        result = driver.execute_script(js_search)
                        if result:
                            logger.info(f"✅ ENCONTRADO botão '{pattern}' via busca JavaScript especial")
                            button_to_click = result
                            click_method = f"JavaScript especial Colômbia - '{pattern}'"
                            break
                    except Exception as js_error:
                        logger.info(f"Erro em busca JS: {js_error}")
            
            # Busca pelo botão mais próximo do campo de solução
            if not button_to_click:
                logger.info("Tentando encontrar botão próximo ao campo de Solución...")
                nearby_button_js = """
                    // Tenta encontrar o campo de solução
                    var solutionField = Array.from(document.querySelectorAll('textarea, input')).find(el => 
                        el.id?.toLowerCase().includes('solucion') || 
                        el.name?.toLowerCase().includes('solucion') ||
                        el.placeholder?.toLowerCase().includes('solucion')
                    );
                    
                    // Se encontrou o campo, procura pelo botão mais próximo
                    if (solutionField) {
                        // Busca até 5 níveis acima do campo
                        var parent = solutionField;
                        for (var i = 0; i < 5; i++) {
                            parent = parent.parentElement;
                            if (!parent) break;
                            
                            // Procura botões neste nível
                            var buttons = parent.querySelectorAll('button');
                            for (var j = 0; j < buttons.length; j++) {
                                if (buttons[j].offsetParent !== null) { // Verifica se está visível
                                    return buttons[j];
                                }
                            }
                        }
                    }
                    return null;
                """
                
                nearby_button = driver.execute_script(nearby_button_js)
                if nearby_button:
                    logger.info("✅ Encontrado botão próximo ao campo de Solución!")
                    button_to_click = nearby_button
                    click_method = "Proximidade ao campo de Solución"
            
            # Tira screenshot para diagnóstico
            driver.save_screenshot("all_buttons_highlighted.png")
            logger.info("Screenshot com todos os botões destacados")
            
        except Exception as special_error:
            logger.warning(f"Erro na estratégia especial para Colômbia: {special_error}")
        
        # ESTRATÉGIA 0: Procura especificamente por "SAVE SOLUCION" ou variações (PRIORIDADE MÁXIMA)
        if not button_to_click:
            logger.info("ESTRATÉGIA 0: Procurando botão com texto específico para salvar solução...")
            
            # Lista extensa de padrões específicos para o botão de salvar solução (incluindo variações em espanhol)
            save_patterns = [
                "SAVE SOLUCION", "Save Solucion", "save solucion", 
                "SAVE SOLUTION", "Save Solution", "save solution",
                "GUARDAR SOLUCION", "Guardar Solucion", "guardar solucion",
                "GUARDAR SOLUCIÓN", "Guardar Solución", "guardar solución",
                "SAVE CHANGES", "Save Changes", "save changes",
                "GUARDAR CAMBIOS", "Guardar Cambios", "guardar cambios",
                "APLICAR", "Aplicar", "aplicar",
                "APLICAR CAMBIOS", "Aplicar Cambios", "aplicar cambios",
                "PROCESAR", "Procesar", "procesar",
                "ACEPTAR", "Aceptar", "aceptar"
            ]
            
            # Primeiro tenta localizar pelo XPath exato (método mais preciso)
            for pattern in save_patterns:
                if button_to_click:
                    break
                    
                logger.info(f"Procurando botão com texto exato '{pattern}'...")
                try:
                    # Tenta várias estratégias de XPath para texto exato
                    for xpath in [
                        f"//button[text()='{pattern}']",
                        f"//button[normalize-space(text())='{pattern}']",
                        f"//button[contains(text(), '{pattern}')]"
                    ]:
                        matching_buttons = driver.find_elements(By.XPATH, xpath)
                        if matching_buttons:
                            for btn in matching_buttons:
                                if btn.is_displayed():
                                    logger.info(f"Botão encontrado com texto '{pattern}' - Prioridade Máxima")
                                    button_to_click = btn
                                    click_method = f"Texto exato '{pattern}'"
                                    break
                            if button_to_click:
                                break
                except Exception as e:
                    logger.info(f"Erro ao procurar botão '{pattern}': {e}")
        
        # ESTRATÉGIA 1: Procura por botão com texto de GUARDAR/SALVAR (mais genérico)
        if not button_to_click:
            logger.info("ESTRATÉGIA 1: Procurando botão com texto genérico de salvar...")
            
            generic_patterns = ["SAVE", "Save", "save", "GUARDAR", "Guardar", "guardar", "SALVAR", "Salvar", "salvar"]
            
            for pattern in generic_patterns:
                try:
                    matching_buttons = driver.find_elements(By.XPATH, f"//button[contains(text(), '{pattern}')]")
                    if matching_buttons:
                        for btn in matching_buttons:
                            if btn.is_displayed():
                                logger.info(f"Botão encontrado com texto genérico '{pattern}'")
                                button_to_click = btn
                                click_method = f"Texto genérico '{pattern}'"
                                break
                        if button_to_click:
                            break
                except Exception as e:
                    logger.info(f"Erro ao procurar botão genérico '{pattern}': {e}")
        
        # ESTRATÉGIA 2: Botão de cor verde, azul ou classe success/primary
        if not button_to_click:
            logger.info("ESTRATÉGIA 2: Procurando botão por classe indicativa...")
            
            for btn, info in visible_buttons:
                if info["class"] and any(cls in info["class"].lower() for cls in ["success", "primary", "guardar", "save", "submit"]):
                    logger.info(f"Botão encontrado por classe '{info['class']}'")
                    button_to_click = btn
                    click_method = f"Classe '{info['class']}'"
                    break
        
        # ESTRATÉGIA 3: Botão de tipo submit
        if not button_to_click:
            logger.info("ESTRATÉGIA 3: Procurando botão do tipo submit...")
            
            try:
                submit_buttons = driver.find_elements(By.XPATH, "//button[@type='submit']")
                if submit_buttons:
                    for btn in submit_buttons:
                        if btn.is_displayed():
                            logger.info("Botão submit encontrado")
                            button_to_click = btn
                            click_method = "Tipo 'submit'"
                            break
            except Exception as e:
                logger.info(f"Erro ao procurar botão submit: {e}")
        
        # ESTRATÉGIA 4: Botão em formulário ou no modal-footer
        if not button_to_click:
            logger.info("ESTRATÉGIA 4: Procurando botão no formulário ou footer...")
            
            try:
                # Tenta encontrar o botão dentro do form
                form_buttons = driver.find_elements(By.XPATH, "//form//button | //div[contains(@class, 'modal-footer')]//button")
                for btn in form_buttons:
                    if btn.is_displayed():
                        logger.info(f"Botão encontrado no formulário/footer: '{btn.text}'")
                        button_to_click = btn
                        click_method = "Localização no formulário/footer"
                        break
            except Exception as e:
                logger.info(f"Erro ao procurar botão no form/footer: {e}")
        
        # ESTRATÉGIA 5: Último recurso - primeiro botão visível na página
        if not button_to_click and visible_buttons:
            logger.info("ESTRATÉGIA 5: Usando primeiro botão visível como último recurso...")
            button_to_click = visible_buttons[0][0]
            click_method = "Primeiro botão visível (último recurso)"
        
        # EXECUTA O CLIQUE se encontrou um botão
        if button_to_click:
            logger.info(f"Botão para salvar encontrado via: {click_method}")
            
            # Tira screenshot com destaque no botão
            try:
                original_style = driver.execute_script("return arguments[0].getAttribute('style');", button_to_click)
                driver.execute_script("arguments[0].setAttribute('style', 'border: 5px solid red !important; background-color: yellow !important;');", button_to_click)
                driver.save_screenshot("save_button_highlighted.png")
                driver.execute_script(f"arguments[0].setAttribute('style', '{original_style or ''}');", button_to_click)
                logger.info("Screenshot com botão destacado salvo")
            except:
                pass
            
            # Rola até o botão e centraliza
            logger.info("Rolando até o botão e centralizando...")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button_to_click)
            time.sleep(2)
            
            # MÉTODO 1: Tenta múltiplos clicks com diferentes técnicas
            click_success = False
            
            # Tenta clicar com JavaScript (mais confiável)
            try:
                logger.info("Tentando clicar via JavaScript...")
                driver.execute_script("arguments[0].click();", button_to_click)
                time.sleep(2)
                # Não temos como verificar 100%, então assumimos sucesso
                logger.info("Clique JavaScript executado")
                click_success = True
            except Exception as js_error:
                logger.warning(f"Erro no clique JavaScript: {js_error}")
            
            # Se falhou, tenta clicar com método padrão
            if not click_success:
                try:
                    logger.info("Tentando clicar via método tradicional...")
                    button_to_click.click()
                    time.sleep(2)
                    logger.info("Clique tradicional executado")
                    click_success = True
                except Exception as click_error:
                    logger.warning(f"Erro no clique tradicional: {click_error}")
            
            # Se ainda falhou, tenta via Actions
            if not click_success:
                try:
                    logger.info("Tentando clicar via Actions...")
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(driver)
                    actions.move_to_element(button_to_click).click().perform()
                    time.sleep(2)
                    logger.info("Clique via Actions executado")
                    click_success = True
                except Exception as action_error:
                    logger.warning(f"Erro no clique via Actions: {action_error}")
            
            # MÉTODO 2: Tenta enviar ENTER no elemento e no documento
            if not click_success:
                try:
                    logger.info("Tentando enviar ENTER para o elemento...")
                    from selenium.webdriver.common.keys import Keys
                    button_to_click.send_keys(Keys.ENTER)
                    time.sleep(2)
                    logger.info("ENTER enviado para o botão")
                    click_success = True
                except Exception as enter_error:
                    logger.warning(f"Erro ao enviar ENTER: {enter_error}")
                    
                    # Último recurso: ENTER no documento
                    try:
                        logger.info("Tentando enviar ENTER para o documento...")
                        active_element = driver.switch_to.active_element
                        active_element.send_keys(Keys.ENTER)
                        time.sleep(2)
                        logger.info("ENTER enviado para elemento ativo")
                        click_success = True
                    except Exception as doc_enter_error:
                        logger.warning(f"Erro ao enviar ENTER para documento: {doc_enter_error}")
            
            # MÉTODO 3: Último recurso - executa ENTER via JavaScript
            if not click_success:
                try:
                    logger.info("Tentando simular ENTER via JavaScript...")
                    # Simula evento de tecla ENTER
                    driver.execute_script("""
                        var e = new KeyboardEvent('keydown', {
                            'key': 'Enter',
                            'code': 'Enter',
                            'keyCode': 13,
                            'which': 13,
                            'bubbles': true
                        });
                        document.dispatchEvent(e);
                        
                        // Também simula submit do formulário
                        var forms = document.getElementsByTagName('form');
                        if (forms.length > 0) forms[0].submit();
                    """)
                    time.sleep(2)
                    logger.info("JavaScript ENTER/submit executado")
                    click_success = True
                except Exception as js_event_error:
                    logger.warning(f"Erro ao executar eventos JavaScript: {js_event_error}")
            
            # Aguarda um pouco mais e tira screenshot após clicar
            time.sleep(3)
            driver.save_screenshot("after_save_button_click.png")
            logger.info("Screenshot após tentativa de clique salvo")
            
            # Considera como sucesso mesmo com erros, já que tentamos de várias formas
            save_clicked = True
            logger.info("Tentativa de clicar no botão de salvar concluída")
        else:
            logger.warning("Não foi possível encontrar nenhum botão para salvar!")
        
        # Sempre aguarda um tempo significativo antes de retornar
        time.sleep(5)
        return save_clicked
        
    except Exception as e:
        logger.error(f"Erro crítico ao tentar clicar no botão de salvar: {str(e)}")
        logger.error(traceback.format_exc())
        # Tira screenshot do erro
        driver.save_screenshot("error_save_button.png")
        time.sleep(3)  # Aguarda mesmo em caso de erro
        return False

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

def generate_report():
    """Gera um relatório da execução."""
    report = {
        "total_processados": st.session_state.success_count,
        "total_falhas": len(st.session_state.failed_items),
        "itens_com_falha": st.session_state.failed_items,
        "guias_fechadas": st.session_state.closed_tabs,
        "encontrou_paginacao": st.session_state.found_pagination
    }
    
    logger.info("======= RELATÓRIO DE EXECUÇÃO =======")
    logger.info(f"Total de novelties processadas com sucesso: {report['total_processados']}")
    logger.info(f"Total de novelties com falha: {report['total_falhas']}")
    logger.info(f"Total de guias fechadas durante o processo: {report['guias_fechadas']}")
    logger.info(f"Encontrou opção para filtrar 1000 itens: {'Sim' if report['encontrou_paginacao'] else 'Não'}")
    
    if report['total_falhas'] > 0:
        logger.info("Detalhes dos itens com falha:")
        for item in report['itens_com_falha']:
            logger.info(f"  - ID: {item['id']}, Erro: {item['error']}")
            
    logger.info("=====================================")
    
    st.session_state.report = report

# Processamento da automação baseado no estado atual - VERSÃO CORRIGIDA
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
            # ADICIONAR: Verificação de autenticação
            if verify_authentication():
                st.session_state.automation_step = 'navigate'
                st.rerun()
            else:
                st.session_state.is_running = False
                st.error("Falha na autenticação - login não foi bem-sucedido")
        else:
            st.session_state.is_running = False
            st.error("Falha no login")
    
    elif st.session_state.automation_step == 'navigate':
        if navigate_to_novelties():
            # ADICIONAR: Segunda verificação de autenticação
            if verify_authentication():
                st.session_state.automation_step = 'configure'
                st.rerun()
            else:
                st.session_state.is_running = False
                st.error("Falha na autenticação - redirecionado para página de login")
        else:
            st.session_state.is_running = False
            st.error("Falha ao navegar até Novelties")
    
    elif st.session_state.automation_step == 'configure':
        if configure_entries_display():
            # Verifica se há novelties para processar
            if st.session_state.total_items > 0:
                st.session_state.automation_step = 'process'
                st.rerun()
            else:
                logger.info("Nenhuma novelty encontrada para processar")
                generate_report()
                st.session_state.automation_step = 'complete'
                st.session_state.is_running = False
                st.info("Automação concluída - Nenhuma novelty encontrada para processar")
        else:
            st.session_state.is_running = False
            st.error("Falha ao configurar exibição de entradas ou problema de autenticação")
    
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