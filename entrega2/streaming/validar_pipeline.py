"""Aceite real via Pub/Sub: fixtures de qualidade ficam só em runs validacao_*.
Não usar esses runs nos pedidos de demonstração/predição.
"""
import copy,datetime as dt,json,pathlib,time,uuid
from google.cloud import bigquery,pubsub_v1
from contrato_referencia import delivery_id
from produtor import evento
HERE=pathlib.Path(__file__).resolve().parent
P='pdm-sistema-eletrico-2026'

def main():
    manifest=json.loads((HERE/'manifesto.json').read_text())
    rows=[json.loads(x) for x in (HERE/manifest['snapshot']).read_text().splitlines()[:5]]
    suffix=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')
    run='validacao_'+suffix;publisher=pubsub_v1.PublisherClient();b=bigquery.Client(project=P)
    topic=publisher.topic_path(P,'inmet-horario-stream')
    def send(e):
        attrs={k:e[k] for k in ('event_id','replay_run_id','schema_version')}
        attrs.update(delivery_id=delivery_id(e['replay_run_id'],e['event_id']),published_at=e['publicado_em_utc'])
        return publisher.publish(topic,json.dumps(e).encode(),**attrs).result(timeout=60)
    real=evento(rows[0],run,manifest,1)
    ids=[send(real),send(real)] # republicação: messageIds distintos, identidade semântica igual
    same_event_other_run=copy.deepcopy(real);same_event_other_run['replay_run_id']=run+'_ciclo2'
    send(same_event_other_run)
    conflict=evento(rows[1],run,manifest,2);send(conflict)
    changed=copy.deepcopy(conflict);changed['medicoes']['temperatura_c']='0' if conflict['medicoes']['temperatura_c']!='0' else '1'
    send(changed)
    quality=evento(rows[2],run,manifest,3)
    quality['medicoes']=dict(temperatura_c='25,5',vento_velocidade_ms='0',radiacao_global_kj_m2='9000',precipitacao_mm='NA')
    send(quality)
    nulls=evento(rows[3],run,manifest,4);nulls['medicoes']={k:None for k in nulls['medicoes']};send(nulls)
    invalid=evento(rows[4],run,manifest,5);invalid['event_id']=str(uuid.uuid4());send(invalid)
    bad_id=publisher.publish(topic,b'{json quebrado').result(timeout=60)
    config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter('run','STRING',run)])
    sql=f"""SELECT
     (SELECT COUNT(*) FROM `{P}.sistema_eletrico.inmet_stream_raw` WHERE replay_run_id=@run) raw,
     (SELECT COUNT(*) FROM `{P}.sistema_eletrico_silver.inmet_stream_horario` WHERE replay_run_id=@run) silver,
     (SELECT COUNT(*) FROM `{P}.sistema_eletrico_gold.v_inmet_stream_horario` WHERE replay_run_id=@run) canonicas,
     (SELECT COUNT(*) FROM `{P}.sistema_eletrico_silver.inmet_stream_rejeitados` WHERE replay_run_id=@run AND codigo_erro='DUPLICATE_CONFLICT') conflitos,
     (SELECT COUNT(*) FROM `{P}.sistema_eletrico_silver.inmet_stream_rejeitados` WHERE replay_run_id=@run AND codigo_erro='CONTRATO_INVALIDO') invalidos,
     (SELECT COUNT(*) FROM `{P}.sistema_eletrico_gold.v_inmet_stream_horario` WHERE replay_run_id=CONCAT(@run,'_ciclo2')) outro_run"""
    deadline=time.monotonic()+240
    while True:
        result=dict(next(iter(b.query(sql,job_config=config,location='US').result())))
        if result['raw']>=7 and result['silver']>=6 and result['canonicas']==3 and result['conflitos']>=1 and result['invalidos']>=1 and result['outro_run']==1:break
        if time.monotonic()>deadline:raise AssertionError(result)
        time.sleep(5)
    query=f"SELECT * FROM `{P}.sistema_eletrico_gold.v_inmet_stream_horario` WHERE replay_run_id=@run"
    cleaned={r.event_id:r for r in b.query(query,job_config=config,location='US').result()}
    q=cleaned[quality['event_id']]
    assert q.temperatura_c==25.5 and q.vento_velocidade_ms==0 and q.radiacao_global_kj_m2 is None and q.precipitacao_mm is None
    assert 'SEM_MEDICAO_VALIDA' in cleaned[nulls['event_id']].flags_qualidade
    assert conflict['event_id'] not in cleaned
    assert cleaned[real['event_id']].pubsub_publish_time.year==2026
    invalid_json=list(b.query(f"SELECT codigo_erro FROM `{P}.sistema_eletrico_silver.inmet_stream_rejeitados` WHERE pubsub_message_id='{bad_id}'",location='US').result())
    assert invalid_json and invalid_json[0].codigo_erro=='JSON_OU_UTF8_INVALIDO'
    result.update(run_id=run,teste='APROVADO',republicacao_message_ids=ids,json_invalido_message_id=bad_id)
    (HERE/'aceite_pipeline.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
if __name__=='__main__':main()
