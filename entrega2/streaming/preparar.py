"""Cria somente objetos novos, congela referências e exporta snapshot rastreável."""
import datetime as dt, hashlib, json, pathlib
from google.cloud import bigquery

P='pdm-sistema-eletrico-2026'
HERE=pathlib.Path(__file__).resolve().parent
b=bigquery.Client(project=P)
def query(sql):
    return b.query(sql,location='US').result()

for t in ('inmet_nordeste_horario','usina_estacao_mes'):
    print('SCHEMA',t,[(f.name,f.field_type) for f in b.get_table(f'{P}.sistema_eletrico_silver.{t}').schema],flush=True)
assert not list(query(f"""SELECT id_ons,mes,COUNT(*) n FROM `{P}.sistema_eletrico_silver.usina_estacao_mes`
 WHERE mes='2026-08-01' GROUP BY 1,2 HAVING n>1""")), 'CADASTRO_MENSAL_DUPLICADO'
query((HERE/'01_infra.sql').read_text())
query(f"""CREATE TABLE IF NOT EXISTS `{P}.sistema_eletrico_silver.inmet_replay_vinculos` AS
 SELECT m.*,CURRENT_TIMESTAMP() congelado_em_utc FROM `{P}.sistema_eletrico_silver.usina_estacao_mes` m
 JOIN (SELECT DISTINCT id_ons FROM `{P}.sistema_eletrico_gold.perda_diaria_usina`
 WHERE dia BETWEEN '2026-08-01' AND '2026-08-19' AND id_estado IN ('MA','PI','CE','RN','PB','PE','AL','SE','BA')) USING(id_ons)
 WHERE m.mes='2026-08-01'""")
stations=[r.codigo_estacao for r in query(f"SELECT DISTINCT codigo_estacao FROM `{P}.sistema_eletrico_silver.inmet_replay_vinculos` WHERE codigo_estacao IS NOT NULL ORDER BY 1")]
assert stations, 'MANIFESTO_VAZIO'
sql=f"""SELECT h.codigo_estacao,h.instante_utc,h.temperatura_c,h.vento_velocidade_ms,
 h.radiacao_kj_m2 AS radiacao_global_kj_m2,h.precipitacao_mm,h.arquivo_origem
 FROM `{P}.sistema_eletrico_silver.inmet_nordeste_horario` h
 WHERE h.instante_utc>='2026-08-01T03:00:00Z' AND h.instante_utc<'2026-08-20T04:00:00Z'
 AND codigo_estacao IN UNNEST(@stations) ORDER BY instante_utc,codigo_estacao"""
cfg=bigquery.QueryJobConfig(query_parameters=[bigquery.ArrayQueryParameter('stations','STRING',stations)])
rows=list(b.query(sql,job_config=cfg,location='US').result())
seen=set()
path=HERE/'snapshot_inmet_agosto2026.jsonl'
with path.open('wb') as out:
    for r in rows:
        instant=r.instante_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
        assert (r.codigo_estacao,instant) not in seen, 'DUPLICATA_NA_ORIGEM'
        seen.add((r.codigo_estacao,instant))
        line={'codigo_estacao':r.codigo_estacao,'instante_utc':instant,
              'medicoes':{k:None if r[k] is None else str(r[k]) for k in ('temperatura_c','vento_velocidade_ms','radiacao_global_kj_m2','precipitacao_mm')},
              'arquivo_historico':r.arquivo_origem}
        out.write((json.dumps(line,ensure_ascii=False,separators=(',',':'))+'\n').encode())
manifest={'schema_version':'1.0.0','project_id':P,'estacoes':stations,'n_estacoes':len(stations),
 'snapshot':path.name,'sha256_arquivo':hashlib.sha256(path.read_bytes()).hexdigest(),'n_eventos':len(rows),
 'horas_esperadas_por_estacao':457,'n_estacao_hora_esperados':len(stations)*457,
 'n_estacao_hora_ausentes':len(stations)*457-len(rows),
 'estagio':'SILVER_HISTORICA','origem':f'{P}.sistema_eletrico_silver.inmet_nordeste_horario',
 'inicio_inclusivo':'2026-08-01T03:00:00Z','fim_exclusivo':'2026-08-20T04:00:00Z',
 'n_linhas_borda_final':sum(r.instante_utc.strftime('%Y-%m-%dT%H:%M:%SZ')=='2026-08-20T03:00:00Z' for r in rows),
 'exportado_em_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
(HERE/'manifesto.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print('MANIFESTO',json.dumps(manifest),flush=True)
print('PREPARACAO_OK',flush=True)
