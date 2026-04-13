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
    "RB-FORTALI"
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
    DEBUG = False  # validação com erros

    for aba in ABAS:
        print(f"Lendo aba: {aba}")
        df = pd.read_excel(ARQUIVO_EXCEL, sheet_name=aba)
        df["origem_base"] = aba
        
        if DEBUG:
            print(f"Colunas: {list(df.columns)}")
            print(f"Primeiras linhas:\n{df.head(2)}")
            print(f"Total linhas: {len(df)}")

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
    from dotenv import load_dotenv
    load_dotenv()
    
    import psycopg2
    from psycopg2.extras import execute_values
    import numpy as np

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL nao definida. Configure o arquivo .env")

    def sanitizar_colunas(df):
        import unicodedata
        novos_nomes = {}
        for col in df.columns:
            novo = col
            novo = novo.replace('%', 'pct')
            novo = novo.replace("'", "")
            novo = novo.replace('"', '')
            novo = novo.replace('\n', ' ')
            novo = novo.replace('\r', '')
            # Remove acentos
            novo = unicodedata.normalize('NFKD', novo)
            novo = ''.join(c for c in novo if not unicodedata.combining(c))
            novos_nomes[col] = novo
        return df.rename(columns=novos_nomes)

    def limpar_valor(v):
        if v is None:
            return None
        if isinstance(v, float) and np.isnan(v):
            return None
        if isinstance(v, pd.Timestamp):
            if pd.isna(v):
                return None
            return v.to_pydatetime()
        if hasattr(v, 'item'):
            return v.item()
        # Trata NaT do pandas
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        return v

    df = sanitizar_colunas(df)

    print("Substituindo tabela pagamentos no banco...")
    conn = psycopg2.connect(database_url)
    conn.autocommit = True
    cursor = conn.cursor()

    cursor.execute("DELETE FROM pagamentos")
    print("Dados anteriores removidos.")

    colunas = list(df.columns)
    colunas_sql = ", ".join(f'"{c}"' for c in colunas)
    placeholder = "INSERT INTO pagamentos (" + colunas_sql + ") VALUES %s"

    registros = [
        tuple(limpar_valor(v) for v in row)
        for row in df.itertuples(index=False, name=None)
    ]

    print(f"Inserindo {len(df)} registros...")
    execute_values(cursor, placeholder, registros, page_size=1000)

    cursor.close()
    conn.close()
    print(f"Dados salvos com sucesso. Total: {len(df)} registros.")


def main():
    df = carregar_excel()
    df = tratar_dados(df)
    salvar_no_supabase(df)
    print("ETL finalizado com sucesso.")


if __name__ == "__main__":
    main()