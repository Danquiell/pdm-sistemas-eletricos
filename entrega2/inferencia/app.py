"""API que diz se um dia de uma usina é anômalo.

POST /predict (ou /v1/predict) recebe os 7 números do dia, como estão na Gold
perda_diaria_usina, e devolve o grupo, a distância e se o dia é anômalo.

Códigos: 200 ok; 400 corpo não é JSON; 413 corpo grande demais;
422 dado errado; 503 arquivo do modelo não carregou.
"""
import datetime as dt
import logging
from typing import Literal, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from detector import Detector

SCHEMA_VERSION = "1.0.1"
# Diferença máxima aceita entre pct_perda e o valor calculado pelas energias.
# Na Gold a maior diferença é 0,0005; com 0,005 também pega percentual mandado de 0 a 1.
TOLERANCIA_PCT_PERDA = 0.005
# Mesmo teto da Silver: nenhuma usina passa de 10.000 MW, então no máximo 240.000 MWh no dia.
MAX_MW = 10_000
MAX_MWH_DIA = MAX_MW * 24
MAX_CORPO_BYTES = 16_384

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="pdm-inferencia-energia", version=SCHEMA_VERSION)

# Se o arquivo do modelo faltar, a API sobe mesmo assim e responde 503.
try:
    detector = Detector()
except Exception:
    logging.exception("ARTEFATO_DO_MODELO_NAO_CARREGOU")
    detector = None


def numero(maximo):
    # número de verdade (não texto), sem NaN nem infinito, entre 0 e o máximo
    return Field(ge=0, le=maximo, allow_inf_nan=False, strict=True)


class Features(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo_usina: Literal["EOLIELETRICA", "FOTOVOLTAICA"]
    mwh_gerado: float = numero(MAX_MWH_DIA)
    mwh_perdido: float = numero(MAX_MWH_DIA)
    pct_perda: float = numero(100)
    pct_horas_restricao: float = numero(100)
    fator_capacidade: float = numero(2)
    mw_disponibilidade_media: float = numero(MAX_MW)

    @model_validator(mode="after")
    def pct_perda_coerente(self):
        total = self.mwh_perdido + self.mwh_gerado
        esperado = 100 * self.mwh_perdido / total if total > 0 else 0.0
        if abs(self.pct_perda - esperado) > TOLERANCIA_PCT_PERDA:
            raise ValueError(
                f"pct_perda={self.pct_perda} incoerente com mwh_perdido e mwh_gerado "
                f"(esperado {esperado:.3f}, escala 0-100)")
        return self


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # opcionais: só voltam na resposta para identificar o pedido
    schema_version: Optional[Literal["1.0.1"]] = None
    request_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    id_ons: Optional[str] = Field(default=None, min_length=1, max_length=80)
    dia: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    replay_run_id: Optional[str] = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    features: Features

    @field_validator("dia")
    @classmethod
    def dia_existe(cls, valor):
        if valor is not None:
            dt.date.fromisoformat(valor)  # recusa datas como 2026-02-30
        return valor


@app.exception_handler(RequestValidationError)
async def entrada_invalida(request: Request, exc: RequestValidationError):
    erros = exc.errors()
    if any(e.get("type") == "json_invalid" for e in erros):
        return JSONResponse(status_code=400, content={"erro": "JSON_MALFORMADO"})
    detalhes = [{"campo": ".".join(str(p) for p in e["loc"][1:]), "motivo": e["msg"]}
                for e in erros]
    return JSONResponse(status_code=422, content={"erro": "ENTRADA_INVALIDA", "detalhes": detalhes})


@app.middleware("http")
async def limita_corpo(request: Request, call_next):
    # um pedido normal tem menos de 1 KB
    if int(request.headers.get("content-length") or 0) > MAX_CORPO_BYTES:
        return JSONResponse(status_code=413, content={"erro": "CORPO_GRANDE_DEMAIS"})
    return await call_next(request)


# No Cloud Run o /healthz na raiz é reservado e não chega na API; lá vale /health.
@app.get("/health")
@app.get("/healthz")
def healthz():
    return {"status": "ok" if detector else "sem_modelo", "modelo_carregado": detector is not None,
            "versao_modelo": detector.versao if detector else None}


@app.post("/predict")
@app.post("/v1/predict")
def predict(req: PredictRequest):
    if detector is None:
        return JSONResponse(status_code=503, content={"erro": "MODELO_INDISPONIVEL"})
    r = detector.avaliar(req.features.model_dump())
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": req.request_id,
        "id_ons": req.id_ons,
        "dia": req.dia,
        "replay_run_id": req.replay_run_id,
        "modelo": {
            "nome": "modelo_anomalia_perda",
            "versao": detector.versao,
            "regra": "ML.DETECT_ANOMALIES K-Means, distancia/raio do grupo >= limiar do treino",
            "clima_como_feature": False,
        },
        "predicao": {
            "centroid_id": r["centroid_id"],
            "normalized_distance": round(r["normalized_distance"], 6),
            "is_anomaly": r["is_anomaly"],
            "limiar": r["limiar"],
            "contamination": detector.contamination,
        },
        "respondido_em_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
