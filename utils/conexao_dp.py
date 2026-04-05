import base64
import hashlib
import hmac
import os
import secrets
import unicodedata
from contextlib import contextmanager
from pathlib import Path

import psycopg2
import psycopg2.extras


BASE_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = BASE_DIR / "assets"
PBKDF2_PREFIX = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 390000


def get_base_dir():
    return str(BASE_DIR)


def get_db_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Variavel de ambiente DATABASE_URL nao definida. "
            "Configure o secret no Streamlit Cloud ou no arquivo .env local."
        )
    return url


@contextmanager
def conectar_banco():
    url = get_db_url()
    url = url.split("?")[0]  # Remove qualquer parametro como ?pgbouncer=true
    conn = psycopg2.connect(url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def gerar_hash_legado(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


PBKDF2_PREFIX = "pbkdf2_sha256"
PBKDF2_SEP = ":"

def gerar_hash_seguro(senha, salt=None, iterations=PBKDF2_ITERATIONS):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"{PBKDF2_PREFIX}{PBKDF2_SEP}{iterations}{PBKDF2_SEP}{salt}{PBKDF2_SEP}{digest}"


def verificar_senha(senha, senha_hash):
    if not senha_hash:
        return False

    if senha_hash.startswith(f"{PBKDF2_PREFIX}{PBKDF2_SEP}"):
        try:
            _, iterations, salt, digest = senha_hash.split(PBKDF2_SEP, 3)
        except ValueError:
            return False

        calculado = gerar_hash_seguro(senha, salt=salt, iterations=int(iterations))
        return hmac.compare_digest(calculado, senha_hash)

    return hmac.compare_digest(gerar_hash_legado(senha), senha_hash)


def hash_precisa_migracao(senha_hash):
    return not str(senha_hash or "").startswith(f"{PBKDF2_PREFIX}{PBKDF2_SEP}")


def senha_temporaria(tamanho=12):
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(tamanho))


def validar_nova_senha(senha):
    if len(senha) < 8:
        return False, "A senha precisa ter pelo menos 8 caracteres."

    if senha.isdigit():
        return False, "A senha nao pode conter apenas numeros."

    return True, ""


def atualizar_senha_usuario(usuario, nova_senha, primeiro_acesso=False):
    senha_hash = gerar_hash_seguro(nova_senha)

    with conectar_banco() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE usuarios
            SET senha_hash = %s, primeiro_acesso = %s
            WHERE TRIM(usuario) = TRIM(%s)
            """,
            (senha_hash, 1 if primeiro_acesso else 0, usuario.strip()),
        )
        return cursor.rowcount


def garantir_tabela_usuarios():
    with conectar_banco() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id              SERIAL PRIMARY KEY,
                usuario         TEXT UNIQUE,
                senha_hash      TEXT NOT NULL,
                contratante     TEXT NOT NULL,
                tipo_usuario    TEXT NOT NULL DEFAULT 'cliente',
                primeiro_acesso INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'usuarios'
            """
        )
        colunas = {linha[0] for linha in cursor.fetchall()}

        if "tipo_usuario" not in colunas:
            cursor.execute(
                """
                ALTER TABLE usuarios
                ADD COLUMN tipo_usuario TEXT NOT NULL DEFAULT 'cliente'
                """
            )

        if "primeiro_acesso" not in colunas:
            cursor.execute(
                """
                ALTER TABLE usuarios
                ADD COLUMN primeiro_acesso INTEGER NOT NULL DEFAULT 1
                """
            )


def autenticar_usuario(usuario, senha):
    usuario = usuario.strip()

    if not usuario or not senha:
        return None

    with conectar_banco() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, usuario, contratante, tipo_usuario, primeiro_acesso, senha_hash
            FROM usuarios
            WHERE TRIM(usuario) = TRIM(%s)
            """,
            (usuario,),
        )
        resultado = cursor.fetchone()

        if not resultado:
            return None

        usuario_id, nome_usuario, contratante, tipo_usuario, primeiro_acesso, senha_hash = resultado

        if not verificar_senha(senha, senha_hash):
            return None

        if hash_precisa_migracao(senha_hash):
            cursor.execute(
                "UPDATE usuarios SET senha_hash = %s WHERE id = %s",
                (gerar_hash_seguro(senha), usuario_id),
            )

        return {
            "id": usuario_id,
            "usuario": nome_usuario,
            "contratante": contratante,
            "tipo_usuario": tipo_usuario,
            "primeiro_acesso": bool(primeiro_acesso),
        }


def carregar_pagamentos():
    with conectar_banco() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pagamentos")
        return cursor.fetchall()


def ler_imagem_base64(caminho):
    caminho = Path(caminho)
    if caminho.exists():
        return base64.b64encode(caminho.read_bytes()).decode("utf-8")
    return None


def encontrar_arquivo_asset(*nomes):
    if not ASSETS_DIR.exists():
        return str(ASSETS_DIR / nomes[0])

    arquivos = {arquivo.name.lower(): arquivo for arquivo in ASSETS_DIR.iterdir()}

    for nome in nomes:
        caminho = ASSETS_DIR / nome
        if caminho.exists():
            return str(caminho)

        encontrado = arquivos.get(nome.lower())
        if encontrado:
            return str(encontrado)

    return str(ASSETS_DIR / nomes[0])


def normalizar_texto(texto):
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return "".join(caractere.lower() for caractere in texto if caractere.isalnum())


def resolver_coluna(df, *nomes):
    mapa = {normalizar_texto(coluna): coluna for coluna in df.columns}

    for nome in nomes:
        coluna = mapa.get(normalizar_texto(nome))
        if coluna:
            return coluna

    raise KeyError(f"Coluna nao encontrada entre as opcoes: {nomes}")
