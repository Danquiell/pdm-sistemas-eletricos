"""Regra de anomalia do modelo K-Means, a mesma do ML.DETECT_ANOMALIES do BigQuery.

Passos:
  1. padroniza cada número: (valor - média do treino) / desvio do treino;
  2. tipo_usina vira duas colunas de 0 ou 1;
  3. calcula a distância do dia até o centro de cada grupo e divide pelo raio do grupo;
  4. o grupo do dia é o de menor resultado (normalized_distance);
  5. o dia é anômalo se normalized_distance >= limiar.
"""
import json
import math
import pathlib

# O arquivo do modelo fica na mesma pasta deste código.
ARTEFATO = pathlib.Path(__file__).resolve().parent / "modelo_anomalia_perda.json"


class Detector:
    def __init__(self, caminho=ARTEFATO):
        a = json.loads(pathlib.Path(caminho).read_text(encoding="utf-8"))
        self.versao = a["exportado_em_utc"]
        self.contamination = a["contamination"]
        self.numericas = a["features_numericas"]
        self.categorias = a["categorias_tipo_usina"]
        self.media = [a["padronizacao"][f]["media"] for f in self.numericas]
        self.desvio = [a["padronizacao"][f]["desvio"] for f in self.numericas]
        self.grupos = []  # (número do grupo, centro, raio)
        for gid, c in a["centroides"].items():
            vetor = [c["numericas"][f] for f in self.numericas]
            vetor += [c["tipo_usina"].get(cat, 0.0) for cat in self.categorias]
            self.grupos.append((int(gid), vetor, a["raio_grupo"][gid]))
        self.limiar = a["limiar"]["menor_distancia_anomala_treino"]

    def vetor(self, features):
        x = [(features[f] - m) / s for f, m, s in zip(self.numericas, self.media, self.desvio)]
        return x + [1.0 if features["tipo_usina"] == cat else 0.0 for cat in self.categorias]

    def avaliar(self, features):
        x = self.vetor(features)
        distancias = {gid: math.dist(x, c) for gid, c, _ in self.grupos}
        normalizadas = {gid: distancias[gid] / raio for gid, _, raio in self.grupos}
        grupo = min(normalizadas, key=normalizadas.get)
        return {
            "centroid_id": grupo,
            "normalized_distance": normalizadas[grupo],
            "is_anomaly": normalizadas[grupo] >= self.limiar,
            "limiar": self.limiar,
            # grupo pela distância sem dividir pelo raio, o que o ML.PREDICT devolve
            "grupo_mais_proximo_bruto": min(distancias, key=distancias.get),
        }
