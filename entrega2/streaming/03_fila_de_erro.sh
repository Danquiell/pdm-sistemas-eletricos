#!/usr/bin/env bash
# Fila de erro (dead-letter) para a assinatura do clima.
# Sem ela, uma mensagem que o Cloud Run recusa sempre (resposta 5xx) fica sendo reenviada
# e some depois de 7 dias, sem rastro. Com ela, depois de 5 tentativas a mensagem vai para
# o tópico inmet-horario-stream-dlq e fica guardada na assinatura inmet-horario-stream-dlq-guarda.
# Rodar uma vez, no Cloud Shell ou com o gcloud logado. Pode rodar de novo sem estragar nada.
set -euo pipefail

PROJETO=pdm-sistema-eletrico-2026
ASSINATURA=inmet-horario-processamento
DLQ=inmet-horario-stream-dlq
NUMERO=$(gcloud projects describe "$PROJETO" --format='value(projectNumber)')
AGENTE="serviceAccount:service-${NUMERO}@gcp-sa-pubsub.iam.gserviceaccount.com"

gcloud pubsub topics describe "$DLQ" --project "$PROJETO" >/dev/null 2>&1 \
  || gcloud pubsub topics create "$DLQ" --project "$PROJETO"
gcloud pubsub subscriptions describe "${DLQ}-guarda" --project "$PROJETO" >/dev/null 2>&1 \
  || gcloud pubsub subscriptions create "${DLQ}-guarda" --topic "$DLQ" \
       --message-retention-duration 7d --project "$PROJETO"

# o próprio Pub/Sub precisa poder publicar na fila de erro e confirmar na assinatura original
gcloud pubsub topics add-iam-policy-binding "$DLQ" --project "$PROJETO" \
  --member "$AGENTE" --role roles/pubsub.publisher >/dev/null
gcloud pubsub subscriptions add-iam-policy-binding "$ASSINATURA" --project "$PROJETO" \
  --member "$AGENTE" --role roles/pubsub.subscriber >/dev/null

gcloud pubsub subscriptions update "$ASSINATURA" --project "$PROJETO" \
  --dead-letter-topic "$DLQ" --max-delivery-attempts 5

gcloud pubsub subscriptions describe "$ASSINATURA" --project "$PROJETO" \
  --format='value(deadLetterPolicy.deadLetterTopic,deadLetterPolicy.maxDeliveryAttempts)'
