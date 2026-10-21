"""Referência de identidade e transformação, sem acesso ao GCP.
Dependência somente para validar o JSON Schema: jsonschema.
"""
import datetime as dt,decimal,hashlib,json,pathlib,re,uuid
HERE=pathlib.Path(__file__).resolve().parent
METRICAS=['temperatura_c','vento_velocidade_ms','radiacao_global_kj_m2','precipitacao_mm']
LIMITES={'temperatura_c':(-50,60),'vento_velocidade_ms':(0,100),'radiacao_global_kj_m2':(0,5000),'precipitacao_mm':(0,500)}
SENTINELAS={'','-','-9999','-9999.0','-9999,0','NULL','NA','NAN'}

def parse_utc(value):
    if not isinstance(value,str) or not value.endswith('Z'):raise ValueError('TIMESTAMP_SEM_UTC_Z')
    stamp=dt.datetime.fromisoformat(value[:-1]+'+00:00')
    if stamp.utcoffset()!=dt.timedelta(0):raise ValueError('TIMESTAMP_INVALIDO')
    return stamp

def identidade(codigo_estacao,instante_utc):
    instant=parse_utc(instante_utc)
    if instant.minute or instant.second or instant.microsecond:raise ValueError('INSTANTE_FORA_DA_HORA')
    if not re.fullmatch(r'A[0-9]{3}',codigo_estacao):raise ValueError('ESTACAO_INVALIDA')
    canonical=instant.strftime('%Y-%m-%dT%H:%M:%SZ')
    return str(uuid.uuid5(uuid.NAMESPACE_URL,f'INMET_AUTOMATICA|{codigo_estacao}|{canonical}|1'))

def delivery_id(run,event_id):return hashlib.sha256(f'{run}|{event_id}'.encode()).hexdigest()
def medicoes_hash(event):
    return hashlib.sha256(json.dumps(event['medicoes'],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()

def limpar_valor(campo,value):
    if value is None:return None,campo+':AUSENTE'
    value=value.strip()
    if value.upper() in SENTINELAS:return None,campo+':AUSENTE'
    if not re.fullmatch(r'[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)',value):return None,campo+':FORMATO_INVALIDO'
    try:parsed=decimal.Decimal(value.replace(',','.'))
    except decimal.InvalidOperation:return None,campo+':FORMATO_INVALIDO'
    if parsed==decimal.Decimal('-9999'):return None,campo+':AUSENTE'
    lo,hi=LIMITES[campo]
    if not parsed.is_finite() or not decimal.Decimal(lo)<=parsed<=decimal.Decimal(hi):return None,campo+':FORA_LIMITE_OPERACIONAL'
    return float(parsed),None

def validar_evento(event):
    from jsonschema import Draft202012Validator,FormatChecker
    schema=json.loads((HERE/'evento_inmet.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(event)
    if event['event_id']!=identidade(event['codigo_estacao'],event['instante_utc']):raise ValueError('EVENT_ID_DIVERGENTE')
    instante=parse_utc(event['instante_utc'])
    cfg=json.loads((HERE/'config_projeto.json').read_text(encoding='utf-8'))['replay']
    if not parse_utc(cfg['instante_utc_inicio_inclusivo'])<=instante<parse_utc(cfg['instante_utc_fim_exclusivo']):raise ValueError('FORA_RECORTE_REPLAY')
    return True

def transformar(event):
    validar_evento(event)
    result={k:event[k] for k in ['schema_version','event_id','replay_run_id','codigo_estacao','instante_utc','publicado_em_utc']}
    result['delivery_id']=delivery_id(event['replay_run_id'],event['event_id'])
    result['medicoes_hash']=medicoes_hash(event)
    result['inicio_intervalo_acumulados_utc']=(parse_utc(event['instante_utc'])-dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    result['flags_qualidade']=[]
    for campo,value in event['medicoes'].items():
        cleaned,flag=limpar_valor(campo,value);result[campo]=cleaned
        if flag:result['flags_qualidade'].append(flag)
    if all(result[c] is None for c in METRICAS):result['flags_qualidade'].append('SEM_MEDICAO_VALIDA')
    return result
