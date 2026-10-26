#!/usr/bin/env bash
# Publica o serviço do streaming (rotas /inmet/pubsub e /pubsub) no Cloud Run.
# Fica com no máximo uma instância porque a checagem de duplicata guarda os hashes em memória.
# Não aceita chamada sem login: só a conta pubsub-push-pipeline, usada pelas assinaturas push,
# tem permissão de chamar o serviço.
# Rodar de dentro de entrega2/streaming, depois do preparar.py (o manifesto.json vai junto).
set -euo pipefail

PROJETO=pdm-sistema-eletrico-2026
REGIAO=us-central1
SERVICO=pipeline-ons-streaming
CONTA=pipeline-streaming@${PROJETO}.iam.gserviceaccount.com

test -f manifesto.json || { echo "falta o manifesto.json: rode python preparar.py antes"; exit 1; }

gcloud run deploy "$SERVICO" --source . --project "$PROJETO" --region "$REGIAO" \
  --service-account "$CONTA" --no-allow-unauthenticated \
  --cpu 1 --memory 512Mi --concurrency 24 --timeout 240 \
  --min-instances 0 --max-instances 1 --cpu-boost \
  --set-env-vars PROJETO="$PROJETO"

gcloud run services describe "$SERVICO" --project "$PROJETO" --region "$REGIAO" \
  --format='value(status.url,status.latestReadyRevisionName)'
