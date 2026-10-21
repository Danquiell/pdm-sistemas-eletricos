"""Testa a API já publicada (Cloud Run ou local) com os dias conhecidos e com dados errados.

Usa só a biblioteca padrão do Python, então roda em qualquer lugar.
Uso: python testar_servico.py URL
Se o serviço for privado, passe o token na variável TOKEN:
  TOKEN=$(gcloud auth print-identity-token) python testar_servico.py URL
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

URL = sys.argv[1].rstrip("/")
TOKEN = os.environ.get("TOKEN")
CASOS = json.loads((pathlib.Path(__file__).parent / "tests" / "casos_conhecidos.json").read_text())


def chamar(caminho, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    pedido = urllib.request.Request(URL + caminho, data=dados, method="POST" if dados else "GET")
    pedido.add_header("Content-Type", "application/json")
    if TOKEN:
        pedido.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(pedido, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        texto = e.read()
        try:
            return e.code, json.loads(texto or b"{}")
        except ValueError:
            return e.code, {}


falhas = 0

status, saude = chamar("/health")
print(f"health: {status} {saude.get('status')}")
falhas += status != 200 or saude.get("status") != "ok"

# dias reais: a resposta tem que ser igual à do BigQuery
iguais = 0
for c in CASOS:
    status, r = chamar("/predict", {"id_ons": c["id_ons"], "dia": c["dia"], "features": c["features"]})
    p = r.get("predicao", {})
    ok = (status == 200 and p.get("is_anomaly") == c["esperado"]["is_anomaly"]
          and p.get("centroid_id") == c["esperado"]["centroid_id"]
          and abs(p.get("normalized_distance", -1) - c["esperado"]["normalized_distance"]) < 1e-5)
    iguais += ok
    if not ok:
        print(f"  diferente: {c['id_ons']} {c['dia']} -> {status} {p}")
print(f"dias conhecidos iguais ao BigQuery: {iguais} de {len(CASOS)}")
falhas += iguais != len(CASOS)

# dados errados: a API tem que recusar com 422
base = CASOS[0]["features"]
errados = {
    "numero negativo": dict(base, mwh_gerado=-5),
    "texto no lugar de numero": dict(base, mwh_perdido="5214"),
    "campo faltando": {k: v for k, v in base.items() if k != "fator_capacidade"},
    "tipo de usina invalido": dict(base, tipo_usina="HIDRELETRICA"),
}
for nome, f in errados.items():
    status, _ = chamar("/predict", {"features": f})
    print(f"{nome}: {status}")
    falhas += status != 422

print("RESULTADO:", "tudo certo" if not falhas else f"{falhas} falha(s)")
sys.exit(1 if falhas else 0)
