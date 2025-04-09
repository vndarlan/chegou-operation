import streamlit as st

# Page header
st.markdown('<div class="header-container">', unsafe_allow_html=True)
st.markdown('<h1 class="page-title">Tutoriais</h1>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle"><strong>Guia prático: aprenda a usar a ferramenta passo a passo!</strong></p>', unsafe_allow_html=True)
st.markdown("---")

# First video (featured)
st.markdown('<div class="video-container">', unsafe_allow_html=True)
st.markdown('<div class="tutorial-title"><strong>Novelties Sem Complicação!</strong></div>', unsafe_allow_html=True)
st.markdown('<div class="tutorial-description">Aprenda a ativar e usar a automação</div>', unsafe_allow_html=True)

st.video("https://www.youtube.com/watch?v=_AgxTh3ddyM")

st.markdown("---")

# Second video
st.markdown('<div class="video-container">', unsafe_allow_html=True)
st.markdown('<div class="tutorial-title"><strong>Engajamento Turbinado! Compre e Limpe a URL!</strong></div>', unsafe_allow_html=True)
st.markdown('<div class="tutorial-description">Veja como comprar, cadastrar e limpar a URL para melhores resultados! </div>', unsafe_allow_html=True)

st.video("https://www.youtube.com/watch?v=sOKeSdpPJX4")

st.markdown("---")

# Third video (new)
st.markdown('<div class="video-container">', unsafe_allow_html=True)
st.markdown('<div class="tutorial-title"><strong>Ache o ID de Moderação Rapidamente!</strong></div>', unsafe_allow_html=True)
st.markdown('<div class="tutorial-description">Descubra o jeito mais fácil de encontrar o ID de moderação</div>', unsafe_allow_html=True)

st.video("https://www.youtube.com/watch?v=sOKeSdpPJX4")
st.markdown("---")

