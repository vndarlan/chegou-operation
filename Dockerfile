FROM python:3.10-slim

# Define variável de ambiente para indicar que estamos no Railway
ENV RAILWAY_ENVIRONMENT=true
ENV PYTHONUNBUFFERED=1

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    unzip \
    bash \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Instala Chrome usando apt
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Configura diretório de trabalho
WORKDIR /app

# Copia arquivos de requisitos primeiro (para aproveitar o cache de camadas)
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante dos arquivos
COPY . .

# Cria arquivos necessários e define permissões
RUN mkdir -p /app/logs \
    && touch /app/dropi_automation.db \
    && chmod -R 777 /app/logs \
    && chmod 666 /app/dropi_automation.db

# Expõe a porta que será usada
EXPOSE 8080

# Comando para executar a aplicação com expansão da variável PORT
CMD streamlit run iniciar.py --server.address=0.0.0.0 --server.port=${PORT:-8080}