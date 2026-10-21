"""Consumidor INMET autenticado pelo IAM do Cloud Run, com raw e quarentena."""
import base64,datetime as dt,json,logging,pathlib,threading
from google.cloud import bigquery
from contrato_referencia import transformar,delivery_id,parse_utc
P='pdm-sistema-eletrico-2026'
HERE=pathlib.Path(__file__).resolve().parent
manifest=json.loads((HERE/'manifesto.json').read_text())
allowed=set(manifest['estacoes'])
b=bigquery.Client(project=P)
guard=threading.Lock(); initialized=False; hashes={}; locks={}

def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def safe_time(value):
    try:return parse_utc(value).isoformat()
    except (ValueError,TypeError,AttributeError):return None
def insert(table,rows,ids=None):
    if not rows:return
    errors=b.insert_rows_json(f'{P}.{table}',rows,row_ids=ids)
    if errors:raise RuntimeError(str(errors))
def init():
    global initialized
    with guard:
        if initialized:return
        for r in b.query(f'SELECT replay_run_id,event_id,ARRAY_AGG(DISTINCT medicoes_hash) hashes FROM `{P}.sistema_eletrico_silver.inmet_stream_horario` GROUP BY 1,2',location='US').result():
            hashes[(r.replay_run_id,r.event_id)]=set(r.hashes)
        initialized=True
def reject(e,mid,text,code,reasons):
    insert('sistema_eletrico_silver.inmet_stream_rejeitados',[dict(
        replay_run_id=e.get('replay_run_id') if isinstance(e.get('replay_run_id'),str) else None,
        event_id=e.get('event_id') if isinstance(e.get('event_id'),str) else None,
        pubsub_message_id=mid,processado_em_utc=now(),codigo_erro=code,motivos=reasons,raw_payload=text)],
        [f'{mid}:{code}'] if mid else None)

def consume(envelope):
    message=envelope.get('message') or {}
    mid=message.get('messageId') or message.get('message_id')
    published=message.get('publishTime') or message.get('publish_time')
    attrs=message.get('attributes') or {}
    encoded=message.get('data','');e={};decode_error=None
    try:
        text=base64.b64decode(encoded,validate=True).decode('utf-8')
        e=json.loads(text)
        if not isinstance(e,dict):e={};decode_error='JSON_NAO_OBJETO'
    except Exception:
        text='BASE64:'+str(encoded);decode_error='JSON_OU_UTF8_INVALIDO'
    # Raw append conserva tentativas inclusive quando persistência posterior falha.
    def string_value(k):return e.get(k) if isinstance(e.get(k),str) else None
    insert('sistema_eletrico.inmet_stream_raw',[dict(
        replay_run_id=string_value('replay_run_id'),event_id=string_value('event_id'),
        codigo_estacao=string_value('codigo_estacao'),instante_utc=safe_time(e.get('instante_utc')),
        publicado_em_utc=safe_time(e.get('publicado_em_utc')),pubsub_message_id=mid,
        pubsub_publish_time=safe_time(published),recebido_em_utc=now(),raw_payload=text,contrato_version=string_value('schema_version'))])
    if decode_error:
        reject(e,mid,text,decode_error,[decode_error]);return
    try:
        row=transformar(e)
        if e['codigo_estacao'] not in allowed:raise ValueError('ESTACAO_FORA_MANIFESTO')
        if e['origem']['arquivo']!=manifest['snapshot'] or e['origem']['sha256_arquivo']!=manifest['sha256_arquivo']:
            raise ValueError('SNAPSHOT_FORA_MANIFESTO')
        if not mid or not safe_time(published):raise ValueError('METADADOS_PUBSUB_AUSENTES')
        expected=dict(event_id=e['event_id'],replay_run_id=e['replay_run_id'],schema_version=e['schema_version'],
            delivery_id=delivery_id(e['replay_run_id'],e['event_id']),published_at=e['publicado_em_utc'])
        if any(attrs.get(k)!=v for k,v in expected.items()):raise ValueError('ATRIBUTOS_DIVERGENTES')
    except Exception as exc:
        reject(e,mid,text,'CONTRATO_INVALIDO',[str(exc)[:2000]]);return
    row.update(pubsub_message_id=mid,pubsub_publish_time=safe_time(published),processado_em_utc=now(),
        arquivo_origem=e['origem']['arquivo'],sha256_arquivo=e['origem']['sha256_arquivo'],linha_origem=e['origem']['linha'])
    init()
    key=(e['replay_run_id'],e['event_id'])
    with guard:keylock=locks.setdefault(key,threading.Lock())
    # Um worker / uma instância no deploy: cache restaurado do banco após restart.
    # A exclusão semântica também está na view, independentemente do insertId.
    with keylock:
        insert('sistema_eletrico_silver.inmet_stream_horario',[row],[mid])
        hashes.setdefault(key,set()).add(row['medicoes_hash'])
        if len(hashes[key])>1:
            reject(e,mid,text,'DUPLICATE_CONFLICT',['Mesmo run/event_id possui medições divergentes; chave excluída da Gold canônica.'])

def register(app):
    from flask import request
    @app.post('/inmet/pubsub')
    def inmet_pubsub():
        try:
            consume(request.get_json(silent=True) or {})
            return '',204
        except Exception:
            logging.exception('INMET_PERSISTENCIA_FALHOU')
            return 'persistencia indisponivel; Pub/Sub deve reenviar',503
    @app.get('/inmet/healthz')
    def inmet_health():
        return dict(servico='inmet-streaming-pdm',contrato='1.0.0',estacoes=len(allowed))
