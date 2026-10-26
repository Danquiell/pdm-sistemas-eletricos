"""Clima do dia (contexto_inmet), lido da view que junta a energia e o clima do streaming.

O clima não entra no modelo. Ele vai junto com a previsão para ajudar a explicar o dia:
uma perda alta com vento forte é diferente de uma perda alta com vento fraco.

A view v_energia_inmet_stream_diario tem uma linha por execução do replay, usina e dia.
Na primeira consulta de uma execução, a API baixa todas as linhas dela (cerca de 3.700,
o Nordeste de 1 a 19/08/2026) e guarda na memória por alguns minutos. As consultas
seguintes da mesma execução não vão ao BigQuery.

Se o BigQuery falhar, a previsão sai do mesmo jeito, com status INDISPONIVEL no clima.
"""
import logging
import os
import threading
import time

PROJETO = os.environ.get("PROJETO_GCP", "pdm-sistema-eletrico-2026")
VIEW = os.environ.get("VIEW_CONTEXTO",
                      f"{PROJETO}.sistema_eletrico_gold.v_energia_inmet_stream_diario")
VALIDADE_S = int(os.environ.get("CONTEXTO_VALIDADE_S", "600"))
MAX_EXECUCOES = 10  # limita a memória: cada execução ocupa cerca de 1 MB

# campos do clima que a resposta devolve, com o mesmo nome da view
CAMPOS = [
    "codigo_estacao", "distancia_km", "temperatura_media_c", "vento_medio_ms",
    "radiacao_soma_observada_kj_m2", "precipitacao_soma_observada_mm",
    "fracao_validas_temperatura", "fracao_validas_vento",
    "fracao_validas_radiacao_08_16", "fracao_validas_precipitacao",
]
REGRA_COMPLETUDE = "BRT_08_16_V1"


def consultar_bigquery(execucao):
    # importa aqui para os testes e o uso local rodarem sem a biblioteca do BigQuery
    from google.cloud import bigquery
    cliente = bigquery.Client(project=PROJETO)
    sql = (f"SELECT id_ons, dia, status_contexto, atualizado_em_utc, {', '.join(CAMPOS)} "
           f"FROM `{VIEW}` WHERE replay_run_id = @execucao")
    config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("execucao", "STRING", execucao)])
    linhas = cliente.query(sql, job_config=config, location="US").result(timeout=20)
    return {(r["id_ons"], r["dia"].isoformat()): dict(r.items()) for r in linhas}


def vazio(status):
    return {"status": status, **{c: None for c in CAMPOS}, "regra_completude": REGRA_COMPLETUDE,
            "usado_no_modelo": False, "atualizado_em_utc": None}


class ContextoInmet:
    def __init__(self, consultar=consultar_bigquery, validade_s=VALIDADE_S):
        self.consultar = consultar
        self.validade_s = validade_s
        self.guardado = {}  # execução -> (instante da carga, {(id_ons, dia): linha})
        self.trava = threading.Lock()
        self.ultima_falha = float("-inf")

    def linhas_da_execucao(self, execucao):
        with self.trava:
            carga = self.guardado.get(execucao)
            if carga and time.monotonic() - carga[0] < self.validade_s:
                return carga[1]
            # depois de uma falha, espera 30 s antes de tentar o BigQuery de novo,
            # para cada pedido não ficar parado 20 s esperando a mesma falha
            if time.monotonic() - self.ultima_falha < 30:
                raise RuntimeError("BigQuery falhou há menos de 30 s")
            try:
                linhas = self.consultar(execucao)
            except Exception:
                self.ultima_falha = time.monotonic()
                raise
            if len(self.guardado) >= MAX_EXECUCOES:
                self.guardado.pop(min(self.guardado, key=lambda k: self.guardado[k][0]))
            self.guardado[execucao] = (time.monotonic(), linhas)
            return linhas

    def buscar(self, id_ons, dia, execucao):
        if not (id_ons and dia and execucao):
            return vazio("SEM_IDENTIFICACAO")
        try:
            linha = self.linhas_da_execucao(execucao).get((id_ons, dia))
        except Exception:
            logging.exception("CONTEXTO_INMET_INDISPONIVEL")
            return vazio("INDISPONIVEL")
        if linha is None:
            # fora do Nordeste, fora de 1 a 19/08/2026 ou execução que não existe
            return vazio("FORA_DO_RECORTE")
        resposta = vazio(linha["status_contexto"])
        for c in CAMPOS:
            valor = linha[c]
            resposta[c] = float(valor) if c != "codigo_estacao" and valor is not None else valor
        if linha["atualizado_em_utc"] is not None:
            resposta["atualizado_em_utc"] = linha["atualizado_em_utc"].strftime("%Y-%m-%dT%H:%M:%SZ")
        return resposta
