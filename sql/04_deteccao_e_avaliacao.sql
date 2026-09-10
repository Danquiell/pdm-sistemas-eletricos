SELECT
  ROUND(davies_bouldin_index, 4)  AS davies_bouldin,
  ROUND(mean_squared_distance, 4) AS distancia_quadratica_media
FROM ML.EVALUATE(MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.modelo_anomalia_perda`);

SELECT
  centroid_id,
  feature,
  ROUND(numerical_value, 2) AS valor
FROM ML.CENTROIDS(MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.modelo_anomalia_perda`)
WHERE feature IN ('mwh_perdido', 'pct_perda', 'pct_horas_restricao', 'fator_capacidade')
ORDER BY centroid_id, feature;

CREATE OR REPLACE TABLE `pdm-sistema-eletrico-2026.sistema_eletrico_gold.anomalias_detectadas`
PARTITION BY DATE_TRUNC(dia, MONTH)
CLUSTER BY anomalia, tipo_usina, id_ons
OPTIONS(description = 'Gold: dias-usina classificados pelo detector de anomalia de perda.')
AS
SELECT
  dia,
  id_ons,
  nom_usina,
  tipo_usina,
  id_estado,
  id_subsistema,
  ROUND(mwh_gerado, 1)          AS mwh_gerado,
  ROUND(mwh_perdido, 1)         AS mwh_perdido,
  ROUND(pct_perda, 1)           AS pct_perda,
  ROUND(horas_restricao, 1)     AS horas_restricao,
  ROUND(fator_capacidade, 3)    AS fator_capacidade,
  razao_dominante,

  is_anomaly                    AS anomalia,
  ROUND(normalized_distance, 4) AS distancia
FROM ML.DETECT_ANOMALIES(
  MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.modelo_anomalia_perda`,
  STRUCT(0.02 AS contamination),
  (
    SELECT *
    FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
    WHERE is_teste
  )
);

SELECT
  anomalia,
  COUNT(*)                                    AS dias,
  COUNT(DISTINCT id_ons)                      AS usinas,
  ROUND(AVG(mwh_perdido), 0)                  AS mwh_perdido_medio,
  ROUND(AVG(pct_perda), 1)                    AS pct_perda_medio,
  ROUND(AVG(horas_restricao), 1)              AS horas_restricao_media,
  ROUND(SUM(mwh_perdido) / 1000, 0)           AS gwh_perdido_total,
  ROUND(100 * SUM(mwh_perdido) / SUM(SUM(mwh_perdido)) OVER (), 1) AS pct_da_perda_total
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.anomalias_detectadas`
GROUP BY anomalia
ORDER BY anomalia DESC;

SELECT
  nom_usina,
  id_estado,
  tipo_usina,
  COUNT(*)                          AS dias_anomalos,
  ROUND(SUM(mwh_perdido) / 1000, 1) AS gwh_perdido,
  ROUND(AVG(pct_perda), 1)          AS pct_perda_medio
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.anomalias_detectadas`
WHERE anomalia
GROUP BY nom_usina, id_estado, tipo_usina
ORDER BY gwh_perdido DESC
LIMIT 15;

SELECT
  dia,
  nom_usina,
  id_estado,
  tipo_usina,
  mwh_gerado,
  mwh_perdido,
  pct_perda,
  horas_restricao,
  razao_dominante,
  distancia
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.anomalias_detectadas`
WHERE anomalia
ORDER BY distancia DESC
LIMIT 20;
