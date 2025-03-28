import streamlit as st
import requests
import re
import json
import time
import sqlite3
import os
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from db_connection import get_db_connection


# Importação condicional para não quebrar se não estiver instalado
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# ---------------------------------------------------------------------------- #
# CONFIGURAÇÕES GERAIS DA APLICAÇÃO
# ---------------------------------------------------------------------------- #

# Inicialização da sessão
if "url_limpa" not in st.session_state:
    st.session_state.url_limpa = None

if "url_para_comprar" not in st.session_state:
    st.session_state.url_para_comprar = None

if "urls_para_comprar_lote" not in st.session_state:
    st.session_state.urls_para_comprar_lote = []

# ---------------------------------------------------------------------------- #
# FUNÇÕES COMUNS
# ---------------------------------------------------------------------------- #

def get_engajamentos():
    """Obtém os engajamentos do banco de dados."""
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Create table if it doesn't exist
        if os.environ.get('RAILWAY_ENVIRONMENT'):
            # PostgreSQL
            c.execute("""
            CREATE TABLE IF NOT EXISTS engajamentos (
                id SERIAL PRIMARY KEY,
                nome TEXT,
                engajamento_id TEXT,
                funcionando TEXT,
                tipo TEXT DEFAULT 'Like'
            )
            """)
            
            # Check if sample data needs to be added (check if table is empty)
            c.execute("SELECT COUNT(*) FROM engajamentos")
            count = c.fetchone()[0]
            
            if count == 0:
                # Add sample data
                exemplos = [
                    ("Like Facebook", "101", "Sim", "Like"),
                    ("Amei Facebook", "102", "Sim", "Amei"),
                    ("Uau Facebook", "103", "Sim", "Uau")
                ]
                for exemplo in exemplos:
                    c.execute("""
                    INSERT INTO engajamentos (nome, engajamento_id, funcionando, tipo)
                    VALUES (%s, %s, %s, %s)
                    """, exemplo)
                
            # Check columns
            c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='engajamentos'")
            columns = [col[0] for col in c.fetchall()]
            if "tipo" not in columns:
                c.execute("ALTER TABLE engajamentos ADD COLUMN tipo TEXT DEFAULT 'Like'")
        else:
            # SQLite (original code)
            if not os.path.exists("engajamentos.db"):
                c.execute('''CREATE TABLE IF NOT EXISTS engajamentos
                            (id INTEGER PRIMARY KEY, nome TEXT, engajamento_id TEXT, funcionando TEXT, tipo TEXT)''')
                # Inserir dados de exemplo
                exemplos = [
                    (1, "Like Facebook", "101", "Sim", "Like"),
                    (2, "Amei Facebook", "102", "Sim", "Amei"),
                    (3, "Uau Facebook", "103", "Sim", "Uau")
                ]
                c.executemany("INSERT OR IGNORE INTO engajamentos VALUES (?, ?, ?, ?, ?)", exemplos)
            
            # Check columns
            c.execute("PRAGMA table_info(engajamentos)")
            columns = [col[1] for col in c.fetchall()]
            if "tipo" not in columns:
                c.execute("ALTER TABLE engajamentos ADD COLUMN tipo TEXT DEFAULT 'Like'")
        
        conn.commit()
        
        # Get engagements
        c.execute("SELECT id, nome, engajamento_id, funcionando, tipo FROM engajamentos")
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        st.error(f"Erro ao acessar o banco de dados: {str(e)}")
        return []

# ---------------------------------------------------------------------------- #
# LAYOUT DA APLICAÇÃO CENTRALIZADO USANDO RECURSOS NATIVOS DO STREAMLIT
# ---------------------------------------------------------------------------- #

# Não usar st.set_page_config aqui pois causa erro em aplicações multipage
# Vamos usar CSS para maximizar a largura disponível

# Aplicar CSS para usar a largura total disponível
st.markdown("""
<style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 95%;
    }
    .column-title {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 15px;
        text-align: center;
    }
    .stTextInput > div > div > input {
        width: 100%;
    }
    .stTextArea > div > div > textarea {
        width: 100%;
    }
    .stButton > button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# Criar um container de largura total
container = st.container()

# Criar as duas colunas principais com proporção melhorada
with container:
    col_limpar, col_comprar = st.columns([5, 5])

# ---------------------------------------------------------------------------- #
#                      PARTE 1: LIMPAR URLs
# ---------------------------------------------------------------------------- #

with col_limpar:
    st.markdown("<div class='column-title'><h3>🧹 Limpar URLs de Anúncios</h3></div>", unsafe_allow_html=True)
    
    def check_selenium_available():
        """Checks if Selenium can be properly initialized in the current environment"""
        try:
            if not SELENIUM_AVAILABLE:
                return False
                
            # Try to initialize a headless browser to see if it works
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
        
            # Check if we're on Railway
            if os.environ.get('RAILWAY_ENVIRONMENT'):
                # Use the Chrome path in Docker
                chrome_path = "/usr/bin/google-chrome-stable"
                options.binary_location = chrome_path
            
                try:
                    # On Railway, create Chrome directly
                    browser = webdriver.Chrome(options=options)
                except Exception as e:
                    print(f"Erro inicializando Chrome no Railway: {str(e)}")
                    return False
            else:
                # Locally, use ChromeDriverManager
                try:
                    service = Service(ChromeDriverManager().install())
                    browser = webdriver.Chrome(service=service, options=options)
                except Exception as e:
                    print(f"Erro inicializando Chrome localmente: {str(e)}")
                    return False
                
            browser.quit()
            return True
        except Exception as e:
            print(f"Erro no check_selenium_available: {str(e)}")
            return False

    def extrair_url_real_via_browser(url):
        """
        Usa um navegador headless para abrir a URL do anúncio e extrair a URL real.
        Esta função simula o processo de clicar em "Copiar link" no anúncio.
        """
        if not SELENIUM_AVAILABLE:
            return None
    
        # Configurar o navegador headless
        try:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')  # Necessário para Docker
            options.add_argument('--disable-dev-shm-usage')  # Necessário para Docker
            options.add_argument('--disable-notifications')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-infobars')
        
            # Adicionar um User-Agent comum para evitar bloqueios
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36')
        
            # Check if we're on Railway
            if os.environ.get('RAILWAY_ENVIRONMENT'):
                # Use the Chrome path in Docker
                chrome_path = "/usr/bin/google-chrome-stable"
                options.binary_location = chrome_path
            
                # On Railway, create Chrome directly
                browser = webdriver.Chrome(options=options)
            else:
                # Locally, use ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                browser = webdriver.Chrome(service=service, options=options)
        
            # Definir um tempo de espera razoável
            wait_time = 8
            
            # Abrir a URL
            browser.get(url)
        
            # Aguardar o carregamento da página
            time.sleep(wait_time)
        
            # PRIORIDADE 1: Procurar diretamente por links de vídeo na página
            video_links = browser.find_elements(By.XPATH, '//a[contains(@href, "/videos/")]')
            for link in video_links:
                href = link.get_attribute('href')
                if href and '/videos/' in href:
                    # Verificar se é um vídeo do Facebook (não um link externo)
                    if 'facebook.com' in href:
                        browser.quit()
                        return href
        
            # PRIORIDADE 2: Verificar se há botão "Ver Mais" ou similar e clicar
            try:
                ver_mais_buttons = browser.find_elements(By.XPATH, 
                    '//div[contains(text(), "Ver Mais") or contains(text(), "Saiba mais") or contains(text(), "See More")]')
                if ver_mais_buttons:
                    for button in ver_mais_buttons:
                        try:
                            button.click()
                            time.sleep(2)  # Esperar a página atualizar
                        
                            # Verificar novamente por links de vídeo após clicar
                            video_links = browser.find_elements(By.XPATH, '//a[contains(@href, "/videos/")]')
                            for link in video_links:
                                href = link.get_attribute('href')
                                if href and '/videos/' in href and 'facebook.com' in href:
                                    browser.quit()
                                    return href
                        except:
                            pass  # Continuar tentando outros botões se este falhar
            except Exception as e:
                pass
        
            # PRIORIDADE 5: Verificar se a URL da página mudou após carregamento
            current_url = browser.current_url
            if current_url != url and "dco_ad_token" not in current_url:
                # Verificar se a URL atual parece ser um permalink ou um link de conteúdo
                if any(x in current_url for x in ['/videos/', '/watch/', '/photo/']):
                    browser.quit()
                    return current_url
                
            # PRIORIDADE 6: Extrair todos os links do Facebook e tentar identificar o mais relevante
            all_links = browser.find_elements(By.TAG_NAME, 'a')
            fb_links = []
            video_links = []
        
            for link in all_links:
                href = link.get_attribute('href')
                if href and 'facebook.com' in href:
                    # Priorizar links que parecem ser vídeos
                    if '/videos/' in href:
                        video_links.append(href)
                    # Ou outros tipos de conteúdo
                    elif any(x in href for x in ['/watch/', '/photo/', '/permalink/']):
                        fb_links.append(href)
        
            # Priorizar links de vídeo
            if video_links:
                browser.quit()
                return video_links[0]
            
            # Ou outro conteúdo relevante
            if fb_links:
                browser.quit()
                return fb_links[0]
            
        except Exception as e:
            print(f"Erro Selenium: {str(e)}")
        finally:
            try:
                browser.quit()
            except:
                pass
    
        return None

    def extrair_via_api_mobile(url):
        """
        Tenta extrair a URL real utilizando a versão móvel da API do Facebook.
        Esta é uma abordagem alternativa que pode funcionar em alguns casos.
        """
        try:
            # Converter para versão móvel (m.facebook.com)
            mobile_url = url.replace('www.facebook.com', 'm.facebook.com')
            
            # Adicionar headers para simular um navegador móvel
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3',
            }
            
            response = requests.get(mobile_url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                return None
            
            # Usar BeautifulSoup para analisar o HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # PRIORIDADE 1: Procurar links de vídeo explícitos
            # Primeiro procurar links específicos de vídeo (alta prioridade)
            video_patterns = [
                'a[href*="/videos/"]',  # Links de vídeo padrão
                'a[href*="/watch/"]',   # Links de assistir vídeo
                'video source[src]',    # Tags de vídeo direto
                'div[data-store*="videoID"]'  # Divs com ID de vídeo
            ]
            
            for pattern in video_patterns:
                elements = soup.select(pattern)
                if elements:
                    for element in elements:
                        if element.name == 'a' and element.get('href'):
                            href = element['href']
                            if not href.startswith('http'):
                                href = 'https://www.facebook.com' + href
                            return href
                        elif element.name == 'source' and element.get('src'):
                            src = element['src']
                            return src
                        elif element.name == 'div' and element.get('data-store'):
                            try:
                                data_store = json.loads(element['data-store'])
                                if 'videoID' in data_store:
                                    video_id = data_store['videoID']
                                    video_url = f"https://www.facebook.com/watch/?v={video_id}"
                                    return video_url
                            except:
                                pass
                
        except Exception as e:
            pass
            
        return None

    # This is a fallback method that doesn't rely on Selenium for Streamlit Cloud
    def extract_url_without_selenium(url):
        """
        A simpler method to extract the real URL by using just requests and BeautifulSoup.
        Not as powerful as Selenium but works in restricted environments.
        """
        try:
            # First try the mobile site approach which doesn't need Selenium
            extracted_url = extrair_via_api_mobile(url)
            if extracted_url:
                return extracted_url
                
            # If mobile approach fails, try a direct request
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
            
            # Check if we were redirected to a more useful URL
            if response.url != url and '/videos/' in response.url:
                return response.url
                
            # Parse with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for og:url meta tag
            og_url = soup.find('meta', property='og:url')
            if og_url and og_url.get('content'):
                return og_url['content']
                
            # Look for video meta tags
            og_video = soup.find('meta', property='og:video:url')
            if og_video and og_video.get('content'):
                return og_video['content']
                
            # Look for canonical link
            canonical = soup.find('link', rel='canonical')
            if canonical and canonical.get('href'):
                return canonical['href']
                
            # If all else fails, extract any facebook.com links that might be useful
            all_links = soup.find_all('a')
            for link in all_links:
                href = link.get('href')
                if href and 'facebook.com' in href and any(x in href for x in ['/videos/', '/watch/', '/photo/']):
                    # Make absolute if relative URL
                    if not href.startswith('http'):
                        href = 'https://www.facebook.com' + href
                    return href
                    
        except Exception as e:
            pass
            
        return None

    # Modified version of limpar_url_facebook that handles Streamlit Cloud limitations
    def limpar_url_facebook(url):
        """
        Tenta obter a URL real de um anúncio do Facebook.
        Retorna apenas a URL base sem parâmetros de consulta (sem o que vem após o '?').
        Modified to work on Streamlit Cloud.
        """
        if not url or 'facebook.com' not in url:
            return url, "erro", "URL inválida"
        
        # Inicializar variáveis
        real_url = None
        status = "sucesso"
        mensagem = ""
        
        # Verificar se a URL já está limpa (não contém parâmetros de anúncio)
        if '/videos/' in url and '?' in url:
            # Se já é uma URL de vídeo, apenas remover os parâmetros
            base_url = url.split('?')[0]
            return base_url, "sucesso", "URL de vídeo encontrada"
        
        # Verificar se temos um mapeamento manual para esta URL
        if 'manual_mappings' in st.session_state and url in st.session_state.manual_mappings:
            mapped_url = st.session_state.manual_mappings[url]
            # Remover parâmetros após '?'
            if '?' in mapped_url:
                mapped_url = mapped_url.split('?')[0]
            return mapped_url, "sucesso", "URL encontrada no mapeamento"
        
        # Determine if we can use Selenium in this environment
        selenium_works = check_selenium_available()
        
        try:
            if selenium_works and SELENIUM_AVAILABLE:
                # Try the Selenium approach first if available
                real_url = extrair_url_real_via_browser(url)
            
            # If Selenium failed or isn't available, try alternative methods
            if not real_url:
                real_url = extract_url_without_selenium(url)
            
            if real_url:
                # Ensure real_url is a string (not bytes)
                if isinstance(real_url, bytes):
                    real_url = real_url.decode('utf-8')
                    
                # Remover tudo após o '?' na URL
                if '?' in real_url:
                    clean_url = real_url.split('?')[0]
                else:
                    clean_url = real_url
                
                # Remover tudo após o '#' se existir
                if '#' in clean_url:
                    clean_url = clean_url.split('#')[0]
                
                return clean_url, "sucesso", "URL extraída com sucesso"
            else:
                return url, "aviso", "Não foi possível extrair a URL"
        except Exception as e:
            return str(url), "erro", f"Erro durante processamento: {str(e)}"

    # Função simplificada para exibir resultados da URL
    def display_url_results(original_url, cleaned_url_tuple):
        """Exibe apenas o antes e depois da URL"""
        url_limpa, status, mensagem = cleaned_url_tuple
        
        # Ensure url_limpa is a string
        if isinstance(url_limpa, bytes):
            url_limpa = url_limpa.decode('utf-8')
        
        st.markdown("### URL Original:")
        st.code(original_url)
        
        st.markdown("### URL Limpa:")
        st.code(url_limpa)
        
        return url_limpa

    def processar_lote_urls(texto_urls):
        """Processa um lote de URLs, uma por linha e retorna resultados com status."""
        urls = [linha.strip() for linha in texto_urls.split('\n') if linha.strip()]
        resultados = []
        
        for url in urls:
            # A função agora retorna uma tupla (url_limpa, status, mensagem)
            url_limpa, status, mensagem = limpar_url_facebook(url)
            resultados.append((url, url_limpa, status, mensagem))
        
        return resultados

    # Interface principal
    tabs = st.tabs(["URL Única", "Lote de URLs"])

    # Tab para URL única
    with tabs[0]:
        url_input = st.text_input("Cole a URL do anúncio do Facebook", 
                                  placeholder="https://www.facebook.com/...",
                                  help="URL original do anúncio com parâmetros de rastreamento")
        
        clean_button = st.button("🔍 Limpar URL", key="btn_limpar_unica", use_container_width=True)
        
        if 'último_processo' not in st.session_state:
            st.session_state.último_processo = {}
            
        if clean_button:
            if url_input:
                with st.spinner("⏳ Processando a URL..."):
                    # Processar a URL
                    cleaned_url_tuple = limpar_url_facebook(url_input)
                    
                # Exibir informações simplificadas
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### URL Original:")
                    st.code(url_input, language="text")
                
                with col2:
                    url_limpa = cleaned_url_tuple[0]
                    st.markdown("### URL Limpa:")
                    st.code(url_limpa, language="text")
                
                # Botão para enviar para compra
                if st.button("↪️ Enviar URL para a seção de compra", key="enviar_para_compra"):
                    # Transferir a URL para o lado de compra
                    st.session_state.url_para_comprar = url_limpa
                    st.rerun() # Importante: forçar recarregamento da página
                
                # Resultado final
                st.markdown(
                    f"""
                    <div class="resultado">
                        <h4>Resultado Final:</h4>
                        <p>{url_limpa}</p>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
            else:
                st.error("❌ Por favor, insira uma URL para limpar.")
    
    # Tab para lote de URLs
    with tabs[1]:
        lote_urls = st.text_area(
            "Cole várias URLs (uma por linha)", 
            height=150,
            placeholder="https://www.facebook.com/...\nhttps://www.facebook.com/..."
        )
        
        process_button = st.button("🔄 Processar Lote", key="btn_limpar_lote", use_container_width=True)
            
        if process_button:
            if lote_urls:
                urls = [linha.strip() for linha in lote_urls.split('\n') if linha.strip()]
                
                if not urls:
                    st.error("❌ Nenhuma URL válida encontrada no texto.")
                else:
                    resultados = []
                    
                    # Barra de progresso
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, url in enumerate(urls):
                        # Atualizar progresso
                        progress = (i) / len(urls)
                        progress_bar.progress(progress)
                        status_text.text(f"Processando URL {i+1} de {len(urls)}...")
                        
                        # Processar URL
                        cleaned_url_tuple = limpar_url_facebook(url)
                        resultados.append((url, cleaned_url_tuple))
                    
                    # Completar o progresso
                    progress_bar.progress(1.0)
                    status_text.text(f"✅ Processamento concluído! {len(urls)} URLs processadas.")
                    
                    # Exibir resultados simplificados
                    st.markdown("### URLs Processadas:")
                    for i, (original, clean_tuple) in enumerate(resultados, 1):
                        url_limpa = clean_tuple[0]
                        # Ensure url_limpa is a string
                        if isinstance(url_limpa, bytes):
                            url_limpa = url_limpa.decode('utf-8')
                        
                        st.markdown(f"**URL {i}**")
                        st.code(f"Original: {original}\nLimpa: {url_limpa}")
                    
                    # Preparar URLs limpas
                    urls_limpas = [
                        clean_tuple[0] if isinstance(clean_tuple[0], str)
                        else clean_tuple[0].decode('utf-8') if isinstance(clean_tuple[0], bytes)
                        else str(clean_tuple[0])
                        for _, clean_tuple in resultados
                    ]
                    
                    # Mostrar um resumo das URLs limpas
                    st.markdown("### Todas as URLs Limpas:")
                    todas_limpas = "\n".join(urls_limpas)
                    st.code(todas_limpas)
                    
                    # Botão para baixar as URLs limpas
                    st.download_button(
                        label="📥 Baixar URLs Limpas",
                        data=todas_limpas,
                        file_name="urls_limpas.txt",
                        mime="text/plain"
                    )
                    
                    # Botão para enviar para compra
                    if st.button("↪️ Enviar URLs para a seção de compra", key="enviar_lote_para_compra"):
                        # Transferir as URLs para o lado de compra
                        st.session_state.urls_para_comprar_lote = urls_limpas
                        st.rerun() # Importante: forçar recarregamento da página
            else:
                st.error("❌ Por favor, insira pelo menos uma URL para processar.")

# ---------------------------------------------------------------------------- #
#                 PARTE 2: COMPRAR ENGAJAMENTO
# ---------------------------------------------------------------------------- #

with col_comprar:
    st.markdown("<div class='column-title'><h3>🛒 Comprar Engajamento</h3></div>", unsafe_allow_html=True)
    
    # --- Configurações da API ---
    API_KEY = "k*4)r(4*C*5@t)3Ty(w*5r)Y)Z("  # Chave de API fornecida
    API_URL = "https://www.smmraja.com/api/v3"
    
    # --- Exibir saldo em formato simples e confiável ---
    st.markdown("### 💰 Saldo Disponível")
    
    # Botão para consultar/atualizar saldo
    if st.button("🔄 Consultar Saldo", key="consultar_saldo"):
        with st.spinner("Consultando saldo..."):
            try:
                # Realizar consulta de saldo
                payload = {
                    "key": API_KEY,
                    "action": "balance"
                }
                
                response = requests.post(API_URL, data=payload)
                st.write("Resposta da API:", response.text)  # Debug
                
                data = response.json()
                
                if "error" in data:
                    st.error(f"Erro retornado pela API: {data['error']}")
                else:
                    saldo = data.get("saldo", "N/A")
                    moeda = data.get("moeda", "")
                    
                    # Exibir o saldo em um formato simples e confiável
                    st.success(f"Saldo atual: {saldo} {moeda}")
                    
                    # Armazenar na sessão para uso futuro
                    st.session_state.saldo_info = (saldo, moeda)
            except Exception as e:
                st.error(f"Erro ao consultar saldo: {str(e)}")
    
    # Mostrar saldo armazenado (se disponível)
    elif "saldo_info" in st.session_state:
        saldo, moeda = st.session_state.saldo_info
        st.info(f"Último saldo consultado: {saldo} {moeda}")
    else:
        st.info("Clique no botão para consultar seu saldo atual")
    
    st.markdown("### Configurar Pedidos de Engajamento")
    
    # --- Carrega os engajamentos cadastrados ---
    engajamentos = get_engajamentos()
    if engajamentos:
        # Filtra os engajamentos por tipo
        opcoes_like = {f"{row[1]} (ID: {row[2]})": row[2] for row in engajamentos if row[3] == "Sim" and row[4].lower() == "like"}
        opcoes_uau = {f"{row[1]} (ID: {row[2]})": row[2] for row in engajamentos if row[3] == "Sim" and row[4].lower() == "uau"}
        opcoes_amei = {f"{row[1]} (ID: {row[2]})": row[2] for row in engajamentos if row[3] == "Sim" and row[4].lower() == "amei"}
    else:
        opcoes_like = {}
        opcoes_uau = {}
        opcoes_amei = {}

    # --- Seção para Like (opcional) ---
    col1, col2, col3 = st.columns(3)
    with col1:
        ativar_like = st.checkbox("Ativar 👍 Like")
        if ativar_like:
            if opcoes_like:
                like_engagement = st.selectbox("Selecione o engajamento para Like", options=list(opcoes_like.keys()))
                like_service = opcoes_like[like_engagement]
                like_quantity = st.number_input("Quantidade para Like", min_value=1, value=100, step=1)
            else:
                st.warning("Não há engajamentos do tipo Like cadastrados.")
                like_service = None
        else:
            like_service = None

    # --- Seção para Uau (opcional) ---
    with col2:
        ativar_uau = st.checkbox("Ativar 😮 Uau")
        if ativar_uau:
            if opcoes_uau:
                uau_engagement = st.selectbox("Selecione o engajamento para Uau", options=list(opcoes_uau.keys()))
                uau_service = opcoes_uau[uau_engagement]
                uau_quantity = st.number_input("Quantidade para Uau", min_value=1, value=200, step=1)
            else:
                st.warning("Não há engajamentos do tipo Uau cadastrados.")
                uau_service = None
        else:
            uau_service = None

    # --- Seção para Amei (opcional) ---
    with col3:
        ativar_amei = st.checkbox("Ativar 😍 Amei")
        if ativar_amei:
            if opcoes_amei:
                amei_engagement = st.selectbox("Selecione o engajamento para Amei", options=list(opcoes_amei.keys()))
                amei_service = opcoes_amei[amei_engagement]
                amei_quantity = st.number_input("Quantidade para Amei", min_value=1, value=400, step=1)
            else:
                st.warning("Não há engajamentos do tipo Amei cadastrados.")
                amei_service = None
        else:
            amei_service = None

    # --- Campo para adicionar links ---
    st.markdown("### Links")
    
    # Verificar se recebemos URLs da seção de limpeza
    if "url_para_comprar" in st.session_state and st.session_state.url_para_comprar:
        # Auto-preencher o campo de texto com a URL recebida
        links_input = st.text_area(
            "Adicione os links (um por linha)", 
            value=st.session_state.url_para_comprar,  # Pre-preencher com a URL limpa
            placeholder="https://exemplo.com/link1"
        )
        
        # Botão para limpar a URL recebida
        if st.button("❌ Limpar URL recebida", key="limpar_url_recebida"):
            st.session_state.url_para_comprar = None
            st.rerun()
    elif "urls_para_comprar_lote" in st.session_state and st.session_state.urls_para_comprar_lote:
        # Auto-preencher com o lote de URLs recebidas
        links_input = st.text_area(
            "Adicione os links (um por linha)",
            value="\n".join(st.session_state.urls_para_comprar_lote),
            placeholder="https://exemplo.com/link1"
        )
        
        # Botão para limpar as URLs recebidas
        if st.button("❌ Limpar URLs recebidas", key="limpar_urls_recebidas"):
            st.session_state.urls_para_comprar_lote = []
            st.rerun()
    else:
        links_input = st.text_area("Adicione os links (um por linha)", placeholder="https://exemplo.com/link1")

    # --- Função para enviar os pedidos ---
    def enviar_pedidos(api_key, api_url, reaction_data, links_str):
        """
        reaction_data: dicionário com cada reação e sua respectiva tupla (service_id, quantidade),
                       ex: {"Like": (service_id_like, 100), "Uau": (service_id_uau, 200)}
        """
        links = [link.strip() for link in links_str.splitlines() if link.strip()]
        if not links:
            return "Erro: Nenhum link foi inserido."
        
        resultados = []
        
        # Para cada reação ativada, envia um pedido para cada link
        for reaction, (service_id, quantidade) in reaction_data.items():
            for link in links:
                payload = {
                    "key": api_key,
                    "action": "add",
                    "service": service_id,
                    "link": link,
                    "quantity": quantidade
                }
                try:
                    response = requests.post(api_url, data=payload)
                    response_data = response.json()
                    resultados.append(
                        f"**{reaction}** - **Engajamento ID:** {service_id} | **Link:** {link}\n"
                        f"**Resposta:** {json.dumps(response_data, indent=2)}"
                    )
                except json.JSONDecodeError:
                    resultados.append(
                        f"**{reaction}** - **Engajamento ID:** {service_id} | **Link:** {link}\n"
                        f"**Erro:** Resposta inválida: {response.text}"
                    )
                except Exception as e:
                    resultados.append(
                        f"**{reaction}** - **Engajamento ID:** {service_id} | **Link:** {link}\n"
                        f"**Erro:** {str(e)}"
                    )
        
        return "\n\n".join(resultados)

    if st.button("📤 Enviar Pedidos"):
        # Monta o dicionário apenas com as reações que foram ativadas
        reaction_data = {}
        if ativar_like:
            if like_service:
                reaction_data["Like"] = (like_service, like_quantity)
            else:
                st.error("Selecione um engajamento para Like.")
        if ativar_uau:
            if uau_service:
                reaction_data["Uau"] = (uau_service, uau_quantity)
            else:
                st.error("Selecione um engajamento para Uau.")
        if ativar_amei:
            if amei_service:
                reaction_data["Amei"] = (amei_service, amei_quantity)
            else:
                st.error("Selecione um engajamento para Amei.")
        
        if not reaction_data:
            st.error("Por favor, ative pelo menos uma reação para enviar pedidos.")
        else:
            resultado = enviar_pedidos(API_KEY, API_URL, reaction_data, links_input)
            st.markdown("### 📈 Resultados")
            st.text_area("", resultado, height=300)