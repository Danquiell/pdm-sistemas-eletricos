"""Nos testes a API não acessa o BigQuery: o clima vem de uma tabela pequena em memória."""
import datetime as dt

import pytest

import app as api
from contexto import ContextoInmet

# linha real da view v_energia_inmet_stream_diario (CONJ. CAJU, RN, 17/08/2026)
LINHA_CAJU = {
    "id_ons": "CJU_RNCAJ1", "dia": dt.date(2026, 8, 17), "status_contexto": "APTO_PARA_CONTEXTO",
    "atualizado_em_utc": dt.datetime(2026, 10, 18, 21, 46, 55, tzinfo=dt.timezone.utc),
    "codigo_estacao": "A372", "distancia_km": 68.87116160485829,
    "temperatura_media_c": 27.995833333333334, "vento_medio_ms": 2.9458333333333333,
    "radiacao_soma_observada_kj_m2": 17638.899999999998, "precipitacao_soma_observada_mm": 0.0,
    "fracao_validas_temperatura": 1.0, "fracao_validas_vento": 1.0,
    "fracao_validas_radiacao_08_16": 1.0, "fracao_validas_precipitacao": 1.0,
}


def view_falsa(execucao):
    if execucao != "demo_20261018_01":
        return {}
    return {(LINHA_CAJU["id_ons"], LINHA_CAJU["dia"].isoformat()): LINHA_CAJU}


@pytest.fixture(autouse=True)
def clima_em_memoria(monkeypatch):
    monkeypatch.setattr(api, "contexto", ContextoInmet(consultar=view_falsa))
