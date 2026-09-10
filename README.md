# Detector de perda por restrição de geração — dados do ONS

Pipeline Medallion no BigQuery e detecção de anomalia com BigQuery ML, sobre os dados
abertos de restrição de geração (constrained-off) de usinas eólicas e fotovoltaicas.

Projeto GCP: `pdm-sistema-eletrico-2026`
Bucket: `gs://dados-ons/bronze/restricao_coff/` — 64 arquivos Parquet, 138 MB
Fonte: conjuntos `restricao_coff_eolica_tm` e `restricao_coff_fotovoltaica_tm` do ONS
Período: 01/10/2023 a 19/08/2026 — 10.670.928 leituras de 30 minutos, 265 usinas

## Ordem de execução

| Arquivo | Camada | Resultado |
|---|---|---|
| `00_preparar_e_subir.py` | local | harmoniza os Parquet e envia ao Cloud Storage |
| `sql/00_bronze_ingestao.sql` | GCS para Bronze | `sistema_eletrico.SistemaEletrico_bronze` — 10.670.928 linhas |
| `sql/01_silver.sql` | Bronze para Silver | `restricao_coff` (10.670.905) e `restricao_coff_rejeitados` (23) |
| `sql/02_gold_perda_diaria.sql` | Silver para Gold | `perda_diaria_usina` — 222.309 linhas |
| `sql/03_modelo_anomalia.sql` | modelo | `modelo_anomalia_perda` — K-Means, 6 grupos |
| `sql/04_deteccao_e_avaliacao.sql` | Gold | `anomalias_detectadas` — 39.822 linhas |
| `sql/06_escolha_do_k.sql` | avaliação | compara k = 4, 6, 8, 10 e 12 |

`sql/05_demo_apresentacao.sql` contém as sete consultas de leitura usadas na demonstração.
Não cria nem altera nada.

## Camadas

**Bronze** — cópia dos 64 Parquet sem transformação. Os campos numéricos entram como texto.

**Silver** — tipagem, padronização de texto, o traço que o ONS usa no campo `ceg` vira nulo,
e validação. As 23 linhas reprovadas vão para uma tabela de quarentena com o registro
original em JSON e o motivo da rejeição.

**Gold** — agrega as 48 leituras de cada dia numa linha por usina e calcula a energia que
a usina foi obrigada a não gerar: `SUM(val_geracaoreferencia - val_geracao) * 0,5`, somente
nas leituras com restrição declarada.

## Modelo

- K-Means, não supervisionado, consumido por `ML.DETECT_ANOMALIES`
- Treino: 182.487 dias-usina anteriores a 2026-03-01 (82%)
- Teste: 39.822 dias-usina de 2026-03-01 em diante (18%), divisão por data
- Colunas: `mwh_gerado`, `mwh_perdido`, `pct_perda`, `pct_horas_restricao`,
  `fator_capacidade`, `mw_disponibilidade_media`, `tipo_usina`
- Saída: `is_anomaly` e `normalized_distance`

O número de grupos foi comparado em k = 4, 6, 8, 10 e 12 pelo índice Davies-Bouldin.
Os valores ficaram entre 1,28 e 1,39, sem mínimo claro. Ficamos com 6 porque cada grupo
tem leitura operacional e o menor deles ainda reúne 7.731 dias-usina.

O K-Means parte de centros aleatórios, então o resultado varia entre treinos. O modelo
publicado é o de melhor concentração entre as execuções realizadas.

## Resultado

492 dias-usina marcados, 1,2% do período de teste, concentrando 7,4% de toda a energia
perdida. Perda média de 2.688 MWh contra 421 MWh nos dias normais.

## Limites

1. A perda é medida em MWh. A base do ONS não traz preço.
2. Não é o indicador oficial de constrained-off do ONS, que usa a referência final e regras
   próprias de apuração. É a energia não gerada em relação à referência, com a fórmula acima.
3. Não é previsão. O modelo classifica dias que já aconteceram.
