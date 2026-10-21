"""Escolhe dias reais do CSV do BigQuery para os testes da API.

Cada caso guarda os 7 números do dia e a resposta do BigQuery.
Uso: python gerar_casos_conhecidos.py bq_teste.csv
"""
import json
import pathlib
import sys

import pandas as pd

from detector import Detector

FEATS = ["tipo_usina", "mwh_gerado", "mwh_perdido", "pct_perda", "pct_horas_restricao",
         "fator_capacidade", "mw_disponibilidade_media"]


def main(caminho):
    df = pd.read_csv(caminho)
    limiar = Detector().limiar
    df["folga"] = df["normalized_distance"] - limiar
    escolhas = {
        # Santa Vitória do Palmar: só os dias 15 a 18 são anômalos
        "santa_vitoria_ago26": df[(df.id_ons == "CJU_RSSVPA") & df.dia.between("2026-08-10", "2026-08-19")],
        "mais_distantes": df.nlargest(3, "normalized_distance"),
        "logo_acima_do_limiar": df[df.folga >= 0].nsmallest(3, "folga"),
        "logo_abaixo_do_limiar": df[df.folga < 0].nlargest(3, "folga"),
        "grupo_detect_difere_do_predict": df[df.centroid_id != df.pred_centroid].head(3),
        "fotovoltaica_anomala": df[(df.tipo_usina == "FOTOVOLTAICA") & df.is_anomaly].head(2),
        "fator_acima_de_1": df[(df.fator_capacidade > 1.05) & df.is_anomaly].head(2),
    }
    casos = []
    for motivo, sub in escolhas.items():
        for r in sub.to_dict("records"):
            casos.append({
                "motivo": motivo, "id_ons": r["id_ons"], "dia": r["dia"],
                "features": {f: r[f] for f in FEATS},
                "esperado": {"centroid_id": int(r["centroid_id"]),
                             "normalized_distance": float(r["normalized_distance"]),
                             "is_anomaly": bool(r["is_anomaly"]),
                             "grupo_ml_predict": int(r["pred_centroid"])},
            })
    saida = pathlib.Path(__file__).resolve().parent / "tests" / "casos_conhecidos.json"
    saida.parent.mkdir(exist_ok=True)
    saida.write_text(json.dumps(casos, indent=2, ensure_ascii=False))
    print(f"{len(casos)} casos em {saida}")


if __name__ == "__main__":
    main(sys.argv[1])
