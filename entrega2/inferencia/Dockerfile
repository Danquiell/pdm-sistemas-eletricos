# API de inferência de anomalias (POST /predict) para o Cloud Run.
# O modelo vem do arquivo modelo_anomalia_perda.json. O BigQuery só é lido para o clima do
# dia (contexto.py); se ele falhar, a previsão sai do mesmo jeito.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependências primeiro: esta camada fica em cache enquanto só o código mudar
COPY requirements.txt .
RUN pip install -r requirements.txt

# Só o que a API usa. O JSON precisa ficar na mesma pasta do detector.py.
COPY app.py detector.py contexto.py modelo_anomalia_perda.json ./

# Não rodar como root dentro do contêiner
RUN useradd --system --no-create-home api
USER api

# O Cloud Run informa a porta em $PORT (8080 por padrão)
EXPOSE 8080
CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}
