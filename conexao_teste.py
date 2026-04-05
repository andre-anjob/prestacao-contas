from dotenv import load_dotenv
load_dotenv()

from utils.conexao_dp import conectar_banco

try:
    with conectar_banco() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        total = cursor.fetchone()[0]
        print(f"Conexao OK! Usuarios cadastrados: {total}")
except Exception as e:
    print(f"Erro na conexao: {e}")