FROM python:3.10-slim

# Define variável de ambiente para indicar que estamos no Railway
ENV RAILWAY_ENVIRONMENT=true

# Instala Chrome e ChromeDriver
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    unzip \
    xvfb \
    libxi6 \
    libgconf-2-4

# Instala Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable

# Instala ChromeDriver
RUN CHROME_VERSION=$(google-chrome --version | sed 's/Google Chrome //g' | sed 's/\..*//g') \
    && CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION") \
    && wget -q -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" \
    && unzip /tmp/chromedriver.zip -d /usr/local/bin/ \
    && rm /tmp/chromedriver.zip \
    && chmod +x /usr/local/bin/chromedriver

# Configura diretório de trabalho
WORKDIR /app

# Copia arquivos de requisitos primeiro (para aproveitar o cache de camadas)
COPY requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante dos arquivos
COPY . .

# Expõe a porta para o Streamlit
EXPOSE 8501

# Comando para executar a aplicação
CMD ["streamlit", "run", "iniciar.py", "--server.port=8501", "--server.address=0.0.0.0"]