# API de anomalias de perda (Pessoa 4)

API que recebe os números de um dia de uma usina e diz se aquele dia é anômalo, com a mesma
resposta do modelo `sistema_eletrico_gold.modelo_anomalia_perda` no BigQuery.

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `app.py` | A API: recebe o pedido, confere os dados e responde |
| `detector.py` | A regra que acha o grupo do dia e diz se ele é anômalo |
| `modelo_anomalia_perda.json` | O modelo copiado do BigQuery (médias, centros, raios e limiar) |
| `requirements.txt` | Bibliotecas da API |
| `requirements-teste.txt` | Bibliotecas dos testes e das comparações |
| `tests/` | 61 testes automáticos |
| `Dockerfile` | Receita da imagem da API para o Cloud Run |
| `testar_servico.py` | Testa a API já publicada |
| `testar_vertex.py` | Testa o endpoint do Vertex AI |
| `consulta_gabarito.sql` | Consulta que baixa a resposta do BigQuery para os dias de teste |
| `comparar_com_bigquery.py` | Compara a regra com o BigQuery, dia por dia |
| `comparar_api_completo.py` | Manda cada dia pela API e compara com o BigQuery |
| `exportar_modelo.py` | Gera o `modelo_anomalia_perda.json` a partir do BigQuery |
| `gerar_casos_conhecidos.py` | Escolhe os dias reais usados nos testes |

## O modelo

K-Means com 6 grupos, treinado no BigQuery com 182.487 dias-usina anteriores a 2026-03-01.
As anomalias saem do `ML.DETECT_ANOMALIES` com `contamination = 0.02`.

Os 7 dados de entrada vêm prontos da Gold `perda_diaria_usina`:

| Campo | O que é |
|---|---|
| `mwh_gerado` | energia gerada no dia (MWh) |
| `mwh_perdido` | energia perdida por restrição no dia (MWh) |
| `pct_perda` | perda em % do total, de 0 a 100 |
| `pct_horas_restricao` | % das horas do dia com restrição, de 0 a 100 |
| `fator_capacidade` | geração dividida pela disponibilidade, de 0 a 2 |
| `mw_disponibilidade_media` | disponibilidade média declarada (MW) |
| `tipo_usina` | `EOLIELETRICA` ou `FOTOVOLTAICA` |

## A regra de anomalia

1. Cada número é padronizado com a média e o desvio do treino. `tipo_usina` vira duas
   colunas de 0 ou 1.
2. Calcula a distância do dia até o centro de cada grupo e divide pelo raio do grupo.
3. O grupo do dia é o de menor resultado. Esse resultado é a `normalized_distance`.
4. O dia é anômalo se `normalized_distance >= 1,6521077`, valor que marca 2% dos dias de treino.

Por causa do passo 2, o grupo da anomalia é diferente do grupo do `ML.PREDICT` em 9.376 dos
39.822 dias de teste (23,5%). O grupo sozinho também não diz se o dia é anômalo: os 6 grupos
têm dias normais e anômalos. Por isso a API devolve o grupo, a distância e o `is_anomaly`.

## A API

```
POST /predict     (também /v1/predict)
GET  /health       (também /healthz; no Cloud Run só /health funciona)
GET  /docs        página de teste no navegador
```

Exemplo (Santa Vitória do Palmar, 16/08/2026, linha real da Gold):

```json
{"features": {"tipo_usina": "EOLIELETRICA", "mwh_gerado": 0.0, "mwh_perdido": 11575.616,
  "pct_perda": 100.0, "pct_horas_restricao": 100.0, "fator_capacidade": 0.0,
  "mw_disponibilidade_media": 408.33}}
```

Resposta esperada: `centroid_id` 4, `normalized_distance` 4.557155, `is_anomaly` true.

Os campos `schema_version`, `request_id`, `id_ons`, `dia` e `replay_run_id` são opcionais
e voltam na resposta.

| Código | Quando |
|---|---|
| 200 | deu certo |
| 400 | o corpo não é JSON |
| 413 | corpo maior que 16 KB |
| 422 | campo faltando ou a mais, texto no lugar de número, valor fora da faixa, NaN, data inválida, ou `pct_perda` que não bate com as energias |
| 503 | o arquivo do modelo não carregou (`/health` mostra `sem_modelo`) |

## Como testar

Python 3.11 ou mais novo (testado com 3.12).

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-teste.txt
pytest tests                       # 61 passed
uvicorn app:app --port 8000        # abrir http://localhost:8000/docs
```

Comparação completa com o BigQuery (precisa de acesso ao projeto; o Cloud Shell já tem `bq`):

```
bq query --project_id=pdm-sistema-eletrico-2026 --nouse_legacy_sql --format=csv \
   --max_rows=300000 "$(cat consulta_gabarito.sql)" > bq_teste.csv
python comparar_com_bigquery.py bq_teste.csv
python comparar_api_completo.py bq_teste.csv
```

Para os dias de treino, trocar `WHERE is_teste` por `WHERE NOT is_teste` na consulta.

## Resultados

| Teste | Resultado |
|---|---|
| Regra contra o BigQuery, 39.822 dias de teste | 39.822 iguais (rodado também no Cloud Shell em 21/10/2026) |
| Regra contra o BigQuery, 182.487 dias de treino | 182.487 iguais |
| Os 222.309 dias (teste e treino) pela API | todas as respostas 200 e iguais ao BigQuery |
| `pytest tests` | 61 passaram, no computador e no Cloud Shell |
| Os 39.822 dias de teste pela API publicada no Cloud Run (`api-anomalia-perda`) | todas as respostas iguais ao BigQuery (21/10/2026) |
| Código estragado de propósito (limiar 1% mais alto; sem dividir pelo raio) | 5 e 27 testes falharam, ou seja, os testes pegam o erro |

## Limites

- O BigQuery não mostra o limiar exato. Pelos dados ele fica entre 1,6520149 e 1,6521077.
  Nenhum dia real caiu nessa faixa, mas um dia futuro pode cair e sair diferente do BigQuery.
- `pct_perda` mandado de 0 a 1 em vez de 0 a 100 só é recusado quando a perda passa de 0,005%.
- `dia` é conferido como data válida, mas não contra o período da Gold.
- Se o modelo for treinado de novo, rodar `exportar_modelo.py` e repetir os testes.

## Para o Docker e o Cloud Run

- O `Dockerfile` da pasta já foi testado: a imagem leva só `app.py`, `detector.py`,
  `modelo_anomalia_perda.json` e `requirements.txt`.
- Publicar: `gcloud run deploy NOME --source . --region us-central1 --min-instances 0 --max-instances 1`.
- Testar o serviço publicado (26 dias reais e 4 entradas erradas):
  `TOKEN=$(gcloud auth print-identity-token) python testar_servico.py URL_DO_SERVICO`.
  Resultado esperado: `RESULTADO: tudo certo`.
- No Cloud Run o `/healthz` na raiz é reservado e não chega na API: use `/health`.
- Para o Vertex AI Model Registry, o arquivo a registrar é o `modelo_anomalia_perda.json`.
  Um endpoint Vertex com o modelo do `EXPORT MODEL` devolve o grupo do `ML.PREDICT` e não
  diz se o dia é anômalo.
