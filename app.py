import streamlit as st
import requests
import time
import pytz
import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client

# ================= CONFIGURAÇÃO DA PÁGINA =================
st.set_page_config(page_title="VISION PRO V3", page_icon="🎯", layout="centered")

# Injeção de Design Moderno e Premium (CSS Customizado)
st.markdown("""
    <style>
        .main { background-color: #0e1117; }
        h1, h2, h3 { color: #00ffcc !important; font-family: 'Helvetica Neue', sans-serif; font-weight: 700; }
        
        div.stButton > button {
            background: linear-gradient(135deg, #00ffcc 0%, #0099ff 100%) !important;
            color: #0e1117 !important;
            font-weight: bold !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 10px 24px !important;
            transition: all 0.3s ease !important;
            box-shadow: 0 4px 15px rgba(0, 255, 204, 0.2) !important;
        }
        div.stButton > button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 20px rgba(0, 255, 204, 0.4) !important;
        }
        
        [data-testid="stSidebar"] {
            background-color: #161b22 !important;
            border-right: 1px solid #21262d;
        }
        .scanner-box {
            background: #1f2937;
            padding: 20px;
            border-radius: 12px;
            border-left: 6px solid #00ffcc;
            margin-bottom: 15px;
            text-align: center;
        }
        .radar-text {
            color: #00ffcc;
            font-family: monospace;
            font-size: 14px;
        }
        .ativo-grande {
            font-size: 42px;
            font-weight: 900;
            color: #00ffcc;
            text-shadow: 0px 0px 15px rgba(0, 255, 204, 0.6);
            letter-spacing: 2px;
            margin: 10px 0;
        }
        
        /* Animação do Scanner Ativo */
        .radar-pulse {
            display: inline-block;
            width: 16px;
            height: 16px;
            background: #00ffcc;
            border-radius: 50%;
            box-shadow: 0 0 0 0 rgba(0, 255, 204, 0.7);
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 204, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 14px rgba(0, 255, 204, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 204, 0); }
        }
    </style>
""", unsafe_allow_html=True)

# ================= TRAVA ANTI-RESET (PERSISTÊNCIA DE SESSÃO) =================
if "USER" not in st.session_state:
    st.session_state["USER"] = None
if "BOT_ATIVO" not in st.session_state:
    st.session_state["BOT_ATIVO"] = False
if "MODO_MERCADO" not in st.session_state:
    st.session_state["MODO_MERCADO"] = "TODOS"
if "TIMEFRAME" not in st.session_state:
    st.session_state["TIMEFRAME"] = 5
if "ESTRATEGIA" not in st.session_state:
    st.session_state["ESTRATEGIA"] = "TODAS"
if "SINAL_DISPLAY" not in st.session_state:
    st.session_state["SINAL_DISPLAY"] = "Aguardando Inicialização..."
if "AG_RESULTADO" not in st.session_state:
    st.session_state["AG_RESULTADO"] = False
if "ATIVO_ATUAL" not in st.session_state:
    st.session_state["ATIVO_ATUAL"] = "Nenhum"
if "MOSTRAR_HISTORICO" not in st.session_state:
    st.session_state["MOSTRAR_HISTORICO"] = False
if "PRECOS_GRAFICO" not in st.session_state:
    st.session_state["PRECOS_GRAFICO"] = []

if "ADM_MSG_SUCESSO" not in st.session_state:
    st.session_state["ADM_MSG_SUCESSO"] = None
if "ADM_MSG_ERRO" not in st.session_state:
    st.session_state["ADM_MSG_ERRO"] = None

# ================= CONEXÃO SUPABASE =================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= CONFIGURAÇÕES TELEGRAM E SUPORTE =================
TOKEN_TELEGRAM = "8710725826:AAFuGmF30Ns-G1glrBYir9ggVya9VwQgZAU"
CHAT_ID_TELEGRAM = "-1002979466366"
ADMIN_EMAIL = "admin@vision.com"
WHATSAPP_SUPORTE = "5511999999999"

def enviar_telegram(mensagem):
    try:
        url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
        payload = {"chat_id": CHAT_ID_TELEGRAM, "text": mensagem, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def enviar_whatsapp_direto(numero, mensagem):
    return f"https://wa.me/{numero}?text={requests.utils.quote(mensagem)}"

# ================= FUNÇÕES DE BANCO DE DADOS =================
def db_carregar_usuario(email):
    if not email or str(email).strip() == "": return None
    try:
        res = supabase.table("usuarios").select("*").eq("email", email.strip().lower()).execute()
        return res.data[0] if hasattr(res, 'data') and res.data else None
    except: return None

def db_salvar_usuario(email, senha, whatsapp, ip="127.0.0.1"):
    try:
        if not email or not senha: return False
        if db_carregar_usuario(email) is not None: return False
        supabase.table("usuarios").insert({"email": email.strip().lower(), "senha": senha.strip(), "whatsapp": whatsapp.strip(), "ip": ip, "criado_em": datetime.now().strftime("%Y-%m-%d"), "wins": 0, "reds": 0, "winrate": 0.0}).execute()
        return True
    except: return False

def db_atualizar_estatisticas(email, is_win):
    try:
        user = db_carregar_usuario(email)
        if user:
            wins = user.get("wins", 0) + 1 if is_win else user.get("wins", 0)
            reds = user.get("reds", 0) + 1 if not is_win else user.get("reds", 0)
            total = wins + reds
            winrate = round((wins / total) * 100, 1) if total > 0 else 0.0
            supabase.table("usuarios").update({"wins": wins, "reds": reds, "winrate": winrate}).eq("email", email.strip().lower()).execute()
    except: pass

def db_renovar_usuario(email):
    try:
        supabase.table("usuarios").update({"criado_em": datetime.now().strftime("%Y-%m-%d")}).eq("email", email.strip().lower()).execute()
        return True
    except: return False

def db_excluir_usuario(email):
    try: supabase.table("usuarios").delete().eq("email", email.strip().lower()).execute(); return True
    except: return False

def db_atualizar_senha(email, nova_senha):
    try: supabase.table("usuarios").update({"senha": nova_senha}).eq("email", email.strip().lower()).execute(); return True
    except: return False

def db_Salvar_sinal(sinal_texto):
    try: supabase.table("historico_sinais").insert({"sinal": sinal_texto, "resultado": "Analisando..."}).execute()
    except: pass

def db_atualizar_ultimo_sinal(resultado):
    try:
        res = supabase.table("historico_sinais").select("id").order("id", desc=True).limit(1).execute()
        if res.data: supabase.table("historico_sinais").update({"resultado": resultado}).eq("id", res.data[0]["id"]).execute()
    except: pass

def db_obter_historico():
    try:
        res = supabase.table("historico_sinais").select("*").order("id", desc=True).limit(10).execute()
        return res.data if res.data else []
    except: return []

# ================= MOTOR DE ANÁLISE =================
ATIVOS_BASE = {"FOREX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURJPY", "USDCAD", "USDCHF", "GBPJPY"], "CRIPTO": ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD", "ADAUSD", "AVAXUSD", "DOGEUSD", "SHIBUSD", "PEPEUSD"]}
MAPA_TICKERS = {par: f"{par}=X" for par in ATIVOS_BASE["FOREX"]}
for par in ATIVOS_BASE["CRIPTO"]: MAPA_TICKERS[par] = "SHIB-USD" if "SHIB" in par else ("PEPE1-USD" if "PEPE" in par else par.replace("USD", "-USD"))

def get_data_v2(ticker, tf):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={tf}m&range=1d"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
        result = res['chart']['result'][0]
        ohlc = {"open": np.array(result['indicators']['quote'][0]['open']), "high": np.array(result['indicators']['quote'][0]['high']), "low": np.array(result['indicators']['quote'][0]['low']), "close": np.array(result['indicators']['quote'][0]['close'])}
        idx = ~np.isnan(ohlc["close"])
        for k in ohlc: ohlc[k] = ohlc[k][idx]
        return ohlc
    except: return None

def analisar_estrategia(data, estrategia, i=-1):
    c, o, h, l = data["close"], data["open"], data["high"], data["low"]
    if len(c) < 15: return None
    if estrategia in ["LOGICA_DO_PRECO", "TODAS"]:
        if c[i] > o[i] and c[i] > h[i-1]: return "CALL"
        if c[i] < o[i] and c[i] < l[i-1]: return "PUT"
    if estrategia in ["MHI1", "TODAS"]:
        cores = [("G" if c[j] > o[j] else "R") for j in range(i-2, i+1)]
        return "PUT" if cores.count("G") > cores.count("R") else "CALL"
    return None

# ================= INTERFACE GRÁFICA =================
if st.session_state["USER"] is None:
    st.title("🎯 VISION PRO V3")
    aba1, aba2 = st.tabs(["🔒 Acessar Painel", "🔑 Recuperar Acesso"])
    with aba1:
        with st.form(key="form_login"):
            email_input = st.text_input("E-mail")
            senha_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                if email_input.strip().lower() == ADMIN_EMAIL and senha_input == "admin123":
                    st.session_state["USER"] = email_input.strip().lower(); st.rerun()
                else:
                    user = db_carregar_usuario(email_input)
                    if user and user["senha"] == senha_input: st.session_state["USER"] = email_input.strip().lower(); st.rerun()
                    else: st.error("Acesso negado.")
    with aba2:
        with st.form(key="form_recuperacao"):
            rec_email = st.text_input("E-mail"); rec_whatsapp = st.text_input("WhatsApp com DDD")
            if st.form_submit_button("Solicitar Nova Senha"):
                user = db_carregar_usuario(rec_email)
                if user and str(user.get("whatsapp", "")).strip() == rec_whatsapp.strip():
                    nova = str(random.randint(100000, 999999))
                    if db_atualizar_senha(rec_email, nova):
                        link = enviar_whatsapp_direto(rec_whatsapp, f"Sua nova senha é: {nova}")
                        st.markdown(f"[🟢 CLIQUE AQUI PARA ENVIAR]({link})")
else:
    st.title("🛡️ DASHBOARD VISION PRO")
    if st.button("Sair"): st.session_state["USER"] = None; st.session_state["BOT_ATIVO"] = False; st.rerun()

    # Histórico Ocultável
    with st.expander("📋 Ver Histórico de Sinais"):
        for h in db_obter_historico(): st.text(f"🕒 {h['sinal']} -> {h['resultado']}")

    # Scanner e Alertas
    if st.session_state["BOT_ATIVO"]:
        seg = datetime.now().second
        if 20 <= seg <= 25: st.warning("⚠️ PREPARAÇÃO: Identificando oportunidade (40s)...")
        elif 55 <= seg <= 59: st.success("🎯 CONFIRMAÇÃO: Entrada Imediata!")

    scanner_placeholder = st.empty()
    grafico_placeholder = st.empty()
    
    col1, col2 = st.columns(2)
    if col1.button("🚀 INICIAR"): st.session_state["BOT_ATIVO"] = True; st.rerun()
    if col2.button("🛑 PAUSAR"): st.session_state["BOT_ATIVO"] = False; st.rerun()

    # Filtros e ADMIN seguem a estrutura original...
    with st.expander("⚙️ Configurações"):
        st.session_state["MODO_MERCADO"] = st.radio("Mercado", ["TODOS", "FOREX", "CRIPTO"])
        st.session_state["TIMEFRAME"] = st.selectbox("Timeframe", [1, 5, 15], index=1)
    
    if st.session_state["USER"] == ADMIN_EMAIL:
        with st.expander("👥 PAINEL ADMINISTRATIVO"):
            target = st.text_input("Email Alvo")
            if st.button("Renovar"): db_renovar_usuario(target); st.success("Renovado!")

    # Loop de Varredura
    if st.session_state["BOT_ATIVO"] and not st.session_state["AG_RESULTADO"]:
        ativos = ATIVOS_BASE["FOREX"] + ATIVOS_BASE["CRIPTO"]
        for ativo in ativos:
            if not st.session_state["BOT_ATIVO"]: break
            st.session_state["ATIVO_ATUAL"] = ativo
            data = get_data_v2(MAPA_TICKERS[ativo], st.session_state["TIMEFRAME"])
            if data:
                sinal = analisar_estrategia(data, st.session_state["ESTRATEGIA"])
                if sinal:
                    st.session_state["AG_RESULTADO"] = True; st.rerun()
            time.sleep(1)
        st.rerun()
