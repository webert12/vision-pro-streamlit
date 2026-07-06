import streamlit as st
import requests
import time
import threading
import numpy as np
import pytz
import random
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
            padding: 15px;
            border-radius: 10px;
            border-left: 5px solid #00ffcc;
            margin-bottom: 15px;
        }
    </style>
""", unsafe_allow_html=True)

# ================= CONEXÃO SUPABASE =================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= CONFIGURAÇÕES TELEGRAM E SUPORTE =================
TOKEN_TELEGRAM = "8710725826:AAFuGmF30Ns-G1glrBYir9ggVya9VwQgZAU"
CHAT_ID_TELEGRAM = "-1002979466366"
ADMIN_EMAIL = "admin@vision.com"
WHATSAPP_SUPORTE = "5511999999999"  # Configure o seu número aqui (com DDI e DDD)

def enviar_telegram(mensagem):
    try:
        url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/sendMessage"
        payload = {"chat_id": CHAT_ID_TELEGRAM, "text": message, "parse_mode": "HTML"}
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

def db_salvar_usuario(email, senha, whatsapp, ip="127.0.0.1"):
    try:
        # Nota: Certifique-se de que a coluna 'whatsapp' existe na tabela 'usuarios' do seu Supabase
        supabase.table("usuarios").insert({"email": email, "senha": senha, "whatsapp": whatsapp, "ip": ip}).execute()
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

def db_atualizar_senha(email, nova_senha):
    try:
        supabase.table("usuarios").update({"senha": nova_senha}).eq("email", email).execute()
        return True
    except:
        return False

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
if "ATIVO_ATUAL" not in st.session_state: st.session_state["ATIVO_ATUAL"] = "Nenhum"
if "GRAFICO_DATA" not in st.session_state: st.session_state["GRAFICO_DATA"] = [0.0] * 20

# ================= LOOP DE SEGUNDO PLANO =================
def bot_background_loop():
    FUSO = pytz.timezone("America/Sao_Paulo")
    while True:
        if st.session_state["BOT_ATIVO"] and not st.session_state["AG_RESULTADO"]:
            ativos = ATIVOS_BASE["FOREX"] + ATIVOS_BASE["CRIPTO"] if st.session_state["MODO_MERCADO"] == "TODOS" else ATIVOS_BASE[st.session_state["MODO_MERCADO"]]
            for ativo in ativos:
                st.session_state["ATIVO_ATUAL"] = ativo
                ticker = MAPA_TICKERS.get(ativo, ativo)
                data = get_data_v2(ticker, st.session_state["TIMEFRAME"])
                if not data: continue

                # Atualiza dinamicamente o gráfico com os últimos fechamentos
                st.session_state["GRAFICO_DATA"] = list(data["close"][-20:])

                sinal = analisar_estrategia(data, "MHI1")
                if sinal:
                    h_ent = datetime.now(FUSO).strftime('%H:%M')
                    h_exp = (datetime.now(FUSO) + timedelta(minutes=st.session_state["TIMEFRAME"])).strftime('%H:%M')
                    sinal_txt = f"{h_ent} | {h_exp} | {ativo}"

                    st.session_state["SINAL_DISPLAY"] = f"🎯 **SINAL CONFIRMADO**\n\n**Ativo:** {ativo}\n**Direção:** {sinal}\n**Entrada:** {h_ent}"
                    db_Salvar_sinal(sinal_txt)

                    enviar_telegram(f"🎯 <b>SINAL CONFIRMADO</b>\n\n📈 Ativo: {ativo}\n🧭 Direção: {sinal}\n🕒 Time: M{st.session_state['TIMEFRAME']}")
                    st.session_state["AG_RESULTADO"] = True
                    break
                time.sleep(0.5)
        time.sleep(2)

if "THREAD_STARTED" not in st.session_state:
    threading.Thread(target=bot_background_loop, daemon=True).start()
    st.session_state["THREAD_STARTED"] = True

# ================= SIDEBAR GLOBAL (SUPORTE E LINK) =================
with st.sidebar:
    st.markdown("### 🎯 VISION NETWORKS")
    st.markdown("---")
    st.markdown("💬 **Precisa de Ajuda?**")
    st.link_button("➡️ Falar com Suporte", "https://t.me/seu_usuario_suporte", use_container_width=True)
    st.markdown("---")
    st.caption("Versão Pro V3.5 Premium")

# ================= INTERFACE GRÁFICA (STREAMLIT UI) =================
if st.session_state["USER"] is None:
    st.title("🎯 VISION PRO V3")
    aba1, aba2 = st.tabs(["🔒 Acessar Painel", "🔑 Recuperar Acesso"])

    with aba1:
        st.subheader("Login Protegido")
        email_input = st.text_input("E-mail", key="login_email_input")
        senha_input = st.text_input("Senha", type="password", key="login_senha_input")
        if st.button("Entrar no Sistema", key="btn_login_submit"):
            if email_input == ADMIN_EMAIL and senha_input == "admin123":
                st.session_state["USER"] = email_input
                st.rerun()
            else:
                user = db_carregar_usuario(email_input)
                if user and user["senha"] == senha_input:
                    st.session_state["USER"] = email_input
                    st.rerun()
                else:
                    st.error("Acesso negado. Entre em contato com o administrador.")

    with aba2:
        st.subheader("Recuperação via WhatsApp")
        rec_email = st.text_input("E-mail Cadastrado", key="rec_email")
        rec_whatsapp = st.text_input("WhatsApp com DDD (Apenas números)", key="rec_whatsapp")
        
        if st.button("Solicitar Nova Senha", key="btn_rec_password"):
            user_data = db_carregar_usuario(rec_email)
            if user_data and str(user_data.get("whatsapp", "")).strip() == rec_whatsapp.strip():
                # Gera nova senha numérica aleatória de 6 dígitos
                nova_senha_gerada = str(random.randint(100000, 999999))
                if db_atualizar_senha(rec_email, nova_senha_gerada):
                    msg_whatsapp = f"Olá, solicitei a recuperação de senha no Vision Pro V3.\nE-mail: {rec_email}\nMinha Nova Senha Gerada: {nova_senha_gerada}"
                    url_api_wa = f"https://api.whatsapp.com/send?phone={WHATSAPP_SUPORTE}&text={requests.utils.quote(msg_whatsapp)}"
                    
                    st.success("Senha atualizada! Clique no botão abaixo para encaminhar a validação direto ao seu WhatsApp de Suporte.")
                    st.markdown(f'<a href="{url_api_wa}" target="_blank"><button style="background-color:#25d366;color:white;border:none;padding:10px;border-radius:5px;font-weight:bold;cursor:pointer;width:100%;">🟢 Enviar Senha para o WhatsApp</button></a>', unsafe_allow_html=True)
            else:
                st.error("Dados incorretos. E-mail ou WhatsApp não conferem no banco.")
else:
    # Cabeçalho do App Autenticado
    st.title("🛡️ DASHBOARD VISION PRO")
    
    col_user, col_logout = st.columns([3, 1])
    with col_user:
        st.write(f"Conectado como: `{st.session_state['USER']}`")
    with col_logout:
        if st.button("Sair", type="primary", use_container_width=True, key="btn_logout"):
            st.session_state["USER"] = None
            st.rerun()

    st.markdown("---")

    # SCANNER EM TEMPO REAL E GRÁFICO PREMIUM
    st.markdown(f"""
        <div class="scanner-box">
            <span style='color:#9ca3af; font-size:14px; font-weight:bold;'>📡 SCANNER MULTI-ATIVOS EM EXECUÇÃO</span><br>
            <span style='color:white; font-size:22px; font-weight:bold;'>Analisando agora: </span>
            <span style='color:#00ffcc; font-size:24px; font-weight:bold;'>{st.session_state["ATIVO_ATUAL"]}</span>
        </div>
    """, unsafe_allow_html=True)
    
    # Gráfico Premium de área mostrando a oscilação do mercado em tempo real
    st.area_chart(st.session_state["GRAFICO_DATA"], use_container_width=True)

    # Área do Painel de Controle e Monitoramento
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 INICIAR ANALISADOR", use_container_width=True, key="btn_start_scan"):
            st.session_state["BOT_ATIVO"] = True
            st.session_state["SINAL_DISPLAY"] = "📡 Procurando oportunidades nos mercados..."
    with col2:
        if st.button("🛑 PAUSAR ANALISADOR", use_container_width=True, key="btn_stop_scan"):
            st.session_state["BOT_ATIVO"] = False
            st.session_state["SINAL_DISPLAY"] = "Scanner Pausado."

    # Mostrador do Alerta Atual
    st.info(st.session_state["SINAL_DISPLAY"])

    # Painel de Resultados Manuais
    if st.session_state["AG_RESULTADO"]:
        st.warning("Aguardando verificação do resultado da operação:")
        c1, c2, c3 = st.columns(3)
        if c1.button("✅ WIN", use_container_width=True, key="btn_win"):
            db_atualizar_ultimo_sinal("Win")
            db_atualizar_estatisticas(st.session_state["USER"], True)
            st.session_state["AG_RESULTADO"] = False
            st.rerun()
        if c2.button("🔄 GALE 1", use_container_width=True, key="btn_gale"):
            db_atualizar_ultimo_sinal("Win G1")
            db_atualizar_estatisticas(st.session_state["USER"], True)
            st.session_state["AG_RESULTADO"] = False
            st.rerun()
        if c3.button("❌ RED", use_container_width=True, key="btn_red"):
            db_atualizar_ultimo_sinal("Red")
            db_atualizar_estatisticas(st.session_state["USER"], False)
            st.session_state["AG_RESULTADO"] = False
            st.rerun()

    # Filtros de Configuração de Estratégias
    with st.expander("⚙️ Configurações de Ativos e Filtros"):
        st.session_state["MODO_MERCADO"] = st.radio("Mercado Alvo", ["TODOS", "FOREX", "CRIPTO"], index=0, key="radio_mercado")
        st.session_state["TIMEFRAME"] = st.selectbox("Timeframe (Minutos)", [1, 5, 15], index=1, key="select_tf")

    # Histórico de Operações vindo direto do Supabase
    st.subheader("📋 Histórico Recente de Sinais")
    historico = db_obter_historico()
    if historico:
        for h in historico:
            st.text(f"🕒 {h['sinal']} -> {h['resultado']}")
    else:
        st.caption("Nenhum registro encontrado no banco de dados Supabase.")

    # ================= PAINEL ADMINISTRATIVO CRUCIAL (GESTÃO DO ADM) =================
    if st.session_state["USER"] == ADMIN_EMAIL:
        st.markdown("---")
        with st.expander("👥 PAINEL ADMINISTRATIVO MASTER"):
            
            # Sub-aba 1: Criar Usuários
            st.markdown("### ➕ Cadastrar Novo Cliente")
            novo_email_adm = st.text_input("E-mail do Cliente", key="adm_novo_email")
            nova_senha_adm = st.text_input("Senha de Acesso", type="password", key="adm_nova_senha")
            novo_whatsapp_adm = st.text_input("WhatsApp do Cliente (Apenas números com DDD)", key="adm_novo_whatsapp")
            
            if st.button("Salvar e Liberar Acesso", key="btn_adm_salvar_user"):
                if novo_email_adm and nova_senha_adm and novo_whatsapp_adm:
                    if db_salvar_usuario(novo_email_adm, nova_senha_adm, novo_whatsapp_adm):
                        st.success(f"Usuário {novo_email_adm} cadastrado com sucesso!")
                    else:
                        st.error("Erro! Usuário já existe ou falha de conexão.")
                else:
                    st.warning("Preencha todos os campos para cadastrar.")
            
            st.markdown("---")
            
            # Sub-aba 2: Gerenciar Clientes Existentes
            st.markdown("### ⚙️ Gerenciar Clientes Cadastrados")
            alvo = st.text_input("E-mail do Cliente Alvo", key="admin_target_user")
            cc1, cc2 = st.columns(2)
            if cc1.button("Renovar Assinatura (+30 Dias)", key="btn_renew_user"):
                if alvo:
                    db_renovar_usuario(alvo)
                    st.success(f"Acesso de {alvo} renovado!")
                else:
                    st.warning("Insira o e-mail do cliente.")
            if cc2.button("Excluir Cliente Permanentemente", type="primary", key="btn_delete_user"):
                if alvo:
                    db_excluir_usuario(alvo)
                    st.error(f"Usuário {alvo} deletado!")
                else:
                    st.warning("Insira o e-mail do cliente.")
