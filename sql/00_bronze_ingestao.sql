CREATE SCHEMA IF NOT EXISTS `pdm-sistema-eletrico-2026.sistema_eletrico`
OPTIONS(location = 'US');

DROP TABLE IF EXISTS `pdm-sistema-eletrico-2026.sistema_eletrico.SistemaEletrico_bronze`;

LOAD DATA OVERWRITE `pdm-sistema-eletrico-2026.sistema_eletrico.SistemaEletrico_bronze`
PARTITION BY TIMESTAMP_TRUNC(din_instante, MONTH)
CLUSTER BY _origem_dataset, id_ons
FROM FILES (
  format = 'PARQUET',
  uris   = ['gs://dados-ons/bronze/restricao_coff/*.parquet']
);

SELECT
  COUNT(*)                                        AS linhas,
  COUNT(DISTINCT id_ons)                          AS usinas,
  COUNT(DISTINCT _origem_dataset)                 AS conjuntos,
  MIN(din_instante)                               AS inicio,
  MAX(din_instante)                               AS fim,
  COUNTIF(_origem_dataset = 'EOLIELETRICA')       AS eolica,
  COUNTIF(_origem_dataset = 'FOTOVOLTAICA')       AS solar
FROM `pdm-sistema-eletrico-2026.sistema_eletrico.SistemaEletrico_bronze`;
