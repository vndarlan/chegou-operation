import streamlit as st
from streamlit.runtime.scriptrunner import RerunException, RerunData

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

def main():
    # Inicializa variáveis de sessão
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "cargo" not in st.session_state:
        st.session_state["cargo"] = None

    # Se NÃO estiver logado, exibe apenas a página de login
    if not st.session_state["logged_in"]:
        pages = [st.Page(login_page, title="Login", icon="🔒")]
        pg = st.navigation(pages, position="sidebar", expanded=False)
        pg.run()
    else:
        # Define páginas de acordo com o cargo
        if st.session_state["cargo"] == "Administrador":
            pages = {
                "Principal": [
                    st.Page("principal/home.py", title="Home", icon="🏠"),
                ],
                "Novelties": [
                    st.Page("novelties/mexico.py",   title="México",   icon="🇲🇽"),
                    st.Page("novelties/chile.py",    title="Chile",    icon="🇨🇱"),
                    st.Page("novelties/colombia.py", title="Colômbia", icon="🇨🇴"),
                    st.Page("novelties/equador.py",  title="Equador",  icon="🇪🇨"),
                ],
                "Moderação": [
                    st.Page("moderacao/busca_id.py", title="Busca pelo ID", icon="🔎"),
                ],
                "Engajamento": [
                    st.Page("engajamento/cadastrar.py",  title="Cadastrar", icon="📝"),
                    st.Page("engajamento/limpar_url.py", title="Limpar URL", icon="🧹"),
                    st.Page("engajamento/comprar.py",    title="Comprar",    icon="🛒"),
                ],
            }
        else:
            # Usuário comum
            pages = {
                "Principal": [
                    st.Page("principal/home.py", title="Home", icon="🏠"),
                ],
                "Novelties": [
                    st.Page("novelties/mexico.py",   title="México",   icon="🌎"),
                    st.Page("novelties/chile.py",    title="Chile",    icon="🌎"),
                    st.Page("novelties/colombia.py", title="Colômbia", icon="🌎"),
                    st.Page("novelties/equador.py",  title="Equador",  icon="🌎"),
                ],
                "Moderação": [
                    st.Page("moderacao/busca_id.py", title="Busca pelo ID", icon="🔎"),
                ],
                "Engajamento": [
                    st.Page("engajamento/cadastrar.py",  title="Cadastrar", icon="📝"),
                    st.Page("engajamento/limpar_url.py", title="Limpar URL", icon="🧹"),
                    st.Page("engajamento/comprar.py",    title="Comprar",    icon="🛒"),
                ],
            }

        # Cria a barra de navegação
        pg = st.navigation(pages, position="sidebar", expanded=False)
        # Exibe botão de logout
        show_logout_button()
        # Executa a página selecionada
        pg.run()

if __name__ == "__main__":
    main()
