"""
ETL - Reflexos de Cálculos
==========================
Processa arquivo .xlsx/.xls de reflexos de cálculos de acordos
e insere os dados no Supabase (tabela reflexos_calculo).

Uso:
    python etl_reflexos.py --arquivo "REFLEXOS_LABOTRAT_27-05-2026.xlsx"
    python etl_reflexos.py --pasta "./arquivos_reflexos"
    python etl_reflexos.py  (usa REFLEXOS_PASTA do .env)
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Mapeamento de meses em português ─────────────────────────────────────────
MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "ABRIL": 4,
    "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
    "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}

# ── Mapeamento de colunas do xlsx → banco ─────────────────────────────────────
MAPA_COLUNAS = {
    "AC. CANCELADO":            "ac_cancelado",
    "AC. ATIVO":                "ac_ativo",
    "CPF/CNPJ":                 "cpf_cnpj",
    "Nome":                     "nome",
    "Data Inclusão":            "data_inclusao",
    "Atraso":                   "atraso",
    " Vencimento":              "vencimento",
    "Vlr Parcela ":             "vlr_parcela",
    "Vl. Negociado":            "vl_negociado",
    "Num Prest":                "num_prest",
    "Plano":                    "plano",
    "% Pago":                   "pct_pago",
    "Faixa de Atraso":          "faixa_atraso",
    "Montante Principal":       "montante_principal",
    "Vl. Principal":            "vl_principal",
    "J. Labotrat":              "j_contratante",
    "J. Smart (50%/70%/85%)":   "j_smart",
    "multa":                    "multa",
    "Ho. Smart":                "ho_smart",
    "Vl. A Recebido":           "vl_a_recebido",
    "Vl. do Repasse":           "vl_repasse",
    "Vl. Comissão":             "vl_comissao",
    "OBS.":                     "obs",
}


def extrair_contratante(df_raw: pd.DataFrame) -> str:
    """
    Extrai o nome do contratante da célula A7.
    Exemplo: 'SMARTCOB - REFLEXOS DE CÁLCULOS - ACORDOS - LABOTRAT'
    → 'LABOTRAT'
    """
    celula = str(df_raw.iloc[6, 0]).strip()
    partes = celula.split(" - ")
    contratante = partes[-1].strip()
    if not contratante:
        raise ValueError(f"Nao foi possivel extrair contratante de: '{celula}'")
    return contratante


def extrair_data_referencia(df_raw: pd.DataFrame) -> datetime.date:
    """
    Extrai e converte a data da célula A9.
    Exemplo: 'FORTALEZA, 27 DE MAIO DE 2026' → date(2026, 5, 27)
    """
    celula = str(df_raw.iloc[8, 0]).strip()
    try:
        parte_data = celula.split(",")[-1].strip()
        partes = parte_data.upper().split(" DE ")
        dia = int(partes[0].strip())
        mes = MESES[partes[1].strip()]
        ano = int(partes[2].strip())
        return datetime(ano, mes, dia).date()
    except Exception as exc:
        raise ValueError(f"Nao foi possivel extrair data de: '{celula}' — {exc}")


def limpar_valor(valor):
    """Converte valor para tipo nativo Python, tratando NaN e NaT."""
    if pd.isna(valor):
        return None
    if isinstance(valor, pd.Timestamp):
        return valor.date()
    if hasattr(valor, "item"):
        return valor.item()
    return valor


def processar_arquivo(caminho: str) -> tuple[str, datetime.date, list[dict]]:
    """
    Lê o arquivo .xlsx/.xls e retorna (contratante, data_referencia, registros).
    """
    caminho = Path(caminho)
    log.info(f"Processando: {caminho.name}")

    engine = "xlrd" if caminho.suffix.lower() == ".xls" else "openpyxl"

    # Leitura raw para extrair contratante e data (células A7 e A9)
    df_raw = pd.read_excel(caminho, header=None, engine=engine)

    contratante = extrair_contratante(df_raw)
    data_referencia = extrair_data_referencia(df_raw)

    log.info(f"  Contratante: {contratante}")
    log.info(f"  Data referencia: {data_referencia}")

    # Leitura dos dados a partir da linha 14 (índice 13)
    df = pd.read_excel(caminho, header=13, engine=engine)

    # Remove linhas completamente vazias
    df = df.dropna(how="all").reset_index(drop=True)

    if df.empty:
        log.warning("  Nenhum dado encontrado no arquivo.")
        return contratante, data_referencia, []

    # Propaga valores de células mescladas em todas as colunas (ffill)
    df = df.ffill()

    log.info(f"  Registros encontrados: {len(df)}")

    registros = []
    for _, row in df.iterrows():
        registro = {
            "contratante":     contratante,
            "data_referencia": data_referencia,
        }

        for col_xlsx, col_banco in MAPA_COLUNAS.items():
            col_encontrada = next(
                (c for c in df.columns if c.strip() == col_xlsx.strip()),
                None
            )
            valor = limpar_valor(row[col_encontrada]) if col_encontrada else None
            registro[col_banco] = valor

        # Trata j_contratante — nome varia por contratante no xlsx
        # Ex: "J. Labotrat", "J. MaxBeauty", etc.
        if registro.get("j_contratante") is None:
            for col in df.columns:
                if col.strip().startswith("J.") and "Smart" not in col:
                    registro["j_contratante"] = limpar_valor(row[col])
                    break

        registros.append(registro)

    return contratante, data_referencia, registros


def conectar_banco() -> psycopg2.extensions.connection:
    url = os.environ.get("DATABASE_URL", "").split("?")[0]
    if not url:
        raise RuntimeError("DATABASE_URL nao definida.")
    return psycopg2.connect(url)


def inserir_registros(registros: list[dict], contratante: str, data_referencia) -> int:
    """
    Insere os registros no Supabase mantendo histórico.
    """
    if not registros:
        return 0

    colunas = list(registros[0].keys())
    placeholders = ", ".join(["%s"] * len(colunas))
    cols_sql = ", ".join(colunas)

    sql = f"INSERT INTO reflexos_calculo ({cols_sql}) VALUES ({placeholders})"

    conn = conectar_banco()
    try:
        with conn:
            with conn.cursor() as cursor:
                valores = [
                    tuple(r[c] for c in colunas)
                    for r in registros
                ]
                psycopg2.extras.execute_batch(cursor, sql, valores, page_size=100)
        log.info(f"  {len(registros)} registro(s) inserido(s) com sucesso.")
        return len(registros)
    finally:
        conn.close()


def processar_pasta(pasta: str) -> None:
    """Processa todos os arquivos .xlsx, .xls e .xlsm de uma pasta."""
    pasta = Path(pasta)
    arquivos = (
        sorted(pasta.glob("*.xlsx")) +
        sorted(pasta.glob("*.xls")) +
        sorted(pasta.glob("*.xlsm"))
    )

    if not arquivos:
        log.warning(f"Nenhum arquivo encontrado em: {pasta}")
        return

    total_inseridos = 0
    erros = []

    for arquivo in arquivos:
        try:
            contratante, data_ref, registros = processar_arquivo(str(arquivo))
            total_inseridos += inserir_registros(registros, contratante, data_ref)
        except Exception as exc:
            log.error(f"  ERRO em {arquivo.name}: {exc}")
            erros.append((arquivo.name, str(exc)))

    log.info(f"\nResumo: {total_inseridos} registro(s) inserido(s) | {len(erros)} erro(s)")
    if erros:
        for nome, msg in erros:
            log.error(f"  {nome}: {msg}")


def main():
    parser = argparse.ArgumentParser(description="ETL Reflexos de Calculos")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--arquivo", help="Caminho para um arquivo especifico")
    group.add_argument("--pasta", help="Pasta com multiplos arquivos")
    args = parser.parse_args()

    # Prioridade: argumento > variavel de ambiente .env
    pasta = args.pasta or os.environ.get("REFLEXOS_PASTA")
    arquivo = args.arquivo

    if arquivo:
        try:
            contratante, data_ref, registros = processar_arquivo(arquivo)
            inserir_registros(registros, contratante, data_ref)
        except Exception as exc:
            log.error(f"Erro: {exc}")
            sys.exit(1)
    elif pasta:
        processar_pasta(pasta)
    else:
        log.error("Informe --arquivo, --pasta ou defina REFLEXOS_PASTA no .env")
        sys.exit(1)


if __name__ == "__main__":
    main()