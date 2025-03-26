# 02_API.py
import streamlit as st
import requests
import json
import sqlite3

# --- Cabeçalho e autenticação ---
st.markdown("<h3>🔒 Área restrita </h3>", unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    with st.form("login_form"):
        senha = st.text_input("Digite a senha para acessar a área de desenvolvedor", type="password")
        submitted = st.form_submit_button("Entrar")
        if submitted:
            if senha == "timeiagc":
                st.session_state.logged_in = True
                st.success("Acesso autorizado!")
            else:
                st.error("Senha incorreta. Tente novamente.")
    st.stop()

# --- Função para obter os engajamentos do banco de dados ---
def get_engajamentos():
    conn = sqlite3.connect("engajamentos.db")
    c = conn.cursor()
    c.execute("SELECT id, nome, engajamento_id, funcionando FROM engajamentos")
    rows = c.fetchall()
    conn.close()
    return rows

# --- Configurações da API ---
API_KEY = "9A*fw(I0@tni*lW(LUX(K"  # Substitua pela sua chave de API
API_URL = "https://www.smmraja.com/api/v3"

# --- Carrega os engajamentos cadastrados ---
engajamentos = get_engajamentos()
if engajamentos:
    # Apenas os engajamentos que estão funcionando
    opcoes = {f"{row[1]} (ID: {row[2]})": row[2] for row in engajamentos if row[3] == "Sim"}
else:
    opcoes = {}

st.markdown("### Configurar Pedidos de Engajamento (Selecione apenas os desejados)")

# --- Seção para Like (opcional) ---
col1, col2, col3 = st.columns(3)
with col1:
    ativar_like = st.checkbox("Ativar 👍 Like")
    if ativar_like and opcoes:
        like_engagement = st.selectbox("Selecione o engajamento para Like", options=list(opcoes.keys()))
        like_service = opcoes[like_engagement]
        like_quantity = st.number_input("Quantidade para Like", min_value=1, value=100, step=1)
    else:
        like_service = None

# --- Seção para Uau (opcional) ---
with col2:
    ativar_uau = st.checkbox("Ativar 😮 Uau")
    if ativar_uau and opcoes:
        uau_engagement = st.selectbox("Selecione o engajamento para Uau", options=list(opcoes.keys()))
        uau_service = opcoes[uau_engagement]
        uau_quantity = st.number_input("Quantidade para Uau", min_value=1, value=200, step=1)
    else:
        uau_service = None

# --- Seção para Amei (opcional) ---
with col3:
    ativar_amei = st.checkbox("Ativar 😍 Amei")
    if ativar_amei and opcoes:
        amei_engagement = st.selectbox("Selecione o engajamento para Amei", options=list(opcoes.keys()))
        amei_service = opcoes[amei_engagement]
        amei_quantity = st.number_input("Quantidade para Amei", min_value=1, value=400, step=1)
    else:
        amei_service = None

# --- Campo para adicionar links ---
st.markdown("### Links")
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
