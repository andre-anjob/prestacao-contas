import sqlite3
import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(BASE_DIR, "database", "pagamentos.db")

conn = sqlite3.connect(db_path)
df = pd.read_sql("SELECT usuario, tipo_usuario, primeiro_acesso FROM usuarios WHERE usuario = 'admin'", conn)
print(df)
conn.close()
