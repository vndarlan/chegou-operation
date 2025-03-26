import streamlit as st
import requests
import re
import json
import time
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

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

st.markdown("<h3>🧹 Limpar URLs de Anúncios</h3>", unsafe_allow_html=True)

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
        
        # Using a very short timeout to quickly check availability
        try:
            service = Service(ChromeDriverManager().install())
            browser = webdriver.Chrome(service=service, options=options)
            browser.quit()
            return True
        except Exception as e:
            st.warning(f"Selenium initialization failed: {str(e)}")
            return False
    except:
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
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-infobars')
        
        # Adicionar um User-Agent comum para evitar bloqueios
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36')
        
        # Usar o webdriver-manager para instalar e gerenciar o ChromeDriver automaticamente
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
        
        # PRIORIDADE 3: Verificar meta tags (og:video) na página
        try:
            video_meta = browser.find_elements(By.XPATH, '//meta[@property="og:video" or @property="og:video:url"]')
            if video_meta:
                for meta in video_meta:
                    content = meta.get_attribute('content')
                    if content and ('facebook.com' in content):
                        browser.quit()
                        return content
        except Exception as e:
            pass
        
        # PRIORIDADE 4: Tentar encontrar botão de menu e opção "Copiar link"
        try:
            # Procurar por botões de menu (três pontos)
            menu_buttons = browser.find_elements(By.XPATH, '//div[@aria-label="Ações para esta publicação" or @aria-label="Actions for this post"]')
            if not menu_buttons:
                menu_buttons = browser.find_elements(By.XPATH, '//div[contains(@aria-label, "Mais opções") or contains(@aria-label, "More options")]')
                
            if menu_buttons:
                for menu_button in menu_buttons:
                    try:
                        menu_button.click()
                        time.sleep(1)  # Esperar o menu aparecer
                        
                        # Procurar a opção "Copiar link"
                        copy_links = browser.find_elements(By.XPATH, '//span[contains(text(), "Copiar link") or contains(text(), "Copy link")]')
                        if copy_links:
                            for copy_link in copy_links:
                                try:
                                    # Tentar obter o link diretamente do elemento pai ou adjacente
                                    parent = copy_link.find_element(By.XPATH, "./..")
                                    if 'href' in parent.get_attribute('outerHTML'):
                                        href = parent.get_attribute('href')
                                        if href:
                                            browser.quit()
                                            return href
                                            
                                    # Se não conseguimos o link assim, vamos clicar e tentar capturar a URL atual
                                    copy_link.click()
                                    time.sleep(1)
                                    # Em alguns casos, clicar em "Copiar link" altera a URL da página
                                    current_url = browser.current_url
                                    if current_url != url:
                                        browser.quit()
                                        return current_url
                                except:
                                    continue
                    except:
                        continue
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
        pass
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
        st.info("🔍 **MÉTODO ATIVO: API Móvel (BeautifulSoup)**")
        
        # Converter para versão móvel (m.facebook.com)
        mobile_url = url.replace('www.facebook.com', 'm.facebook.com')
        
        # Adicionar headers para simular um navegador móvel
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3',
        }
        
        st.info(f"Acessando versão móvel: {mobile_url}")
        response = requests.get(mobile_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            st.warning(f"❌ Falha ao acessar a versão móvel: status {response.status_code}")
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
                        st.success(f"✅ Encontrado link de vídeo na versão móvel: {href}")
                        return href
                    elif element.name == 'source' and element.get('src'):
                        src = element['src']
                        st.success(f"✅ Encontrada fonte de vídeo direta: {src}")
                        return src
                    elif element.name == 'div' and element.get('data-store'):
                        try:
                            data_store = json.loads(element['data-store'])
                            if 'videoID' in data_store:
                                video_id = data_store['videoID']
                                video_url = f"https://www.facebook.com/watch/?v={video_id}"
                                st.success(f"✅ Extraído ID de vídeo ({video_id}): {video_url}")
                                return video_url
                        except:
                            pass
        
        # PRIORIDADE 2: Metadados do Open Graph para vídeo
        og_video = soup.find('meta', property='og:video:url')
        if og_video and og_video.get('content'):
            st.success(f"✅ Encontrada URL de vídeo nas meta tags: {og_video['content']}")
            return og_video['content']
            
        og_url = soup.find('meta', property='og:url')
        if og_url and og_url.get('content') and 'videos' in og_url['content']:
            st.success(f"✅ Encontrada URL nas meta tags og:url: {og_url['content']}")
            return og_url['content']
        
        # PRIORIDADE 3: Extrair scripts com informações de vídeo
        scripts = soup.find_all('script')
        for script in scripts:
            content = script.string
            if not content:
                continue
                
            # Procurar IDs de vídeo em scripts
            video_id_match = re.search(r'"videoId":"([0-9]+)"', content)
            if video_id_match:
                video_id = video_id_match.group(1)
                video_url = f"https://www.facebook.com/watch/?v={video_id}"
                st.success(f"✅ Extraído ID de vídeo de script: {video_url}")
                return video_url
                
            # Procurar permalinks completos em scripts
            permalink_match = re.search(r'"permalink_url":"([^"]+)"', content)
            if permalink_match:
                permalink = permalink_match.group(1).replace('\\', '')
                st.success(f"✅ Encontrado permalink em script: {permalink}")
                return permalink
        
        # PRIORIDADE 4: Procurar redirects
        # Verificar se temos algum redirect na página
        redirects = soup.select('a[href*="l.facebook.com/l.php"]')
        for redirect in redirects:
            href = redirect.get('href')
            if href and ('facebook.com/videos' in href or 'facebook.com/watch' in href):
                # Extrair a URL real do parâmetro 'u='
                parsed = urlparse(href)
                query_params = parse_qs(parsed.query)
                if 'u' in query_params:
                    target_url = query_params['u'][0]
                    st.success(f"✅ Encontrado redirecionamento para: {target_url}")
                    return target_url
                else:
                    st.success(f"✅ Encontrado link de redirecionamento: {href}")
                    return href
    
        # PRIORIDADE 5: Procurar por links que contenham "permalink"
        permalink_links = soup.select('a[href*="permalink.php"]')
        for link in permalink_links:
            permalink = link.get('href')
            if permalink:
                if not permalink.startswith('http'):
                    permalink = 'https://www.facebook.com' + permalink
                
                # Verificar se é um permalink para um vídeo
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    permalink_response = requests.get(permalink, headers=headers, timeout=5)
                    if '/videos/' in permalink_response.url:
                        st.success(f"✅ Permalink redirecionou para vídeo: {permalink_response.url}")
                        return permalink_response.url
                except:
                    # Se falhar, retornamos o permalink mesmo assim
                    st.success(f"✅ Encontrado permalink: {permalink}")
                    return permalink
                
    except Exception as e:
        st.warning(f"❌ Erro ao extrair via API móvel: {str(e)}")
        
    return None

def extrair_via_graph_api(url, token=None):
    """
    Tenta extrair informações usando o Graph API do Facebook.
    Requer um token de acesso válido com permissões.
    """
    if not token:
        return None
        
    try:
        st.info("📊 **MÉTODO ATIVO: Facebook Graph API**")
        
        # Extrair o ID do post ou vídeo da URL
        post_id = None
        
        # Padrões comuns de IDs de posts/vídeos do Facebook
        patterns = [
            r'facebook\.com/(?:[\w\.]+/)?posts/(\d+)',
            r'facebook\.com/(?:[\w\.]+/)?videos/(\d+)',
            r'facebook\.com/(\d+)/posts/(\d+)',
            r'facebook\.com/(\d+)/videos/(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                # Se tiver dois grupos, é formato página/post ou página/vídeo
                if len(match.groups()) == 2:
                    post_id = f"{match.group(1)}_{match.group(2)}"
                else:
                    post_id = match.group(1)
                break
                
        if not post_id:
            st.warning("❌ Não foi possível extrair ID do post/vídeo para consultar a API")
            return None
        
        st.info(f"ID extraído para consulta na API: {post_id}")
            
        # Chamar o Graph API
        api_url = f"https://graph.facebook.com/v16.0/{post_id}?access_token={token}&fields=permalink_url,source,attachments"
        response = requests.get(api_url)
        
        if response.status_code != 200:
            st.warning(f"❌ Falha na consulta à API: status {response.status_code}")
            return None
            
        data = response.json()
        st.info(f"Dados retornados pela API: {json.dumps(data)}")
        
        # Tentar obter URL de vídeo diretamente
        if 'source' in data:
            st.success(f"✅ Encontrada fonte de vídeo via API: {data['source']}")
            return data['source']
            
        # Verificar se há anexos de vídeo
        if 'attachments' in data and 'data' in data['attachments']:
            for attachment in data['attachments']['data']:
                if 'type' in attachment and attachment['type'] == 'video_inline':
                    if 'url' in attachment:
                        st.success(f"✅ Encontrado anexo de vídeo via API: {attachment['url']}")
                        return attachment['url']
                    elif 'media' in attachment and 'source' in attachment['media']:
                        st.success(f"✅ Encontrada fonte de mídia via API: {attachment['media']['source']}")
                        return attachment['media']['source']
                        
        # Se não encontrou vídeo, retornar permalink
        if 'permalink_url' in data:
            st.success(f"✅ Encontrado permalink via API: {data['permalink_url']}")
            return data['permalink_url']
            
        st.warning("❌ Nenhuma URL de conteúdo encontrada via API")
            
    except Exception as e:
        st.warning(f"❌ Erro ao usar Graph API: {str(e)}")
        
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
        st.warning(f"Error in non-Selenium extraction: {str(e)}")
        
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
            st.info("Selenium não disponível ou falhou. Usando método alternativo.")
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

# Safely displays URL results handling different return types
def display_url_results(original_url, cleaned_url_tuple):
    """Safely displays URL results handling different return types"""
    url_limpa, status, mensagem = cleaned_url_tuple
    
    # Ensure url_limpa is a string
    if isinstance(url_limpa, bytes):
        url_limpa = url_limpa.decode('utf-8')
    
    st.markdown("### URL Original:")
    st.code(original_url)
    
    st.markdown("### URL Limpa:")
    st.code(url_limpa)
    
    # Result message
    if status == "sucesso":
        st.success(f"✅ {mensagem}")
    elif status == "aviso":
        st.warning(f"⚠️ {mensagem}")
    else:
        st.error(f"❌ {mensagem}")
    
    # Display parsed URL carefully
    try:
        parsed = urlparse(url_limpa)
        components = {
            "domínio": parsed.netloc,
            "caminho": parsed.path,
            "parâmetros": parse_qs(parsed.query) if parsed.query else {}
        }
        st.markdown("#### Componentes da URL:")
        st.json(components)
    except Exception as e:
        st.error(f"Erro ao analisar componentes da URL: {str(e)}")
    
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
with st.container():
    st.markdown("### 🧹 Limpar URLs de Anúncios")
    
    tabs = st.tabs(["URL Única", "Lote de URLs"])

    # Tab para URL única
    with tabs[0]:
        url_input = st.text_input("Cole a URL do anúncio do Facebook", 
                                  placeholder="https://www.facebook.com/...",
                                  help="URL original do anúncio com parâmetros de rastreamento")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            clean_button = st.button("🔍 Limpar URL", key="btn_limpar_unica", use_container_width=True)
        with col2:
            show_details = st.checkbox("Mostrar detalhes", value=False, 
                                      help="Exibe detalhes técnicos do processo de limpeza")
        
        if 'último_processo' not in st.session_state:
            st.session_state.último_processo = {}
            
        if clean_button:
            if url_input:
                with st.spinner("⏳ Processando a URL..."):
                    # Capturar o início do tempo para medir a duração
                    start_time = time.time()
                    
                    # Processar a URL
                    cleaned_url_tuple = limpar_url_facebook(url_input)
                    
                    # Calcular duração
                    duration = time.time() - start_time
                    
                    # Salvar informações do processo
                    st.session_state.último_processo = {
                        "original": url_input,
                        "limpa": cleaned_url_tuple[0],
                        "sucesso": cleaned_url_tuple[1] == "sucesso",
                        "duração": f"{duration:.2f} segundos"
                    }
                    
                # Exibir informações detalhadas ou resumidas
                if show_details:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("### URL Original:")
                        st.code(url_input, language="text")
                        
                        # Análise da URL original
                        try:
                            parsed = urlparse(url_input)
                            st.markdown("#### Componentes da URL Original:")
                            st.json({
                                "domínio": parsed.netloc,
                                "caminho": parsed.path,
                                "parâmetros": parse_qs(parsed.query) if parsed.query else {}
                            })
                        except Exception as e:
                            st.error(f"Erro ao analisar URL original: {str(e)}")
                    
                    with col2:
                        url_limpa = cleaned_url_tuple[0]
                        st.markdown("### URL Limpa:")
                        st.code(url_limpa, language="text")
                        
                        # Análise da URL limpa
                        if url_limpa != url_input:
                            try:
                                parsed = urlparse(url_limpa)
                                st.markdown("#### Componentes da URL Limpa:")
                                st.json({
                                    "domínio": parsed.netloc,
                                    "caminho": parsed.path,
                                    "parâmetros": parse_qs(parsed.query) if parsed.query else {}
                                })
                            except Exception as e:
                                st.error(f"Erro ao analisar URL limpa: {str(e)}")
                        
                    # Informações do processo
                    st.markdown("### Informações do Processo:")
                    st.info(f"⏱️ Tempo de processamento: {st.session_state.último_processo['duração']}")
                else:
                    # Using the safe display function
                    url_limpa = display_url_results(url_input, cleaned_url_tuple)
                
                # Resultado final e botões de ação
                if cleaned_url_tuple[1] == "sucesso":
                    st.success("✅ URL processada com sucesso!")
                    
                    # Adicionar botão para usar na compra
                    if st.button("🛒 Usar esta URL para comprar engajamento", key="usar_url"):
                        # Redirecionar para a página de compra (pode ser implementado posteriormente)
                        st.session_state.url_para_compra = url_limpa
                        st.info("URL pronta para compra. Acesse a página 'Comprar' para continuar.")
                else:
                    st.warning("⚠️ Não foi possível limpar esta URL ou ocorreu um erro no processo.")
                
                # Botão para copiar para a área de transferência
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
        
        col1, col2 = st.columns([3, 1])
        with col1:
            process_button = st.button("🔄 Processar Lote", key="btn_limpar_lote", use_container_width=True)
        with col2:
            batch_details = st.checkbox("Mostrar detalhes do lote", value=False)
            
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
                    
                    # Exibir resultados
                    st.markdown("### Resultados:")
                    
                    if batch_details:
                        # Criar uma tabela de resultados detalhada
                        for i, (original, clean_tuple) in enumerate(resultados, 1):
                            with st.expander(f"URL {i}"):
                                url_limpa, status, mensagem = clean_tuple
                                
                                # Ensure url_limpa is a string
                                if isinstance(url_limpa, bytes):
                                    url_limpa = url_limpa.decode('utf-8')
                                
                                st.markdown("**Original:**")
                                st.code(original)
                                st.markdown("**Limpa:**")
                                st.code(url_limpa)
                                
                                if status == "sucesso":
                                    st.success(f"✅ {mensagem}")
                                elif status == "aviso":
                                    st.warning(f"⚠️ {mensagem}")
                                else:
                                    st.error(f"❌ {mensagem}")
                    else:
                        # Criar uma tabela resumida de resultados
                        tabela_dados = []
                        for i, (original, clean_tuple) in enumerate(resultados, 1):
                            url_limpa, status, mensagem = clean_tuple
                            
                            # Ensure url_limpa is a string
                            if isinstance(url_limpa, bytes):
                                url_limpa = url_limpa.decode('utf-8')
                                
                            status_icon = "✅" if status == "sucesso" else "⚠️" if status == "aviso" else "❌"
                            tabela_dados.append({
                                "URL #": i,
                                "URL Original": original[:50] + "..." if len(original) > 50 else original,
                                "URL Limpa": url_limpa[:50] + "..." if len(url_limpa) > 50 else url_limpa,
                                "Status": f"{status_icon} {mensagem}"
                            })
                        
                        # Exibir tabela
                        st.dataframe(tabela_dados)
                    
                    # Mostrar um resumo das URLs limpas
                    st.markdown("### Todas as URLs Limpas:")
                    todas_limpas = "\n".join([clean_tuple[0] if isinstance(clean_tuple[0], str) 
                                             else clean_tuple[0].decode('utf-8') if isinstance(clean_tuple[0], bytes)
                                             else str(clean_tuple[0])
                                             for _, clean_tuple in resultados])
                    st.code(todas_limpas)
                    
                    # Botão para baixar as URLs limpas
                    st.download_button(
                        label="📥 Baixar URLs Limpas",
                        data=todas_limpas,
                        file_name="urls_limpas.txt",
                        mime="text/plain"
                    )
                    
                    # Botão para usar na compra
                    if st.button("🛒 Usar estas URLs para comprar engajamento", key="usar_urls_lote"):
                        # Armazenar URLs para uso na página de compra
                        st.session_state.urls_para_compra = [clean_tuple[0] for _, clean_tuple in resultados]
                        st.info("URLs prontas para compra. Acesse a página 'Comprar' para continuar.")
            else:
                st.error("❌ Por favor, insira pelo menos uma URL para processar.")