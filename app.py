import streamlit as st
import requests
import time
import threading
import numpy as np
import pytz
from datetime import datetime, timedelta
from supabase import create_client, Client

# ================= CONFIGURAÇÃO DA PÁGINA =================
st.set_page_config(page_title="VISION PRO V3", page_icon="🎯", layout="centered")

# ================= CONEXÃO SUPABASE =================
# O Streamlit vai puxar essas credenciais de forma segura através dos Secrets
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= CONFIGURAÇÕES TELEGRAM =================
TOKEN_TELEGRAM = "8710725826:AAFuGmF30Ns-G1glrBYir9ggVya9VwQgZAU"
CHAT_ID_TELEGRAM = "-1002979466366"
ADMIN_EMAIL = "admin@vision.com"

def enviar_telegram(mensagem):
    try:
        url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
        payload = {"chat_id": CHAT_ID_TELEGRAM, "text": mensagem, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro Telegram: {e}")

# ================= FUNÇÕES DE BANCO DE DADOS (SUPABASE) =================
def db_carregar_usuario(email):
    try:
        res = supabase.table("usuarios").select("*").eq("email", email).execute()
        return res.data[0] if res.data else None
    except:
        return None

def db_salvar_usuario(email, senha, ip):
    try:
        supabase.table("usuarios").insert({"email": email, "senha": senha, "ip": ip}).execute()
        return True
    except:
        return False

def db_atualizar_estatisticas(email, is_win):
    user = db_carregar_usuario(email)
    if user:
        wins = user["wins"] + 1 if is_win else user["wins"]
        reds = user["reds"] + 1 if not is_win else user["reds"]
        total = wins + reds
        winrate = round((wins / total) * 100, 1) if total > 0 else 0
        supabase.table("usuarios").update({"wins": wins, "reds": reds, "winrate": winrate}).execute()

def db_renovar_usuario(email):
    hoje = datetime.now().strftime("%Y-%m-%d")
    supabase.table("usuarios").update({"criado_em": hoje}).execute()

def db_excluir_usuario(email):
    supabase.table("usuarios").delete().eq("email", email).execute()

def db_verificar_assinatura(email):
    if email == ADMIN_EMAIL: return True, 999
    user = db_carregar_usuario(email)
    if not user: return False, 0
    try:
        data_criacao = datetime.strptime(user["criado_em"], "%Y-%m-%d")
        dias_restantes = 30 - (datetime.now() - data_criacao).days
        return (True, dias_restantes) if dias_restantes > 0 else (False, 0)
    except:
        return False, 0

def db_Salvar_sinal(sinal_texto):
    try:
        supabase.table("historico_sinais").insert({"sinal": sinal_texto, "resultado": "Analisando..."}).execute()
    except:
        pass

def db_atualizar_ultimo_sinal(resultado):
    try:
        res = supabase.table("historico_sinais").select("id").order("id", desc=True).limit(1).execute()
        if res.data:
            supabase.table("historico_sinais").update({"resultado": resultado}).eq("id", res.data[0]["id"]).execute()
    except:
        pass

def db_obter_historico():
    try:
        res = supabase.table("historico_sinais").select("*").order("id", desc=True).limit(10).execute()
        return res.data if res.data else []
    except:
        return []

# ================= MOTOR DE ANÁLISE =================
ATIVOS_BASE = {
    "FOREX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURJPY", "USDCAD", "USDCHF", "GBPJPY"],
    "CRIPTO": ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD", "ADAUSD", "AVAXUSD", "DOGEUSD", "SHIBUSD", "PEPEUSD"]
}

MAPA_TICKERS = {}
for par in ATIVOS_BASE["FOREX"]: MAPA_TICKERS[par] = f"{par}=X"
for par in ATIVOS_BASE["CRIPTO"]: MAPA_TICKERS[par] = "SHIB-USD" if "SHIB" in par else ("PEPE1-USD" if "PEPE" in par else par.replace("USD", "-USD"))

def get_data_v2(ticker, tf):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={tf}m&range=5d"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
        result = res['chart']['result'][0]
        ohlc = {
            "open": np.array(result['indicators']['quote'][0]['open']),
            "high": np.array(result['indicators']['quote'][0]['high']),
            "low": np.array(result['indicators']['quote'][0]['low']),
            "close": np.array(result['indicators']['quote'][0]['close'])
        }
        idx = ~np.isnan(ohlc["close"])
        for k in ohlc: ohlc[k] = ohlc[k][idx]
        return ohlc
    except: return None

def analisar_estrategia(data, estrategia, i=-1):
    c, o, h, l = data["close"], data["open"], data["high"], data["low"]
    if len(c) < 30: return None
    if estrategia == "LOGICA_DO_PRECO":
        if c[i] > o[i] and c[i] > h[i-1]: return "CALL"
        if c[i] < o[i] and c[i] < l[i-1]: return "PUT"
    if estrategia == "MHI1":
        cores = [("G" if c[j] > o[j] else "R") for j in range(i-2, i+1)]
        return "PUT" if cores.count("G") > cores.count("R") else "CALL"
    return None

# ================= ESTADOS GLOBAIS DO STREAMLIT =================
if "USER" not in st.session_state: st.session_state["USER"] = None
if "BOT_ATIVO" not in st.session_state: st.session_state["BOT_ATIVO"] = False
if "MODO_MERCADO" not in st.session_state: st.session_state["MODO_MERCADO"] = "TODOS"
if "TIMEFRAME" not in st.session_state: st.session_state["TIMEFRAME"] = 5
if "ESTRATEGIA" not in st.session_state: st.session_state["ESTRATEGIA"] = "TODAS"
if "SINAL_DISPLAY" not in st.session_state: st.session_state["SINAL_DISPLAY"] = "Aguardando Inicialização..."
if "AG_RESULTADO" not in st.session_state: st.session_state["AG_RESULTADO"] = False

# ================= LOOP DE SEGUNDO PLANO =================
def bot_background_loop():
    FUSO = pytz.timezone("America/Sao_Paulo")
    while True:
        if st.session_state["BOT_ATIVO"] and not st.session_state["AG_RESULTADO"]:
            ativos = ATIVOS_BASE["FOREX"] + ATIVOS_BASE["CRIPTO"] if st.session_state["MODO_MERCADO"] == "TODOS" else ATIVOS_BASE[st.session_state["MODO_MERCADO"]]
            for ativo in ativos:
                ticker = MAPA_TICKERS.get(ativo, ativo)
                data = get_data_v2(ticker, st.session_state["TIMEFRAME"])
                if not data: continue

                sinal = analisar_estrategia(data, "MHI1") # Simplificado para teste estável
                if sinal:
                    h_ent = datetime.now(FUSO).strftime('%H:%M')
                    h_exp = (datetime.now(FUSO) + timedelta(minutes=st.session_state["TIMEFRAME"])).strftime('%H:%M')
                    sinal_txt = f"{h_ent} | {h_exp} | {ativo}"

                    st.session_state["SINAL_DISPLAY"] = f"🎯 **SINAL CONFIRMADO**\n\n**Ativo:** {ativo}\n**Direção:** {sinal}\n**Entrada:** {h_ent}"
                    db_Salvar_sinal(sinal_txt)

                    enviar_telegram(f"🎯 <b>SINAL CONFIRMADO</b>\n\n📈 Ativo: {ativo}\n🧭 Direção: {sinal}\n🕒 Time: M{st.session_state['TIMEFRAME']}")
                    st.session_state["AG_RESULTADO"] = True
                    break
        time.sleep(10)

if "THREAD_STARTED" not in st.session_state:
    threading.Thread(target=bot_background_loop, daemon=True).start()
    st.session_state["THREAD_STARTED"] = True

# ================= INTERFACE GRÁFICA (STREAMLIT UI) =================
if st.session_state["USER"] is None:
    aba1, aba2 = st.tabs(["🔒 Login", "📝 Cadastro"])

    with aba1:
        st.subheader("Login Vision Pro")
        email_input = st.text_input("E-mail")
        senha_input = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            # ASSINATURA DE ADM COMPORTAMENTO MASTER (Bypass direto)
            if email_input == ADMIN_EMAIL and senha_input == "admin123":
                st.session_state["USER"] = email_input
                st.rerun()
            else:
                # Comportamento padrão para clientes normais (busca no Supabase)
                user = db_carregar_usuario(email_input)
                if user and user["senha"] == senha_input:
                    st.session_state["USER"] = email_input
                    st.rerun()
                else:
                    st.error("Credenciais inválidas ou assinatura expirada.")

    with aba2:
        st.subheader("Criar Nova Conta")
        novo_email = st.text_input("Novo E-mail")
        nova_senha = st.text_input("Nova Senha", type="password")
        if st.button("Cadastrar"):
            if db_salvar_usuario(novo_email, nova_senha, "127.0.0.1"):
                st.success("Cadastro realizado com sucesso! Faça login.")
            else:
                st.error("Erro ao cadastrar ou usuário já existente.")
else:
    # Cabeçalho do App Autenticado
    st.title("🛡️ VISION PRO V3")
    st.write(f"Conectado como: `{st.session_state['USER']}`")
    if st.button("Sair da Conta", type="primary"):
        st.session_state["USER"] = None
        st.rerun()

    st.markdown("---")

    # Área do Painel de Controle e Monitoramento
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 INICIAR SCANNER", use_container_width=True):
            st.session_state["BOT_ATIVO"] = True
            st.session_state["SINAL_DISPLAY"] = "📡 Procurando oportunidades nos mercados..."
    with col2:
        if st.button("🛑 PARAR SCANNER", use_container_width=True):
            st.session_state["BOT_ATIVO"] = False
            st.session_state["SINAL_DISPLAY"] = "Scanner Pausado."

    # Mostrador do Alerta Atual
    st.info(st.session_state["SINAL_DISPLAY"])

    # Painel de Resultados Manuais (Aparece se houver sinal ativo)
    if st.session_state["AG_RESULTADO"]:
        st.warning("Aguardando verificação do resultado da operação:")
        c1, c2, c3 = st.columns(3)
        if c1.button("✅ WIN", use_container_width=True):
            db_atualizar_ultimo_sinal("Win")
            db_atualizar_estatisticas(st.session_state["USER"], True)
            st.session_state["AG_RESULTADO"] = False
            st.rerun()
        if c2.button("🔄 GALE 1", use_container_width=True):
            db_atualizar_ultimo_sinal("Win G1")
            db_atualizar_estatisticas(st.session_state["USER"], True)
            st.session_state["AG_RESULTADO"] = False
            st.rerun()
        if c3.button("❌ RED", use_container_width=True):
            db_atualizar_ultimo_sinal("Red")
            db_atualizar_estatisticas(st.session_state["USER"], False)
            st.session_state["AG_RESULTADO"] = False
            st.rerun()

    # Filtros de Configuração de Estratégias
    with st.expander("⚙️ Configurações de Ativos e Filtros"):
        st.session_state["MODO_MERCADO"] = st.radio("Mercado Alvo", ["TODOS", "FOREX", "CRIPTO"], index=0)
        st.session_state["TIMEFRAME"] = st.selectbox("Timeframe (Minutos)", [1, 5, 15], index=1)

    # Histórico de Operações vindo direto do Supabase
    st.subheader("📋 Histórico Recente de Sinais")
    historico = db_obter_historico()
    if historico:
        for h in historico:
            st.text(f"🕒 {h['sinal']} -> {h['resultado']}")
    else:
        st.caption("Nenhum registro encontrado no banco de dados Supabase.")

    # Painel Administrativo Oculto (Apenas para o admin)
    if st.session_state["USER"] == ADMIN_EMAIL:
        st.markdown("---")
        with st.expander("👥 PAINEL ADMINISTRATIVO (GESTÃO DE CLIENTES)"):
            st.write("Gerencie os acessos do banco de dados aqui.")
            # Interface simplificada de exclusão/renovação via e-mail
            alvo = st.text_input("E-mail do Cliente Alvo")
            cc1, cc2 = st.columns(2)
            if cc1.button("Renovar +30 Dias"):
                db_renovar_usuario(alvo)
                st.success(f"{alvo} renovado!")
            if cc2.button("Excluir Usuário", type="primary"):
                db_excluir_usuario(alvo)
                st.error(f"{alvo} deletado do banco!")
