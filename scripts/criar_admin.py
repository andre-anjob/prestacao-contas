import sqlite3
import os
import hashlib

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(BASE_DIR, "database", "pagamentos.db")


def gerar_hash(senha):
    return hashlib.sha256(senha.encode()).hexdigest()


conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
INSERT INTO usuarios (usuario, senha_hash, contratante, tipo_usuario, primeiro_acesso)
VALUES (?, ?, ?, ?, ?)
""", (
    "admin",
    gerar_hash("admin123"),
    "ADMIN",
    "admin",
    1
))

conn.commit()
conn.close()

print("Usuário admin criado com sucesso.")
