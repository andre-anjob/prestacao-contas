import os
import subprocess
import sys
import io
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "atualizacao.log"

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


def executar_etapa(nome, script):
    """Executa um script e loga stdout e stderr. Retorna True se OK."""
    log(f"--- {nome} ---")
    resultado = subprocess.run(
        [PYTHON, str(BASE_DIR / "scripts" / script)],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if resultado.stdout and resultado.stdout.strip():
        log(resultado.stdout)

    # Loga stderr SEMPRE — independente do returncode
    if resultado.stderr and resultado.stderr.strip():
        log(f"[STDERR {nome}]:\n{resultado.stderr}")

    if resultado.returncode != 0:
        log(f"ERRO em {nome} — returncode: {resultado.returncode}")
        return False

    return True


def verificar_planilha_disponivel():
    """Verifica se a planilha Excel está acessível e não bloqueada."""
    try:
        sys.path.insert(0, str(BASE_DIR / "scripts"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "etl", BASE_DIR / "scripts" / "etl_pagamentos.py"
        )
        etl_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(etl_mod)
        caminho = Path(etl_mod.ARQUIVO_EXCEL)
    except Exception:
        return True  # não conseguiu verificar — deixa o ETL tentar

    if not caminho.exists():
        log(f"AVISO: Planilha não encontrada: {caminho}")
        return False

    try:
        with open(caminho, "rb") as f:
            f.read(8)  # lê só o cabeçalho para testar acesso
        return True
    except (IOError, OSError, PermissionError) as e:
        log(f"AVISO: Planilha bloqueada ou em uso — {e}")
        log("Aguardando 60 segundos para nova tentativa...")
        import time
        time.sleep(60)
        try:
            with open(caminho, "rb") as f:
                f.read(8)
            log("Planilha disponível após aguardar.")
            return True
        except Exception:
            log("ERRO: Planilha continua bloqueada. ETL abortado.")
            return False


def main():
    inicio = datetime.now()
    log("=== INICIANDO ATUALIZACAO ===")

    # Verifica planilha antes de rodar o ETL
    if not verificar_planilha_disponivel():
        log("ATUALIZACAO ABORTADA — planilha indisponível.")
        sys.exit(1)

    # ETAPA 1 — ETL Pagamentos
    if not executar_etapa("ETAPA 1: ETL PAGAMENTOS", "etl_pagamentos.py"):
        log("ATUALIZACAO ABORTADA — verifique o log acima.")
        sys.exit(1)

    # ETAPA 2 — Usuarios
    if not executar_etapa("ETAPA 2: USUARIOS", "criar_usuarios.py"):
        log("ATUALIZACAO ABORTADA — verifique o log acima.")
        sys.exit(1)

    # ETAPA 3 — ETL Reflexos de Cálculos
    if not executar_etapa("ETAPA 3: ETL REFLEXOS", "etl_reflexos.py"):
        log("ATUALIZACAO ABORTADA — verifique o log acima.")
        sys.exit(1)

    duracao = (datetime.now() - inicio).seconds
    log(f"=== ATUALIZACAO CONCLUIDA em {duracao}s ===")


if __name__ == "__main__":
    main()