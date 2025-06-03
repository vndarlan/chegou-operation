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
from selenium.webdriver.common.keys import Keys
import logging
import traceback
from io import StringIO
import sys
import os
import platform
import re
import datetime
import plotly.express as px

# Adiciona o diretório pai ao path para importar db_connection
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from db_connection import get_execution_history, is_railway
except ImportError:
    st.error("❌ Erro ao importar db_connection. Verifique se o arquivo existe no diretório raiz.")
    def get_execution_history(*args, **kwargs):
        return pd.DataFrame()
    def is_railway():
        return "RAILWAY_ENVIRONMENT" in os.environ
    
THIS_COUNTRY = "chile"

# Função para criar pasta de screenshots se não existir
def create_screenshots_folder():
    if not os.path.exists("screenshots"):
        os.makedirs("screenshots")
        return "screenshots"
    return "screenshots"

# Título e descrição
st.markdown("<h1 style='text-align: center;'>🇨🇱 Automação Chile</h1>", unsafe_allow_html=True)

# CSS customizado
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

# Verifica se o usuário tem permissão
if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
    st.error("❌ Você precisa estar logado para acessar esta página.")
    st.stop()

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
if 'screenshots_folder' not in st.session_state:
    st.session_state.screenshots_folder = create_screenshots_folder()

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

# Interface do usuário
col1, col2 = st.columns([2, 1])

# FUNÇÕES DE DEBUG E VERIFICAÇÃO
def verify_credentials_and_urls():
    """Verifica se as credenciais e URLs estão corretas."""
    logger.info("=== VERIFICAÇÃO DE CREDENCIAIS E URLS ===")
    
    # CREDENCIAIS ATUAIS
    current_email = "llegolatiendachile@gmail.com"
    current_password = "Chegou123!"
    
    logger.info(f"Email atual: {current_email}")
    logger.info(f"Senha atual: {'*' * len(current_password)}")
    
    # TESTE: URLs DO DROPI QUE PODEM TER MUDADO
    test_urls = [
        "https://app.dropi.cl",
        "https://app.dropi.cl/auth/login", 
        "https://app.dropi.cl/login",
        "https://dropi.cl/login",
        "https://app.dropi.co/auth/login",
        "https://panel.dropi.cl/login",
        "https://admin.dropi.cl/login"
    ]
    
    logger.info("URLs sendo testadas:")
    for url in test_urls:
        logger.info(f"  - {url}")
    
    return current_email, current_password, test_urls

def test_login_page_accessibility():
    """Testa se as páginas de login estão acessíveis."""
    try:
        driver = st.session_state.driver
        
        urls_to_test = [
            "https://app.dropi.cl/auth/login",
            "https://app.dropi.cl/login", 
            "https://dropi.cl/login"
        ]
        
        accessible_urls = []
        
        for url in urls_to_test:
            try:
                logger.info(f"Testando acessibilidade de: {url}")
                driver.get(url)
                time.sleep(3)
                
                current_url = driver.current_url
                page_title = driver.title
                
                # Verifica se tem campos de login
                email_inputs = driver.find_elements(By.XPATH, "//input[@type='email' or contains(@name, 'email') or contains(@placeholder, 'email')]")
                password_inputs = driver.find_elements(By.XPATH, "//input[@type='password']")
                
                if email_inputs and password_inputs:
                    accessible_urls.append({
                        "url": url,
                        "final_url": current_url,
                        "title": page_title,
                        "has_login_form": True
                    })
                    logger.info(f"✅ {url} - ACESSÍVEL com formulário de login")
                else:
                    logger.warning(f"❌ {url} - Sem formulário de login válido")
                    
            except Exception as e:
                logger.error(f"❌ Erro ao acessar {url}: {str(e)}")
        
        return accessible_urls
        
    except Exception as e:
        logger.error(f"Erro no teste de acessibilidade: {str(e)}")
        return []

def alternative_login_flow():
    """Fluxo de login alternativo para casos especiais."""
    try:
        driver = st.session_state.driver
        
        logger.info("=== TENTANDO FLUXO DE LOGIN ALTERNATIVO ===")
        
        # Tenta limpar cookies e cache primeiro
        try:
            driver.delete_all_cookies()
            logger.info("Cookies limpos")
        except:
            pass
        
        # URLs alternativas com diferentes formatos
        alternative_urls = [
            "https://app.dropi.cl/",  # Página inicial primeiro
            "https://dropi.cl/", 
            "https://panel.dropi.cl/"
        ]
        
        for base_url in alternative_urls:
            try:
                logger.info(f"Tentando acesso via: {base_url}")
                driver.get(base_url)
                time.sleep(3)
                
                # Procura por links de login na página
                login_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'login') or contains(text(), 'Login') or contains(text(), 'Iniciar')]")
                
                if login_links:
                    for link in login_links:
                        if link.is_displayed():
                            try:
                                logger.info(f"Clicando em link de login: {link.text}")
                                link.click()
                                time.sleep(3)
                                
                                # Verifica se chegou na página de login
                                current_url = driver.current_url
                                if "login" in current_url.lower():
                                    logger.info(f"✅ Página de login alcançada via link: {current_url}")
                                    return True
                            except Exception as e:
                                logger.info(f"Erro ao clicar no link: {str(e)}")
                                continue
                
            except Exception as e:
                logger.info(f"Erro ao tentar {base_url}: {str(e)}")
                continue
        
        return False
        
    except Exception as e:
        logger.error(f"Erro no fluxo alternativo: {str(e)}")
        return False

def show_debug_instructions():
    """Mostra instruções de debug para o usuário."""
    logger.info("=== INSTRUÇÕES DE DEBUG ===")
    logger.info("1. Verifique se as credenciais estão corretas:")
    logger.info(f"   Email: llegolatiendachile@gmail.com")
    logger.info(f"   Senha: Chegou123!")
    logger.info("")
    logger.info("2. Verifique se o site está funcionando:")
    logger.info("   - Acesse https://app.dropi.cl/auth/login manualmente")
    logger.info("   - Teste o login manual com as credenciais")
    logger.info("")
    logger.info("3. Possíveis problemas:")
    logger.info("   - Site do Dropi pode estar fora do ar")
    logger.info("   - Credenciais podem ter expirado")
    logger.info("   - URL de login pode ter mudado")
    logger.info("   - Pode ter captcha ou 2FA ativado")
    logger.info("")
    logger.info("4. Verifique os screenshots salvos em /app/screenshots/")
    logger.info("   - login_page.png (como a página aparece)")
    logger.info("   - after_login.png (resultado após tentativa)")
    logger.info("=====================================")

# Interface de teste manual de credenciais
def manual_credential_test():
    """Permite testar credenciais manualmente."""
    try:
        logger.info("=== TESTE MANUAL DE CREDENCIAIS ===")
        
        # Cria uma interface simples no Streamlit para teste
        with st.expander("🔧 Debug: Teste Manual de Credenciais", expanded=False):
            st.write("Use esta seção para testar credenciais diferentes:")
            
            test_email = st.text_input("Email de teste:", value="llegolatiendachile@gmail.com")
            test_password = st.text_input("Senha de teste:", value="Chegou123!", type="password")
            
            if st.button("Testar Credenciais"):
                st.session_state.email = test_email
                st.session_state.password = test_password
                st.info(f"Credenciais atualizadas: {test_email}")
                st.rerun()
        
        return True
        
    except Exception as e:
        logger.error(f"Erro no teste manual: {str(e)}")
        return False

# Mostra a interface de teste de credenciais
manual_credential_test()

with st.form("automation_form"):
    submit_button = st.form_submit_button("Iniciar Automação", use_container_width=True)
    
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
            # Credenciais fixas
            st.session_state.email = "llegolatiendachile@gmail.com"
            st.session_state.password = "Chegou123!"
            st.session_state.use_headless = use_headless
            st.success("Iniciando automação... Aguarde.")
            st.rerun()

if st.session_state.is_running:
    st.info("✅ Automação em execução...")
    
    if st.button("Parar Automação"):
        st.session_state.is_running = False
        
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
if 'show_log' not in st.session_state:
    st.session_state.show_log = False

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

# Rodapé
st.markdown("---")
st.caption("Automação Dropi Novelties Chile © 2025")

# FUNÇÕES DE AUTOMAÇÃO 
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

def enhanced_setup_driver():
    """Setup do driver com verificações adicionais."""
    logger.info("=== SETUP AVANÇADO DO DRIVER ===")
    
    # Verifica credenciais primeiro
    email, password, test_urls = verify_credentials_and_urls()
    st.session_state.email = email
    st.session_state.password = password
    
    # Setup normal do driver
    if not setup_driver():
        return False
    
    # Testa acessibilidade das páginas de login
    accessible_urls = test_login_page_accessibility()
    
    if accessible_urls:
        logger.info(f"✅ {len(accessible_urls)} URLs de login acessíveis encontradas")
        for url_info in accessible_urls:
            logger.info(f"  - {url_info['url']} -> {url_info['title']}")
    else:
        logger.error("❌ Nenhuma URL de login acessível encontrada")
        # Tenta fluxo alternativo
        if alternative_login_flow():
            logger.info("✅ Fluxo alternativo funcionou")
        else:
            logger.error("❌ Fluxo alternativo também falhou")
            return False
    
    return True

def login():
    """Função de login melhorada com debug detalhado."""
    try:
        driver = st.session_state.driver
        driver.maximize_window()
        
        # CREDENCIAIS PARA TESTE - VERIFIQUE SE ESTÃO CORRETAS
        email = st.session_state.email  # "llegolatiendachile@gmail.com"
        password = st.session_state.password  # "Chegou123!"
        
        logger.info("=== INICIANDO PROCESSO DE LOGIN ===")
        logger.info(f"Email configurado: {email}")
        logger.info(f"Senha configurada: {'*' * len(password)}")
        
        # TESTE MÚLTIPLAS URLs DE LOGIN
        login_urls = [
            "https://app.dropi.cl/auth/login",
            "https://app.dropi.cl/login", 
            "https://dropi.cl/login",
            "https://app.dropi.co/auth/login"
        ]
        
        successful_url = None
        
        for url in login_urls:
            try:
                logger.info(f"Tentando URL: {url}")
                driver.get(url)
                time.sleep(3)
                
                current_url = driver.current_url
                page_title = driver.title
                logger.info(f"URL carregada: {current_url}")
                logger.info(f"Título da página: {page_title}")
                
                # Verifica se chegou numa página válida
                if "login" in current_url.lower() or "auth" in current_url.lower():
                    successful_url = url
                    logger.info(f"✅ URL válida encontrada: {url}")
                    break
                else:
                    logger.warning(f"❌ URL {url} redirecionou para: {current_url}")
                    
            except Exception as e:
                logger.warning(f"❌ Erro ao tentar URL {url}: {str(e)}")
                continue
        
        if not successful_url:
            logger.error("❌ Nenhuma URL de login válida encontrada")
            return False
        
        # Aguarda a página carregar completamente
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # CAPTURA SCREENSHOT PARA DEBUG
        try:
            screenshot_path = os.path.join(st.session_state.screenshots_folder, "login_page.png")
            driver.save_screenshot(screenshot_path)
            logger.info(f"Screenshot da página de login salvo: {screenshot_path}")
        except Exception as e:
            logger.warning(f"Não foi possível salvar screenshot: {str(e)}")
        
        # ANALISA A ESTRUTURA DA PÁGINA
        logger.info("=== ANALISANDO ESTRUTURA DA PÁGINA ===")
        
        # Verifica se há campos de input visíveis
        all_inputs = driver.find_elements(By.TAG_NAME, "input")
        visible_inputs = [inp for inp in all_inputs if inp.is_displayed()]
        logger.info(f"Total de inputs encontrados: {len(all_inputs)}")
        logger.info(f"Inputs visíveis: {len(visible_inputs)}")
        
        # Lista todos os inputs visíveis
        for i, inp in enumerate(visible_inputs):
            input_type = inp.get_attribute("type")
            input_name = inp.get_attribute("name")
            input_id = inp.get_attribute("id")
            input_placeholder = inp.get_attribute("placeholder")
            logger.info(f"Input {i}: tipo='{input_type}', nome='{input_name}', id='{input_id}', placeholder='{input_placeholder}'")
        
        # PROCURA POR CAMPOS DE EMAIL COM MÚLTIPLOS SELETORES
        email_field = None
        email_selectors = [
            "//input[@type='email']",
            "//input[@name='email']",
            "//input[@id='email']", 
            "//input[contains(@placeholder, 'email')]",
            "//input[contains(@placeholder, 'Email')]",
            "//input[contains(@placeholder, 'correo')]",
            "//input[contains(@name, 'user')]",
            "//input[contains(@id, 'user')]"
        ]
        
        for selector in email_selectors:
            try:
                email_elements = driver.find_elements(By.XPATH, selector)
                for element in email_elements:
                    if element.is_displayed():
                        email_field = element
                        logger.info(f"✅ Campo de email encontrado com seletor: {selector}")
                        break
                if email_field:
                    break
            except Exception as e:
                logger.info(f"Seletor {selector} falhou: {str(e)}")
        
        if not email_field:
            logger.error("❌ Campo de email não encontrado")
            # Tenta pegar o primeiro input de texto visível
            text_inputs = [inp for inp in visible_inputs if inp.get_attribute("type") in ["text", "email", ""]]
            if text_inputs:
                email_field = text_inputs[0]
                logger.warning(f"⚠️ Usando primeiro input de texto como campo de email")
            else:
                return False
        
        # PROCURA POR CAMPOS DE SENHA
        password_field = None
        password_selectors = [
            "//input[@type='password']",
            "//input[@name='password']",
            "//input[@id='password']",
            "//input[contains(@placeholder, 'senha')]",
            "//input[contains(@placeholder, 'password')]",
            "//input[contains(@placeholder, 'contraseña')]"
        ]
        
        for selector in password_selectors:
            try:
                password_elements = driver.find_elements(By.XPATH, selector)
                for element in password_elements:
                    if element.is_displayed():
                        password_field = element
                        logger.info(f"✅ Campo de senha encontrado com seletor: {selector}")
                        break
                if password_field:
                    break
            except Exception as e:
                logger.info(f"Seletor {selector} falhou: {str(e)}")
        
        if not password_field:
            logger.error("❌ Campo de senha não encontrado")
            return False
        
        # PREENCHE OS CAMPOS
        logger.info("=== PREENCHENDO CAMPOS ===")
        
        try:
            # Limpa e preenche email
            driver.execute_script("arguments[0].scrollIntoView(true);", email_field)
            time.sleep(0.5)
            email_field.clear()
            email_field.send_keys(email)
            logger.info(f"✅ Email preenchido: {email}")
            
            # Verifica se o email foi realmente preenchido
            email_value = email_field.get_attribute("value")
            logger.info(f"Valor atual do campo email: '{email_value}'")
            
        except Exception as e:
            logger.error(f"❌ Erro ao preencher email: {str(e)}")
            return False
        
        try:
            # Limpa e preenche senha
            driver.execute_script("arguments[0].scrollIntoView(true);", password_field)
            time.sleep(0.5)
            password_field.clear()
            password_field.send_keys(password)
            logger.info("✅ Senha preenchida")
            
            # Verifica se a senha foi realmente preenchida (sem mostrar o valor)
            password_value = password_field.get_attribute("value")
            logger.info(f"Campo senha preenchido: {len(password_value) > 0}")
            
        except Exception as e:
            logger.error(f"❌ Erro ao preencher senha: {str(e)}")
            return False
        
        # PROCURA E CLICA NO BOTÃO DE LOGIN
        logger.info("=== PROCURANDO BOTÃO DE LOGIN ===")
        
        login_button = None
        login_selectors = [
            "//button[contains(text(), 'Iniciar Sesión')]",
            "//button[contains(text(), 'Iniciar Sesion')]", 
            "//button[contains(text(), 'Login')]",
            "//button[contains(text(), 'Entrar')]",
            "//button[contains(text(), 'Ingresar')]",
            "//input[@type='submit']",
            "//button[@type='submit']",
            "//button[contains(@class, 'login')]",
            "//button[contains(@class, 'btn-primary')]"
        ]
        
        for selector in login_selectors:
            try:
                login_elements = driver.find_elements(By.XPATH, selector)
                for element in login_elements:
                    if element.is_displayed():
                        login_button = element
                        logger.info(f"✅ Botão de login encontrado com seletor: {selector}")
                        logger.info(f"Texto do botão: '{element.text}'")
                        break
                if login_button:
                    break
            except Exception as e:
                logger.info(f"Seletor {selector} falhou: {str(e)}")
        
        if not login_button:
            logger.error("❌ Botão de login não encontrado")
            # Lista todos os botões visíveis para debug
            all_buttons = driver.find_elements(By.TAG_NAME, "button")
            visible_buttons = [btn for btn in all_buttons if btn.is_displayed()]
            logger.info(f"Botões visíveis na página:")
            for i, btn in enumerate(visible_buttons):
                btn_text = btn.text
                btn_type = btn.get_attribute("type")
                btn_class = btn.get_attribute("class")
                logger.info(f"Botão {i}: texto='{btn_text}', tipo='{btn_type}', classe='{btn_class}'")
            return False
        
        # CLICA NO BOTÃO DE LOGIN
        logger.info("=== TENTANDO FAZER LOGIN ===")
        
        try:
            # Tenta múltiplos métodos de clique
            driver.execute_script("arguments[0].scrollIntoView(true);", login_button)
            time.sleep(1)
            
            # Método 1: Clique normal
            try:
                login_button.click()
                logger.info("✅ Clique normal realizado")
            except Exception as e1:
                logger.info(f"Clique normal falhou: {str(e1)}")
                # Método 2: JavaScript
                try:
                    driver.execute_script("arguments[0].click();", login_button)
                    logger.info("✅ Clique JavaScript realizado")
                except Exception as e2:
                    logger.info(f"Clique JavaScript falhou: {str(e2)}")
                    # Método 3: Enter no formulário
                    try:
                        password_field.send_keys(Keys.ENTER)
                        logger.info("✅ Enter enviado")
                    except Exception as e3:
                        logger.error(f"Todos os métodos de clique falharam: {str(e3)}")
                        return False
        except Exception as e:
            logger.error(f"❌ Erro ao clicar no botão de login: {str(e)}")
            return False
        
        # AGUARDA E VERIFICA O RESULTADO
        logger.info("=== VERIFICANDO RESULTADO DO LOGIN ===")
        time.sleep(8)  # Aguarda o redirecionamento
        
        current_url = driver.current_url
        page_title = driver.title
        logger.info(f"URL após login: {current_url}")
        logger.info(f"Título após login: {page_title}")
        
        # Captura screenshot após login
        try:
            screenshot_path = os.path.join(st.session_state.screenshots_folder, "after_login.png")
            driver.save_screenshot(screenshot_path)
            logger.info(f"Screenshot pós-login salvo: {screenshot_path}")
        except:
            pass
        
        # VERIFICA INDICADORES DE SUCESSO/FALHA
        success_indicators = ["dashboard", "novelties", "orders", "panel"]
        failure_indicators = ["login", "auth", "error", "invalid"]
        
        url_lower = current_url.lower()
        
        # Verifica indicadores de sucesso
        for indicator in success_indicators:
            if indicator in url_lower:
                logger.info(f"✅ LOGIN BEM-SUCEDIDO - Indicador de sucesso encontrado: {indicator}")
                return True
        
        # Verifica indicadores de falha
        for indicator in failure_indicators:
            if indicator in url_lower:
                logger.warning(f"❌ Possível falha de login - Indicador: {indicator}")
        
        # Verifica mensagens de erro na página
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            error_messages = ["credenciais inválidas", "senha incorreta", "email incorreto", "login failed", "error"]
            for error_msg in error_messages:
                if error_msg in page_text:
                    logger.error(f"❌ Mensagem de erro encontrada: {error_msg}")
                    return False
        except:
            pass
        
        # Se não redirecionou da página de login, provavelmente falhou
        if "login" in url_lower or "auth" in url_lower:
            logger.error("❌ LOGIN FALHOU - Ainda na página de login")
            return False
        
        # Teste final: tenta navegar para o dashboard
        logger.info("=== TESTE FINAL: NAVEGANDO PARA DASHBOARD ===")
        try:
            dashboard_urls = [
                "https://app.dropi.cl/dashboard",
                "https://app.dropi.cl/dashboard/novelties"
            ]
            
            for dashboard_url in dashboard_urls:
                try:
                    driver.get(dashboard_url)
                    time.sleep(3)
                    final_url = driver.current_url
                    
                    if "login" not in final_url.lower():
                        logger.info(f"✅ LOGIN CONFIRMADO - Acesso autorizado ao dashboard: {final_url}")
                        return True
                    else:
                        logger.warning(f"❌ Redirecionado para login ao tentar acessar: {dashboard_url}")
                except Exception as e:
                    logger.info(f"Erro ao testar dashboard {dashboard_url}: {str(e)}")
                    continue
        except Exception as e:
            logger.error(f"Erro no teste final: {str(e)}")
        
        logger.error("❌ LOGIN FALHOU - Não foi possível confirmar autenticação")
        return False
        
    except Exception as e:
        logger.error(f"❌ ERRO GERAL NO LOGIN: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def verify_authentication():
    """Verifica se o usuário está autenticado."""
    try:
        driver = st.session_state.driver
        current_url = driver.current_url
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        
        # Indicadores de que NÃO está autenticado
        if ("login" in current_url or 
            "registro" in page_text or 
            "crear cuenta" in page_text or
            "registrarme" in page_text):
            return False
        
        return True
    except:
        return False

def navigate_to_novelties():
    """Navega até a página de novelties."""
    try:
        driver = st.session_state.driver
        
        # Verifica se já estamos na dashboard
        logger.info("Verificando a página atual...")
        current_url = driver.current_url
        logger.info(f"URL atual: {current_url}")
        
        # CORREÇÃO: URL correta para novelties
        logger.info("Navegando diretamente para a página de novelties...")
        driver.get("https://app.dropi.cl/dashboard/novelties")  # URL CORRIGIDA
        time.sleep(5)
        
        # Verifica se chegou na página correta
        current_url = driver.current_url
        logger.info(f"URL atual após navegação: {current_url}")
        
        # Verifica se está autenticado
        if not verify_authentication():
            logger.error("Não está autenticado - redirecionado para página de registro/login")
            return False
        
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
        
        # VERIFICAÇÃO ADICIONAL: Confirma que está na página correta
        current_url = driver.current_url
        if "novelties" not in current_url:
            logger.warning(f"Não está na página de novelties. URL atual: {current_url}")
            logger.info("Tentando navegar para a página correta...")
            driver.get("https://app.dropi.cl/dashboard/novelties")  # URL CORRIGIDA
            time.sleep(5)
        
        # Verifica se a página tem conteúdo de novelties
        page_text = driver.find_element(By.TAG_NAME, "body").text
        if "registro" in page_text.lower() or "crear cuenta" in page_text.lower():
            logger.error("Está na página de registro em vez de novelties - problema de autenticação")
            return False
        
        # Rola até o final da página
        logger.info("Rolando até o final da página para verificar opções de exibição...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)  # Aguarda para verificar se a opção está presente
        
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

def extract_customer_info(driver):
    """Extrai informações do cliente da página, incluindo nome, endereço e telefone."""
    try:
        logger.info("Extraindo informações do cliente...")
        
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

def parse_chilean_address(address):
    """Extrai componentes específicos de um endereço chileno."""
    try:
        logger.info(f"Analisando endereço chileno: {address}")
        
        # Inicializa os componentes
        components = {
            "calle": "",
            "numero": "",
            "comuna": "",
            "region": ""
        }
        
        # PRIMEIRO: Sempre extrair o número (primeiro conjunto numérico) independentemente de outros processamentos
        numero_match = re.search(r'\d+', address)
        if numero_match:
            components["numero"] = numero_match.group(0)
            logger.info(f"Número extraído: {components['numero']}")
        else:
            # Se nenhum número for encontrado, usa "1" como valor padrão
            components["numero"] = "1"
            logger.info("Nenhum número encontrado no endereço, usando valor padrão: 1")
        
        # SEGUNDO: Extrai "calle" como tudo antes do primeiro "-" no endereço
        dash_index = address.find('-')
        if dash_index != -1:
            components["calle"] = address[:dash_index].strip()
            logger.info(f"Calle extraída (antes do primeiro '-'): '{components['calle']}'")
        else:
            # Se não encontrou o traço, usa método alternativo
            if numero_match:
                numero = components["numero"]
                # Para Calle, use todo o texto antes do número
                calle_index = address.find(numero)
                if calle_index > 0:
                    components["calle"] = address[:calle_index].strip()
                    logger.info(f"Calle extraída (método alternativo): '{components['calle']}'")
            else:
                # Se não encontrou número, usa o endereço completo como calle
                components["calle"] = address
                logger.info(f"Calle extraída (endereço completo): '{components['calle']}'")
        
        # SOLUÇÃO APRIMORADA PARA COMUNA E REGIÃO
        # Exemplo: "Melitene 555 Los Melitenes con Biobio -, CHILE, VINA DEL MAR - VALPARAISO"
        # Comuna: o texto entre a última vírgula e o último hífen -> "VINA DEL MAR"
        # Região: o texto após o último hífen -> "VALPARAISO"
        
        # Exemplo especial: "Calle santa clemira 17 Cerca de los carabineros -, CHILE, CHIGUAYANTE - BIO - BIO"
        # Comuna: "CHIGUAYANTE"
        # Região: "BIO - BIO"
        
        # Encontra a posição da última vírgula
        last_comma_index = address.rfind(',')
        
        if last_comma_index != -1:
            # Extrai a parte após a última vírgula que contém comuna e região
            comuna_region_part = address[last_comma_index+1:].strip()
            
            # Verifica se contém "BIO - BIO" no final (caso especial)
            if "BIO - BIO" in comuna_region_part.upper():
                logger.info("Detectado caso especial: BIO - BIO na região")
                
                # Procura pela posição de "BIO - BIO"
                bio_index = comuna_region_part.upper().find("BIO - BIO")
                
                # Encontra o hífen antes de "BIO - BIO"
                dash_before_bio = comuna_region_part[:bio_index].rfind('-')
                
                if dash_before_bio != -1:
                    # Comuna é o texto entre a vírgula e o hífen antes de "BIO - BIO"
                    components["comuna"] = comuna_region_part[:dash_before_bio].strip()
                    logger.info(f"Comuna extraída (caso BIO - BIO): '{components['comuna']}'")
                    
                    # Região é "BIO - BIO"
                    components["region"] = "BIO - BIO"
                    logger.info(f"Região extraída (caso especial): '{components['region']}'")
                else:
                    # Se não encontrou hífen antes de BIO - BIO, tenta extrair baseado em padrões
                    parts = comuna_region_part.split('-')
                    if len(parts) >= 3:  # Deve ter pelo menos 3 partes para ter "X - BIO - BIO"
                        components["comuna"] = parts[0].strip()
                        components["region"] = "BIO - BIO"
                        logger.info(f"Comuna extraída (caso BIO - BIO alternativo): '{components['comuna']}'")
                        logger.info(f"Região extraída (caso BIO - BIO alternativo): '{components['region']}'")
            else:
                # Encontra a posição do último hífen
                last_hyphen_index = comuna_region_part.rfind('-')
                
                if last_hyphen_index != -1:
                    # Extrai a comuna (entre a última vírgula e o último hífen)
                    components["comuna"] = comuna_region_part[:last_hyphen_index].strip()
                    logger.info(f"Comuna extraída (padrão): '{components['comuna']}'")
                    
                    # Extrai a região (após o último hífen)
                    components["region"] = comuna_region_part[last_hyphen_index+1:].strip()
                    logger.info(f"Região extraída (padrão): '{components['region']}'")
                else:
                    # Se não encontrou hífen, usa todo o texto após a vírgula como comuna
                    components["comuna"] = comuna_region_part.strip()
                    logger.info(f"Comuna extraída (sem região): '{components['comuna']}'")
        
        # Método de fallback para casos em que o padrão não é encontrado
        if not components["comuna"] or not components["region"]:
            logger.info("Usando método de fallback para comuna e região")
            parts = address.split(',')
            if len(parts) >= 3:  # Se há pelo menos 3 partes separadas por vírgula
                if not components["comuna"]:
                    comuna_part = parts[-2].strip()
                    components["comuna"] = comuna_part
                    logger.info(f"Comuna extraída (fallback): '{comuna_part}'")
                
                if not components["region"] and '-' in parts[-1]:
                    region_part = parts[-1].split('-')[-1].strip()
                    # Verifica novamente o caso especial BIO - BIO
                    if region_part.upper() == "BIO" and "BIO - BIO" in parts[-1].upper():
                        components["region"] = "BIO - BIO"
                        logger.info(f"Região extraída (fallback especial): 'BIO - BIO'")
                    else:
                        components["region"] = region_part
                        logger.info(f"Região extraída (fallback): '{region_part}'")
        
        # Validação final e log
        logger.info(f"Componentes finais extraídos do endereço:")
        logger.info(f"Calle: '{components['calle']}'")
        logger.info(f"Numero: '{components['numero']}'")
        logger.info(f"Comuna: '{components['comuna']}'")
        logger.info(f"Region: '{components['region']}'")
        
        return components
    except Exception as e:
        logger.error(f"Erro geral ao analisar endereço chileno: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "calle": "",
            "numero": "",
            "comuna": "",
            "region": ""
        }
    
def generate_automatic_message(form_text):
    """Gera mensagens automáticas com base no texto específico da incidência no formulário."""
    try:
        # Converte para maiúsculas para facilitar a verificação
        form_text = form_text.upper().strip()
        logger.info(f"Texto completo do formulário: '{form_text}'")
        
        # Tenta extrair apenas a incidência relevante do formulário
        # Procura pelo padrão específico da incidência que aparece isolada no meio do formulário
        incidence = ""
        
        # Busca por linhas que contenham apenas a incidência, normalmente entre textos específicos
        lines = form_text.split('\n')
        for line in lines:
            line = line.strip()
            # Verifica se a linha contém uma das incidências conhecidas
            if any(key in line for key in ["RECHAZA", "INCORRECTA", "AUSENTE", "INUBICABLE", "FALTAN DATOS"]) and "INCIDENCE:" not in line:
                incidence = line
                logger.info(f"INCIDÊNCIA PRINCIPAL DETECTADA: '{incidence}'")
                break
        
        # Se não encontrou nenhuma incidência isolada, usa o texto completo
        if not incidence:
            incidence = form_text
            logger.info("Nenhuma incidência isolada encontrada, usando texto completo.")
            
        # Verifica cada tipo de incidência
        if any(phrase in incidence for phrase in ["CLIENTE AUSENTE", "NADIE EN CASA"]):
            message = "Entramos en contacto con el cliente y él se disculpó y mencionó que estará en casa para recibir el producto en este próximo intento."
            logger.info("Resposta selecionada: CLIENTE AUSENTE")
            return message
        
        if "PROBLEMA COBRO" in incidence:
            message = "En llamada telefónica, el cliente afirmó que estará con dinero suficiente para comprar el producto, por favor intenten nuevamente."
            logger.info("Resposta selecionada: PROBLEMA COBRO")
            return message
        
        if any(phrase in incidence for phrase in ["DIRECCIÓN INCORRECTA", "DIRECCION INCORRECTA", "FALTAN DATOS", "INUBICABLE", "COMUNA ERRADA", "CAMBIO DE DOMICILIO"]):
            message = "En llamada telefónica, el cliente rectificó sus datos para que la entrega suceda de forma más asertiva."
            logger.info("Resposta selecionada: PROBLEMA DE ENDEREÇO")
            return message
        
        if any(phrase in incidence for phrase in ["RECHAZA", "RECHAZADA"]):
            message = "En llamada telefónica, el cliente afirma que quiere el producto y mencionó que no fue buscado por la transportadora. Por lo tanto, por favor envíen el producto hasta el cliente."
            logger.info("Resposta selecionada: RECHAZO DE ENTREGA")
            return message
        
        logger.warning("Nenhuma condição conhecida encontrada na incidência")
        return ""
        
    except Exception as e:
        logger.error(f"Erro ao gerar mensagem automática: {str(e)}")
        logger.error(traceback.format_exc())
        return ""
    
def fill_form_fields(driver, form_modal, customer_info):
    """Preenche os campos do formulário com as informações do cliente."""
    try:
        logger.info("Preenchendo campos do formulário...")
        fields_filled = 0
        
        # Extrai componentes do endereço chileno
        address_components = parse_chilean_address(customer_info["address"])
        
        # Primeiro vamos encontrar todos os campos do formulário para entender o que precisa ser preenchido
        form_fields = []
        try:
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
        
        # Agora preenche cada campo obrigatório
        logger.info("Tentando preencher todos os campos obrigatórios...")
        
        # CORREÇÃO: Sempre tenta preencher os campos Datos adicionales e Solución, que são os mais importantes
        # 1. Preenche o campo Datos adicionales a la dirección (opcional)
        datos_adicionales_filled = fill_field_by_label(driver, form_modal, 
                                            ["Datos adicionales a la dirección", "Datos adicionales", "datos adicionales"], 
                                            customer_info["address"])
        if datos_adicionales_filled:
            fields_filled += 1
            logger.info("✅ Campo Datos adicionales preenchido com sucesso")
        else:
            logger.warning("❌ Não foi possível preencher o campo Datos adicionales")
        
        # 2. Preenche o campo Solución
        # Verifica se há uma mensagem automática disponível
        if "automatic_message" in customer_info and customer_info["automatic_message"]:
            solucion_text = customer_info["automatic_message"]
        else:
            solucion_text = customer_info["address"]  # Comportamento original

        solucion_filled = fill_field_by_label(driver, form_modal, 
                                            ["Solución", "Solucion", "solución", "solucion", "Solution"], 
                                            solucion_text)
        if solucion_filled:
            fields_filled += 1
            logger.info("✅ Campo Solución preenchido com sucesso")
        else:
            logger.warning("❌ Não foi possível preencher o campo Solución")
            
            # CORREÇÃO: Tenta método alternativo para o campo Solución se o método principal falhar
            try:
                # Tenta encontrar qualquer campo que possa ser o de solução
                solucion_inputs = form_modal.find_elements(By.XPATH, "//input[contains(@id, 'solucion') or contains(@name, 'solucion') or contains(@placeholder, 'solucion')]")
                
                if not solucion_inputs:
                    # Tenta com variações de caracteres especiais
                    solucion_inputs = form_modal.find_elements(By.XPATH, "//input[contains(@id, 'soluc') or contains(@name, 'soluc') or contains(@placeholder, 'soluc')]")
                
                if not solucion_inputs:
                    # Procura por textareas que possam conter a solução
                    solucion_inputs = form_modal.find_elements(By.XPATH, "//textarea")
                
                if solucion_inputs:
                    solucion_input = solucion_inputs[0]
                    if solucion_input.is_displayed():
                        # Limpa e preenche
                        driver.execute_script("arguments[0].value = '';", solucion_input)
                        time.sleep(0.5)
                        driver.execute_script(f"arguments[0].value = '{solucion_text}';", solucion_input)
                        # Dispara eventos para garantir que o site registre a alteração
                        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", solucion_input)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", solucion_input)
                        logger.info("✅ Campo Solución preenchido via método alternativo")
                        fields_filled += 1
                        solucion_filled = True
            except Exception as e:
                logger.info(f"Erro ao tentar método alternativo para Solución: {str(e)}")
        
        # 3. Preenche o campo Calle
        calle_filled = fill_field_by_label(driver, form_modal, 
                                          ["Calle"], 
                                          address_components["calle"])
        if calle_filled:
            fields_filled += 1
            logger.info("✅ Campo Calle preenchido com sucesso")
        else:
            logger.warning("❌ Não foi possível preencher o campo Calle")
            
            # Tenta encontrar e preencher o campo pelo ID ou classe
            try:
                calle_inputs = form_modal.find_elements(By.XPATH, "//input[contains(@id, 'calle') or contains(@name, 'calle')]")
                if calle_inputs:
                    calle_input = calle_inputs[0]
                    if calle_input.is_displayed():
                        # Limpa e preenche
                        driver.execute_script("arguments[0].value = '';", calle_input)
                        time.sleep(0.5)
                        driver.execute_script(f"arguments[0].value = '{address_components['calle']}';", calle_input)
                        # Dispara eventos para garantir que o site registre a alteração
                        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", calle_input)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", calle_input)
                        logger.info("✅ Campo Calle preenchido via seletor alternativo")
                        fields_filled += 1
                        calle_filled = True
            except Exception as e:
                logger.info(f"Erro ao tentar método alternativo para Calle: {str(e)}")
        
        # 4. Preenche o campo Numero
        numero_filled = fill_field_by_label(driver, form_modal, 
                                           ["Numero", "Número"], 
                                           address_components["numero"])
        if numero_filled:
            fields_filled += 1
            logger.info("✅ Campo Numero preenchido com sucesso")
        else:
            logger.warning("❌ Não foi possível preencher o campo Numero")
            
            # Tenta encontrar e preencher o campo pelo ID ou classe
            try:
                numero_inputs = form_modal.find_elements(By.XPATH, "//input[contains(@id, 'numero') or contains(@name, 'numero')]")
                if numero_inputs:
                    numero_input = numero_inputs[0]
                    if numero_input.is_displayed():
                        # Limpa e preenche
                        driver.execute_script("arguments[0].value = '';", numero_input)
                        time.sleep(0.5)
                        driver.execute_script(f"arguments[0].value = '{address_components['numero']}';", numero_input)
                        # Dispara eventos para garantir que o site registre a alteração
                        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", numero_input)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", numero_input)
                        logger.info("✅ Campo Numero preenchido via seletor alternativo")
                        fields_filled += 1
                        numero_filled = True
            except Exception as e:
                logger.info(f"Erro ao tentar método alternativo para Numero: {str(e)}")
                    
        # 5. Preenche o campo Comuna
        comuna_filled = fill_field_by_label(driver, form_modal, 
                                           ["Comuna"], 
                                           address_components["comuna"])
        if comuna_filled:
            fields_filled += 1
            logger.info("✅ Campo Comuna preenchido com sucesso")
        else:
            logger.warning("❌ Não foi possível preencher o campo Comuna")
            
            # Tenta encontrar e preencher o campo pelo ID ou classe
            try:
                comuna_inputs = form_modal.find_elements(By.XPATH, "//input[contains(@id, 'comuna') or contains(@name, 'comuna')]")
                if comuna_inputs:
                    comuna_input = comuna_inputs[0]
                    if comuna_input.is_displayed():
                        # Limpa e preenche
                        driver.execute_script("arguments[0].value = '';", comuna_input)
                        time.sleep(0.5)
                        driver.execute_script(f"arguments[0].value = '{address_components['comuna']}';", comuna_input)
                        # Dispara eventos para garantir que o site registre a alteração
                        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", comuna_input)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", comuna_input)
                        logger.info("✅ Campo Comuna preenchido via seletor alternativo")
                        fields_filled += 1
                        comuna_filled = True
            except Exception as e:
                logger.info(f"Erro ao tentar método alternativo para Comuna: {str(e)}")
                    
        # 6. Preenche o campo Region
        region_filled = fill_field_by_label(driver, form_modal, 
                                           ["Region", "Región"], 
                                           address_components["region"])
        if region_filled:
            fields_filled += 1
            logger.info("✅ Campo Region preenchido com sucesso")
        else:
            logger.warning("❌ Não foi possível preencher o campo Region")
            
            # Tenta encontrar e preencher o campo pelo ID ou classe
            try:
                region_inputs = form_modal.find_elements(By.XPATH, "//input[contains(@id, 'region') or contains(@name, 'region')]")
                if region_inputs:
                    region_input = region_inputs[0]
                    if region_input.is_displayed():
                        # Limpa e preenche
                        driver.execute_script("arguments[0].value = '';", region_input)
                        time.sleep(0.5)
                        driver.execute_script(f"arguments[0].value = '{address_components['region']}';", region_input)
                        # Dispara eventos para garantir que o site registre a alteração
                        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", region_input)
                        driver.execute_script("arguments[0].dispatchEvent(new Event('input'));", region_input)
                        logger.info("✅ Campo Region preenchido via seletor alternativo")
                        fields_filled += 1
                        region_filled = True
            except Exception as e:
                logger.info(f"Erro ao tentar método alternativo para Region: {str(e)}")
                    
        # 7. Preenche o campo Nombre
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
        
        # 8. Preenche o campo Celular
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
        
        # 9. Tenta preencher todos os campos obrigatórios vazios
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
                        elif "calle" in field_id.lower() or "calle" in field_name.lower():
                            value_to_use = address_components["calle"]
                        elif "numero" in field_id.lower() or "numero" in field_name.lower():
                            value_to_use = address_components["numero"]
                        elif "comuna" in field_id.lower() or "comuna" in field_name.lower():
                            value_to_use = address_components["comuna"]
                        elif "region" in field_id.lower() or "region" in field_name.lower():
                            value_to_use = address_components["region"]
                        elif "direccion" in field_id.lower() or "endereco" in field_id.lower() or "address" in field_id.lower() or \
                             "direccion" in field_name.lower() or "endereco" in field_name.lower() or "address" in field_name.lower():
                            value_to_use = customer_info["address"]
                        elif "celular" in field_id.lower() or "telefono" in field_id.lower() or "phone" in field_id.lower() or \
                             "celular" in field_name.lower() or "telefono" in field_name.lower() or "phone" in field_name.lower():
                            value_to_use = customer_info["phone"]
                        elif "solucion" in field_id.lower() or "solution" in field_id.lower() or \
                             "solucion" in field_name.lower() or "solution" in field_name.lower():
                            # Verifica se há uma mensagem automática disponível
                            if "automatic_message" in customer_info and customer_info["automatic_message"]:
                                value_to_use = customer_info["automatic_message"]
                            else:
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
        
        # Verifica se todos os campos foram preenchidos
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
        return fields_filled > 0
    except Exception as e:
        logger.error(f"Erro ao preencher campos do formulário: {str(e)}")
        return False

def fill_field_by_label(driver, form_modal, label_texts, value):
    """Preenche um campo específico do formulário identificado por texto da label."""
    try:
        logger.info(f"Tentando preencher campo com labels {label_texts}...")
        
        field_found = False
        
        # Método 1: Procura por labels exatas
        for label_text in label_texts:
            try:
                labels = form_modal.find_elements(By.XPATH, f"//label[contains(text(), '{label_text}')]")
                
                for label in labels:
                    if label.is_displayed():
                        logger.info(f"Label encontrada: '{label.text}'")
                        
                        # Procura o campo de input associado ao label
                        input_id = label.get_attribute("for")
                        if input_id:
                            try:
                                input_field = driver.find_element(By.ID, input_id)
                                if input_field.is_displayed():
                                    # Rola até o elemento
                                    driver.execute_script("arguments[0].scrollIntoView(true);", input_field)
                                    time.sleep(0.5)
                                    
                                    # Clica no campo para garantir o foco
                                    driver.execute_script("arguments[0].click();", input_field)
                                    
                                    # CORREÇÃO: Limpa completamente o campo usando JavaScript
                                    driver.execute_script("arguments[0].value = '';", input_field)
                                    time.sleep(0.5)
                                    
                                    # CORREÇÃO: Preenche usando apenas JavaScript
                                    driver.execute_script(f"arguments[0].value = '{value}';", input_field)
                                    
                                    # IMPORTANTE: Dispara TODOS os eventos possíveis para garantir que o site reconheça a mudança
                                    events = ["input", "change", "blur", "keyup", "keydown"]
                                    for event in events:
                                        driver.execute_script(f"arguments[0].dispatchEvent(new Event('{event}', {{bubbles: true}}));", input_field)
                                    
                                    # Simula interação de teclado
                                    input_field.send_keys(Keys.TAB)
                                    
                                    # Verifica o valor após preenchimento
                                    actual_value = input_field.get_attribute("value")
                                    logger.info(f"Campo '{label_text}' preenchido. Valor atual: {actual_value}")
                                    
                                    field_found = True
                                    return True
                            except Exception as e:
                                logger.info(f"Erro ao preencher campo '{label_text}': {str(e)}")
            except Exception as e:
                logger.info(f"Erro ao buscar label '{label_text}': {str(e)}")
        
        # Método 2: Encontrar qualquer input visível próximo à label
        if not field_found:
            for label_text in label_texts:
                try:
                    label_elements = form_modal.find_elements(By.XPATH, f"//*[contains(text(), '{label_text}')]")
                    for label in label_elements:
                        if label.is_displayed():
                            try:
                                # Busca por inputs próximos ao label
                                parent = label.find_element(By.XPATH, "./..")
                                nearby_inputs = parent.find_elements(By.TAG_NAME, "input")
                                for input_field in nearby_inputs:
                                    if input_field.is_displayed():
                                        # Rola até o elemento
                                        driver.execute_script("arguments[0].scrollIntoView(true);", input_field)
                                        time.sleep(0.5)
                                        
                                        # Clica no campo para garantir o foco
                                        driver.execute_script("arguments[0].click();", input_field)
                                        
                                        # CORREÇÃO: Limpa completamente o campo usando JavaScript
                                        driver.execute_script("arguments[0].value = '';", input_field)
                                        time.sleep(0.5)
                                        
                                        # CORREÇÃO: Preenche usando apenas JavaScript
                                        driver.execute_script(f"arguments[0].value = '{value}';", input_field)
                                        
                                        # IMPORTANTE: Dispara TODOS os eventos possíveis para garantir que o site reconheça a mudança
                                        events = ["input", "change", "blur", "keyup", "keydown"]
                                        for event in events:
                                            driver.execute_script(f"arguments[0].dispatchEvent(new Event('{event}', {{bubbles: true}}));", input_field)
                                            
                                        # Simula interação de teclado
                                        input_field.send_keys(Keys.TAB)
                                        
                                        # Verifica o valor após preenchimento
                                        actual_value = input_field.get_attribute("value")
                                        logger.info(f"Campo próximo a '{label_text}' preenchido. Valor atual: {actual_value}")
                                        
                                        field_found = True
                                        return True
                            except Exception as e:
                                logger.info(f"Erro ao preencher campo próximo a '{label_text}': {str(e)}")
                except Exception as e:
                    logger.info(f"Erro ao buscar elementos com texto '{label_text}': {str(e)}")
        
        if not field_found:
            logger.warning(f"Não foi possível encontrar campo com labels {label_texts}")
            return False
    except Exception as e:
        logger.error(f"Erro ao preencher campo: {str(e)}")
        return False

def click_save_button(driver):
    """Tenta clicar no botão de salvar usando várias estratégias."""
    try:
        logger.info("Tentando clicar no botão de salvar...")
        
        # PAUSA MAIOR: Aumentando para 5 segundos para garantir que o formulário seja completamente validado
        logger.info("Aguardando 5 segundos para garantir que o formulário esteja pronto e validado...")
        time.sleep(5)
        
        save_clicked = False
        
        # Método 0: Procura especificamente por "SAVE SOLUCION" primeiro (PRIORIDADE MÁXIMA)
        try:
            logger.info("Procurando especificamente pelo botão 'SAVE SOLUCION'...")
            
            # Tenta vários formatos e combinações de case
            save_solution_patterns = [
                "SAVE SOLUCION", "Save Solucion", "save solucion", 
                "SAVE SOLUTION", "Save Solution", "save solution",
                "SAVE", "Save", "save",
                "GUARDAR", "Guardar", "guardar",
                "ENVIAR", "Enviar", "enviar"
            ]
            
            for pattern in save_solution_patterns:
                save_solution_buttons = driver.find_elements(By.XPATH, f"//button[contains(text(), '{pattern}')]")
                
                if save_solution_buttons:
                    for button in save_solution_buttons:
                        try:
                            if button.is_displayed():
                                logger.info(f"Botão com texto '{pattern}' encontrado, tentando clicar...")
                                
                                # Rola para garantir visibilidade e centraliza
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
                                time.sleep(1)
                                
                                # IMPORTANTE: Tenta múltiplos métodos de clique
                                try:
                                    # Método 1: Clique direto
                                    button.click()
                                    logger.info(f"Clicado no botão '{pattern}' via clique direto")
                                except Exception as click_error:
                                    logger.info(f"Clique direto falhou: {str(click_error)}, tentando JavaScript...")
                                    try:
                                        # Método 2: JavaScript click
                                        driver.execute_script("arguments[0].click();", button)
                                        logger.info(f"Clicado no botão '{pattern}' via JavaScript")
                                    except Exception as js_error:
                                        logger.info(f"Clique JavaScript falhou: {str(js_error)}, tentando Actions...")
                                        try:
                                            # Método 3: Actions chains
                                            from selenium.webdriver.common.action_chains import ActionChains
                                            actions = ActionChains(driver)
                                            actions.move_to_element(button).click().perform()
                                            logger.info(f"Clicado no botão '{pattern}' via ActionChains")
                                        except Exception as action_error:
                                            logger.info(f"Todos os métodos de clique falharam: {str(action_error)}")
                                            continue
                                
                                # Aguarda um pouco após clicar
                                time.sleep(2)
                                
                                # Verifica se o botão ainda está visível (se o clique funcionou, ele pode ter desaparecido)
                                try:
                                    if not button.is_displayed():
                                        logger.info(f"Botão '{pattern}' não está mais visível após o clique - sucesso!")
                                        save_clicked = True
                                        return True
                                except:
                                    # Se der erro ao verificar, provavelmente o botão foi removido do DOM
                                    logger.info(f"Erro ao verificar visibilidade do botão - provável sucesso!")
                                    save_clicked = True
                                    return True
                                
                                # Se chegou aqui, o botão ainda está visível
                                logger.info(f"Botão '{pattern}' ainda está visível após o clique, mas considerando como clicado")
                                save_clicked = True
                                return True
                        except Exception as e:
                            logger.info(f"Erro ao tentar clicar no botão '{pattern}': {str(e)}")
                            continue
            
            if not save_clicked:
                logger.info("Nenhum botão SAVE SOLUCION encontrado pelas variações de texto")
        except Exception as e:
            logger.info(f"Erro ao procurar botão 'SAVE SOLUCION': {str(e)}")
        
        if not save_clicked:
            # Último recurso: Pressiona Enter como se tivesse enviado um formulário
            try:
                logger.info("Tentando enviar o formulário pressionando Enter...")
                active_element = driver.switch_to.active_element
                active_element.send_keys(Keys.ENTER)
                logger.info("Tecla Enter enviada para o elemento ativo")
                time.sleep(2)
                save_clicked = True
            except Exception as e:
                logger.info(f"Erro ao enviar Enter: {str(e)}")
        
        # Mesmo que não tenha clicado, aguarda um pouco mais
        time.sleep(3)
        
        return save_clicked
    except Exception as e:
        logger.error(f"Erro ao tentar clicar no botão de salvar: {str(e)}")
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
            
            # Captura screenshot do erro
            screenshots_folder = st.session_state.screenshots_folder
            error_screenshot = os.path.join(screenshots_folder, f"error_treat_{row_id}.png")
            try:
                driver.save_screenshot(error_screenshot)
                logger.info(f"Screenshot do erro de tratamento salvo em: {error_screenshot}")
            except:
                pass
            
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

def process_current_novelty():
    """Processa a novelty atual na lista."""
    try:
        driver = st.session_state.driver
        
        # Verificação para garantir que estamos na página correta de novelties
        current_url = driver.current_url
        if "/novelties" not in current_url and "/dashboard" not in current_url:
            logger.info("Redirecionando para a página principal de novelties...")
            driver.get("https://app.dropi.cl/dashboard/novelties")  # URL CORRIGIDA
            time.sleep(5)  # Aguarda o carregamento da página
        
        # Verifica se há rows para processar
        if not st.session_state.rows:
            logger.info("Nenhuma novidade encontrada na tabela")
            return True
        
        # Verifica se todas as rows já foram processadas
        if st.session_state.current_row_index >= len(st.session_state.rows):
            logger.info("Todas as novelties foram processadas")
            return True
        
        # NOVA CORREÇÃO: Contador de tentativas para evitar loops infinitos
        if 'current_retry_count' not in st.session_state:
            st.session_state.current_retry_count = 0
            
        # Obtém o ID da linha para referência
        try:
            # Importante: Precisamos recarregar as linhas da tabela para evitar StaleElementReference
            rows = driver.find_elements(By.XPATH, "//table/tbody/tr")
            
            # NOVA CORREÇÃO: Se não encontrar linhas após algumas tentativas, considere como processado
            if not rows and st.session_state.current_retry_count >= 3:
                logger.warning(f"Não foi possível encontrar linhas da tabela após {st.session_state.current_retry_count} tentativas. Considerando novelty como processada.")
                st.session_state.processed_items = st.session_state.current_row_index + 1
                st.session_state.progress = (st.session_state.current_row_index + 1) / st.session_state.total_items
                st.session_state.current_row_index += 1
                st.session_state.current_retry_count = 0  # Reset para a próxima novelty
                return False
            
            if rows and st.session_state.current_row_index < len(rows):
                row = rows[st.session_state.current_row_index]
                try:
                    row_id = row.find_elements(By.TAG_NAME, "td")[0].text
                    logger.info(f"Processando novelty ID: {row_id} ({st.session_state.current_row_index+1}/{len(rows)})")
                    # Reset do contador de tentativas pois encontramos a linha
                    st.session_state.current_retry_count = 0
                except:
                    row_id = f"Linha {st.session_state.current_row_index+1}"
                    logger.info(f"Processando {row_id}/{len(rows)}")
            else:
                row_id = f"Linha {st.session_state.current_row_index+1}"
                logger.info(f"Processando {row_id} (linhas não disponíveis)")
                
                # Incrementa o contador de tentativas
                st.session_state.current_retry_count += 1
                
                # NOVA CORREÇÃO: Abordagem mais robusta para recarregar a página
                logger.warning(f"Linhas da tabela não disponíveis. Tentativa {st.session_state.current_retry_count}/3. Recarregando a página...")
                driver.refresh()
                time.sleep(5)
                
                # NOVA CORREÇÃO: Tenta navegar novamente para novelties se ainda não encontrou
                if st.session_state.current_retry_count >= 2:
                    logger.warning("Tentando navegar novamente para a página de novelties...")
                    driver.get("https://app.dropi.cl/dashboard/novelties")  # URL CORRIGIDA
                    time.sleep(7)
                
                # Atualiza o progresso mesmo assim
                st.session_state.processed_items = st.session_state.current_row_index + 1
                st.session_state.progress = (st.session_state.current_row_index + 1) / st.session_state.total_items
                
                # Incrementa o índice apenas se excedeu o número máximo de tentativas
                if st.session_state.current_retry_count >= 3:
                    logger.warning("Número máximo de tentativas excedido. Passando para a próxima novelty.")
                    st.session_state.current_row_index += 1
                    st.session_state.current_retry_count = 0  # Reset para a próxima novelty
                
                return False
        except Exception as e:
            logger.error(f"Erro ao obter informações da linha: {str(e)}")
            row_id = f"Linha {st.session_state.current_row_index+1}"
        
        # Atualiza o progresso
        st.session_state.processed_items = st.session_state.current_row_index + 1
        st.session_state.progress = (st.session_state.current_row_index + 1) / st.session_state.total_items
        
        try:
            # CORREÇÃO PARA O ERRO STALE ELEMENT: Recarregar o elemento antes de interagir
            logger.info(f"Tentando localizar o botão 'Save' para a novelty {row_id}...")
            try:
                # Recarrega as linhas novamente para garantir que estão atuais
                fresh_rows = driver.find_elements(By.XPATH, "//table/tbody/tr")
                
                if fresh_rows and st.session_state.current_row_index < len(fresh_rows):
                    current_row = fresh_rows[st.session_state.current_row_index]
                    
                    # Tenta encontrar o botão Save na linha atual
                    save_buttons = current_row.find_elements(By.XPATH, ".//button[contains(@class, 'btn-success')]")
                    
                    if save_buttons:
                        save_button = save_buttons[0]
                        
                        # Rola até o botão para garantir que esteja visível
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", save_button)
                        time.sleep(1)
                        
                        # Tenta clicar com JavaScript para maior confiabilidade
                        driver.execute_script("arguments[0].click();", save_button)
                        logger.info("Botão 'Save' clicado via JavaScript")
                    else:
                        logger.warning("Botão 'Save' não encontrado na linha atual")
                        # Incrementa o índice e continua para a próxima novelty
                        st.session_state.current_row_index += 1
                        st.session_state.current_retry_count = 0  # Reset do contador de tentativas
                        return False
                else:
                    logger.warning("Não foi possível localizar a linha atual na tabela")
                    # Incrementa o índice e continua para a próxima novelty
                    st.session_state.current_row_index += 1
                    st.session_state.current_retry_count = 0  # Reset do contador de tentativas
                    return False
            except Exception as e:
                logger.error(f"Erro ao clicar no botão 'Save': {str(e)}")
                # Incrementa o índice e continua para a próxima novelty
                st.session_state.current_row_index += 1
                st.session_state.current_retry_count = 0  # Reset do contador de tentativas
                return False
            
            # Espera pelo popup - tempo aumentado
            logger.info("Aguardando 5 segundos pelo popup...")
            time.sleep(5)
            
            # Tenta diferentes métodos para encontrar e clicar no botão "Yes" ou "Sim"
            yes_clicked = False
            
            # Método 1: Procura por texto exato
            for text in ["Yes", "Sim", "YES", "SIM", "yes", "sim"]:
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
            
            # Espera após clicar no botão Yes - tempo aumentado
            logger.info("Aguardando 5 segundos após 'Yes'...")
            time.sleep(5)
            
            # Agora vamos tentar encontrar o formulário ou os campos
            logger.info("Procurando campos para preenchimento...")
            
            # Extrai as informações do cliente
            customer_info = extract_customer_info(driver)
            
            # NOVO BLOCO - Captura o texto da página para verificar frases específicas
            try:
                logger.info("Verificando texto da página para mensagens automáticas...")
                
                # Captura todo o texto visível na página
                page_text = driver.find_element(By.TAG_NAME, "body").text
                logger.info("Texto da página capturado para análise")
                
                # Testa várias estratégias para encontrar textos relevantes
                novelty_text = ""
                
                # Procura explicitamente por textos de problemas conhecidos
                problem_phrases = [
                    "ENTREGA RECHAZADA", "RECHAZA PAQUETE", "RECHAZA",
                    "PROBLEMA COBRO", 
                    "FALTAN DADOS", "DIRECCION INUBICABLE", "COMUNA ERRADA", 
                    "CAMBIO DE DOMICILIO", "DIRECCIÓN INCORRECTA", "FALTAN DATOS",
                    "CLIENTE AUSENTE"
                ]
                
                # Verifica a presença de cada frase-chave e registra para debugging
                found_phrases = []
                for phrase in problem_phrases:
                    if phrase in page_text.upper():
                        found_phrases.append(phrase)
                        logger.info(f"Frase-chave encontrada: '{phrase}'")
                
                if found_phrases:
                    logger.info(f"Total de {len(found_phrases)} frases-chave encontradas: {found_phrases}")
                else:
                    logger.warning("Nenhuma frase-chave conhecida encontrada na página")
                
                # Verificação específica para textos explícitos de novidade que aparecem no meio do formulário
                try:
                    # Busca específica por elementos de novidade ou mensagens de erro no formulário
                    novedad_elements = driver.find_elements(By.XPATH, "//div[contains(text(), 'Novedad') or contains(text(), 'Novelty')]")
                    if novedad_elements:
                        logger.info("Encontrado elemento de novidade no formulário")
                        
                        # Busca textos específicos que conhecemos
                        error_texts = [
                            "DIRECCIÓN INCORRECTA",
                            "ENTREGA RECHAZADA",
                            "RECHAZA PAQUETE",
                            "RECHAZA",
                            "PROBLEMA COBRO",
                            "CLIENTE AUSENTE"
                        ]
                        
                        # Busca direta por estes textos com XPath mais preciso
                        for error in error_texts:
                            # Busca por texto exato (ignorando maiúsculas/minúsculas)
                            exact_xpath = f"//*[contains(translate(., 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{error}')]"
                            error_elements = driver.find_elements(By.XPATH, exact_xpath)
                            
                            if error_elements:
                                for elem in error_elements:
                                    if elem.is_displayed():
                                        error_text = elem.text.strip()
                                        logger.info(f"IMPORTANTE! Texto de erro encontrado: '{error}' no elemento: '{error_text}'")
                                        # Adiciona este texto com alta prioridade
                                        novelty_text = error + " " + novelty_text
                                        break
                except Exception as e:
                    logger.info(f"Erro ao buscar elementos de novidade específicos: {str(e)}")
                
                # Procura por textos de problemas explicitamente em elementos mais prováveis
                try:
                    # Busca direta por elementos com os textos dos problemas comuns
                    for phrase in problem_phrases:
                        xpath = f"//*[contains(translate(text(), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'), '{phrase}')]"
                        matching_elements = driver.find_elements(By.XPATH, xpath)
                        
                        if matching_elements:
                            for element in matching_elements:
                                if element.is_displayed():
                                    el_text = element.text.strip()
                                    if el_text:
                                        logger.info(f"Elemento encontrado com texto contendo '{phrase}': '{el_text}'")
                                        # Adiciona imediatamente ao texto da novidade
                                        novelty_text += " " + el_text
                except Exception as e:
                    logger.info(f"Erro ao buscar elementos com textos de problemas específicos: {str(e)}")
                
                # Tenta primeiro obter o texto de elementos com informações da novidade
                try:
                    # Procura por elementos que podem conter descrições da novidade
                    for selector in [
                        "//div[contains(@class, 'card') or contains(@class, 'panel')]", 
                        "//table//tr", 
                        "//div[contains(@class, 'modal-body')]"
                    ]:
                        elements = driver.find_elements(By.XPATH, selector)
                        for element in elements:
                            if element.is_displayed():
                                el_text = element.text
                                if len(el_text) > 20:  # Ignora textos muito curtos
                                    novelty_text += " " + el_text
                except Exception as e:
                    logger.info(f"Erro ao extrair texto de elementos específicos: {str(e)}")
                
                # Se não encontrou texto específico, usa todo o texto da página
                if not novelty_text.strip():
                    novelty_text = page_text
                
                # Log do texto encontrado para debug
                logger.info(f"Texto da novidade para análise (primeiros 200 caracteres): '{novelty_text[:200]}...'")
                
                # Gera mensagem automática baseada no texto encontrado
                automatic_message = generate_automatic_message(novelty_text)
                
                if automatic_message:
                    # Adiciona a mensagem automática ao dicionário de informações do cliente
                    customer_info["automatic_message"] = automatic_message
                    logger.info(f"Mensagem automática gerada com sucesso: '{automatic_message}'")
                else:
                    logger.info("Nenhuma mensagem automática gerada - nenhuma condição conhecida encontrada")
            except Exception as e:
                logger.error(f"Erro ao analisar texto da página para mensagens automáticas: {str(e)}")
                logger.error(traceback.format_exc())
            # FIM DO NOVO BLOCO
            
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
                
                # Preenche os campos do formulário
                fields_filled = fill_form_fields(driver, form_modal, customer_info)
                
                # Clica em Salvar/Guardar se pelo menos um campo foi preenchido
                if fields_filled:
                    # Clica em Salvar/Guardar - tentando vários textos
                    save_clicked = click_save_button(driver)
                    
                    # CÓDIGO REDIRECIONAMENTO - Verifica o erro específico "Ups, tenemos el siguiente inconveniente"
                    logger.info("Verificando se apareceu o erro 'Ups, tenemos el siguiente inconveniente'...")
                    try:
                        # Espera um pouco para o popup aparecer
                        time.sleep(3)
                        
                        # Procura pelo texto de erro específico
                        error_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Ups, tenemos el siguiente inconveniente')]")
                        
                        if error_elements:
                            logger.warning("Detectado erro 'Ups, tenemos el siguiente inconveniente'")
                            
                            # Tira um screenshot do erro
                            screenshots_folder = st.session_state.screenshots_folder
                            error_screenshot = os.path.join(screenshots_folder, f"error_ups_{row_id}.png")
                            driver.save_screenshot(error_screenshot)
                            logger.info(f"Screenshot do erro salvo em: {error_screenshot}")
                            
                            # Registra o erro
                            error_msg = "Erro 'Ups, tenemos el siguiente inconveniente'"
                            logger.error(f"Erro ao processar novelty {row_id}: {error_msg}")
                            st.session_state.failed_items.append({"id": row_id, "error": error_msg})
                            st.session_state.failed_count = len(st.session_state.failed_items)
                            
                            # Redireciona para a lista de novelties
                            logger.info("Redirecionando para a lista de novelties...")
                            driver.get("https://app.dropi.cl/dashboard/novelties")  # URL CORRIGIDA
                            
                            # Aguarda o carregamento da página
                            time.sleep(5)
                            
                            # Incrementa o índice para pular esta novelty
                            st.session_state.current_row_index += 1
                            # Reset do contador de tentativas
                            st.session_state.current_retry_count = 0
                            
                            # Atualiza o progresso
                            st.session_state.processed_items = st.session_state.current_row_index
                            st.session_state.progress = st.session_state.current_row_index / st.session_state.total_items
                            
                            # Retorna False para continuar com a próxima novelty
                            return False
                    except Exception as e:
                        logger.info(f"Erro ao verificar popup de erro específico: {str(e)}")
                    # FIM DO CÓDIGO REDIRECIONAMENTO
                    
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
                    logger.warning("Nenhum campo foi preenchido, mas tentando continuar...")
                    try:
                        # Tenta clicar em salvar mesmo assim
                        save_clicked = click_save_button(driver)
                        
                        # CÓDIGO REDIRECIONAMENTO - Verifica o erro específico "Ups, tenemos el siguiente inconveniente"
                        logger.info("Verificando se apareceu o erro 'Ups, tenemos el siguiente inconveniente'...")
                        try:
                            # Espera um pouco para o popup aparecer
                            time.sleep(3)
                            
                            # Procura pelo texto de erro específico
                            error_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Ups, tenemos el siguiente inconveniente')]")
                            
                            if error_elements:
                                logger.warning("Detectado erro 'Ups, tenemos el siguiente inconveniente'")
                                
                                # Tira um screenshot do erro
                                screenshots_folder = st.session_state.screenshots_folder
                                error_screenshot = os.path.join(screenshots_folder, f"error_ups_{row_id}.png")
                                driver.save_screenshot(error_screenshot)
                                logger.info(f"Screenshot do erro salvo em: {error_screenshot}")
                                
                                # Registra o erro
                                error_msg = "Erro 'Ups, tenemos el siguiente inconveniente'"
                                logger.error(f"Erro ao processar novelty {row_id}: {error_msg}")
                                st.session_state.failed_items.append({"id": row_id, "error": error_msg})
                                st.session_state.failed_count = len(st.session_state.failed_items)
                                
                                # Redireciona para a lista de novelties
                                logger.info("Redirecionando para a lista de novelties...")
                                driver.get("https://app.dropi.cl/dashboard/novelties")  # URL CORRIGIDA
                                
                                # Aguarda o carregamento da página
                                time.sleep(5)
                                
                                # Incrementa o índice para pular esta novelty
                                st.session_state.current_row_index += 1
                                # Reset do contador de tentativas
                                st.session_state.current_retry_count = 0
                                
                                # Atualiza o progresso
                                st.session_state.processed_items = st.session_state.current_row_index
                                st.session_state.progress = st.session_state.current_row_index / st.session_state.total_items
                                
                                # Retorna False para continuar com a próxima novelty
                                return False
                        except Exception as e:
                            logger.info(f"Erro ao verificar popup de erro específico: {str(e)}")
                        # FIM DO CÓDIGO REDIRECIONAMENTO
                    except:
                        pass
            else:
                logger.warning("Não foi possível encontrar o formulário ou campos para preencher")
                try:
                    # Tenta continuar mesmo sem encontrar o formulário
                    logger.info("Tentando continuar sem preencher campos...")
                    
                    # Procura por botões de salvar na página
                    for save_text in ["Guardar", "Salvar", "Save", "GUARDAR", "SALVAR", "SAVE"]:
                        try:
                            save_form_button = driver.find_element(By.XPATH, f"//button[contains(text(), '{save_text}')]")
                            if save_form_button.is_displayed():
                                driver.execute_script("arguments[0].click();", save_form_button)
                                logger.info(f"Clicado no botão '{save_text}' sem preencher campos")
                                
                                # CÓDIGO REDIRECIONAMENTO - Verifica o erro específico "Ups, tenemos el siguiente inconveniente"
                                logger.info("Verificando se apareceu o erro 'Ups, tenemos el siguiente inconveniente'...")
                                try:
                                    # Espera um pouco para o popup aparecer
                                    time.sleep(3)
                                    
                                    # Procura pelo texto de erro específico
                                    error_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'Ups, tenemos el siguiente inconveniente')]")
                                    
                                    if error_elements:
                                        logger.warning("Detectado erro 'Ups, tenemos el siguiente inconveniente'")
                                        
                                        # Tira um screenshot do erro
                                        screenshots_folder = st.session_state.screenshots_folder
                                        error_screenshot = os.path.join(screenshots_folder, f"error_ups_{row_id}.png")
                                        driver.save_screenshot(error_screenshot)
                                        logger.info(f"Screenshot do erro salvo em: {error_screenshot}")
                                        
                                        # Registra o erro
                                        error_msg = "Erro 'Ups, tenemos el siguiente inconveniente'"
                                        logger.error(f"Erro ao processar novelty {row_id}: {error_msg}")
                                        st.session_state.failed_items.append({"id": row_id, "error": error_msg})
                                        st.session_state.failed_count = len(st.session_state.failed_items)
                                        
                                        # Redireciona para a lista de novelties
                                        logger.info("Redirecionando para a lista de novelties...")
                                        driver.get("https://app.dropi.cl/dashboard/novelties")  # URL CORRIGIDA
                                        
                                        # Aguarda o carregamento da página
                                        time.sleep(5)
                                        
                                        # Incrementa o índice para pular esta novelty
                                        st.session_state.current_row_index += 1
                                        # Reset do contador de tentativas
                                        st.session_state.current_retry_count = 0
                                        
                                        # Atualiza o progresso
                                        st.session_state.processed_items = st.session_state.current_row_index
                                        st.session_state.progress = st.session_state.current_row_index / st.session_state.total_items
                                        
                                        # Retorna False para continuar com a próxima novelty
                                        return False
                                except Exception as e:
                                    logger.info(f"Erro ao verificar popup de erro específico: {str(e)}")
                                # FIM DO CÓDIGO REDIRECIONAMENTO
                                
                                break
                        except:
                            continue
                except:
                    pass
            
            # Espera adicional após salvar
            time.sleep(5)
            
            # Procura e clica no popup "OK" que aparece após salvar
            logger.info("Procurando popup de confirmação com botão OK...")
            try:
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
            
            # NOVA VERIFICAÇÃO DE REDIRECIONAMENTO: Se o processamento terminou, volte para a lista de novelties
            # para garantir que podemos continuar com a próxima
            current_url = driver.current_url
            if "/novelties" not in current_url and "/dashboard" not in current_url:
                logger.info("Retornando à lista de novelties para continuar o processamento...")
                driver.get("https://app.dropi.cl/dashboard/novelties")  # URL CORRIGIDA
                time.sleep(5)  # Aguarda o carregamento da página
                
                # Recarrega a lista de novelties se necessário
                try:
                    # Verifica se a lista precisa ser recarregada
                    rows = driver.find_elements(By.XPATH, "//table/tbody/tr")
                    if len(rows) > 0:
                        logger.info(f"Lista de novelties recarregada com {len(rows)} itens")
                        st.session_state.rows = rows
                        st.session_state.total_items = len(rows)
                    else:
                        logger.warning("Não foi possível encontrar a tabela de novelties após redirecionamento")
                except Exception as e:
                    logger.error(f"Erro ao recarregar a lista de novelties: {str(e)}")
            
            # Pequena pausa entre processamentos
            time.sleep(1)
            
        except Exception as e:
            # Registra o erro
            error_msg = f"Erro ao processar novelty {row_id}: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            st.session_state.failed_items.append({"id": row_id, "error": str(e)})
            st.session_state.failed_count = len(st.session_state.failed_items)
            
            # Captura screenshot do erro
            screenshots_folder = st.session_state.screenshots_folder
            error_screenshot = os.path.join(screenshots_folder, f"error_process_{row_id}.png")
            try:
                driver.save_screenshot(error_screenshot)
                logger.info(f"Screenshot do erro salvo em: {error_screenshot}")
            except Exception as se:
                logger.error(f"Erro ao capturar screenshot: {str(se)}")
            
            # Tratamento de erro conforme especificado
            handle_error(row, row_id)
        
        # Incrementa o índice para a próxima novelty
        st.session_state.current_row_index += 1
        
        # Reset do contador de tentativas para a próxima novelty
        st.session_state.current_retry_count = 0
        
        # Verifica se todas as novelties foram processadas
        if st.session_state.current_row_index >= len(st.session_state.rows):
            logger.info("Todas as novelties foram processadas")
            generate_report()
            return True
        
        # IMPORTANTE: Retorna False para continuar processando a próxima novelty
        logger.info(f"Continuando para a próxima novelty. Restam {len(st.session_state.rows) - st.session_state.current_row_index} novelties.")
        return False
            
    except Exception as e:
        logger.error(f"Erro geral ao processar novelty: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Captura screenshot do erro crítico
        screenshots_folder = st.session_state.screenshots_folder
        critical_error_screenshot = os.path.join(screenshots_folder, "critical_error.png")
        try:
            driver.save_screenshot(critical_error_screenshot)
            logger.info(f"Screenshot de erro crítico salvo em: {critical_error_screenshot}")
        except:
            pass
        
        # TRATAMENTO DE RECUPERAÇÃO DE ERRO CRÍTICO
        try:
            logger.info("Tentando recuperar de erro crítico, redirecionando para a página principal...")
            driver.get("https://app.dropi.cl/dashboard/novelties")  # URL CORRIGIDA
            time.sleep(5)
            
            # Incrementa o índice para tentar a próxima novelty
            st.session_state.current_row_index += 1
            # Reset do contador de tentativas
            st.session_state.current_retry_count = 0
            return False
        except:
            logger.error("Falha na recuperação de erro crítico")
            return False

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

# Processamento da automação baseado no estado atual
if st.session_state.is_running:
    # Etapas da automação
    if st.session_state.automation_step == 'setup':
        if enhanced_setup_driver():
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

with tab2:
    # Filtros de data
    col1, col2 = st.columns(2)
    with col1:
        default_start_date = datetime.date.today() - datetime.timedelta(days=30)
        start_date = st.date_input("Data Inicial", value=default_start_date, key="report_start_date")
    with col2:
        default_end_date = datetime.date.today()
        end_date = st.date_input("Data Final", value=default_end_date, key="report_end_date")

    start_datetime = datetime.datetime.combine(start_date, datetime.datetime.min.time())
    end_datetime = datetime.datetime.combine(end_date, datetime.datetime.max.time())

    if st.button("Atualizar Relatório", key="update_report"):
        start_date_str = start_datetime.strftime("%Y-%m-%d %H:%M:%S")
        end_date_str = end_datetime.strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.filtered_data = get_execution_history(start_date_str, end_date_str, THIS_COUNTRY)  # CORRIGIDO
        st.success("Relatório atualizado!")

    if 'filtered_data' not in st.session_state:
        start_date_str = start_datetime.strftime("%Y-%m-%d %H:%M:%S")
        end_date_str = end_datetime.strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.filtered_data = get_execution_history(start_date_str, end_date_str, THIS_COUNTRY)  # CORRIGIDO

    if 'filtered_data' in st.session_state and not st.session_state.filtered_data.empty:
        df_original = st.session_state.filtered_data.copy()

        # --- Preparação dos Dados ---
        df_original['execution_date'] = pd.to_datetime(df_original['execution_date'])
        # Converte tempo de segundos para minutos
        df_original['Tempo (minutos)'] = df_original['execution_time'] / 60

        # Cria cópia para exibição na tabela
        display_df = df_original.copy()

        # Formata a data para exibição amigável
        display_df['Data'] = display_df['execution_date'].dt.strftime('%d/%m/%Y %H:%M')

        # Renomeia colunas para português e seleciona/ordena para exibição
        display_df.rename(columns={
            'total_processed': 'Total Processado',
            'successful': 'Sucessos',
            'failed': 'Falhas',
        }, inplace=True)

        # Seleciona e ordena as colunas para exibição
        display_columns = ['Data', 'Total Processado', 'Sucessos', 'Falhas', 'Tempo (minutos)']
        display_df = display_df[display_columns]
        display_df = display_df.sort_values(by='Data', ascending=True)

        # --- Cálculo dos Totais ---
        total_processed = df_original['total_processed'].sum()
        total_success = df_original['successful'].sum()
        total_failed = df_original['failed'].sum()
        # Calcula a média em minutos
        avg_time_minutes = df_original['Tempo (minutos)'].mean() if not df_original['Tempo (minutos)'].empty else 0

        # --- Adiciona a Linha de Total ao DataFrame de Exibição ---
        total_row = pd.DataFrame({
            'Data': ['Total'],
            'Total Processado': [total_processed],
            'Sucessos': [total_success],
            'Falhas': [total_failed],
            'Tempo (minutos)': [f"{avg_time_minutes:.2f}"]
        })

        # Formata a coluna de minutos para 2 casas decimais ANTES de concatenar o total (que já é string formatada)
        display_df['Tempo (minutos)'] = display_df['Tempo (minutos)'].map('{:.2f}'.format)

        display_df_with_total = pd.concat([display_df, total_row], ignore_index=True)

        # --- Exibição da Tabela ---
        st.dataframe(display_df_with_total, width=800, hide_index=True)

    elif 'filtered_data' in st.session_state and st.session_state.filtered_data.empty:
        st.info("Não há dados de execução para o período selecionado.")
    else:
        st.info("Clique em 'Atualizar Relatório' para carregar os dados.")