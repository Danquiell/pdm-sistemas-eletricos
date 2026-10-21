"""Pipeline de streaming: Pub/Sub (push) -> limpeza e enriquecimento -> BigQuery.

O Pub/Sub entrega cada mensagem do tópico `aula-pdm-sistema-eletrico` com um POST em /pubsub.
Para cada leitura do ONS o serviço:
  1. valida e converte os tipos (as mesmas regras da Silver do lote);
  2. enriquece com a fonte da usina e a estação INMET do mês (tabelas do lote no BigQuery);
  3. calcula o corte da leitura (mw_cortado) e a latência desde a publicação;
  4. grava em `restricao_coff_stream`, ou em `restricao_coff_stream_rejeitados` com o motivo.

Respostas: 2xx confirma a mensagem (inclusive as rejeitadas, que já foram registradas);
5xx faz o Pub/Sub tentar de novo e, depois de 5 tentativas, mandar para a DLQ.
"""

import base64
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

from flask import Flask, request
from google.cloud import bigquery

PROJETO = os.environ.get("PROJETO", "pdm-sistema-eletrico-2026")
SILVER = f"{PROJETO}.sistema_eletrico_silver"
TABELA_OK = f"{SILVER}.restricao_coff_stream"
TABELA_REJEITADOS = f"{SILVER}.restricao_coff_stream_rejeitados"
RECARGA_REFERENCIAS_S = 6 * 3600

CAMPOS_TEXTO = [
    "id_subsistema", "nom_subsistema", "id_estado", "nom_estado", "nom_usina", "id_ons", "ceg",
    "cod_razaorestricao", "cod_origemrestricao", "dsc_restricao", "origem_dataset",
]
CAMPOS_NUMERICOS = [
    "val_geracao", "val_geracaolimitada", "val_disponibilidade",
    "val_geracaoreferencia", "val_geracaoreferenciafinal",
]

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
bq = bigquery.Client(project=PROJETO)


class Referencias:
    """Tabelas do lote usadas no enriquecimento, em memória e recarregadas a cada 6 h."""

    def __init__(self):
        self._trava = threading.Lock()
        self._carregado_em = 0.0
        self.fonte = {}    # id_ons -> EOLICA / FOTOVOLTAICA
        self.estacao = {}  # (id_ons, "AAAA-MM") -> (codigo_estacao, distancia_km)

    def garantir(self):
        if time.time() - self._carregado_em < RECARGA_REFERENCIAS_S:
            return
        with self._trava:
            if time.time() - self._carregado_em < RECARGA_REFERENCIAS_S:
                return
            fonte = {r.id_ons: r.fonte for r in bq.query(
                f"SELECT id_ons, fonte FROM `{SILVER}.dim_usina_nordeste`").result()}
            estacao = {(r.id_ons, r.mes.strftime("%Y-%m")): (r.codigo_estacao, r.distancia_km)
                       for r in bq.query(
                f"SELECT id_ons, mes, codigo_estacao, distancia_km FROM `{SILVER}.usina_estacao_mes`").result()}
            self.fonte, self.estacao = fonte, estacao
            self._carregado_em = time.time()
            logging.info("referências carregadas: %d usinas, %d usina-mês", len(fonte), len(estacao))


referencias = Referencias()


def converter_instante(texto):
    # Aceita "AAAA-MM-DD HH:MM:SS" (formato do gerador) e ISO com "T".
    return datetime.fromisoformat(str(texto).replace("T", " ").replace("Z", ""))


def limpar(bruto):
    """Devolve (linha_limpa, motivos). Se `motivos` não estiver vazio, a leitura é rejeitada."""
    motivos = []
    linha = {}

    for campo in CAMPOS_TEXTO:
        valor = bruto.get(campo)
        valor = str(valor).strip() if valor is not None else None
        linha[campo] = valor or None

    if not linha["id_ons"]:
        motivos.append("id_ons_ausente")

    try:
        instante = converter_instante(bruto["din_instante"])
        linha["din_instante"] = instante.strftime("%Y-%m-%d %H:%M:%S")
    except (KeyError, TypeError, ValueError):
        instante = None
        motivos.append("din_instante_invalido")

    for campo in CAMPOS_NUMERICOS:
        valor = bruto.get(campo)
        if valor is None or valor == "":
            linha[campo] = None
            continue
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            motivos.append(f"{campo}_nao_numerico")
            continue
        if numero < 0:
            motivos.append(f"{campo}_negativo")
        linha[campo] = numero

    return linha, motivos, instante


def enriquecer(linha, instante):
    referencias.garantir()
    linha["fonte"] = referencias.fonte.get(linha["id_ons"])
    estacao, distancia = referencias.estacao.get((linha["id_ons"], instante.strftime("%Y-%m")), (None, None))
    linha["codigo_estacao"] = estacao
    linha["distancia_estacao_km"] = distancia

    linha["em_restricao"] = linha["cod_razaorestricao"] is not None
    referencia, geracao = linha["val_geracaoreferencia"], linha["val_geracao"]
    if linha["em_restricao"] and referencia is not None and geracao is not None:
        linha["mw_cortado"] = round(max(referencia - geracao, 0.0), 3)
    else:
        linha["mw_cortado"] = 0.0 if not linha["em_restricao"] else None
    return linha


@app.post("/pubsub")
def receber():
    envelope = request.get_json(silent=True) or {}
    mensagem = envelope.get("message") or {}
    message_id = mensagem.get("messageId") or mensagem.get("message_id")
    agora = datetime.now(timezone.utc)

    try:
        texto = base64.b64decode(mensagem.get("data", "")).decode("utf-8")
        bruto = json.loads(texto)
        if not isinstance(bruto, dict):
            raise ValueError("o corpo não é um objeto JSON")
    except (ValueError, UnicodeDecodeError) as erro:
        return rejeitar(mensagem.get("data", ""), ["json_invalido"], message_id, agora, erro)

    linha, motivos, instante = limpar(bruto)
    if motivos:
        return rejeitar(texto, motivos, message_id, agora)

    linha = enriquecer(linha, instante)
    publicado_em = mensagem.get("publishTime") or mensagem.get("publish_time")
    if publicado_em:
        publicado = datetime.fromisoformat(publicado_em.replace("Z", "+00:00"))
        linha["publicado_em"] = publicado.isoformat()
        linha["latencia_s"] = round((agora - publicado).total_seconds(), 3)
    linha["processado_em"] = agora.isoformat()
    linha["message_id"] = message_id

    # row_ids = message_id: se o Pub/Sub reentregar a mesma mensagem, o BigQuery descarta a cópia.
    erros = bq.insert_rows_json(TABELA_OK, [linha], row_ids=[message_id])
    if erros:
        logging.error("falha ao gravar %s: %s", message_id, erros)
        return "erro ao gravar no BigQuery", 500  # o Pub/Sub tenta de novo
    return "", 204


def rejeitar(registro, motivos, message_id, agora, erro=None):
    logging.warning("rejeitada %s: %s %s", message_id, motivos, erro or "")
    erros = bq.insert_rows_json(TABELA_REJEITADOS, [{
        "registro_original": str(registro)[:100_000],
        "motivos_rejeicao": motivos,
        "message_id": message_id,
        "recebido_em": agora.isoformat(),
    }], row_ids=[message_id])
    if erros:
        logging.error("falha ao gravar rejeitada %s: %s", message_id, erros)
        return "erro ao gravar rejeitada", 500
    return "", 204


@app.get("/")
def saude():
    return {"servico": "pipeline-ons-streaming", "tabela": TABELA_OK}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
