import streamlit as st
from streamlit.runtime.scriptrunner import RerunException, RerunData

# Configuração global da página
st.set_page_config( 
    page_title="Chegou Operation", 
    page_icon="assets/favicon.png"
)

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
    st.title("Chegou Operation")
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
    if st.sidebar.button("Sair", key="logout_button"):
        st.session_state["logged_in"] = False
        st.session_state["cargo"] = None
        force_rerun()

def main():
    # Inicializa variáveis de sessão
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "cargo" not in st.session_state:
        st.session_state["cargo"] = None

    # Adiciona CSS personalizado para a borda direita
    st.markdown("""
    <style>
    section[data-testid="stSidebar"] {
        border-right: 1px solid #e0e0e0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Se NÃO estiver logado, exibe apenas a página de login
    if not st.session_state["logged_in"]:     
        pages = [st.Page(login_page, title="Login", icon=":material/lock:")]
        pg = st.navigation(pages, position="sidebar", expanded=False)
        pg.run()
    else:     
        # Define páginas de acordo com o cargo
        if st.session_state["cargo"] == "Administrador":
            pages = {
                "Principal": [
                    st.Page("principal/home.py", title="Home", icon=":material/home:"),
                    st.Page("principal/tutoriais.py", title="Tutoriais", icon=":material/home:"),
                ],
                "Novelties": [
                    st.Page("novelties/mexico.py",   title="México",   icon=":material/flag:"),
                    st.Page("novelties/chile.py",    title="Chile",    icon=":material/flag:"),
                    st.Page("novelties/colombia.py", title="Colômbia", icon=":material/flag:"),
                    st.Page("novelties/equador.py",  title="Equador",  icon=":material/flag:"),
                ],
                "Moderação": [
                    st.Page("moderacao/busca_id.py", title="Busca pelo ID", icon=":material/manage_search:"),
                ],
                "Engajamento": [
                    st.Page("engajamento/cadastrar.py",  title="Cadastrar", icon=":material/edit_note:"),
                    st.Page("engajamento/comprar.py",    title="Comprar",    icon=":material/shopping_cart:"),
                ],
            }
        else:
            # Usuário comum
            pages = {
                "Principal": [
                    st.Page("principal/home.py", title="Home", icon=":material/home:"),
                ],
                "Novelties": [
                    st.Page("novelties/mexico.py",   title="México",   icon=":material/flag:"),
                    st.Page("novelties/chile.py",    title="Chile",    icon=":material/flag:"),
                    st.Page("novelties/colombia.py", title="Colômbia", icon=":material/flag:"),
                    st.Page("novelties/equador.py",  title="Equador",  icon=":material/flag:"),
                ],
                "Moderação": [
                    st.Page("moderacao/busca_id.py", title="Busca pelo ID", icon=":material/manage_search:"),
                ],
                "Engajamento": [
                    st.Page("engajamento/cadastrar.py",  title="Cadastrar", icon=":material/edit_note:"),
                    st.Page("engajamento/comprar.py",    title="Comprar",    icon=":material/shopping_cart:"),
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