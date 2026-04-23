import os
import sys
import time
from io import BytesIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from utils.conexao_dp import (  # noqa: E402
    atualizar_senha_usuario,
    autenticar_usuario,
    conectar_banco,
    encontrar_arquivo_asset,
    ler_imagem_base64,
    normalizar_texto,
    resolver_coluna,
    validar_nova_senha,
)


st.set_page_config(
    page_title="Portal de Prestacao de Contas",
    page_icon=":bar_chart:",
    layout="wide",
)

LOGO_PATH = encontrar_arquivo_asset("logo.png", "Logo.png")
LOGO_EMPRESA_PATH = encontrar_arquivo_asset("logo_empresa.png")
BOTAO_DOWNLOAD_PATH = encontrar_arquivo_asset("botao_download.png")
CSV_ICON_PATH = encontrar_arquivo_asset("csv.png")
EXCEL_ICON_PATH = encontrar_arquivo_asset("excel.png")
PDF_ICON_PATH = encontrar_arquivo_asset("pdf.png")


def formatar_real(valor):
    if pd.isna(valor):
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_csv(df):
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def gerar_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


def gerar_pdf(df):
    output = BytesIO()
    pdf = SimpleDocTemplate(output, pagesize=landscape(A4))

    if df.empty:
        dados = [["Mensagem"], ["Nenhum dado disponivel para exportacao."]]
    else:
        dados = [df.columns.tolist()] + df.astype(str).values.tolist()

    tabela = Table(dados, repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b3c88")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )

    pdf.build([tabela])
    return output.getvalue()


COLUNAS_TABELA_DESEJADAS = [
    ("Contratante", ("Contratante",)),
    ("Tipo de Titulo", ("Tipo de Titulo",)),
    ("Tipo de Acordo", ("Tipo de Acordo",)),
    ("CPF", ("CPF",)),
    ("Devedor", ("Devedor",)),
    ("Titulos Negociados", ("Titulos Negociados",)),
    ("Data Venc", ("Data Venc",)),
    ("Data Acordo", ("Data Acordo",)),
    ("Data Pagto", ("Data Pagto",)),
    ("Dias", ("Dias",)),
    ("N Pres", ("N Pres",)),
    ("Q Pres", ("Q Pres",)),
    ("V. Princ", ("V. Princ",)),
    ("V. Juros Contrat", ("V. Juros Contrat",)),
    ("V. Juros Asses", ("V. Juros Asses",)),
    ("V. Multa", ("V. Multa",)),
    ("V. Honor", ("V. Honor",)),
    ("V. Receb", ("V. Receb",)),
    ("V. Repasse", ("V. Repasse",)),
    ("V. Comissão", ("V. Comissão", "V. Comissao", "V. ComissÃ£o")),
    ("Tipo de Baixa", ("Tipo de Baixa",)),
]


@st.cache_data(show_spinner=False)
def carregar_dados():
    import os
    from sqlalchemy import create_engine
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    database_url = database_url.split("?")[0]
    engine = create_engine(database_url)
    return pd.read_sql("SELECT * FROM pagamentos", engine)

def inicializar_sessao():
    st.session_state.setdefault("logado", False)
    st.session_state.setdefault("usuario", "")
    st.session_state.setdefault("usuario_id", None)
    st.session_state.setdefault("contratante", "")
    st.session_state.setdefault("tipo_usuario", "")
    st.session_state.setdefault("primeiro_acesso", False)
    st.session_state.setdefault("mostrar_carregamento_dashboard", False)
    st.session_state.setdefault("dashboard_df_preparado", None)
    st.session_state.setdefault("dashboard_colunas_preparadas", None)
    st.session_state.setdefault("busca_contratante", "")
    st.session_state.setdefault("contratantes_selecionados", [])
    st.session_state.setdefault("contratantes_disponiveis_cache", ())


def obter_colunas_tabela(df):
    colunas_exibir = []

    colunas_valor = {
        "V. Princ", "V. Juros Contrat", "V. Juros Asses",
        "V. Multa", "V. Honor", "V. Receb", "V. Repasse", "V. Comissão"
    }

    def formatar_cpf_cnpj(valor):
        if pd.isna(valor):
            return ""
        numero = str(int(float(valor))) if str(valor).replace(".", "").isdigit() else str(valor)
        numero = numero.strip().replace(".", "").replace("-", "").replace("/", "")
        numero = numero.zfill(14) if len(numero) > 11 else numero.zfill(11)
        if len(numero) == 14:
            return f"{numero[:2]}.{numero[2:5]}.{numero[5:8]}/{numero[8:12]}-{numero[12:]}"
        elif len(numero) == 11:
            return f"{numero[:3]}.{numero[3:6]}.{numero[6:9]}-{numero[9:]}"
        return numero

    for nome_exibicao, aliases in COLUNAS_TABELA_DESEJADAS:
        try:
            coluna_real = resolver_coluna(df, *aliases)
        except KeyError:
            continue

        if coluna_real not in df.columns:
            continue

        serie = df[coluna_real].rename(nome_exibicao)

        if nome_exibicao in colunas_valor:
            serie = pd.to_numeric(serie, errors="coerce")
            serie = serie.apply(
                lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                if pd.notna(v) else ""
            )
        elif nome_exibicao == "CPF":
            serie = serie.apply(formatar_cpf_cnpj)

        colunas_exibir.append(serie)

    if not colunas_exibir:
        return df.iloc[:, 0:0].copy()

    return pd.concat(colunas_exibir, axis=1)


def aplicar_estilos():
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

            @keyframes floatGlow {
                0% { transform: scale(1) translateY(0px); box-shadow: 0 16px 40px rgba(10, 31, 102, 0.26); }
                50% { transform: scale(1.045) translateY(-4px); box-shadow: 0 24px 56px rgba(27, 60, 136, 0.34); }
                100% { transform: scale(1) translateY(0px); box-shadow: 0 16px 40px rgba(10, 31, 102, 0.26); }
            }

            @keyframes pulseLoader {
                0% { transform: scale(0.96); opacity: 0.7; }
                50% { transform: scale(1); opacity: 1; }
                100% { transform: scale(0.96); opacity: 0.7; }
            }

            html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
                min-height: 100vh;
                background:
                    radial-gradient(circle at top left, rgba(218, 223, 232, 0.9), transparent 24%),
                    radial-gradient(circle at top right, rgba(239, 241, 245, 0.95), transparent 26%),
                    linear-gradient(180deg, #eef1f5 0%, #f8f9fb 52%, #ffffff 100%);
                background-size: cover;
                background-repeat: no-repeat;
                background-attachment: fixed;
            }

            [data-testid="stAppViewContainer"] > .main { background: transparent; }
            [data-testid="stAppViewContainer"] > .main > div { padding-top: 0 !important; }
            [data-testid="stVerticalBlock"] { gap: 0 !important; }
            .main { padding-top: 0 !important; }

            .block-container {
                padding: 1rem 1.25rem 1.25rem 1.25rem !important;
                min-height: 100vh;
                display: block !important;
            }

            /* ===== TOPO DO DASHBOARD ===== */
            .bloco-logos-dashboard {
                background: linear-gradient(135deg, #000040 0%, #0a1f66 55%, #1b3c88 100%);
                padding: 6px 12px;
                border-radius: 12px;
                width: 180px;
                height: 80px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                box-shadow: 0 6px 12px rgba(0, 0, 0, 0.16);
                margin-top: 2px;
                margin-left: 4px;
            }

            .bloco-logos-dashboard,
            .bloco-logos-dashboard * { color: #f8fbff !important; }

            .logo-principal {
                max-height: 50px;
                max-width: 136px;
                object-fit: contain;
            }

            .logo-secundaria {
                max-height: 26px;
                max-width: 78px;
                object-fit: contain;
            }

            .topo-dashboard-wrap {
                padding: 1.5rem 0 1rem 0;
            }

            .topo-dashboard-title {
                margin: 0;
                line-height: 1.1;
                font-size: clamp(2rem, 2.3vw, 2.8rem);
                font-weight: 700;
                color: #10213f !important;
                letter-spacing: -0.02em;
            }

            .topo-dashboard-subtitle {
                margin-top: 0.45rem;
                color: #4b5b78;
                font-size: 0.9rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                flex-wrap: wrap;
            }

            .topo-badge {
                background: linear-gradient(135deg, #0a1f66, #1b3c88);
                border-radius: 20px;
                padding: 2px 10px;
                font-size: 0.75rem;
                color: #ffffff !important;
                font-weight: 500;
            }

            /* ===== LOGIN ===== */
            [data-testid="stAppViewContainer"]:has(.login-stage-marker),
            [data-testid="stAppViewContainer"]:has(.login-stage-marker) > .main,
            [data-testid="stAppViewContainer"]:has(.login-stage-marker) > .main > div,
            [data-testid="stAppViewContainer"]:has(.login-stage-marker) .block-container {
                background: linear-gradient(135deg, #060d1f, #0d1e3d) !important;
            }

            [data-testid="stAppViewContainer"]:has(.login-stage-marker) .block-container {
                padding: 0 !important;
                min-height: 100vh;
            }

            [data-testid="stAppViewContainer"]:has(.login-stage-marker) .bloco-logos-dashboard {
                display: none !important;
            }

            .login-stage-marker { display: none; }

            .login-shell {
                position: relative;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 100%;
                padding: 0;
            }

            div[data-testid="stVerticalBlock"]:has(.login-stage-marker) {
                position: relative;
                overflow: hidden;
                background:
                    radial-gradient(ellipse 60% 50% at 20% 30%, rgba(30, 80, 180, 0.35), transparent 70%),
                    radial-gradient(ellipse 50% 60% at 80% 70%, rgba(180, 80, 20, 0.20), transparent 65%),
                    radial-gradient(ellipse 80% 80% at 50% 50%, rgba(10, 25, 60, 0.80), transparent 100%),
                    linear-gradient(135deg, #060d1f 0%, #0d1e3d 40%, #111827 100%);
                border: 0;
                border-radius: 0;
                box-shadow: none;
                padding: 0;
                width: 100%;
                max-width: none;
                min-height: 100vh;
                margin: 0;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            div[data-testid="stVerticalBlock"]:has(.login-stage-marker)::before,
            div[data-testid="stVerticalBlock"]:has(.login-stage-marker)::after {
                content: "";
                position: absolute;
                border-radius: 999px;
                filter: blur(42px);
                pointer-events: none;
                z-index: 0;
            }

            div[data-testid="stVerticalBlock"]:has(.login-stage-marker)::before {
                width: 520px; height: 520px;
                background: radial-gradient(circle, rgba(30, 80, 180, 0.40), transparent 62%);
                top: -170px; left: -170px;
                animation: float 8s ease-in-out infinite;
            }

            div[data-testid="stVerticalBlock"]:has(.login-stage-marker)::after {
                width: 700px; height: 700px;
                background: radial-gradient(circle, rgba(180, 80, 20, 0.25), transparent 66%);
                bottom: -280px; right: -240px;
                animation: float 8s ease-in-out infinite;
                animation-delay: -3s;
            }

            @keyframes float {
                0%   { transform: scale(1) translateY(0px); }
                50%  { transform: scale(1.05) translateY(-20px); }
                100% { transform: scale(1) translateY(0px); }
            }

            div[data-testid="stVerticalBlock"]:has(.login-stage-marker) > div {
                position: relative; z-index: 1; width: 100%;
            }

            .login-shell::before {
                content: "";
                position: absolute;
                width: 460px; height: 460px;
                left: 50%; top: 42%;
                transform: translate(-50%, -50%);
                background: radial-gradient(circle, rgba(86, 125, 208, 0.24), transparent 60%);
                filter: blur(48px);
                border-radius: 999px;
                pointer-events: none; z-index: 0;
            }

            .login-shell::after {
                content: "";
                position: absolute;
                width: 300px; height: 300px;
                left: 28%; bottom: 14%;
                background: radial-gradient(circle, rgba(120, 151, 226, 0.2), transparent 60%);
                filter: blur(44px);
                border-radius: 999px;
                pointer-events: none; z-index: 0;
            }

            .login-form-col { width: 100%; max-width: 420px; margin: 0 auto; }
            .login-form-header { margin-bottom: 0.95rem; display: flex; justify-content: center; }
            .login-form-panel { position: relative; width: 100%; }

            .login-card-logo {
                width: 100%;
                max-width: 126px;
                object-fit: contain;
                background: rgba(255, 255, 255, 0.08);
                padding: 0.55rem 0.75rem;
                border-radius: 12px;
            }

            [data-testid="stVerticalBlock"]:has(.login-stage-marker) div[data-testid="stForm"] {
                border-radius: 18px;
                padding: 2rem 1.75rem 1.45rem 1.75rem;
                background: linear-gradient(135deg, #0a1f44, #1b3c88);
                border: 1px solid rgba(255, 255, 255, 0.12);
                backdrop-filter: blur(12px);
                box-shadow: 0 15px 40px rgba(0, 0, 0, 0.15);
            }

            [data-testid="stVerticalBlock"]:has(.login-stage-marker) div[data-testid="stForm"] > div:first-child { gap: 0.2rem; }

            [data-testid="stVerticalBlock"]:has(.login-stage-marker) div[data-testid="stForm"] label {
                color: rgba(255, 255, 255, 0.82) !important;
                font-weight: 600 !important;
                font-size: 0.9rem !important;
            }

            [data-testid="stVerticalBlock"]:has(.login-stage-marker) div[data-testid="stForm"] .stTextInput { margin-bottom: 0.28rem; }

            [data-testid="stVerticalBlock"]:has(.login-stage-marker) div[data-testid="stTextInput"] input {
                background: #ffffff !important;
                color: #0f172a !important;
                border: 1px solid rgba(255, 255, 255, 0.24) !important;
            }

            [data-testid="stVerticalBlock"]:has(.login-stage-marker) div[data-testid="stTextInput"] input::placeholder { color: #7b879c !important; }

            [data-testid="stVerticalBlock"]:has(.login-stage-marker) div[data-testid="stTextInput"] input:focus {
                border: 1px solid #bfdbfe !important;
                box-shadow: 0 0 0 1px #bfdbfe, 0 0 0 5px rgba(191, 219, 254, 0.18) !important;
            }

            /* ===== METRICAS ===== */
            div[data-testid="stMetric"],
            div[data-testid="stMetric"] * { color: #f8fbff !important; }

            div[data-testid="stMetric"] {
                background: linear-gradient(135deg, #0d2260, #1b3c88);
                border: 1px solid rgba(100, 149, 255, 0.2);
                padding: 18px 20px;
                border-radius: 16px;
                box-shadow: 0 8px 24px rgba(10, 31, 102, 0.15);
                transition: transform 0.2s ease, box-shadow 0.2s ease;
            }

            div[data-testid="stMetric"]:hover {
                transform: translateY(-2px);
                box-shadow: 0 12px 32px rgba(10, 31, 102, 0.22);
            }

            div[data-testid="stMetricLabel"] {
                color: rgba(180, 210, 255, 0.85) !important;
                font-size: 0.82rem !important;
                font-weight: 500 !important;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            div[data-testid="stMetricValue"] {
                color: #ffffff !important;
                font-size: 26px !important;
                font-weight: 700 !important;
                letter-spacing: -0.02em;
            }

            /* ===== FILTROS ===== */
            .filtros-wrap {
                background: rgba(255, 255, 255, 0.7);
                border: 1px solid rgba(27, 60, 136, 0.1);
                border-radius: 16px;
                padding: 1rem 1.2rem 1rem 1.2rem;
                margin-bottom: 1rem;
                box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05);
            }

            .filtros-titulo {
                font-size: 0.78rem;
                font-weight: 600;
                color: #4b5b78;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                margin-bottom: 1rem;
            }
            div[data-testid="stTextInput"] input {
                border: 1px solid rgba(154, 166, 178, 0.22) !important;
                border-radius: 12px !important;
                box-shadow: none !important;
                min-height: 2.85rem !important;
                background: rgba(255, 255, 255, 0.92) !important;
                color: #0f172a !important;
                font-size: 0.95rem !important;
                padding-top: 0.32rem !important;
                padding-bottom: 0.32rem !important;
            }

            div[data-testid="stTextInput"] input:focus {
                border: 1px solid #1b3c88 !important;
                box-shadow: 0 0 0 1px #1b3c88, 0 0 0 6px rgba(27, 60, 136, 0.12) !important;
            }

            div[data-testid="stTextInput"] input::placeholder { color: #7f8aa3 !important; }
            div[data-testid="stDateInputField"] { border-radius: 10px !important; }

            div[data-testid="stDateInput"] label,
            div[data-testid="stDateInput"] p { color: #10213f !important; }

            /* ===== EXPANDER ===== */
            div[data-testid="stExpander"] summary,
            div[data-testid="stExpander"] summary p,
            div[data-testid="stExpander"] label,
            div[data-testid="stExpander"] .stCaption,
            div[data-testid="stExpander"] [data-testid="stMarkdownContainer"] p,
            div[data-testid="stExpander"] [data-testid="stMarkdownContainer"] label,
            div[data-testid="stExpanderDetails"] label,
            div[data-testid="stExpanderDetails"] p,
            div[data-testid="stExpanderDetails"] span,
            div[data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"] p,
            div[data-testid="stExpanderDetails"] [data-testid="stCaptionContainer"] { color: #f8fbff !important; }

            div[data-testid="stExpander"] {
                background: linear-gradient(135deg, #17336f, #1b3c88);
                border: 1px solid rgba(27, 60, 136, 0.18);
                border-radius: 16px;
                padding: 0.2rem 0.3rem;
                box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
            }

            div[data-testid="stExpander"] summary { border-radius: 12px; }
            div[data-testid="stExpanderDetails"] { padding-top: 0.4rem; }

            /* ===== BOTOES ===== */
            div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] > button {
                width: 100%;
                border-radius: 12px;
                font-weight: 600;
                min-height: 2.8rem;
                border: 0 !important;
                color: #1b3c88 !important;
                background: #ffffff !important;
                box-shadow: 0 12px 28px rgba(4, 15, 42, 0.18);
                transition: transform 0.18s ease, box-shadow 0.18s ease;
                margin-top: 0.6rem;
            }

            div[data-testid="stForm"] div[data-testid="stFormSubmitButton"] > button:hover {
                transform: translateY(-1px);
                color: #10213f !important;
                box-shadow: 0 16px 32px rgba(4, 15, 42, 0.22);
            }

            button[data-testid="stBaseButton-secondary"] {
                background: linear-gradient(135deg, #c62828, #e53935) !important;
                color: #f8fbff !important;
                border: 1px solid #b71c1c !important;
                font-weight: 600 !important;
                border-radius: 10px !important;
                transition: opacity 0.2s ease !important;
                min-height: 2rem !important;
                height: 2rem !important;
                padding: 0 1rem !important;
                font-size: 0.85rem !important;
                width: auto !important;
            }

            button[data-testid="stBaseButton-secondary"]:hover,
            button[data-testid="stBaseButton-secondary"]:focus,
            button[data-testid="stBaseButton-secondary"]:active {
                opacity: 0.8 !important;
                background: linear-gradient(135deg, #c62828, #e53935) !important;
                color: #f8fbff !important;
            }

            button[data-testid="stBaseButton-secondary"] * {
                color: #f8fbff !important;
            }
                        /* ===== GRAFICO ===== */
            .grafico-card {
                margin-top: 0.35rem;
                margin-bottom: 0.4rem;
                padding: 0.85rem 0.85rem 0.35rem 0.85rem;
                border-radius: 18px;
                background: rgba(255, 255, 255, 0.72);
                border: 1px solid rgba(27, 60, 136, 0.08);
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
            }

            /* ===== TABELA ===== */
            .tabela-card {
                margin-top: 0.65rem;
                padding: 0.9rem 0.9rem 0.5rem 0.9rem;
                border-radius: 18px;
                background: rgba(255, 255, 255, 0.84);
                border: 1px solid rgba(27, 60, 136, 0.08);
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
                position: relative;
                overflow: visible;
            }

            .tabela-header {
                display: block;
                margin-bottom: 0.35rem;
                padding-bottom: 0.95rem;
                border-bottom: 1px solid rgba(27, 60, 136, 0.08);
                position: relative;
            }

            .tabela-header-titulo { color: #10213f; font-size: 1.02rem; font-weight: 700; letter-spacing: -0.01em; }
            .tabela-header-subtitulo { color: #5b6b86; font-size: 0.84rem; margin-top: 0.12rem; }

            .tabela-acoes {
                display: flex;
                justify-content: flex-end;
                align-items: center;
                gap: 0.35rem;
                position: relative;
                width: fit-content;
                margin-left: auto;
                margin-top: -2.15rem;
                margin-right: 0.15rem;
                margin-bottom: 0.3rem;
                z-index: 8;
            }

            .tabela-acoes [data-testid="stPopover"] { width: 100%; display: flex; justify-content: flex-end; }
            .tabela-acoes [data-testid="stPopover"] > div { width: 100%; display: flex; justify-content: flex-end; }
            
            [data-testid="stPopover"] button {
                background-color: #1b3c88 !important;
                color: #f8fbff !important;
                font-weight: 600 !important;
                border-radius: 12px !important;
                border: 1px solid rgba(27, 60, 136, 0.12) !important;
                transition: opacity 0.2s ease !important;
            }

            [data-testid="stPopover"] button:hover,
            [data-testid="stPopover"] button:focus,
            [data-testid="stPopover"] button:active {
                opacity: 0.8 !important;
                background-color: #1b3c88 !important;
                color: #f8fbff !important;
            }

            [data-testid="stPopover"] button p,
            [data-testid="stPopover"] button span,
            [data-testid="stPopover"] button * {
                color: #f8fbff !important;
            }
            .exportacao-popover-titulo { color: #10213f; font-size: 0.96rem; font-weight: 700; margin-bottom: 0.2rem; }
            .exportacao-popover-subtitulo { color: #5b6b86; font-size: 0.82rem; line-height: 1.45; margin-bottom: 0.7rem; }

            .exportacao-icone-wrap {
                display: flex; align-items: center; justify-content: center;
                width: 44px; height: 44px; border-radius: 12px;
                background: rgba(255, 255, 255, 0.84);
                border: 1px solid rgba(27, 60, 136, 0.08);
            }

            .exportacao-icone { width: 26px; height: 26px; object-fit: contain; }

            .tabela-card [data-testid="stElementToolbar"] {
                display: none !important; visibility: hidden !important;
                opacity: 0 !important; pointer-events: none !important;
            }

            .tabela-card div[data-testid="stDataFrame"] { margin-top: -0.1rem; }

            /* ===== LOADER ===== */
            .dashboard-loader-wrap {
                min-height: calc(100vh - 2rem);
                display: flex; align-items: center; justify-content: center;
            }

            .dashboard-loader-card {
                width: min(420px, 100%);
                padding: 2rem 1.8rem;
                border-radius: 24px;
                background: rgba(8, 14, 34, 0.58);
                border: 1px solid rgba(180, 201, 255, 0.14);
                box-shadow: 0 18px 44px rgba(2, 8, 23, 0.22);
                backdrop-filter: blur(12px);
                text-align: center;
            }

            .dashboard-loader-dot {
                width: 56px; height: 56px;
                margin: 0 auto 1rem auto;
                border-radius: 999px;
                background: radial-gradient(circle at 35% 35%, #60a5fa, #1d4ed8 58%, #1b3c88 100%);
                animation: pulseLoader 1.5s ease-in-out infinite;
                box-shadow: 0 0 0 10px rgba(29, 78, 216, 0.08);
            }

            .dashboard-loader-title { color: #f8fbff; font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; }
            .dashboard-loader-subtitle { color: #93a4c8; font-size: 0.95rem; margin-top: 0.45rem; line-height: 1.55; }

            /* ===== RESPONSIVE ===== */
            @media (max-width: 980px) {
                .topo-dashboard-outer { border-radius: 0 0 14px 14px; padding: 0.75rem 1rem; }
                .topo-dashboard-title { font-size: 1.1rem; }
                .tabela-acoes { margin-top: -1.55rem; margin-right: 0; }
                .tabela-acoes [data-testid="stPopover"] button { min-width: 138px; }

                div[data-testid="stVerticalBlock"]:has(.login-stage-marker) {
                    width: 100%; margin: 0; padding: 0; min-height: auto; display: block;
                }

                div[data-testid="stVerticalBlock"]:has(.login-stage-marker)::before {
                    width: 320px; height: 320px; top: -100px; left: -100px;
                }

                div[data-testid="stVerticalBlock"]:has(.login-stage-marker)::after {
                    width: 380px; height: 380px; right: -150px; bottom: -180px;
                }

                .login-shell::before { width: 280px; height: 280px; }
                .login-shell::after { width: 180px; height: 180px; }
                .login-form-col { max-width: none; margin: 0 auto; }
                .login-shell { min-height: 100vh; padding: 1.5rehm 1rem; }
            }

            .tabela-acoes [data-testid="stPopover"] button:hover,
            .tabela-acoes [data-testid="stPopover"] button:focus,
            .tabela-acoes [data-testid="stPopover"] button:active {
                background: linear-gradient(135deg, #17336f, #1b3c88) !important;
                color: #f8fbff !important;
                filter: brightness(1.2) !important;
            }
            [data-testid="stCaptionContainer"] p,
            [data-testid="stCaptionContainer"] {
                color: #10213f !important;
                font-size: 0.82rem !important;
            }

            /* ===== AGGRID — FORÇAR MODO CLARO ===== */
            .ag-theme-alpine {
                --ag-background-color: #ffffff !important;
                --ag-odd-row-background-color: #f4f6fb !important;
                --ag-row-hover-color: #e8edf8 !important;
                --ag-border-color: rgba(27, 60, 136, 0.12) !important;
                --ag-secondary-border-color: rgba(27, 60, 136, 0.06) !important;
                --ag-foreground-color: #10213f !important;
                --ag-secondary-foreground-color: #4b5b78 !important;
                --ag-data-color: #10213f !important;
                --ag-header-background-color: #1b3c88 !important;
                --ag-header-foreground-color: #f8fbff !important;
                --ag-header-column-separator-color: rgba(255,255,255,0.15) !important;
                --ag-header-column-resize-handle-color: rgba(255,255,255,0.3) !important;
                --ag-control-panel-background-color: #ffffff !important;
                --ag-subheader-background-color: #f0f3fa !important;
                --ag-subheader-toolbar-background-color: #f0f3fa !important;
                --ag-input-focus-border-color: #1b3c88 !important;
                --ag-input-border-color: rgba(27, 60, 136, 0.25) !important;
                --ag-checkbox-background-color: #ffffff !important;
                --ag-checkbox-checked-color: #1b3c88 !important;
                --ag-range-selection-border-color: #1b3c88 !important;
                --ag-selected-row-background-color: #dbe4f5 !important;
                --ag-modal-overlay-background-color: rgba(255,255,255,0.85) !important;
                --ag-popup-shadow: 0 8px 24px rgba(15,23,42,0.12) !important;
                color-scheme: light !important;
            }

            .ag-theme-alpine .ag-root-wrapper {
                border-radius: 10px !important;
                overflow: hidden;
                border: 1px solid rgba(27, 60, 136, 0.12) !important;
            }

            .ag-theme-alpine .ag-header {
                background: linear-gradient(135deg, #0a1f66, #1b3c88) !important;
            }

            .ag-theme-alpine .ag-header-cell-text {
                color: #f8fbff !important;
                font-weight: 600 !important;
                font-size: 0.8rem !important;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .ag-theme-alpine .ag-icon {
                color: #f8fbff !important;
            }

            .ag-theme-alpine .ag-floating-filter .ag-icon {
                color: #1b3c88 !important;
            }

            .ag-theme-alpine .ag-floating-filter {
                background-color: #f0f3fa !important;
            }

            .ag-theme-alpine .ag-cell {
                color: #10213f !important;
                font-size: 0.84rem !important;
            }

            .ag-theme-alpine .ag-row {
                color: #10213f !important;
            }

            .ag-theme-alpine .ag-popup,
            .ag-theme-alpine .ag-popup-child,
            .ag-theme-alpine .ag-filter,
            .ag-theme-alpine .ag-menu {
                background-color: #ffffff !important;
                color: #10213f !important;
            }

            .ag-theme-alpine .ag-filter *,
            .ag-theme-alpine .ag-menu *,
            .ag-theme-alpine .ag-popup * {
                color: #10213f !important;
            }

            .ag-theme-alpine .ag-picker-field-wrapper,
            .ag-theme-alpine .ag-select .ag-picker-field-display,
            .ag-theme-alpine .ag-input-field-input {
                background-color: #ffffff !important;
                color: #10213f !important;
            }

            .ag-theme-alpine .ag-paging-panel {
                background-color: #ffffff !important;
                color: #4b5b78 !important;
                border-top: 1px solid rgba(27, 60, 136, 0.08) !important;
            }

        </style>
        """,
        unsafe_allow_html=True,
    )


def renderizar_bloco_logos(classe_css):
    logo_1 = ler_imagem_base64(LOGO_PATH)
    logo_2 = ler_imagem_base64(LOGO_EMPRESA_PATH)

    if not (logo_1 or logo_2):
        return

    html = f'<div class="{classe_css}">'
    if logo_2:
        html += f'<img src="data:image/png;base64,{logo_2}" class="logo-secundaria">'
    if logo_1:
        html += f'<img src="data:image/png;base64,{logo_1}" class="logo-principal">'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def renderizar_acao_exportacao(label, nome_arquivo, dados, icone_path, chave):
    icone_base64 = ler_imagem_base64(icone_path) if icone_path else None
    col_icone, col_botao = st.columns([0.22, 0.78], gap="small", vertical_alignment="center")

    with col_icone:
        if icone_base64:
            st.markdown(
                f"""
                <div class="exportacao-icone-wrap">
                    <img src="data:image/png;base64,{icone_base64}" class="exportacao-icone" alt="{label}">
                </div>
                """,
                unsafe_allow_html=True,
            )

    with col_botao:
        st.download_button(
            f"Baixar {label}",
            dados,
            nome_arquivo,
            key=chave,
            use_container_width=True,
        )


def renderizar_login():
    with st.container():
        st.markdown('<div class="login-stage-marker"></div>', unsafe_allow_html=True)
        _, col_form, _ = st.columns([1.15, 0.7, 1.15], gap="large")

        with col_form:
            with st.form("login_form", clear_on_submit=False):
                logo_central = ler_imagem_base64(LOGO_PATH)
                if logo_central:
                    st.markdown(
                        f"""
                        <div class="login-form-panel">
                            <div class="login-form-header">
                                <img src="data:image/png;base64,{logo_central}" class="login-card-logo" alt="Logo">
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                usuario = st.text_input("Usuario", key="login_usuario", placeholder="Digite seu usuario")
                senha = st.text_input("Senha", type="password", key="login_senha", placeholder="Digite sua senha")
                st.markdown('<div class="botao-entrar-login">', unsafe_allow_html=True)
                submitted = st.form_submit_button("Entrar no portal", use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        auth = autenticar_usuario(usuario, senha)
        if auth:
            st.session_state["logado"] = True
            st.session_state["usuario_id"] = auth["id"]
            st.session_state["usuario"] = auth["usuario"]
            st.session_state["contratante"] = auth["contratante"]
            st.session_state["tipo_usuario"] = auth["tipo_usuario"]
            st.session_state["primeiro_acesso"] = auth["primeiro_acesso"]
            st.session_state["mostrar_carregamento_dashboard"] = True
            st.rerun()
        else:
            st.error("Usuario ou senha invalidos.")


def renderizar_primeiro_acesso():
    st.title("Troca obrigatoria de senha")
    st.info("Defina uma nova senha para continuar.")

    with st.form("troca_senha_form"):
        nova_senha = st.text_input("Nova senha", type="password")
        confirmar_senha = st.text_input("Confirmar nova senha", type="password")
        submitted = st.form_submit_button("Salvar nova senha", use_container_width=True)

    if not submitted:
        return

    if nova_senha != confirmar_senha:
        st.error("As senhas informadas nao coincidem.")
        return

    senha_valida, mensagem = validar_nova_senha(nova_senha)
    if not senha_valida:
        st.error(mensagem)
        return

    linhas_afetadas = atualizar_senha_usuario(
        st.session_state["usuario"],
        nova_senha,
        primeiro_acesso=False,
    )
    if not linhas_afetadas:
        st.error("Nao foi possivel atualizar a senha do usuario atual.")
        return

    st.session_state["primeiro_acesso"] = False
    st.success("Senha atualizada com sucesso.")
    st.rerun()


def renderizar_carregamento_dashboard():
    st.markdown(
        """
        <div class="dashboard-loader-wrap">
            <div class="dashboard-loader-card">
                <div class="dashboard-loader-dot"></div>
                <div class="dashboard-loader-title">Carregando portal</div>
                <div class="dashboard-loader-subtitle">
                    Estamos preparando seus indicadores, filtros e dados financeiros.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.spinner("Carregando indicadores e dados do portal..."):
        time.sleep(0.35)
        preparar_dataframe()
    st.session_state["mostrar_carregamento_dashboard"] = False
    st.rerun()


def preparar_dataframe():
    if (
        st.session_state.get("dashboard_df_preparado") is not None
        and st.session_state.get("dashboard_colunas_preparadas") is not None
    ):
        return (
            st.session_state["dashboard_df_preparado"].copy(),
            dict(st.session_state["dashboard_colunas_preparadas"]),
        )

    try:
        df = carregar_dados()
    except Exception as exc:
        st.error(f"Falha ao carregar os dados do portal: {exc}")
        st.stop()

    if df.empty:
        return df, {}

    try:
        colunas = {
            "contratante": resolver_coluna(df, "Contratante"),
            "valor_principal": resolver_coluna(df, "V. Receb"),
            "valor_repasse": resolver_coluna(df, "V. Repasse"),
            "valor_comissao": resolver_coluna(df, "V. Comissao", "V. Comissão", "V. ComissÃ£o"),
            "data_pagto": resolver_coluna(df, "Data Pagto"),
        }
    except KeyError as exc:
        st.error(str(exc))
        st.stop()

    df[colunas["valor_principal"]] = pd.to_numeric(df[colunas["valor_principal"]], errors="coerce")
    df[colunas["valor_repasse"]] = pd.to_numeric(df[colunas["valor_repasse"]], errors="coerce")
    df[colunas["valor_comissao"]] = pd.to_numeric(df[colunas["valor_comissao"]], errors="coerce")
    df[colunas["data_pagto"]] = pd.to_datetime(df[colunas["data_pagto"]], errors="coerce")
    df = df.dropna(subset=[colunas["data_pagto"]]).copy()
    st.session_state["dashboard_df_preparado"] = df.copy()
    st.session_state["dashboard_colunas_preparadas"] = dict(colunas)
    return df, colunas


def renderizar_topo(data_atualizacao=None):
    col_logo, col_titulo, col_sair = st.columns([1.2, 5.2, 1.0], vertical_alignment="center")

    usuario = st.session_state.get("usuario", "")
    tipo = st.session_state.get("tipo_usuario", "")
    badge_tipo = "Administrador" if tipo == "admin" else "Cliente"

    data_str = ""
    if data_atualizacao:
        data_str = f'<span class="topo-badge">Dados de {data_atualizacao}</span>'

    with col_logo:
        renderizar_bloco_logos("bloco-logos-dashboard")

    with col_titulo:
        st.markdown(
            f"""
            <div class="topo-dashboard-wrap">
                <h1 class="topo-dashboard-title">Portal de Prestacao de Contas</h1>
                <div class="topo-dashboard-subtitle">
                    <span>Usuario: <strong>{usuario}</strong></span>
                    <span class="topo-badge">{badge_tipo}</span>
                    {data_str}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_sair:
        st.markdown('<div class="botao-sair-vermelho">', unsafe_allow_html=True)
        if st.button("Sair", use_container_width=True):
            for chave in (
                "logado", "usuario", "usuario_id", "contratante",
                "tipo_usuario", "primeiro_acesso",
                "mostrar_carregamento_dashboard",
                "dashboard_df_preparado", "dashboard_colunas_preparadas",
                "login_usuario", "login_senha",
            ):
                st.session_state.pop(chave, None)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


def chave_checkbox_contratante(contratante):
    return f"contratante_checkbox::{normalizar_texto(contratante)}"


def renderizar_filtro_contratantes(contratantes):
    st.markdown('<div style="color:#10213f; font-weight:700; margin-bottom:0.6rem; font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em;">Contratantes</div>', unsafe_allow_html=True)

    contratantes_cache = tuple(contratantes)
    if st.session_state.get("contratantes_disponiveis_cache") != contratantes_cache:
        st.session_state["contratantes_disponiveis_cache"] = contratantes_cache
        selecionados_validos = [
            contratante
            for contratante in st.session_state.get("contratantes_selecionados", [])
            if contratante in contratantes
        ]
        st.session_state["contratantes_selecionados"] = selecionados_validos

    def sincronizar_checkboxes(selecionados):
        selecionados_set = set(selecionados)
        for contratante in contratantes:
            st.session_state[chave_checkbox_contratante(contratante)] = contratante in selecionados_set

    def selecionar_todos():
        st.session_state["contratantes_selecionados"] = contratantes.copy()
        sincronizar_checkboxes(contratantes)

    def limpar_filtros():
        st.session_state["busca_contratante"] = ""
        st.session_state["contratantes_selecionados"] = []
        sincronizar_checkboxes([])

    def aplicar_resultado_busca():
        busca_atual = st.session_state.get("busca_contratante", "").strip().lower()
        contratantes_visiveis = [
            contratante
            for contratante in contratantes
            if busca_atual in contratante.lower()
        ]
        st.session_state["contratantes_selecionados"] = contratantes_visiveis
        sincronizar_checkboxes(contratantes_visiveis)

    selecionados_atuais = [
        contratante
        for contratante in st.session_state["contratantes_selecionados"]
        if contratante in contratantes
    ]

    with st.expander(
        f"Selecionar contratantes ({len(selecionados_atuais)}/{len(contratantes)})",
        expanded=False,
    ):
        busca = st.text_input(
            "Buscar contratante",
            key="busca_contratante",
            placeholder="Digite para filtrar a lista",
            on_change=aplicar_resultado_busca,
        ).strip().lower()

        acoes_1, acoes_2 = st.columns(2)
        with acoes_1:
            st.button("Marcar todos", use_container_width=True, key="marcar_todos_contratantes", on_click=selecionar_todos)
        with acoes_2:
            st.button("Limpar filtros", use_container_width=True, key="limpar_contratantes", on_click=limpar_filtros)

        contratantes_visiveis = [
            contratante for contratante in contratantes
            if busca in contratante.lower()
        ]

        novos_selecionados = []

        if contratantes_visiveis:
            colunas_checkbox = st.columns(3)
            for indice, contratante in enumerate(contratantes_visiveis):
                coluna = colunas_checkbox[indice % 3]
                chave_checkbox = chave_checkbox_contratante(contratante)
                if chave_checkbox not in st.session_state:
                    st.session_state[chave_checkbox] = contratante in selecionados_atuais

                marcado = coluna.checkbox(contratante, key=chave_checkbox)
                if marcado:
                    novos_selecionados.append(contratante)

            for contratante in contratantes:
                if (
                    contratante not in contratantes_visiveis
                    and contratante in st.session_state["contratantes_selecionados"]
                ):
                    novos_selecionados.append(contratante)
        else:
            st.info("Nenhum contratante encontrado para a busca informada.")
            novos_selecionados = []

        st.session_state["contratantes_selecionados"] = novos_selecionados

    resumo = st.session_state["contratantes_selecionados"]
    if not resumo:
        st.caption("Nenhum contratante marcado. Todos os dados estao sendo considerados.")
    elif len(resumo) == len(contratantes):
        st.caption("Todos os contratantes selecionados.")
    else:
        st.caption(f"{len(resumo)} contratante(s) selecionado(s).")

    return st.session_state["contratantes_selecionados"]


def renderizar_dashboard():
    df, colunas = preparar_dataframe()

    # Data de atualizacao para exibir no topo
    data_atualizacao = None
    if not df.empty and colunas.get("data_pagto"):
        data_max_raw = df[colunas["data_pagto"]].max()
        if not pd.isna(data_max_raw):
            data_atualizacao = pd.Timestamp(data_max_raw).strftime("%d/%m/%Y")

    renderizar_topo(data_atualizacao=data_atualizacao)

    if df.empty:
        st.warning("Nao ha pagamentos disponiveis para exibicao.")
        return

    if st.session_state["tipo_usuario"] != "admin":
        df = df[df[colunas["contratante"]] == st.session_state["contratante"]].copy()

    if df.empty:
        st.warning("Nao ha pagamentos disponiveis para o usuario logado.")
        return

    data_max = df[colunas["data_pagto"]].max()
    if pd.isna(data_max):
        st.warning("Nao foi possivel determinar o periodo dos pagamentos.")
        return

    primeiro_dia_mes = data_max.replace(day=1)

    st.markdown('<div class="filtros-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="filtros-titulo">Filtros</div>', unsafe_allow_html=True)
    filtro_1, filtro_2 = st.columns(2)

    with filtro_1:
        contratantes = sorted(df[colunas["contratante"]].dropna().unique().tolist())
        selecionados = renderizar_filtro_contratantes(contratantes)

    with filtro_2:
        st.markdown('<div style="color:#10213f; font-weight:700; margin-bottom:0.6rem; font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em;">Periodo</div>', unsafe_allow_html=True)
        periodo = st.date_input(
            "Periodo",
            value=(primeiro_dia_mes.date(), data_max.date()),
            format="DD/MM/YYYY",
            label_visibility="collapsed",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    data_inicio = data_fim = None
    if isinstance(periodo, (list, tuple)):
        if len(periodo) >= 2:
            data_inicio = periodo[0]
            data_fim = periodo[1]
        elif len(periodo) == 1:
            data_inicio = data_fim = periodo[0]
    elif periodo:
        data_inicio = data_fim = periodo

    filtro_periodo = pd.Series(True, index=df.index)
    if data_inicio is not None and data_fim is not None:
        data_inicio = pd.Timestamp(data_inicio).normalize()
        data_fim = pd.Timestamp(data_fim).normalize() + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        filtro_periodo = (
            (df[colunas["data_pagto"]] >= data_inicio)
            & (df[colunas["data_pagto"]] <= data_fim)
        )

    contratantes_efetivos = selecionados or contratantes

    df_filtrado = df[
        (df[colunas["contratante"]].isin(contratantes_efetivos))
        & filtro_periodo
    ].copy()

    total_valor = df_filtrado[colunas["valor_principal"]].sum()
    total_repasse = df_filtrado[colunas["valor_repasse"]].sum()
    total_comissao = df_filtrado[colunas["valor_comissao"]].sum()
    total_pagamentos = len(df_filtrado)

    metrica_1, metrica_2, metrica_3, metrica_4 = st.columns(4)
    metrica_1.metric("Valor total recebido", formatar_real(total_valor))
    metrica_2.metric("Valor de repasse", formatar_real(total_repasse))
    metrica_3.metric("Total de comissao", formatar_real(total_comissao))
    metrica_4.metric("Quantidade de pagamentos", total_pagamentos)

    if df_filtrado.empty:
        st.info("Nenhum pagamento encontrado para os filtros selecionados.")
        return

    df_grafico = (
        df_filtrado.groupby(df_filtrado[colunas["data_pagto"]].dt.date)[colunas["valor_principal"]]
        .sum()
        .reset_index()
    )
    df_grafico.columns = ["Data", "Valor"]
    df_grafico["DataLabel"] = pd.to_datetime(df_grafico["Data"]).dt.strftime("%d/%m")
    df_grafico["ValorLabel"] = df_grafico["Valor"].apply(formatar_real)

    fig = go.Figure()
    fig.add_bar(
        x=df_grafico["DataLabel"],
        y=df_grafico["Valor"],
        name="Sombra",
        marker=dict(color="rgba(15, 23, 42, 0.05)", line=dict(color="rgba(15, 23, 42, 0.08)", width=0)),
        width=0.66, offset=0.018, hoverinfo="skip", showlegend=False,
    )
    fig.add_bar(
        x=df_grafico["DataLabel"],
        y=df_grafico["Valor"],
        name="Valor",
        text=df_grafico["ValorLabel"],
        texttemplate="%{text}",
        textposition="outside",
        marker=dict(color="#e9781d", line=dict(color="#c65f10", width=1.4), opacity=0.97),
        width=0.68,
        hoverlabel=dict(bgcolor="#fff7ed", bordercolor="#c65f10", font=dict(color="#10213f")),
        hovertemplate="<b>%{x}</b><br>Valor: %{text}<extra></extra>",
        cliponaxis=False, showlegend=False,
    )
    fig.update_layout(
        title=dict(text="Evolucao de Valores por Dia", x=0, xanchor="left", font=dict(size=18, color="#10213f")),
        plot_bgcolor="#f8f9fa",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#334155", size=12),
        barmode="overlay", bargap=0.24, bargroupgap=0.02,
        margin=dict(t=68, r=18, b=26, l=18),
        hovermode="x unified",
        xaxis=dict(
            title="Data", color="#10213f",
            tickfont=dict(color="#334155", size=11),
            title_font=dict(color="#10213f", size=12),
            gridcolor="rgba(0,0,0,0)", showgrid=False, showline=False, tickangle=0,
        ),
        yaxis=dict(
            title="Valores (R$)", color="#334155",
            tickfont=dict(color="#475569", size=11),
            title_font=dict(color="#10213f", size=12),
            gridcolor="rgba(148, 163, 184, 0.14)",
            zerolinecolor="rgba(148, 163, 184, 0.12)",
            tickprefix="R$ ",
        ),
    )
    fig.update_layout(barcornerradius=7)
    fig.update_traces(textfont=dict(color="#10213f", size=11))
    st.markdown('<div class="grafico-card">', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    df_tabela = df_filtrado.copy()
    df_tabela[colunas["data_pagto"]] = df_tabela[colunas["data_pagto"]].dt.strftime("%d/%m/%Y")
    df_exibicao = obter_colunas_tabela(df_tabela)

    csv_file = gerar_csv(df_exibicao)
    excel_file = gerar_excel(df_exibicao)
    pdf_file = gerar_pdf(df_exibicao)

    st.markdown('<div class="tabela-card">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="tabela-header">
            <div>
                <div class="tabela-header-titulo">Detalhamento dos pagamentos</div>
                <div class="tabela-header-subtitulo">A exportacao reflete exatamente os filtros aplicados na tabela.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="tabela-acoes">', unsafe_allow_html=True)
    with st.popover("Exportar", use_container_width=False):
        st.markdown(
            """
            <div class="exportacao-popover-titulo">Exportar dados filtrados</div>
            <div class="exportacao-popover-subtitulo">
                Escolha o formato desejado para baixar os dados visiveis na tabela.
            </div>
            """,
            unsafe_allow_html=True,
        )
        renderizar_acao_exportacao("PDF", "dados_filtrados.pdf", pdf_file, PDF_ICON_PATH, "download_pdf_popup")
        renderizar_acao_exportacao("Excel", "dados_filtrados.xlsx", excel_file, EXCEL_ICON_PATH, "download_excel_popup")
        renderizar_acao_exportacao("CSV", "dados_filtrados.csv", csv_file, CSV_ICON_PATH, "download_csv_popup")
    st.markdown("</div>", unsafe_allow_html=True)

    # ── AgGrid com filtros por coluna (estilo Excel) ─────────────────────────
    colunas_valor_aggrid = {
        "V. Princ", "V. Juros Contrat", "V. Juros Asses",
        "V. Multa", "V. Honor", "V. Receb", "V. Repasse", "V. Comissão",
    }

    gb = GridOptionsBuilder.from_dataframe(df_exibicao)

    gb.configure_default_column(
        resizable=True,
        sortable=True,
        filter=True,
        floatingFilter=True,
        suppressMenu=False,
        filterParams={"buttons": ["reset"], "closeOnApply": True},
        cellStyle={"fontSize": "13px", "color": "#10213f"},
    )

    colunas_numericas = {
        "V. Princ", "V. Juros Contrat", "V. Juros Asses",
        "V. Multa", "V. Honor", "V. Receb", "V. Repasse", "V. Comissão",
        "Dias", "Titulos Negociados", "N Pres", "Q Pres",
    }

    colunas_data = {"Data Venc", "Data Acordo", "Data Pagto"}

    date_comparator = JsCode("""
        function(filterDate, cellValue) {
            if (!cellValue) return -1;
            var parts = cellValue.split('/');
            if (parts.length !== 3) return -1;
            var cellDate = new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
            if (cellDate < filterDate) return -1;
            if (cellDate > filterDate) return 1;
            return 0;
        }
    """)

    for col in df_exibicao.columns:
        if col in colunas_numericas:
            df_exibicao[col] = pd.to_numeric(
                df_exibicao[col].astype(str)
                    .str.replace("R$", "", regex=False)
                    .str.replace(".", "", regex=False)
                    .str.replace(",", ".", regex=False)
                    .str.strip(),
                errors="coerce",
            )
            gb.configure_column(
                col,
                filter="agNumberColumnFilter",
                filterParams={
                    "buttons": ["reset"],
                    "filterOptions": [
                        "equals", "notEqual",
                        "lessThan", "lessThanOrEqual",
                        "greaterThan", "greaterThanOrEqual",
                        "inRange", "blank", "notBlank",
                    ],
                },
                valueFormatter="value != null ? 'R$ ' + value.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : ''"
                    if col in colunas_valor_aggrid else None,
                headerTooltip=col,
                type=["numericColumn"],
            )
        elif col in colunas_data:
            gb.configure_column(
                col,
                filter="agDateColumnFilter",
                filterParams={
                    "buttons": ["reset"],
                    "filterOptions": [
                        "equals", "notEqual",
                        "lessThan", "greaterThan",
                        "inRange", "blank", "notBlank",
                    ],
                    "comparator": date_comparator,
                    "browserDatePicker": True,
                },
                headerTooltip=col,
            )
        else:
            gb.configure_column(
                col,
                filter="agTextColumnFilter",
                filterParams={"buttons": ["reset"]},
                headerTooltip=col,
            )

    gb.configure_grid_options(
        domLayout="normal",
        rowHeight=36,
        headerHeight=42,
        floatingFiltersHeight=36,
        suppressMovableColumns=False,
        enableBrowserTooltips=True,
        animateRows=True,
        floatingFilter=True,
        localeText={
            "filterOoo": "Filtrar...",
            "equals": "Igual a",
            "notEqual": "Diferente de",
            "lessThan": "Anterior a",
            "greaterThan": "Posterior a",
            "lessThanOrEqual": "Menor ou igual",
            "greaterThanOrEqual": "Maior ou igual",
            "inRange": "Entre períodos",
            "inRangeStart": "De",
            "inRangeEnd": "Até",
            "contains": "Contém",
            "notContains": "Não contém",
            "startsWith": "Começa com",
            "endsWith": "Termina com",
            "blank": "Vazio",
            "notBlank": "Não vazio",
            "andCondition": "E",
            "orCondition": "Ou",
            "resetFilter": "Limpar filtro",
            "applyFilter": "Aplicar",
            "clearFilter": "Limpar",
            "cancelFilter": "Cancelar",
            "dateFormatOoo": "dd/mm/yyyy",
            "page": "Página",
            "more": "Mais",
            "to": "até",
            "of": "de",
            "next": "Próxima",
            "last": "Última",
            "first": "Primeira",
            "previous": "Anterior",
            "loadingOoo": "Carregando...",
            "noRowsToShow": "Nenhum registro encontrado",
            "columns": "Colunas",
            "filters": "Filtros",
            "sortAscending": "Ordem crescente",
            "sortDescending": "Ordem decrescente",
        },
    )

    grid_options = gb.build()

    AgGrid(
        df_exibicao,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.NO_UPDATE,
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        enable_enterprise_modules=False,
        theme="alpine",
        height=520,
        use_container_width=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


def main():
    aplicar_estilos()
    inicializar_sessao()

    if not st.session_state["logado"]:
        renderizar_login()
        return

    if st.session_state["primeiro_acesso"]:
        renderizar_primeiro_acesso()
        return

    if st.session_state["mostrar_carregamento_dashboard"]:
        renderizar_carregamento_dashboard()
        return

    renderizar_dashboard()


main()

# FIM
