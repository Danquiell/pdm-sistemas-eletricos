"""Copia do BigQuery o que a API precisa e grava em modelo_anomalia_perda.json.

Grava: média e desvio de cada número, o centro e o raio de cada grupo,
e o limiar de anomalia. Rodar de novo sempre que o modelo for treinado de novo.
Uso: python exportar_modelo.py   (precisa do comando bq com login feito)
"""
import datetime as dt
import json
import pathlib
import subprocess

PROJETO = "pdm-sistema-eletrico-2026"
MODELO = f"`{PROJETO}.sistema_eletrico_gold.modelo_anomalia_perda`"
GOLD = f"`{PROJETO}.sistema_eletrico_gold.perda_diaria_usina`"
CONTAMINATION = 0.02
NUMERICAS = ["mwh_gerado", "mwh_perdido", "pct_perda", "pct_horas_restricao",
             "fator_capacidade", "mw_disponibilidade_media"]
SAIDA = pathlib.Path(__file__).resolve().parent / "modelo_anomalia_perda.json"


def bq(sql):
    out = subprocess.run(
        ["bq", "query", f"--project_id={PROJETO}", "--use_legacy_sql=false",
         "--format=json", "--max_rows=1000", sql],
        check=True, capture_output=True, text=True).stdout
    return json.loads(out[out.index("["):])


def main():
    # média e desvio usados para padronizar
    info = {r["input"]: r for r in bq(f"SELECT * FROM ML.FEATURE_INFO(MODEL {MODELO})")}
    padronizacao = {f: {"media": float(info[f]["mean"]), "desvio": float(info[f]["stddev"])}
                    for f in NUMERICAS}

    # centro de cada grupo, já padronizado
    centroides = {}
    for r in bq(f"""SELECT centroid_id, feature, numerical_value, categorical_value
                    FROM ML.CENTROIDS(MODEL {MODELO}, STRUCT(TRUE AS standardize))"""):
        c = centroides.setdefault(int(r["centroid_id"]), {"numericas": {}, "tipo_usina": {}})
        if r["feature"] == "tipo_usina":
            c["tipo_usina"] = {x["category"]: float(x["value"]) for x in r["categorical_value"]}
        else:
            c["numericas"][r["feature"]] = float(r["numerical_value"])

    # raio de cada grupo, da última rodada do treino
    ultima = bq(f"""SELECT cluster_info FROM ML.TRAINING_INFO(MODEL {MODELO})
                    ORDER BY iteration DESC LIMIT 1""")[0]["cluster_info"]
    raio = {int(x["centroid_id"]): float(x["cluster_radius"]) for x in ultima}

    # limiar: o BigQuery marca 2% dos dias de treino; o corte fica entre
    # a menor distância marcada e a maior não marcada
    lim = bq(f"""SELECT MIN(IF(is_anomaly, normalized_distance, NULL)) menor_anomala,
                        MAX(IF(NOT is_anomaly, normalized_distance, NULL)) maior_normal,
                        COUNTIF(is_anomaly) anomalas, COUNT(*) n
                 FROM ML.DETECT_ANOMALIES(MODEL {MODELO}, STRUCT({CONTAMINATION} AS contamination),
                      (SELECT * FROM {GOLD} WHERE NOT is_teste))""")[0]

    artefato = {
        "modelo": "modelo_anomalia_perda",
        "origem": f"{PROJETO}.sistema_eletrico_gold.modelo_anomalia_perda",
        "tipo": "KMEANS",
        "contamination": CONTAMINATION,
        "exportado_em_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "features_numericas": NUMERICAS,
        "categorias_tipo_usina": ["EOLIELETRICA", "FOTOVOLTAICA"],
        "padronizacao": padronizacao,
        "centroides": {str(k): centroides[k] for k in sorted(centroides)},
        "raio_grupo": {str(k): raio[k] for k in sorted(raio)},
        "limiar": {
            "menor_distancia_anomala_treino": float(lim["menor_anomala"]),
            "maior_distancia_normal_treino": float(lim["maior_normal"]),
            "anomalas_treino": int(lim["anomalas"]),
            "dias_treino": int(lim["n"]),
        },
    }
    SAIDA.write_text(json.dumps(artefato, indent=2, ensure_ascii=False))
    print(f"gravado {SAIDA}")


if __name__ == "__main__":
    main()
