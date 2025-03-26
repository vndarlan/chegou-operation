FROM python:3.10-slim

# Define variável de ambiente para indicar que estamos no Railway
ENV RAILWAY_ENVIRONMENT=true

# Instala dependências
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    unzip \
    bash

# Instala Chrome usando apt
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable

# Usa o chromedriver fornecido pelo selenium
# Isso evita a necessidade de instalar manualmente o chromedriver
RUN pip install selenium webdriver-manager

# Configura diretório de trabalho
WORKDIR /app

# Copia arquivos de requisitos primeiro (para aproveitar o cache de camadas)
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante dos arquivos
COPY . .

# Expõe a porta padrão para o Streamlit
EXPOSE 8501

# Comando para executar a aplicação com expansão da variável PORT
CMD bash -c "streamlit run iniciar.py --server.address=0.0.0.0 --server.port=\${PORT:-8501}"