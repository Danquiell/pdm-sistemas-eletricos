"""Testes da API: dias reais com a resposta do BigQuery e dados errados de propósito."""
import copy
import json
import pathlib

import pytest
from fastapi.testclient import TestClient

import app as api

CASOS = json.loads((pathlib.Path(__file__).parent / "casos_conhecidos.json").read_text())
client = TestClient(api.app)
VALIDO = {"features": CASOS[0]["features"]}


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: f"{c['motivo']}-{c['id_ons']}-{c['dia']}")
def test_caso_conhecido_igual_ao_bigquery(caso):
    r = client.post("/predict", json={"id_ons": caso["id_ons"], "dia": caso["dia"],
                                      "features": caso["features"]})
    assert r.status_code == 200, r.text
    p = r.json()["predicao"]
    assert p["is_anomaly"] == caso["esperado"]["is_anomaly"]
    assert p["centroid_id"] == caso["esperado"]["centroid_id"]
    assert p["normalized_distance"] == pytest.approx(caso["esperado"]["normalized_distance"], abs=1e-6)


def test_santa_vitoria_marca_exatamente_15_a_18():
    marcados = sorted(c["dia"] for c in CASOS if c["motivo"] == "santa_vitoria_ago26"
                      and client.post("/predict", json={"features": c["features"]}).json()["predicao"]["is_anomaly"])
    assert marcados == ["2026-08-15", "2026-08-16", "2026-08-17", "2026-08-18"]


def test_grupo_nao_e_anomalia():
    # o grupo 4 tem dias normais e anômalos: só o grupo não diz se o dia é anômalo
    respostas = [client.post("/predict", json={"features": c["features"]}).json()["predicao"]
                 for c in CASOS]
    assert {p["is_anomaly"] for p in respostas if p["centroid_id"] == 4} == {True, False}


def test_igualdade_no_limiar_e_anomalia():
    det = api.detector
    caso = next(c for c in CASOS if c["motivo"] == "logo_acima_do_limiar")
    distancia = det.avaliar(caso["features"])["normalized_distance"]
    limiar_original = det.limiar
    try:
        det.limiar = distancia
        assert det.avaliar(caso["features"])["is_anomaly"] is True
        det.limiar = distancia + 1e-12
        assert det.avaliar(caso["features"])["is_anomaly"] is False
    finally:
        det.limiar = limiar_original


def test_limiar_fica_entre_maior_normal_e_menor_anomalo_do_treino():
    a = json.loads((pathlib.Path(api.__file__).parent / "modelo_anomalia_perda.json").read_text())
    assert a["limiar"]["maior_distancia_normal_treino"] < api.detector.limiar
    assert a["limiar"]["anomalas_treino"] / a["limiar"]["dias_treino"] == pytest.approx(0.02, abs=5e-4)


def test_rota_do_contrato_v1_e_pedido_completo():
    pedido = {"schema_version": "1.0.1", "request_id": "3f1c2a4e-0000-4000-8000-000000000001",
              "id_ons": "CJU_RSSVPA", "dia": "2026-08-16", "replay_run_id": "demo_20261018_01",
              "features": CASOS[0]["features"]}
    r = client.post("/v1/predict", json=pedido)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["request_id"] == pedido["request_id"] and corpo["dia"] == "2026-08-16"
    assert corpo["respondido_em_utc"].endswith("Z")


def test_healthz():
    assert client.get("/healthz").json()["modelo_carregado"] is True
    assert client.get("/health").json()["status"] == "ok"  # rota usada no Cloud Run


def _com(**mudancas):
    corpo = copy.deepcopy(VALIDO)
    for campo, valor in mudancas.items():
        if valor is _REMOVER:
            corpo["features"].pop(campo)
        else:
            corpo["features"][campo] = valor
    return corpo


_REMOVER = object()


@pytest.mark.parametrize("mudanca,campo", [
    ({"mwh_gerado": -1.0}, "mwh_gerado"),
    ({"mwh_gerado": 1e308}, "mwh_gerado"),             # acima do teto da Silver
    ({"mw_disponibilidade_media": 10_000.5}, "mw_disponibilidade_media"),
    ({"pct_horas_restricao": 101.0}, "pct_horas_restricao"),
    ({"fator_capacidade": 2.5}, "fator_capacidade"),
    ({"tipo_usina": "HIDRELETRICA"}, "tipo_usina"),
    ({"tipo_usina": "eolieletrica"}, "tipo_usina"),
    ({"mwh_perdido": "5214"}, "mwh_perdido"),          # texto não vira número
    ({"mwh_perdido": True}, "mwh_perdido"),            # booleano não vira número
    ({"mwh_perdido": None}, "mwh_perdido"),
    ({"fator_capacidade": _REMOVER}, "fator_capacidade"),
    ({"temperatura_c": 25.0}, "temperatura_c"),        # clima não é feature do modelo
])
def test_feature_invalida_da_422(mudanca, campo):
    r = client.post("/predict", json=_com(**mudanca))
    assert r.status_code == 422, r.text
    assert any(campo in d["campo"] for d in r.json()["detalhes"])


def test_pct_na_escala_0_a_1_e_recusado():
    f = {"tipo_usina": "EOLIELETRICA", "mwh_gerado": 300.0, "mwh_perdido": 100.0,
         "pct_perda": 0.25, "pct_horas_restricao": 50.0, "fator_capacidade": 0.3,
         "mw_disponibilidade_media": 50.0}
    r = client.post("/predict", json={"features": f})
    assert r.status_code == 422 and "pct_perda" in r.text
    f["pct_perda"] = 25.0
    assert client.post("/predict", json={"features": f}).status_code == 200


def test_pct_na_escala_0_a_1_com_perda_pequena_e_recusado():
    f = {"tipo_usina": "EOLIELETRICA", "mwh_gerado": 10000.0, "mwh_perdido": 4.0,
         "pct_perda": 0.0004, "pct_horas_restricao": 2.08, "fator_capacidade": 0.5,
         "mw_disponibilidade_media": 800.0}
    assert client.post("/predict", json={"features": f}).status_code == 422
    f["pct_perda"] = 0.04
    assert client.post("/predict", json={"features": f}).status_code == 200


def test_inteiro_em_json_e_aceito():
    f = dict(VALIDO["features"], mwh_gerado=0)
    assert client.post("/predict", json={"features": f}).status_code == 200


def test_corpo_grande_da_413():
    corpo = json.dumps({"features": VALIDO["features"], "id_ons": "x" * 20_000})
    r = client.post("/predict", content=corpo, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_nan_e_infinito_recusados():
    # NaN e Infinity passam como JSON, então a API precisa recusar
    for valor in ("NaN", "Infinity"):
        corpo = json.dumps(VALIDO).replace('"mwh_gerado": 0.0', f'"mwh_gerado": {valor}')
        assert valor in corpo
        r = client.post("/predict", content=corpo, headers={"content-type": "application/json"})
        assert r.status_code == 422, (valor, r.text)


def test_json_malformado_da_400():
    r = client.post("/predict", content=b"{features: ", headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json()["erro"] == "JSON_MALFORMADO"


F = VALIDO["features"]


@pytest.mark.parametrize("corpo,campo", [
    ({}, "features"),
    ({"features": {}}, "features.tipo_usina"),
    ({"features": F, "extra": 1}, "extra"),
    ({"features": F, "dia": "2026-13-01"}, "dia"),
    ({"features": F, "dia": 0}, "dia"),
    ({"features": F, "dia": "2026-08-16T00:00:00"}, "dia"),
    ({"features": F, "request_id": ""}, "request_id"),
    ({"features": F, "replay_run_id": "Run Com Espaco"}, "replay_run_id"),
])
def test_corpo_fora_do_contrato_da_422(corpo, campo):
    r = client.post("/predict", json=corpo)
    assert r.status_code == 422, r.text
    assert campo in [d["campo"] for d in r.json()["detalhes"]], r.text


def test_corpo_que_nao_e_objeto_da_422():
    assert client.post("/predict", json=[]).status_code == 422


def test_modelo_ausente_da_503(monkeypatch):
    monkeypatch.setattr(api, "detector", None)
    assert client.post("/predict", json=VALIDO).status_code == 503
    assert client.get("/healthz").json()["status"] == "sem_modelo"


def test_artefato_ausente_nao_derruba_o_processo(tmp_path):
    # roda a API numa pasta sem o arquivo do modelo
    import shutil
    import subprocess
    import sys
    pasta = pathlib.Path(api.__file__).parent
    for nome in ("app.py", "detector.py", "contexto.py"):
        shutil.copy(pasta / nome, tmp_path / nome)
    codigo = ("from fastapi.testclient import TestClient; import app; c = TestClient(app.app); "
              "print(c.post('/predict', json={}).status_code, "
              "c.post('/predict', json=" + repr(VALIDO) + ").status_code, c.get('/healthz').json()['status'])")
    saida = subprocess.run([sys.executable, "-c", codigo], cwd=tmp_path, capture_output=True, text=True)
    assert saida.stdout.split() == ["422", "503", "sem_modelo"], saida.stderr
