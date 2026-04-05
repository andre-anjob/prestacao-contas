import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
from sqlalchemy import create_engine, text


ARQUIVO_EXCEL = r"C:\Users\SMARTCOB\OneDrive\Pagamentos\PLANILHA DE PRESTAÇÕES DE CONTAS - RELATÓRIOS - NOVA 2024.xlsx"

ABAS = [
    "Base G12",
    "Base - Pgto no Contratante",
    "Base Outros",
]


def get_engine(autocommit=False):
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL nao definida. Configure o arquivo .env")

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    if autocommit:
        return create_engine(database_url, isolation_level="AUTOCOMMIT")
    return create_engine(database_url)


def carregar_excel():
    lista_df = []
    for aba in ABAS:
        print(f"Lendo aba: {aba}")
        df = pd.read_excel(ARQUIVO_EXCEL, sheet_name=aba)
        df["origem_base"] = aba
        lista_df.append(df)

    df_final = pd.concat(lista_df, ignore_index=True)
    print(f"Total de registros carregados: {len(df_final)}")
    return df_final


def tratar_dados(df):
    colunas_numericas = [
        "V. Princ", "V. Repasse", "V. Comissão",
        "V. Juros Contrat", "V. Juros Asses", "V. Honor",
        "V. Receb", "Taxa do boleto",
    ]
    for coluna in colunas_numericas:
        if coluna in df.columns:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce")

    for coluna_data in ["Data Pagto", "Data Venc"]:
        if coluna_data in df.columns:
            df[coluna_data] = pd.to_datetime(df[coluna_data], errors="coerce")

    print(df[["V. Princ", "V. Repasse", "V. Comissão"]].dtypes)
    print(df[["V. Princ", "V. Repasse", "V. Comissão"]].head())
    print(df["Data Pagto"].head())

    return df


def salvar_no_supabase(df):
    print("Substituindo tabela pagamentos no banco...")

    # Engine 1 — AUTOCOMMIT para o DELETE
    engine_delete = get_engine(autocommit=True)
    with engine_delete.connect() as conn:
        conn.execute(text("DELETE FROM pagamentos"))
    engine_delete.dispose()
    print("Dados anteriores removidos.")

    # Engine 2 — transacao normal para o INSERT
    engine_insert = get_engine(autocommit=False)
    df.to_sql(
        "pagamentos",
        engine_insert,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
    )
    engine_insert.dispose()

    print(f"Dados salvos com sucesso. Total: {len(df)} registros.")


def main():
    df = carregar_excel()
    df = tratar_dados(df)
    salvar_no_supabase(df)
    print("ETL finalizado com sucesso.")


if __name__ == "__main__":
    main()