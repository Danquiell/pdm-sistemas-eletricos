FROM python:3.12-slim

WORKDIR /app

# bibliotecas da API
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# código e modelo (o JSON precisa ficar na mesma pasta do detector.py)
COPY app.py detector.py modelo_anomalia_perda.json ./

# o Cloud Run informa a porta pela variável PORT
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
