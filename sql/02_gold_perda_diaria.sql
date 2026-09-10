CREATE SCHEMA IF NOT EXISTS `pdm-sistema-eletrico-2026.sistema_eletrico_gold`
OPTIONS(location = 'US');

CREATE OR REPLACE TABLE `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
PARTITION BY DATE_TRUNC(dia, MONTH)
CLUSTER BY is_teste, tipo_usina, id_ons
OPTIONS(description = 'Gold: perda de geracao por restricao, agregada por usina e dia.')
AS
WITH diario AS (
  SELECT
    id_ons,
    DATE(din_instante)                       AS dia,

    ANY_VALUE(nom_usina)                     AS nom_usina,
    ANY_VALUE(id_estado)                     AS id_estado,
    ANY_VALUE(id_subsistema)                 AS id_subsistema,
    ANY_VALUE(origem_dataset)                AS tipo_usina,

    COUNT(*)                                 AS leituras,

    ROUND(SUM(val_geracao) * 0.5, 3)         AS mwh_gerado,
    ROUND(SUM(val_disponibilidade) * 0.5, 3) AS mwh_disponivel,
    ROUND(SUM(IF(cod_razaorestricao IS NOT NULL,
                 GREATEST(val_geracaoreferencia - val_geracao, 0),
                 0)) * 0.5, 3)               AS mwh_perdido,

    ROUND(COUNTIF(cod_razaorestricao IS NOT NULL) * 0.5, 2) AS horas_restricao,
    COUNTIF(cod_razaorestricao = 'ENE')      AS n_ene,
    COUNTIF(cod_razaorestricao = 'CNF')      AS n_cnf,
    COUNTIF(cod_razaorestricao = 'REL')      AS n_rel,

    ROUND(MAX(val_geracao), 3)               AS mw_pico_geracao,
    ROUND(AVG(val_disponibilidade), 3)       AS mw_disponibilidade_media
  FROM `pdm-sistema-eletrico-2026.sistema_eletrico_silver.restricao_coff`
  WHERE val_geracao           IS NOT NULL
    AND val_disponibilidade   IS NOT NULL
    AND val_geracaoreferencia IS NOT NULL
  GROUP BY id_ons, dia
)
SELECT
  * EXCEPT(n_ene, n_cnf, n_rel),

  IFNULL(ROUND(100 * SAFE_DIVIDE(mwh_perdido, mwh_perdido + mwh_gerado), 3), 0) AS pct_perda,

  IFNULL(LEAST(ROUND(SAFE_DIVIDE(mwh_gerado, mwh_disponivel), 4), 2.0), 0) AS fator_capacidade,

  ROUND(100 * horas_restricao / 24, 2)                               AS pct_horas_restricao,

  CASE
    WHEN n_ene >= n_cnf AND n_ene >= n_rel AND n_ene > 0 THEN 'ENE'
    WHEN n_cnf >= n_rel AND n_cnf > 0                    THEN 'CNF'
    WHEN n_rel > 0                                       THEN 'REL'
    ELSE 'SEM RESTRICAO'
  END                                                                AS razao_dominante,

  dia >= DATE '2026-03-01'                                           AS is_teste
FROM diario;

SELECT
  COUNT(*)                         AS linhas,
  COUNT(DISTINCT id_ons)           AS usinas,
  COUNT(DISTINCT dia)              AS dias,
  COUNTIF(leituras != 48)          AS dias_incompletos,
  COUNTIF(NOT is_teste)            AS treino,
  COUNTIF(is_teste)                AS teste,
  ROUND(SUM(mwh_perdido) / 1e6, 2) AS twh_perdido,
  ROUND(SUM(mwh_gerado)  / 1e6, 2) AS twh_gerado
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`;

SELECT
  nom_usina,
  id_estado,
  tipo_usina,
  ROUND(SUM(mwh_perdido) / 1000, 1)                         AS gwh_perdido,
  ROUND(SUM(mwh_gerado)  / 1000, 1)                         AS gwh_gerado,
  ROUND(100 * SAFE_DIVIDE(SUM(mwh_perdido),
             SUM(mwh_perdido) + SUM(mwh_gerado)), 1)        AS pct_perda,
  ROUND(AVG(pct_horas_restricao), 1)                        AS pct_medio_do_dia_restrito
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
GROUP BY nom_usina, id_estado, tipo_usina
ORDER BY gwh_perdido DESC
LIMIT 10;
