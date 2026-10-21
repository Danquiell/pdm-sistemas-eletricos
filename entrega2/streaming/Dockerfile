FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py ons_legacy.py inmet_service.py contrato_referencia.py evento_inmet.schema.json config_projeto.json manifesto.json ./
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "24", "--timeout", "240", "main:app"]
