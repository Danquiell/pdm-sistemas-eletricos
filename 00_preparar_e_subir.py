import argparse
import glob
import os
import re
import subprocess
import sys

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

SAIDA_LOCAL = config.DIR_UPLOAD

SCHEMA_CANONICO = pa.schema([
    ("id_subsistema", pa.string()),
    ("nom_subsistema", pa.string()),
    ("id_estado", pa.string()),
    ("nom_estado", pa.string()),
    ("nom_usina", pa.string()),
    ("id_ons", pa.string()),
    ("ceg", pa.string()),
    ("din_instante", pa.timestamp("us")),
    ("val_geracao", pa.string()),
    ("val_geracaolimitada", pa.string()),
    ("val_disponibilidade", pa.string()),
    ("val_geracaoreferencia", pa.string()),
    ("val_geracaoreferenciafinal", pa.string()),
    ("cod_razaorestricao", pa.string()),
    ("cod_origemrestricao", pa.string()),
    ("dsc_restricao", pa.string()),
    ("_origem_dataset", pa.string()),
])

def harmonizar(caminho: str, origem: str) -> pa.Table:
    t = pq.read_table(caminho)
    colunas = {}

    for campo in SCHEMA_CANONICO:
        nome = campo.name

        if nome == "_origem_dataset":
            colunas[nome] = pa.array([origem] * t.num_rows, pa.string())
            continue

        if nome not in t.column_names:

            colunas[nome] = pa.nulls(t.num_rows, pa.string())
            continue

        col = t[nome].combine_chunks()

        if campo.type == pa.string() and col.type != pa.string():

            col = pa.array(
                [None if v is None else repr(v) for v in col.to_pylist()],
                pa.string(),
            )
        elif pa.types.is_timestamp(campo.type):
            col = col.cast(campo.type)

        colunas[nome] = col

    return pa.table(colunas, schema=SCHEMA_CANONICO)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="harmoniza local mas não sobe para o GCS")
    args = ap.parse_args()

    os.makedirs(SAIDA_LOCAL, exist_ok=True)
    total_linhas = 0
    total_arquivos = 0

    for origem, pasta in config.CONJUNTOS.items():
        padrao = os.path.join(config.DIR_LOCAL, pasta, "*.parquet")
        arquivos = sorted(glob.glob(padrao))
        if not arquivos:
            sys.exit(f"ERRO: nenhum Parquet em {padrao}\n"
                     f"Rode antes o script de download do bucket S3 do ONS.")

        print(f"\n=== {origem}  ({len(arquivos)} arquivos)")
        for caminho in arquivos:
            competencia = re.search(r"(\d{4}(?:_\d{2})?)\.parquet$", caminho)
            competencia = competencia.group(1) if competencia else "sem_data"

            tabela = harmonizar(caminho, origem)
            destino = os.path.join(
                SAIDA_LOCAL, f"restricao_{origem.lower()}_{competencia}.parquet"
            )
            pq.write_table(tabela, destino, compression="snappy")

            total_linhas += tabela.num_rows
            total_arquivos += 1
            print(f"  {competencia}  {tabela.num_rows:>8,} linhas")

    tamanho = sum(
        os.path.getsize(f) for f in glob.glob(f"{SAIDA_LOCAL}/*.parquet")
    ) / 1024 ** 2
    print(f"\nHarmonizado: {total_arquivos} arquivos | "
          f"{total_linhas:,} linhas | {tamanho:.1f} MB")
    print(f"Local: {SAIDA_LOCAL}")

    if args.dry_run:
        print("\n--dry-run: parando antes do upload.")
        return

    destino_gcs = f"gs://{config.BUCKET_NAME}/{config.GCS_PREFIX}/"
    print(f"\nSubindo para {destino_gcs} ...")
    subprocess.run(
        ["gsutil", "-m", "cp", f"{SAIDA_LOCAL}/*.parquet", destino_gcs],
        check=True,
    )
    print("Upload concluído.")
    print(f"\nPróximo passo: 01_Raw_to_bronze.ipynb "
          f"(lê de {config.GCS_URI_WILDCARD})")

if __name__ == "__main__":
    main()
