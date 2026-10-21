"""Replay finito, ordenado e retomável; novo ciclo exige outro run explícito."""
import argparse,collections,datetime as dt,hashlib,json,pathlib,time
from google.cloud import pubsub_v1
from contrato_referencia import identidade,delivery_id
HERE=pathlib.Path(__file__).resolve().parent

def evento(row,run,manifest,line):
    stamp=dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
    return dict(schema_version='1.0.0',event_id=identidade(row['codigo_estacao'],row['instante_utc']),
        replay_run_id=run,source='INMET_AUTOMATICA',modo='REPLAY_HISTORICO',
        codigo_estacao=row['codigo_estacao'],instante_utc=row['instante_utc'],publicado_em_utc=stamp,
        origem=dict(arquivo=manifest['snapshot'],sha256_arquivo=manifest['sha256_arquivo'],linha=line,estagio='SILVER_HISTORICA'),
        medicoes=row['medicoes'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--rate',type=float,default=20)
    p.add_argument('--limit',type=int);a=p.parse_args()
    assert a.rate>0
    import re
    assert re.fullmatch(r'[a-z0-9][a-z0-9_-]{2,63}',a.run_id)
    manifest=json.loads((HERE/'manifesto.json').read_text())
    snapshot=HERE/manifest['snapshot']
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest()==manifest['sha256_arquivo']
    checkpoint=HERE/('checkpoint_'+a.run_id+'.json')
    state=json.loads(checkpoint.read_text()) if checkpoint.exists() else {'ultima_linha':0,'sha256_arquivo':manifest['sha256_arquivo']}
    assert state['sha256_arquivo']==manifest['sha256_arquivo'], 'RUN_NAO_PODE_TROCAR_SNAPSHOT'
    publisher=pubsub_v1.PublisherClient()
    topic=publisher.topic_path(manifest['project_id'],'inmet-horario-stream')
    start=time.monotonic(); sent=0; pending=collections.deque()
    def confirm(item):
        line,payload,attrs,future=item
        for attempt in range(8):
            try:
                future.result(timeout=60);break
            except Exception:
                if attempt==7:raise
                time.sleep(min(2**attempt,30))
                future=publisher.publish(topic,payload,**attrs)
        state.update(ultima_linha=line)
        tmp=checkpoint.with_suffix('.tmp');tmp.write_text(json.dumps(state));tmp.replace(checkpoint)
    with snapshot.open(encoding='utf-8') as f:
        for line,text in enumerate(f,1):
            if line<=state['ultima_linha']:continue
            row=json.loads(text);e=evento(row,a.run_id,manifest,line)
            attrs={k:e[k] for k in ('event_id','replay_run_id','schema_version')}
            attrs.update(delivery_id=delivery_id(a.run_id,e['event_id']),published_at=e['publicado_em_utc'])
            # Janela assíncrona: confirmação ordenada antes do checkpoint.
            payload=json.dumps(e,ensure_ascii=False,separators=(',',':')).encode()
            pending.append((line,payload,attrs,publisher.publish(topic,payload,**attrs)))
            if len(pending)>=100:confirm(pending.popleft())
            sent+=1
            if sent%100==0:print(json.dumps({'run':a.run_id,'publicados_nesta_execucao':sent,'ultima_linha':line,'total':manifest['n_eventos']}),flush=True)
            if a.limit and sent>=a.limit:break
            time.sleep(max(0,start+sent/a.rate-time.monotonic()))
    while pending:confirm(pending.popleft())
    print(json.dumps({'run':a.run_id,'publicados_nesta_execucao':sent,'ultima_linha':state['ultima_linha'],'fim':True}),flush=True)
if __name__=='__main__':main()
