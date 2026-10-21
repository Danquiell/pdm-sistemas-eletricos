-- Contrato de destino. NAO EXECUTADO NO GCP.
-- Criar somente apos conferir IAM, objetos existentes e implementacao do grupo.
-- Nomes novos; nao altera as tabelas batch. Sem CREATE OR REPLACE nas tabelas.
CREATE TABLE IF NOT EXISTS `pdm-sistema-eletrico-2026.sistema_eletrico.inmet_stream_raw` (
 replay_run_id STRING,event_id STRING,codigo_estacao STRING,instante_utc TIMESTAMP,
 publicado_em_utc TIMESTAMP,pubsub_message_id STRING,pubsub_publish_time TIMESTAMP,
 recebido_em_utc TIMESTAMP,raw_payload STRING,contrato_version STRING
) PARTITION BY DATE(recebido_em_utc) CLUSTER BY replay_run_id,codigo_estacao
OPTIONS(description='Bronze streaming INMET; envelope e bytes JSON UTF-8. Inclui tentativas repetidas e eventos invalidos; metadados extraidos podem ser nulos.');

CREATE TABLE IF NOT EXISTS `pdm-sistema-eletrico-2026.sistema_eletrico_silver.inmet_stream_horario` (
 replay_run_id STRING,event_id STRING,delivery_id STRING,schema_version STRING,
 codigo_estacao STRING,instante_utc TIMESTAMP,inicio_intervalo_acumulados_utc TIMESTAMP,
 publicado_em_utc TIMESTAMP,pubsub_message_id STRING,pubsub_publish_time TIMESTAMP,
 processado_em_utc TIMESTAMP,medicoes_hash STRING,
 temperatura_c FLOAT64,vento_velocidade_ms FLOAT64,radiacao_global_kj_m2 FLOAT64,precipitacao_mm FLOAT64,
 flags_qualidade ARRAY<STRING>,arquivo_origem STRING,sha256_arquivo STRING,linha_origem INT64
) PARTITION BY DATE(instante_utc) CLUSTER BY replay_run_id,codigo_estacao
OPTIONS(description='Eventos tipados append; limpeza por variavel. Consumidores de negocio devem usar a view canonica, que remove reentregas e bloqueia conflitos.');

CREATE TABLE IF NOT EXISTS `pdm-sistema-eletrico-2026.sistema_eletrico_silver.inmet_stream_rejeitados` (
 replay_run_id STRING,event_id STRING,pubsub_message_id STRING,
 processado_em_utc TIMESTAMP,codigo_erro STRING,motivos ARRAY<STRING>,raw_payload STRING
) PARTITION BY DATE(processado_em_utc) CLUSTER BY replay_run_id,codigo_erro;

CREATE OR REPLACE VIEW `pdm-sistema-eletrico-2026.sistema_eletrico_gold.v_inmet_stream_horario` AS
WITH valido AS (
 SELECT replay_run_id,event_id
 FROM `pdm-sistema-eletrico-2026.sistema_eletrico_silver.inmet_stream_horario`
 GROUP BY replay_run_id,event_id
 HAVING COUNT(DISTINCT medicoes_hash)=1
)
SELECT s.* FROM `pdm-sistema-eletrico-2026.sistema_eletrico_silver.inmet_stream_horario` s
JOIN valido USING(replay_run_id,event_id)
QUALIFY ROW_NUMBER() OVER(PARTITION BY replay_run_id,event_id ORDER BY processado_em_utc,pubsub_message_id)=1;

-- Guardar esta consulta como verificacao operacional; o pipeline registra
-- os conflitos em rejeitados, e a view canonica ja os exclui por completo.
SELECT replay_run_id,event_id,COUNT(DISTINCT medicoes_hash) versoes_conflitantes
FROM `pdm-sistema-eletrico-2026.sistema_eletrico_silver.inmet_stream_horario`
GROUP BY replay_run_id,event_id HAVING COUNT(DISTINCT medicoes_hash)>1;
