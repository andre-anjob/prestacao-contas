import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd

from utils.conexao_dp import conectar_banco, gerar_hash_seguro


def criar_usuarios():
    with conectar_banco() as conn:
        cursor = conn.cursor()

        # Garante estrutura da tabela
        print("Ajustando estrutura da tabela usuarios...")
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
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'usuarios'
            """
        )
        colunas = {linha[0] for linha in cursor.fetchall()}

        if "tipo_usuario" not in colunas:
            cursor.execute(
                "ALTER TABLE usuarios ADD COLUMN tipo_usuario TEXT NOT NULL DEFAULT 'cliente'"
            )

        if "primeiro_acesso" not in colunas:
            cursor.execute(
                "ALTER TABLE usuarios ADD COLUMN primeiro_acesso INTEGER NOT NULL DEFAULT 1"
            )

        print("Estrutura validada.")

        # Carrega contratantes da base de pagamentos
        print("Carregando contratantes da base...")
        df = pd.read_sql('SELECT DISTINCT "Contratante" FROM pagamentos', conn)
        print(f"Total de contratantes encontrados: {len(df)}")

        # Insere usuarios clientes
        inseridos = 0
        ignorados = 0
        for _, row in df.iterrows():
            contratante = row["Contratante"]
            if pd.isna(contratante):
                continue

            usuario = str(contratante).strip()
            senha_hash = gerar_hash_seguro("123456")

            cursor.execute(
                """
                INSERT INTO usuarios (usuario, senha_hash, contratante, tipo_usuario, primeiro_acesso)
                VALUES (%s, %s, %s, 'cliente', 1)
                ON CONFLICT (usuario) DO NOTHING
                """,
                (usuario, senha_hash, usuario),
            )

            if cursor.rowcount > 0:
                inseridos += 1
            else:
                ignorados += 1

        print(f"Usuarios clientes: {inseridos} inseridos, {ignorados} ja existiam.")

        # Garante usuario admin
        print("Garantindo usuario admin...")
        senha_admin = gerar_hash_seguro("admin123")
        cursor.execute(
            """
            INSERT INTO usuarios (usuario, senha_hash, contratante, tipo_usuario, primeiro_acesso)
            VALUES (%s, %s, 'ADMIN', 'admin', 1)
            ON CONFLICT (usuario) DO NOTHING
            """,
            ("admin", senha_admin),
        )

        if cursor.rowcount > 0:
            print("Admin criado.")
        else:
            print("Admin ja existe, mantido sem alteracao.")

    print("Processo finalizado com sucesso.")


if __name__ == "__main__":
    criar_usuarios()
    