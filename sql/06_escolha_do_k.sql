CREATE OR REPLACE MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k4`
OPTIONS(model_type='KMEANS', num_clusters=4, standardize_features=TRUE,
        kmeans_init_method='KMEANS++', max_iterations=30) AS
SELECT mwh_gerado, mwh_perdido, pct_perda, pct_horas_restricao,
       fator_capacidade, mw_disponibilidade_media, tipo_usina
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
WHERE NOT is_teste;

CREATE OR REPLACE MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k8`
OPTIONS(model_type='KMEANS', num_clusters=8, standardize_features=TRUE,
        kmeans_init_method='KMEANS++', max_iterations=30) AS
SELECT mwh_gerado, mwh_perdido, pct_perda, pct_horas_restricao,
       fator_capacidade, mw_disponibilidade_media, tipo_usina
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
WHERE NOT is_teste;

CREATE OR REPLACE MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k10`
OPTIONS(model_type='KMEANS', num_clusters=10, standardize_features=TRUE,
        kmeans_init_method='KMEANS++', max_iterations=30) AS
SELECT mwh_gerado, mwh_perdido, pct_perda, pct_horas_restricao,
       fator_capacidade, mw_disponibilidade_media, tipo_usina
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
WHERE NOT is_teste;

CREATE OR REPLACE MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k12`
OPTIONS(model_type='KMEANS', num_clusters=12, standardize_features=TRUE,
        kmeans_init_method='KMEANS++', max_iterations=30) AS
SELECT mwh_gerado, mwh_perdido, pct_perda, pct_horas_restricao,
       fator_capacidade, mw_disponibilidade_media, tipo_usina
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
WHERE NOT is_teste;

SELECT  4 AS k, ROUND(davies_bouldin_index, 4) AS davies_bouldin,
        ROUND(mean_squared_distance, 4) AS dist_quadratica_media
FROM ML.EVALUATE(MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k4`)
UNION ALL
SELECT  6, ROUND(davies_bouldin_index, 4), ROUND(mean_squared_distance, 4)
FROM ML.EVALUATE(MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.modelo_anomalia_perda`)
UNION ALL
SELECT  8, ROUND(davies_bouldin_index, 4), ROUND(mean_squared_distance, 4)
FROM ML.EVALUATE(MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k8`)
UNION ALL
SELECT 10, ROUND(davies_bouldin_index, 4), ROUND(mean_squared_distance, 4)
FROM ML.EVALUATE(MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k10`)
UNION ALL
SELECT 12, ROUND(davies_bouldin_index, 4), ROUND(mean_squared_distance, 4)
FROM ML.EVALUATE(MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k12`)
ORDER BY davies_bouldin;

DROP MODEL IF EXISTS `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k4`;
DROP MODEL IF EXISTS `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k8`;
DROP MODEL IF EXISTS `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k10`;
DROP MODEL IF EXISTS `pdm-sistema-eletrico-2026.sistema_eletrico_gold.teste_k12`;
