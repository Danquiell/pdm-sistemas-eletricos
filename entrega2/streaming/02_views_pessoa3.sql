-- Somente entradas INMET canônicas. Dias locais e acumulados separados.
CREATE OR REPLACE VIEW `pdm-sistema-eletrico-2026.sistema_eletrico_gold.v_inmet_stream_diario` AS
WITH h AS (
 SELECT * FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.v_inmet_stream_horario`
), i AS (
 SELECT replay_run_id,codigo_estacao,DATE(instante_utc,'America/Sao_Paulo') dia,
 AVG(temperatura_c) temperatura_media_c,AVG(vento_velocidade_ms) vento_medio_ms,
 COUNT(temperatura_c) n_validas_temperatura,COUNT(vento_velocidade_ms) n_validas_vento,
 COUNT(*) n_observacoes_instantes,MAX(processado_em_utc) atualizado_i
 FROM h GROUP BY 1,2,3
), a AS (
 SELECT replay_run_id,codigo_estacao,DATE(inicio_intervalo_acumulados_utc,'America/Sao_Paulo') dia,
 SUM(radiacao_global_kj_m2) radiacao_soma_observada_kj_m2,SUM(precipitacao_mm) precipitacao_soma_observada_mm,
 COUNTIF(radiacao_global_kj_m2 IS NOT NULL AND EXTRACT(HOUR FROM DATETIME(inicio_intervalo_acumulados_utc,'America/Sao_Paulo')) BETWEEN 8 AND 16) n_validas_radiacao_08_16,
 COUNT(precipitacao_mm) n_validas_precipitacao,COUNT(*) n_intervalos_acumulados,
 MAX(processado_em_utc) atualizado_a
 FROM h GROUP BY 1,2,3
)
SELECT replay_run_id,codigo_estacao,dia,temperatura_media_c,vento_medio_ms,
 radiacao_soma_observada_kj_m2,precipitacao_soma_observada_mm,
 COALESCE(n_validas_temperatura,0) n_validas_temperatura,
 COALESCE(n_validas_vento,0) n_validas_vento,
 COALESCE(n_validas_radiacao_08_16,0) n_validas_radiacao_08_16,
 COALESCE(n_validas_precipitacao,0) n_validas_precipitacao,
 COALESCE(n_observacoes_instantes,0) n_observacoes_instantes,
 COALESCE(n_intervalos_acumulados,0) n_intervalos_acumulados,
 COALESCE(n_validas_temperatura,0)/24.0 fracao_validas_temperatura,
 COALESCE(n_validas_vento,0)/24.0 fracao_validas_vento,
 COALESCE(n_validas_radiacao_08_16,0)/9.0 fracao_validas_radiacao_08_16,
 COALESCE(n_validas_precipitacao,0)/24.0 fracao_validas_precipitacao,
 'BRT_08_16_V1' regra_completude,
 codigo_estacao IN ('A369','A349','A421','A425','A437') radiacao_sensor_suspeito_relatorio,
 GREATEST(COALESCE(atualizado_i,TIMESTAMP '1970-01-01'),COALESCE(atualizado_a,TIMESTAMP '1970-01-01')) atualizado_em_utc
FROM i FULL OUTER JOIN a USING(replay_run_id,codigo_estacao,dia)
WHERE dia BETWEEN '2026-08-01' AND '2026-08-19';

CREATE OR REPLACE VIEW `pdm-sistema-eletrico-2026.sistema_eletrico_gold.v_energia_inmet_stream_diario` AS
WITH runs AS (
 SELECT DISTINCT replay_run_id FROM `pdm-sistema-eletrico-2026.sistema_eletrico_silver.inmet_stream_horario`
), energia AS (
 SELECT * FROM `pdm-sistema-eletrico-2026.sistema_eletrico_gold.perda_diaria_usina`
 WHERE dia BETWEEN '2026-08-01' AND '2026-08-19'
 AND id_estado IN ('MA','PI','CE','RN','PB','PE','AL','SE','BA')
)
SELECT r.replay_run_id,g.*,v.codigo_estacao,v.distancia_km,
 v.fonte fonte_cadastro,v.congelado_em_utc vinculo_congelado_em_utc,
 d.* EXCEPT(replay_run_id,codigo_estacao,dia),FALSE clima_usado_no_modelo,
 CASE WHEN v.codigo_estacao IS NULL THEN 'SEM_VINCULO'
 WHEN d.replay_run_id IS NULL THEN 'AGUARDANDO_STREAM'
 WHEN (v.fonte='EOLICA' AND d.fracao_validas_vento>=0.8)
 OR (v.fonte='FOTOVOLTAICA' AND d.fracao_validas_radiacao_08_16>=0.8 AND d.fracao_validas_temperatura>=0.8)
 THEN 'APTO_PARA_CONTEXTO' ELSE 'PARCIAL' END status_contexto
FROM energia g CROSS JOIN runs r
LEFT JOIN `pdm-sistema-eletrico-2026.sistema_eletrico_silver.inmet_replay_vinculos` v
 ON g.id_ons=v.id_ons AND DATE_TRUNC(g.dia,MONTH)=v.mes
LEFT JOIN `pdm-sistema-eletrico-2026.sistema_eletrico_gold.v_inmet_stream_diario` d
 ON r.replay_run_id=d.replay_run_id AND v.codigo_estacao=d.codigo_estacao AND g.dia=d.dia;
