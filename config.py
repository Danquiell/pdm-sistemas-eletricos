import os

PROJECT_ID = "pdm-sistema-eletrico-2026"
BUCKET_NAME = "dados-ons"
LOCATION = "US"

DATASET_BRONZE = "sistema_eletrico"
DATASET_SILVER = "sistema_eletrico_silver"
DATASET_GOLD = "sistema_eletrico_gold"

TB_BRONZE = f"{PROJECT_ID}.{DATASET_BRONZE}.SistemaEletrico_bronze"
TB_SILVER = f"{PROJECT_ID}.{DATASET_SILVER}.restricao_coff"
TB_SILVER_REJEITADOS = f"{PROJECT_ID}.{DATASET_SILVER}.restricao_coff_rejeitados"
TB_GOLD = f"{PROJECT_ID}.{DATASET_GOLD}.perda_diaria_usina"
TB_ANOMALIAS = f"{PROJECT_ID}.{DATASET_GOLD}.anomalias_detectadas"
MODELO = f"{PROJECT_ID}.{DATASET_GOLD}.modelo_anomalia_perda"

DIR_LOCAL = os.environ.get("ONS_DIR_LOCAL", "./dados/ons")
DIR_UPLOAD = os.environ.get("ONS_DIR_UPLOAD", "./parquet_para_subir")

CONJUNTOS = {
    "EOLIELETRICA": "restricao_coff_eolica_tm",
    "FOTOVOLTAICA": "restricao_coff_fotovoltaica_tm",
}

GCS_PREFIX = "bronze/restricao_coff"
GCS_URI_WILDCARD = f"gs://{BUCKET_NAME}/{GCS_PREFIX}/*.parquet"

DATA_CORTE_TREINO = "2026-03-01"
CONTAMINATION = 0.02
NUM_CLUSTERS = 6
