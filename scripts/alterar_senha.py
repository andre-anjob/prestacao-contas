import sqlite3
import hashlib
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(BASE_DIR, "database", "pagamentos.db")


def gerar_hash(senha):
    return hashlib.sha256(senha.encode()).hexdigest()


usuario = input("Usuário: ")
nova_senha = input("Nova senha: ")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
UPDATE usuarios
SET senha_hash = ?
WHERE TRIM(usuario) = TRIM(?)
""", (gerar_hash(nova_senha), usuario))

conn.commit()
conn.close()

print("Senha atualizada.")
