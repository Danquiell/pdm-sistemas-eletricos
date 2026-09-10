CREATE OR REPLACE MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.modelo_anomalia_perda`
OPTIONS(
  model_type           = 'KMEANS',
  num_clusters         = 6,
  standardize_features = TRUE,
  kmeans_init_method   = 'KMEANS++',
  max_iterations       = 30
) AS
SELECT
  mwh_gerado,
  mwh_perdido,
  pct_perda,
  pct_horas_restricao,
  fator_capacidade,
  mw_disponibilidade_media,
  tipo_usina
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
WHERE NOT is_teste;
