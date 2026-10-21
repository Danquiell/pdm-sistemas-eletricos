"""Aceite de cardinalidade, pedidos reais da API e comparação independente diária."""
import argparse,collections,datetime as dt,json,math,pathlib,uuid
from zoneinfo import ZoneInfo
from google.cloud import bigquery
from jsonschema import Draft202012Validator,FormatChecker
from contrato_referencia import limpar_valor
P='pdm-sistema-eletrico-2026';HERE=pathlib.Path(__file__).resolve().parent
UF="('MA','PI','CE','RN','PB','PE','AL','SE','BA')"
FEATURES=['tipo_usina','mwh_gerado','mwh_perdido','pct_horas_restricao','mw_disponibilidade_media','pct_perda','fator_capacidade']
def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--final',action='store_true');args=p.parse_args()
    b=bigquery.Client(project=P)
    cfg=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter('run','STRING',args.run_id)])
    def q(sql):return list(b.query(sql,job_config=cfg,location='US').result())
    def scalar(sql):return next(iter(q(sql)))[0]
    base=f"`{P}.sistema_eletrico_gold.perda_diaria_usina`"
    scope=f"dia BETWEEN '2026-08-01' AND '2026-08-19' AND id_estado IN {UF}"
    expected=scalar(f'SELECT COUNT(*) FROM {base} WHERE {scope}')
    assert not q(f'SELECT id_ons,dia FROM {base} WHERE {scope} GROUP BY 1,2 HAVING COUNT(*)>1')
    assert not q(f"SELECT id_ons,mes FROM `{P}.sistema_eletrico_silver.inmet_replay_vinculos` GROUP BY 1,2 HAVING COUNT(*)>1")
    counts=[dict(r) for r in q(f'SELECT replay_run_id,COUNT(*) n FROM `{P}.sistema_eletrico_gold.v_energia_inmet_stream_diario` GROUP BY 1')]
    assert counts and all(x['n']==expected for x in counts), (expected,counts)
    assert not q(f"SELECT replay_run_id,id_ons,dia FROM `{P}.sistema_eletrico_gold.v_energia_inmet_stream_diario` GROUP BY 1,2,3 HAVING COUNT(*)>1")
    assert not q(f"SELECT * FROM `{P}.sistema_eletrico_gold.v_inmet_stream_diario` WHERE fracao_validas_temperatura>1 OR fracao_validas_vento>1 OR fracao_validas_radiacao_08_16>1 OR fracao_validas_precipitacao>1")
    scored_path=HERE/'baseline_recorte_referencia.json'
    if scored_path.exists():
        scored=json.loads(scored_path.read_text())
    else:
        scored=[dict(r) for r in q(f"""SELECT id_ons,dia,{','.join(FEATURES)},centroid_id,normalized_distance,is_anomaly
         FROM ML.DETECT_ANOMALIES(MODEL `{P}.sistema_eletrico_gold.modelo_anomalia_perda`,
          STRUCT(0.02 AS contamination),
          (SELECT id_ons,dia,{','.join(FEATURES)} FROM {base} WHERE {scope}
           AND {' AND '.join(f'{f} IS NOT NULL' for f in FEATURES)}))
         ORDER BY tipo_usina,is_anomaly DESC,dia,id_ons""")]
        scored_path.write_text(json.dumps(scored,default=str))
    groups=collections.defaultdict(list)
    for r in scored:groups[(r['tipo_usina'],r['is_anomaly'])].append(r)
    rows=[r for group in groups.values() for r in group[:5]]
    used={(r['id_ons'],str(r['dia'])) for r in rows}
    for r in scored:
        if len(rows)>=20:break
        key=(r['id_ons'],str(r['dia']))
        if key not in used:rows.append(r);used.add(key)
    request_schema=json.loads((HERE/'predict_request.schema.json').read_text())
    validator=Draft202012Validator(request_schema,format_checker=FormatChecker())
    requests=[];references=[]
    for r in rows:
        obj=dict(schema_version='1.0.1',request_id=str(uuid.uuid5(uuid.NAMESPACE_URL,f"pdm|{args.run_id}|{r['id_ons']}|{r['dia']}")),
            id_ons=r['id_ons'],dia=str(r['dia']),replay_run_id=args.run_id,features={f:r[f] for f in FEATURES})
        validator.validate(obj);requests.append(obj)
        references.append(dict(request_id=obj['request_id'],id_ons=r['id_ons'],dia=str(r['dia']),
            centroid_id=r['centroid_id'],normalized_distance=r['normalized_distance'],is_anomaly=r['is_anomaly'],contamination=0.02))
    assert len(requests)>=20 and len({r['features']['tipo_usina'] for r in requests})>=2
    (HERE/'requests_reais_api.json').write_text(json.dumps(requests,ensure_ascii=False,indent=2))
    (HERE/'referencia_bigquery_requests.json').write_text(json.dumps(references,ensure_ascii=False,indent=2))
    summary={'run_id':args.run_id,'linhas_gold_recorte':expected,'cardinalidade_por_run':counts,'n_requests_reais':len(requests),
        'tipos_requests':sorted({r['features']['tipo_usina'] for r in requests}),
        'classes_requests':sorted({r['is_anomaly'] for r in references}),
        'status_contexto':[dict(r) for r in q(f"SELECT status_contexto,COUNT(*) n FROM `{P}.sistema_eletrico_gold.v_energia_inmet_stream_diario` WHERE replay_run_id=@run GROUP BY 1")],
        'sem_vinculo':[dict(r) for r in q(f"SELECT DISTINCT id_ons,nom_usina,tipo_usina FROM `{P}.sistema_eletrico_gold.v_energia_inmet_stream_diario` WHERE replay_run_id=@run AND codigo_estacao IS NULL")],
        'cardinalidade':'APROVADA','requests':'VALIDADOS_CONTRA_SCHEMA','final':args.final}
    if args.final:
        manifest=json.loads((HERE/'manifesto.json').read_text())
        n=scalar(f'SELECT COUNT(*) FROM `{P}.sistema_eletrico_gold.v_inmet_stream_horario` WHERE replay_run_id=@run')
        assert n==manifest['n_eventos'], (n,manifest['n_eventos'])
        assert scalar(f'SELECT COUNT(*) FROM `{P}.sistema_eletrico_silver.inmet_stream_rejeitados` WHERE replay_run_id=@run')==0
        # Cálculo independente em Python, a partir de todas as linhas do snapshot.
        metrics=['temperatura_c','vento_velocidade_ms','radiacao_global_kj_m2','precipitacao_mm']
        daily=collections.defaultdict(lambda:{m:[] for m in metrics}|{'rad_dia':0,'instantes':0,'intervalos':0})
        zone=ZoneInfo('America/Sao_Paulo')
        for line in (HERE/manifest['snapshot']).read_text().splitlines():
            obj=json.loads(line);stamp=dt.datetime.fromisoformat(obj['instante_utc'].replace('Z','+00:00'))
            instant=stamp.astimezone(zone);acc=(stamp-dt.timedelta(hours=1)).astimezone(zone)
            ki=(obj['codigo_estacao'],instant.date());ka=(obj['codigo_estacao'],acc.date())
            daily[ki]['instantes']+=1;daily[ka]['intervalos']+=1
            for m,raw in obj['medicoes'].items():
                val,_=limpar_valor(m,raw)
                if val is None:continue
                daily[ki if m in metrics[:2] else ka][m].append(val)
                if m==metrics[2] and 8<=acc.hour<=16:daily[ka]['rad_dia']+=1
        observed=q(f'SELECT * FROM `{P}.sistema_eletrico_gold.v_inmet_stream_diario` WHERE replay_run_id=@run')
        exp_keys={k for k in daily if dt.date(2026,8,1)<=k[1]<=dt.date(2026,8,19)}
        assert {(r.codigo_estacao,r.dia) for r in observed}==exp_keys
        def eq(actual,values,mean=False):
            expected_value=sum(values)/(len(values) if mean else 1) if values else None
            assert (actual is None and expected_value is None) or (actual is not None and expected_value is not None and math.isclose(actual,expected_value,rel_tol=1e-9,abs_tol=1e-8)),(actual,expected_value)
        for r in observed:
            d=daily[(r.codigo_estacao,r.dia)]
            eq(r.temperatura_media_c,d[metrics[0]],True);eq(r.vento_medio_ms,d[metrics[1]],True)
            eq(r.radiacao_soma_observada_kj_m2,d[metrics[2]]);eq(r.precipitacao_soma_observada_mm,d[metrics[3]])
            assert r.n_validas_temperatura==len(d[metrics[0]]) and r.n_validas_vento==len(d[metrics[1]])
            assert r.n_validas_precipitacao==len(d[metrics[3]]) and r.n_validas_radiacao_08_16==d['rad_dia']
            assert r.fracao_validas_temperatura==len(d[metrics[0]])/24
            assert r.fracao_validas_vento==len(d[metrics[1]])/24
            assert r.fracao_validas_precipitacao==len(d[metrics[3]])/24
            assert r.fracao_validas_radiacao_08_16==d['rad_dia']/9
        summary.update(eventos_canonicos=n,comparacao_independente='APROVADA',estacao_dias_comparados=len(observed),
            atualizado_em_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    (HERE/('aceite_pessoa3_final.json' if args.final else 'aceite_pessoa3_parcial.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str))
    print(json.dumps(summary,ensure_ascii=False,default=str),flush=True)
if __name__=='__main__':main()
