SELECT
  COUNT(*)                                  AS linhas,
  COUNT(DISTINCT id_ons)                    AS usinas,
  MIN(din_instante)                         AS inicio,
  MAX(din_instante)                         AS fim,
  COUNTIF(_origem_dataset = 'EOLIELETRICA') AS eolica,
  COUNTIF(_origem_dataset = 'FOTOVOLTAICA') AS solar
FROM `pdm-sistema-eletrico-2026.sistema_eletrico.SistemaEletrico_bronze`;

SELECT 'aprovadas' AS destino, COUNT(*) AS linhas, CAST(NULL AS STRING) AS motivos
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_silver.restricao_coff`
UNION ALL
SELECT 'quarentena', COUNT(*), STRING_AGG(DISTINCT motivo)
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_silver.restricao_coff_rejeitados`,
     UNNEST(motivos_rejeicao) AS motivo;

SELECT
  nom_usina,
  id_estado,
  tipo_usina,
  ROUND(SUM(mwh_perdido) / 1000, 1)                  AS gwh_perdido,
  ROUND(100 * SAFE_DIVIDE(SUM(mwh_perdido),
        SUM(mwh_perdido) + SUM(mwh_gerado)), 1)      AS pct_do_potencial_perdido
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
GROUP BY nom_usina, id_estado, tipo_usina
ORDER BY gwh_perdido DESC
LIMIT 10;

SELECT
  ROUND(davies_bouldin_index, 4)  AS davies_bouldin,
  ROUND(mean_squared_distance, 4) AS distancia_quadratica_media
FROM ML.EVALUATE(MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.modelo_anomalia_perda`);

SELECT
  dia,
  ROUND(mwh_gerado, 0)      AS mwh_gerado,
  ROUND(mwh_perdido, 0)     AS mwh_perdido,
  ROUND(pct_perda, 1)       AS pct_perda,
  ROUND(horas_restricao, 1) AS horas_restricao
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
WHERE nom_usina = 'CONJ. SANTA VITÓRIA DO PALMAR'
  AND dia >= DATE '2026-08-01'
ORDER BY dia;

SELECT
  dia,
  ROUND(mwh_gerado, 0)          AS mwh_gerado,
  ROUND(mwh_perdido, 0)         AS mwh_perdido,
  ROUND(pct_perda, 1)           AS pct_perda,

  is_anomaly                    AS anomalia,
  ROUND(normalized_distance, 3) AS distancia
FROM ML.DETECT_ANOMALIES(
  MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.modelo_anomalia_perda`,
  STRUCT(0.02 AS contamination),
  (
    SELECT *
    FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
    WHERE dia >= DATE '2026-08-01'
  )
)
WHERE nom_usina = 'CONJ. SANTA VITÓRIA DO PALMAR'
ORDER BY dia;

SELECT
  IF(anomalia, 'Dias anomalos', 'Dias normais')                    AS grupo,
  COUNT(*)                                                         AS dias,
  ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)                 AS pct_dos_dias,
  ROUND(SUM(mwh_perdido) / 1000, 0)                                AS gwh_perdido,
  ROUND(100 * SUM(mwh_perdido) / SUM(SUM(mwh_perdido)) OVER (), 1) AS pct_da_perda,
  ROUND(AVG(mwh_perdido), 0)                                       AS perda_media_por_dia
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.anomalias_detectadas`
GROUP BY anomalia
ORDER BY anomalia DESC;
