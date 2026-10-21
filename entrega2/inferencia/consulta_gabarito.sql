/* Gabarito do BigQuery para os dias de teste: resposta do ML.DETECT_ANOMALIES e do ML.PREDICT.
   Para os dias de treino, trocar as duas ocorrências de "WHERE is_teste" por "WHERE NOT is_teste".
   Este comentário não usa "--" porque o bq trataria o texto como opção de linha de comando. */
WITH d AS (
  SELECT id_ons, dia, mwh_gerado, mwh_perdido, pct_perda, pct_horas_restricao,
         fator_capacidade, mw_disponibilidade_media, tipo_usina,
         centroid_id, normalized_distance, is_anomaly
  FROM ML.DETECT_ANOMALIES(MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.modelo_anomalia_perda`,
       STRUCT(0.02 AS contamination),
       (SELECT * FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina` WHERE is_teste))),
p AS (
  SELECT id_ons, dia, CENTROID_ID AS pred_centroid
  FROM ML.PREDICT(MODEL `pdm-sistema-eletrico-2026.sistema_eletrico_gold.modelo_anomalia_perda`,
       (SELECT * FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina` WHERE is_teste)))
SELECT d.*, p.pred_centroid FROM d JOIN p USING (id_ons, dia)
