CREATE SCHEMA IF NOT EXISTS `pdm-sistema-eletrico-2026.sistema_eletrico_silver`
OPTIONS(location = 'US');

CREATE TEMP FUNCTION PARA_FLOAT(valor STRING)
AS (
  SAFE_CAST(REPLACE(NULLIF(TRIM(valor), ''), ',', '.') AS FLOAT64)
);

CREATE TEMP TABLE registros_avaliados AS
WITH tipado AS (
  SELECT
    TO_JSON_STRING(b)                                             AS registro_original,

    UPPER(NULLIF(TRIM(id_subsistema), ''))                        AS id_subsistema,
    REGEXP_REPLACE(UPPER(TRIM(nom_subsistema)), r'\s+', ' ')      AS nom_subsistema,
    UPPER(NULLIF(TRIM(id_estado), ''))                            AS id_estado,
    REGEXP_REPLACE(UPPER(TRIM(nom_estado)), r'\s+', ' ')          AS nom_estado,
    NULLIF(REGEXP_REPLACE(UPPER(TRIM(nom_usina)), r'\s+', ' '), '') AS nom_usina,
    UPPER(NULLIF(TRIM(id_ons), ''))                               AS id_ons,

    NULLIF(UPPER(NULLIF(TRIM(ceg), '')), '-')                     AS ceg,

    din_instante,

    PARA_FLOAT(val_geracao)                                       AS val_geracao,
    PARA_FLOAT(val_geracaolimitada)                               AS val_geracaolimitada,
    PARA_FLOAT(val_disponibilidade)                               AS val_disponibilidade,
    PARA_FLOAT(val_geracaoreferencia)                             AS val_geracaoreferencia,
    PARA_FLOAT(val_geracaoreferenciafinal)                        AS val_geracaoreferenciafinal,

    UPPER(NULLIF(TRIM(cod_razaorestricao), ''))                   AS cod_razaorestricao,
    UPPER(NULLIF(TRIM(cod_origemrestricao), ''))                  AS cod_origemrestricao,
    NULLIF(TRIM(dsc_restricao), '')                               AS dsc_restricao,

    NULLIF(TRIM(_origem_dataset), '')                             AS origem_dataset,
    CURRENT_TIMESTAMP()                                           AS processado_em
  FROM `pdm-sistema-eletrico-2026.sistema_eletrico.SistemaEletrico_bronze` AS b
)
SELECT
  *,
  ARRAY(
    SELECT motivo
    FROM UNNEST([
      IF(id_subsistema IS NULL OR nom_subsistema IS NULL
         OR id_estado IS NULL OR nom_estado IS NULL
         OR id_ons IS NULL OR din_instante IS NULL,
         'Campo obrigatorio ausente', NULL),

      IF(val_geracao IS NULL, 'Geracao ausente ou nao numerica', NULL),

      IF(val_geracao < 0 OR val_geracaolimitada < 0
         OR val_disponibilidade < 0 OR val_geracaoreferencia < 0
         OR val_geracaoreferenciafinal < 0,
         'Valor negativo', NULL),

      IF(val_disponibilidade   > 10000
         OR val_geracao        > 10000
         OR val_geracaoreferencia > 10000,
         'Valor fisicamente impossivel', NULL),

      IF(cod_razaorestricao IS NOT NULL
         AND cod_razaorestricao NOT IN ('REL','CNF','ENE','PAR'),
         'Razao da restricao invalida', NULL),

      IF(cod_origemrestricao IS NOT NULL
         AND cod_origemrestricao NOT IN ('LOC','SIS'),
         'Origem da restricao invalida', NULL),

      IF(CHAR_LENGTH(id_subsistema) > 2
         OR CHAR_LENGTH(id_estado) != 2
         OR CHAR_LENGTH(ceg) > 30
         OR CHAR_LENGTH(dsc_restricao) > 600,
         'Tamanho de campo invalido', NULL)
    ]) AS motivo
    WHERE motivo IS NOT NULL
  ) AS motivos_rejeicao
FROM tipado;

CREATE OR REPLACE TABLE `pdm-sistema-eletrico-2026.sistema_eletrico_silver.restricao_coff`
PARTITION BY TIMESTAMP_TRUNC(din_instante, MONTH)
CLUSTER BY origem_dataset, id_estado, cod_razaorestricao
OPTIONS(description = 'Silver: tipada, padronizada, tracos do ONS trocados por NULL. Eolica + fotovoltaica.')
AS
SELECT * EXCEPT(registro_original, motivos_rejeicao)
FROM registros_avaliados
WHERE ARRAY_LENGTH(motivos_rejeicao) = 0;

CREATE OR REPLACE TABLE `pdm-sistema-eletrico-2026.sistema_eletrico_silver.restricao_coff_rejeitados`
OPTIONS(description = 'Silver: linhas reprovadas na validacao, com registro original e motivo.')
AS
SELECT *
FROM registros_avaliados
WHERE ARRAY_LENGTH(motivos_rejeicao) > 0;

SELECT
  COUNT(*)                                    AS linhas,
  COUNTIF(val_geracao IS NULL)                AS geracao_nula,
  COUNTIF(ceg IS NULL)                        AS ceg_nulo,
  COUNT(DISTINCT id_ons)                      AS usinas,
  COUNT(DISTINCT DATE(din_instante))          AS dias,
  ROUND(100 * COUNTIF(cod_razaorestricao IS NOT NULL) / COUNT(*), 1) AS pct_restricao,
  COUNT(*) - COUNT(DISTINCT FORMAT('%s|%t', id_ons, din_instante))   AS duplicatas
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_silver.restricao_coff`;

SELECT motivo, COUNT(*) AS linhas
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_silver.restricao_coff_rejeitados`,
     UNNEST(motivos_rejeicao) AS motivo
GROUP BY motivo
ORDER BY linhas DESC;
