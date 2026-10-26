#!/usr/bin/env bash
# Publica a API de anomalias no Cloud Run sem tirar a versão atual do ar.
# 1) sobe uma revisão nova com a tag "teste", que ainda não recebe tráfego;
# 2) roda testar_servico.py contra o endereço da tag;
# 3) só se o teste passar, manda 100% do tráfego para a revisão nova e testa de novo.
# Se o teste da tag falhar, o script para e a versão antiga continua respondendo.
# Rodar de dentro de entrega2/inferencia, no Cloud Shell ou com o gcloud logado.
set -euo pipefail

PROJETO=pdm-sistema-eletrico-2026
REGIAO=us-central1
SERVICO=api-anomalia-perda
CONTA=api-inferencia@${PROJETO}.iam.gserviceaccount.com

gcloud run deploy "$SERVICO" --source . --project "$PROJETO" --region "$REGIAO" \
  --service-account "$CONTA" --allow-unauthenticated \
  --cpu 1 --memory 512Mi --concurrency 40 --timeout 30 \
  --min-instances 0 --max-instances 2 --cpu-boost \
  --no-traffic --tag teste

URL=$(gcloud run services describe "$SERVICO" --project "$PROJETO" --region "$REGIAO" \
  --format='value(status.url)')
URL_TESTE=$(gcloud run services describe "$SERVICO" --project "$PROJETO" --region "$REGIAO" \
  --format='value(status.traffic[].url)' | tr ';' '\n' | grep '//teste---')

python testar_servico.py "$URL_TESTE"

gcloud run services update-traffic "$SERVICO" --project "$PROJETO" --region "$REGIAO" --to-latest
gcloud run services update-traffic "$SERVICO" --project "$PROJETO" --region "$REGIAO" --remove-tags teste
python testar_servico.py "$URL"
