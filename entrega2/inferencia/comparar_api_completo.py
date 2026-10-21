"""Manda cada dia do CSV pela API e compara a resposta com a do BigQuery.

O CSV sai da consulta_gabarito.sql.
Uso: python comparar_api_completo.py bq_teste.csv
"""
import logging
import sys

import pandas as pd
from fastapi.testclient import TestClient

from app import app

FEATS = ["tipo_usina", "mwh_gerado", "mwh_perdido", "pct_perda", "pct_horas_restricao",
         "fator_capacidade", "mw_disponibilidade_media"]

logging.getLogger("httpx").setLevel(logging.WARNING)  # sem uma linha de log por pedido
client = TestClient(app)
for caminho in sys.argv[1:]:
    df = pd.read_csv(caminho)
    status, anom, grupo, erro = {}, 0, 0, 0.0
    for r in df.to_dict("records"):
        resp = client.post("/predict", json={"features": {f: r[f] for f in FEATS}})
        status[resp.status_code] = status.get(resp.status_code, 0) + 1
        if resp.status_code != 200:
            continue
        p = resp.json()["predicao"]
        anom += p["is_anomaly"] == r["is_anomaly"]
        grupo += p["centroid_id"] == r["centroid_id"]
        erro = max(erro, abs(p["normalized_distance"] - r["normalized_distance"]))
    print(f"{caminho}\n  linhas={len(df)} status={status} is_anomaly_iguais={anom} "
          f"grupo_igual={grupo} erro_max_distancia={erro:.2e}")
