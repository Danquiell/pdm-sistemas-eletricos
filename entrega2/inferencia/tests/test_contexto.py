"""Testes do clima do dia (contexto_inmet) e do formato da resposta pelo contrato."""
import json
import pathlib

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

import app as api
from contexto import ContextoInmet
from conftest import view_falsa

CASOS = json.loads((pathlib.Path(__file__).parent / "casos_conhecidos.json").read_text())
CONTRATO = pathlib.Path(__file__).resolve().parents[2] / "streaming" / "predict_response.schema.json"
client = TestClient(api.app)
# CONJ. CAJU no dia 17/08/2026, linha real da Gold; o BigQuery marca como anômalo
CAJU = {"id_ons": "CJU_RNCAJ1", "dia": "2026-08-17", "features": {
    "tipo_usina": "EOLIELETRICA", "mwh_gerado": 2341.861, "mwh_perdido": 10108.501,
    "pct_perda": 81.19, "pct_horas_restricao": 100.0, "fator_capacidade": 0.1423,
    "mw_disponibilidade_media": 685.8}}


def validar_contrato(corpo):
    esquema = json.loads(CONTRATO.read_text(encoding="utf-8"))
    Draft202012Validator(esquema, format_checker=FormatChecker()).validate(corpo)


def test_dia_do_nordeste_traz_o_clima():
    r = client.post("/predict", json=CAJU)
    assert r.status_code == 200, r.text
    corpo = r.json()
    c = corpo["contexto_inmet"]
    assert c["status"] == "APTO_PARA_CONTEXTO" and c["codigo_estacao"] == "A372"
    assert round(c["temperatura_media_c"], 1) == 28.0 and round(c["vento_medio_ms"], 1) == 2.9
    assert c["usado_no_modelo"] is False and c["atualizado_em_utc"] == "2026-10-18T21:46:55Z"
    assert corpo["replay_run_id"] == "demo_20261018_01"  # execução oficial quando o pedido não diz
    # anomalias_detectadas no BigQuery: anomalia = true, distancia = 3.8348
    assert corpo["predicao"]["is_anomaly"] is True
    assert round(corpo["predicao"]["normalized_distance"], 4) == 3.8348
    validar_contrato(corpo)


def test_clima_nao_muda_a_previsao(monkeypatch):
    com = client.post("/predict", json=CAJU).json()["predicao"]
    monkeypatch.setattr(api, "contexto", ContextoInmet(consultar=lambda e: {}))
    sem = client.post("/predict", json=CAJU).json()["predicao"]
    assert com == sem


def test_usina_fora_do_nordeste_fica_fora_do_recorte():
    caso = CASOS[0]  # Santa Vitória do Palmar, RS
    corpo = client.post("/predict", json={"id_ons": caso["id_ons"], "dia": caso["dia"],
                                          "features": caso["features"]}).json()
    assert corpo["contexto_inmet"]["status"] == "FORA_DO_RECORTE"
    assert corpo["contexto_inmet"]["temperatura_media_c"] is None
    validar_contrato(corpo)


def test_pedido_sem_identificacao():
    corpo = client.post("/predict", json={"features": CAJU["features"]}).json()
    assert corpo["contexto_inmet"]["status"] == "SEM_IDENTIFICACAO"
    assert corpo["replay_run_id"] is None and corpo["id_ons"] is None
    validar_contrato(corpo)


def test_outra_execucao_e_buscada_pelo_nome():
    corpo = client.post("/predict", json=dict(CAJU, replay_run_id="validacao_20261018_1")).json()
    assert corpo["replay_run_id"] == "validacao_20261018_1"
    assert corpo["contexto_inmet"]["status"] == "FORA_DO_RECORTE"


def test_bigquery_fora_do_ar_nao_derruba_a_previsao(monkeypatch):
    def quebrado(execucao):
        raise RuntimeError("sem acesso")
    monkeypatch.setattr(api, "contexto", ContextoInmet(consultar=quebrado))
    r = client.post("/predict", json=CAJU)
    assert r.status_code == 200
    assert r.json()["contexto_inmet"]["status"] == "INDISPONIVEL"
    assert r.json()["predicao"]["is_anomaly"] is True
    validar_contrato(r.json())


def test_bigquery_e_consultado_uma_vez_por_execucao():
    chamadas = []
    ctx = ContextoInmet(consultar=lambda e: chamadas.append(e) or view_falsa(e))
    for _ in range(5):
        ctx.buscar("CJU_RNCAJ1", "2026-08-17", "demo_20261018_01")
    assert chamadas == ["demo_20261018_01"]


def test_depois_de_falha_espera_antes_de_tentar_de_novo():
    chamadas = []

    def quebrado(execucao):
        chamadas.append(execucao)
        raise RuntimeError("sem acesso")
    ctx = ContextoInmet(consultar=quebrado)
    for _ in range(5):
        assert ctx.buscar("CJU_RNCAJ1", "2026-08-17", "demo_20261018_01")["status"] == "INDISPONIVEL"
    assert len(chamadas) == 1


@pytest.mark.parametrize("caso", CASOS[:5], ids=lambda c: f"{c['id_ons']}-{c['dia']}")
def test_resposta_segue_o_contrato(caso):
    pedido = {"schema_version": "1.1.0", "request_id": "3f1c2a4e-0000-4000-8000-000000000001",
              "id_ons": caso["id_ons"], "dia": caso["dia"], "replay_run_id": "demo_20261018_01",
              "features": caso["features"]}
    corpo = client.post("/v1/predict", json=pedido).json()
    validar_contrato(corpo)
    assert corpo["request_id"] == pedido["request_id"]


def test_request_id_e_gerado_quando_falta():
    corpo = client.post("/predict", json=CAJU).json()
    assert len(corpo["request_id"]) == 36
    validar_contrato(corpo)
