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


def log(mensagem):
    if not mensagem or not str(mensagem).strip():
        return
    for linha in str(mensagem).strip().splitlines():
        linha = linha.strip()
        if not linha:
            continue
        entrada = f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] {linha}"
        # Tenta escrever no log com retry
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


def popup(titulo, mensagem, tipo="Information"):
    mensagem_limpa = (
        mensagem
        .replace("'", "")
        .replace('"', "")
        .replace("\n", " | ")
        .encode("ascii", errors="replace")
        .decode("ascii")
    )
    titulo_limpo = (
        titulo
        .encode("ascii", errors="replace")
        .decode("ascii")
    )
    subprocess.run([
        "powershell", "-Command",
        f'Add-Type -AssemblyName PresentationFramework; '
        f'[System.Windows.MessageBox]::Show('
        f'"{mensagem_limpa}", '
        f'"{titulo_limpo}", '
        f'"OK", '
        f'"{tipo}")'
    ])


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
        popup(
            "Erro - Atualizar Base SmartCob",
            f"Erro na ETAPA 1 (ETL). Verifique o log em: {LOG_FILE}",
            tipo="Error",
        )
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
        popup(
            "Erro - Atualizar Base SmartCob",
            f"Erro na ETAPA 2 (Usuarios). Verifique o log em: {LOG_FILE}",
            tipo="Error",
        )
        sys.exit(1)

    duracao = (datetime.now() - inicio).seconds
    log(f"=== ATUALIZACAO CONCLUIDA em {duracao}s ===")
    popup(
        "Sucesso - Atualizar Base SmartCob",
        f"Base atualizada com sucesso! Duracao: {duracao} segundos.",
        tipo="Information",
    )


if __name__ == "__main__":
    main()
    