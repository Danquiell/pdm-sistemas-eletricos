"""Manda os dias conhecidos para o endpoint do Vertex e compara com o BigQuery.

Mostra se o endpoint devolve o grupo da detecção de anomalia ou o grupo do ML.PREDICT.
Uso: TOKEN=$(gcloud auth print-access-token) python testar_vertex.py ID_DO_ENDPOINT
"""
import json
import os
import pathlib
import sys
import urllib.request

PROJETO, REGIAO = "pdm-sistema-eletrico-2026", "us-central1"
ENDPOINT = sys.argv[1]
CASOS = json.loads((pathlib.Path(__file__).parent / "tests" / "casos_conhecidos.json").read_text())

url = (f"https://{REGIAO}-aiplatform.googleapis.com/v1/projects/{PROJETO}"
       f"/locations/{REGIAO}/endpoints/{ENDPOINT}:predict")
corpo = json.dumps({"instances": [c["features"] for c in CASOS]}).encode()
pedido = urllib.request.Request(url, data=corpo, method="POST")
pedido.add_header("Content-Type", "application/json")
pedido.add_header("Authorization", f"Bearer {os.environ['TOKEN']}")
with urllib.request.urlopen(pedido, timeout=60) as r:
    previsoes = json.loads(r.read())["predictions"]

print("exemplo de resposta do endpoint:", json.dumps(previsoes[0])[:300])
# com o raio e o limiar do modelo_anomalia_perda.json, as distâncias do endpoint viram a regra de anomalia
modelo = json.loads((pathlib.Path(__file__).parent / "modelo_anomalia_perda.json").read_text())
igual_predict = igual_anomalia = anomalia_certa = 0
for c, p in zip(CASOS, previsoes):
    grupo = p["nearest_centroid_id"][0]
    igual_predict += grupo == c["esperado"]["grupo_ml_predict"]
    igual_anomalia += grupo == c["esperado"]["centroid_id"]
    norm = {g: d / modelo["raio_grupo"][str(g)] for g, d in zip(p["centroid_ids"], p["centroid_distances"])}
    anomalo = min(norm.values()) >= modelo["limiar"]["menor_distancia_anomala_treino"]
    anomalia_certa += anomalo == c["esperado"]["is_anomaly"]
print(f"grupo do endpoint igual ao ML.PREDICT: {igual_predict} de {len(CASOS)}")
print(f"grupo do endpoint igual ao da detecção de anomalia: {igual_anomalia} de {len(CASOS)}")
print("o endpoint diz se o dia é anômalo?", any("anomal" in k.lower() for k in previsoes[0]))
print(f"anomalia certa aplicando raio e limiar às distâncias do endpoint: {anomalia_certa} de {len(CASOS)}")
