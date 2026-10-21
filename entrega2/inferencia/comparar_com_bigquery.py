"""Compara a regra do detector.py com a resposta do BigQuery, dia por dia.

O CSV sai da consulta_gabarito.sql.
Uso: python comparar_com_bigquery.py bq_teste.csv
"""
import sys

import pandas as pd

from detector import Detector


def comparar(caminho, det):
    df = pd.read_csv(caminho)
    feats = det.numericas + ["tipo_usina"]
    saida = [det.avaliar(r) for r in df[feats].to_dict("records")]
    py = pd.DataFrame(saida)
    erro = (py["normalized_distance"] - df["normalized_distance"]).abs()
    ok_anom = py["is_anomaly"] == df["is_anomaly"]
    return {
        "arquivo": caminho,
        "linhas": len(df),
        "anomalas_bigquery": int(df["is_anomaly"].sum()),
        "anomalas_python": int(py["is_anomaly"].sum()),
        "is_anomaly_iguais": int(ok_anom.sum()),
        "centroid_iguais": int((py["centroid_id"] == df["centroid_id"]).sum()),
        "erro_max_distancia": float(erro.max()),
        "erro_p99_distancia": float(erro.quantile(0.99)),
        # dias em que o grupo da anomalia é diferente do grupo do ML.PREDICT
        "bq_detect_vs_predict_grupo_diferente": int((df["centroid_id"] != df["pred_centroid"]).sum()),
        "python_bruto_igual_predict": int((py["grupo_mais_proximo_bruto"] == df["pred_centroid"]).sum()),
        "divergencias": df.loc[~ok_anom, ["id_ons", "dia", "normalized_distance"]]
                          .assign(py=py.loc[~ok_anom, "normalized_distance"]).to_dict("records"),
    }


if __name__ == "__main__":
    det = Detector()
    for caminho in sys.argv[1:]:
        for k, v in comparar(caminho, det).items():
            print(f"{k:40s} {v}")
        print()
