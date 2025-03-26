import streamlit as st
from streamlit.runtime.scriptrunner import RerunException, RerunData
import os
import importlib.util
import sys

# Função interna para forçar rerun (substitui st.experimental_rerun())
def force_rerun():
    raise RerunException(RerunData(None))

# Dicionário de usuários (NÃO use em produção sem hashing de senhas)
USERS = {
    "adminoperacional@grupochegou.com": {"password": "admgcopera2025", "cargo": "Administrador"},
    "operacional@grupochegou.com":  {"password": "gcopera2025",  "cargo": "Usuário"},
}

def login_page():
    """Página de Login."""
    st.title("GC Operacional")
    st.subheader("Faça seu login")

    email = st.text_input("Email")
    password = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if email in USERS and USERS[email]["password"] == password:
            st.session_state["logged_in"] = True
            st.session_state["cargo"] = USERS[email]["cargo"]
            # Em vez de st.experimental_rerun(), usamos force_rerun():
            force_rerun()
        else:
            st.error("Credenciais inválidas. Tente novamente.")

def show_logout_button():
    """Exibe um botão de logout na sidebar."""
    if st.sidebar.button("Sair"):
        st.session_state["logged_in"] = False
        st.session_state["cargo"] = None
        force_rerun()

def load_page(page_path):
    """Carrega dinamicamente uma página Python e executa sua função main()."""
    try:
        module_name = page_path.replace("/", ".").replace(".py", "")
        spec = importlib.util.spec_from_file_location(module_name, page_path)
        if not spec:
            st.error(f"Não foi possível encontrar a página: {page_path}")
            return
            
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        # Verifica se o módulo tem uma função 'main' e a executa
        if hasattr(module, 'main'):
            module.main()
        else:
            st.error(f"A página {page_path} não tem uma função main().")
    except Exception as e:
        st.error(f"Erro ao carregar a página {page_path}: {str(e)}")

def main():
    # Inicializa variáveis de sessão
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "cargo" not in st.session_state:
        st.session_state["cargo"] = None
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "login"

    # Se NÃO estiver logado, exibe apenas a página de login
    if not st.session_state["logged_in"]:
        login_page()
    else:
        # Define páginas de acordo com o cargo
        if st.session_state["cargo"] == "Administrador":
            pages = {
                "Principal": [
                    {"title": "Home", "icon": "🏠", "path": "principal/home.py"},
                ],
                "Novelties": [
                    {"title": "México", "icon": "🇲🇽", "path": "novelties/mexico.py"},
                    {"title": "Chile", "icon": "🇨🇱", "path": "novelties/chile.py"},
                    {"title": "Colômbia", "icon": "🇨🇴", "path": "novelties/colombia.py"},
                    {"title": "Equador", "icon": "🇪🇨", "path": "novelties/equador.py"},
                ],
                "Moderação": [
                    {"title": "Busca pelo ID", "icon": "🔎", "path": "moderacao/busca_id.py"},
                ],
                "Engajamento": [
                    {"title": "Cadastrar", "icon": "📝", "path": "engajamento/cadastrar.py"},
                    {"title": "Limpar URL", "icon": "🧹", "path": "engajamento/limpar_url.py"},
                    {"title": "Comprar", "icon": "🛒", "path": "engajamento/comprar.py"},
                ],
            }
        else:
            # Usuário comum
            pages = {
                "Principal": [
                    {"title": "Home", "icon": "🏠", "path": "principal/home.py"},
                ],
                "Novelties": [
                    {"title": "México", "icon": "🌎", "path": "novelties/mexico.py"},
                    {"title": "Chile", "icon": "🌎", "path": "novelties/chile.py"},
                    {"title": "Colômbia", "icon": "🌎", "path": "novelties/colombia.py"},
                    {"title": "Equador", "icon": "🌎", "path": "novelties/equador.py"},
                ],
                "Moderação": [
                    {"title": "Busca pelo ID", "icon": "🔎", "path": "moderacao/busca_id.py"},
                ],
                "Engajamento": [
                    {"title": "Cadastrar", "icon": "📝", "path": "engajamento/cadastrar.py"},
                    {"title": "Limpar URL", "icon": "🧹", "path": "engajamento/limpar_url.py"},
                    {"title": "Comprar", "icon": "🛒", "path": "engajamento/comprar.py"},
                ],
            }

        # Cria menu de navegação na sidebar
        st.sidebar.title("Navegação")
        
        # Lista as categorias e páginas
        all_pages = []
        for category, category_pages in pages.items():
            st.sidebar.subheader(category)
            for page in category_pages:
                page_key = f"{category}_{page['title']}"
                if st.sidebar.button(f"{page['icon']} {page['title']}", key=page_key):
                    st.session_state["current_page"] = page["path"]
                    force_rerun()
                all_pages.append(page)
        
        # Exibe botão de logout
        show_logout_button()
        
        # Carrega a página atual
        if st.session_state["current_page"] == "login":
            # Se não selecionou nenhuma página, carrega a primeira
            if all_pages:
                load_page(all_pages[0]["path"])
        else:
            load_page(st.session_state["current_page"])

if __name__ == "__main__":
    # Configura o tema para dark
    st.set_page_config(
        page_title="GC Operacional",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    main()