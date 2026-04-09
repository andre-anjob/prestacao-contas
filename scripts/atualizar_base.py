import os
import subprocess
import sys
import io
from pathlib import Path
from datetime import datetime

# Corrige encoding do terminal Windows (cp1252 -> utf-8)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "atualizacao.log"

# Garante DATABASE_URL mesmo sem .env
if not os.environ.get("DATABASE_URL"):
    try:
        sys.path.insert(0, str(BASE_DIR))
        from config import DATABASE_URL as _db_url
        os.environ["DATABASE_URL"] = _db_url
    except ImportError:
        pass


def log(mensagem):
    if not mensagem or not str(mensagem).strip():
        return
    for linha in str(mensagem).strip().splitlines():
        linha = linha.strip()
        if not linha:
            continue
        entrada = f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] {linha}"
        for tentativa in range(3):
            try:
                with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as f:
                    f.write(entrada + "\n")
                break
            except PermissionError:
                import time
                time.sleep(0.5)
        try:
            print(entrada)
        except Exception:
            pass


def main():
    inicio = datetime.now()
    log("=== INICIANDO ATUALIZACAO ===")

    # ETAPA 1 — ETL
    log("--- ETAPA 1: ETL ---")
    resultado_etl = subprocess.run(
        [PYTHON, str(BASE_DIR / "scripts" / "etl_pagamentos.py")],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    log(resultado_etl.stdout)

    if resultado_etl.returncode != 0:
        erro = resultado_etl.stderr or "Erro desconhecido."
        log(f"ERRO NO ETL: {erro}")
        log("ATUALIZACAO ABORTADA — verifique o log acima.")
        sys.exit(1)

    # ETAPA 2 — Usuarios
    log("--- ETAPA 2: USUARIOS ---")
    resultado_usuarios = subprocess.run(
        [PYTHON, str(BASE_DIR / "scripts" / "criar_usuarios.py")],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    log(resultado_usuarios.stdout)

    if resultado_usuarios.returncode != 0:
        erro = resultado_usuarios.stderr or "Erro desconhecido."
        log(f"ERRO AO CRIAR USUARIOS: {erro}")
        log("ATUALIZACAO ABORTADA — verifique o log acima.")
        sys.exit(1)

    duracao = (datetime.now() - inicio).seconds
    log(f"=== ATUALIZACAO CONCLUIDA em {duracao}s ===")


if __name__ == "__main__":
    main()