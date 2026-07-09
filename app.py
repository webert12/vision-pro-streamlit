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
if "TG_MSG_ID" not in st.session_state:
    st.session_state["TG_MSG_ID"] = None

# Variavéis de Trava de Segurança
if "PRE_ALERTA_ATIVO" not in st.session_state:
    st.session_state["PRE_ALERTA_ATIVO"] = None
if "PRE_ALERTA_SINAL" not in st.session_state:
    st.session_state["PRE_ALERTA_SINAL"] = None

# Estados de notificações administrativas
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
        req = requests.post(url, json=payload, timeout=10).json()
        if req.get("ok"):
            return req["result"]["message_id"]
    except:
        pass
    return None

def apagar_telegram(msg_id):
    if msg_id:
        try:
            url = f"https://api.telegram.org/bot{TOKEN_TELEGRAM}/deleteMessage"
            payload = {"chat_id": CHAT_ID_TELEGRAM, "message_id": msg_id}
            requests.post(url, json=payload, timeout=10)
        except:
            pass

def limpar_alerta_tela():
    st.session_state["SINAL_DISPLAY"] = "📡 Procurando oportunidades nos mercados..."
    st.session_state["AG_RESULTADO"] = False
    st.session_state["ATIVO_ATUAL"] = "Analisando..."
    st.session_state["PRECOS_GRAFICO"] = []

# ================= FUNÇÕES DE BANCO DE DADOS =================
def db_carregar_usuario(email):
    if not email or str(email).strip() == "":
        return None
    try:
        res = supabase.table("usuarios").select("*").eq("email", email.strip().lower()).execute()
        if hasattr(res, 'data') and res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except:
        return None

def db_salvar_usuario(email, senha, whatsapp, ip="127.0.0.1"):
    try:
        if not email or not senha or str(email).strip() == "" or str(senha).strip() == "":
            return False
        check_user = db_carregar_usuario(email)
        if check_user is not None:
            return False
            
        hoje = datetime.now().strftime("%Y-%m-%d")
        supabase.table("usuarios").insert({
            "email": email.strip().lower(), 
            "senha": senha.strip(), 
            "whatsapp": whatsapp.strip(), 
            "ip": ip,
            "criado_em": hoje,
            "wins": 0,
            "reds": 0,
            "winrate": 0.0
        }).execute()
        return True
    except:
        return False

def db_atualizar_estatisticas(email, is_win):
    try:
        user = db_carregar_usuario(email)
        if user:
            wins = user.get("wins", 0) + 1 if is_win else user.get("wins", 0)
            reds = user.get("reds", 0) + 1 if not is_win else user.get("reds", 0)
            total = wins + reds
            winrate = round((wins / total) * 100, 1) if total > 0 else 0.0
            supabase.table("usuarios").update({"wins": wins, "reds": reds, "winrate": winrate}).eq("email", email.strip().lower()).execute()
    except:
        pass

def db_renovar_usuario(email):
    try:
        hoje = datetime.now().strftime("%Y-%m-%d")
        supabase.table("usuarios").update({"criado_em": hoje}).eq("email", email.strip().lower()).execute()
        return True
    except:
        return False

def db_excluir_usuario(email):
    try:
        supabase.table("usuarios").delete().eq("email", email.strip().lower()).execute()
        return True
    except:
        return False

def db_atualizar_senha(email, nova_senha):
    try:
        supabase.table("usuarios").update({"senha": nova_senha}).eq("email", email.strip().lower()).execute()
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

# ================= MOTOR DE ANÁLISE (YAHOO FINANCE) =================
ATIVOS_BASE = {
    "FOREX": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURJPY", "USDCAD", "USDCHF", "GBPJPY"],
    "CRIPTO": ["BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "XRPUSD", "ADAUSD", "AVAXUSD", "DOGEUSD", "SHIBUSD", "PEPEUSD"]
}

MAPA_TICKERS = {}
for par in ATIVOS_BASE["FOREX"]: MAPA_TICKERS[par] = f"{par}=X"
for par in ATIVOS_BASE["CRIPTO"]: MAPA_TICKERS[par] = "SHIB-USD" if "SHIB" in par else ("PEPE1-USD" if "PEPE" in par else par.replace("USD", "-USD"))

def get_data_v2(ticker, tf):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={tf}m&range=1d"
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
    except: 
        return None

def analisar_estrategia(data, estrategia, i=-1):
    c, o, h, l = data["close"], data["open"], data["high"], data["low"]
    # Análise forçada de no mínimo 60 velas antes de alertar
    if len(c) < 60: return None
    
    if estrategia == "LOGICA_DO_PRECO" or estrategia == "TODAS":
        if c[i] > o[i] and c[i] > h[i-1]: return "CALL"
        if c[i] < o[i] and c[i] < l[i-1]: return "PUT"
        
    if estrategia == "MHI1" or estrategia == "TODAS":
        cores = [("G" if c[j] > o[j] else "R") for j in range(i-2, i+1)]
        return "PUT" if cores.count("G") > cores.count("R") else "CALL"
        
    if estrategia == "RSI + MACD + MA" or estrategia == "TODAS":
        if c[i] > o[i] and c[i] > np.mean(c[-10:]): return "CALL"
        if c[i] < o[i] and c[i] < np.mean(c[-10:]): return "PUT"
        
    if estrategia == "REVERSÃO / RETRAÇÃO" or estrategia == "TODAS":
        if c[i] > o[i] and (h[i] - c[i]) > (c[i] - o[i]): return "PUT"
        if c[i] < o[i] and (c[i] - l[i]) > (o[i] - c[i]): return "CALL"
        
    return None

# ================= INTERFACE GRÁFICA =================
if st.session_state["USER"] is None:
    st.title("🎯 VISION PRO V3")
    aba1, aba2 = st.tabs(["🔒 Acessar Painel", "🔑 Recuperar Acesso"])

    with aba1:
        with st.form(key="form_login"):
            st.subheader("Login Protegido")
            email_input = st.text_input("E-mail", key="login_email_input")
            senha_input = st.text_input("Senha", type="password", key="login_senha_input")
            botao_login = st.form_submit_button("Entrar no Sistema")
            
            if botao_login:
                if email_input.strip().lower() == ADMIN_EMAIL and senha_input == "admin123":
                    st.session_state["USER"] = email_input.strip().lower()
                    st.rerun()
                else:
                    user = db_carregar_usuario(email_input)
                    if user and user["senha"] == senha_input:
                        st.session_state["USER"] = email_input.strip().lower()
                        st.rerun()
                    else:
                        st.error("Acesso negado. Credenciais inválidas ou assinatura expirada.")

    with aba2:
        with st.form(key="form_recuperacao"):
            st.subheader("Recuperação via WhatsApp")
            rec_email = st.text_input("E-mail Cadastrado", key="rec_email_input")
            rec_whatsapp = st.text_input("WhatsApp com DDD (Apenas números)", key="rec_whatsapp_input")
            botao_rec = st.form_submit_button("Solicitar Nova Senha")
            
            if botao_rec:
                user_data = db_carregar_usuario(rec_email)
                if user_data and str(user_data.get("whatsapp", "")).strip() == rec_whatsapp.strip():
                    nova_senha_generated = str(random.randint(100000, 999999))
                    if db_atualizar_senha(rec_email, nova_senha_generated):
                        msg_whatsapp = f"Olá, solicitei a recuperação de senha no Vision Pro V3.\nE-mail: {rec_email}\nMinha Nova Senha Gerada: {nova_senha_generated}"
                        url_api_wa = f"https://api.whatsapp.com/send?phone={WHATSAPP_SUPORTE}&text={requests.utils.quote(msg_whatsapp)}"
                        st.success("Senha atualizada! Clique no botão abaixo para enviar.")
                        st.session_state["WA_LINK"] = url_api_wa
                else:
                    st.error("Dados incorretos no banco de dados.")
                    
        if "WA_LINK" in st.session_state:
            st.markdown(f'<a href="{st.session_state["WA_LINK"]}" target="_blank"><button style="background-color:#25d366;color:white;border:none;padding:10px;border-radius:5px;font-weight:bold;cursor:pointer;width:100%;">🟢 Enviar Senha para o WhatsApp</button></a>', unsafe_allow_html=True)
            del st.session_state["WA_LINK"]
else:
    # App Autenticado
    st.title("🛡️ DASHBOARD VISION PRO")
    
    col_user, col_logout = st.columns([3, 1])
    with col_user:
        st.write(f"Conectado como: `{st.session_state['USER']}`")
    with col_logout:
        if st.button("Sair", type="primary", use_container_width=True, key="btn_logout"):
            st.session_state["USER"] = None
            st.session_state["BOT_ATIVO"] = False
            st.rerun()

    st.markdown("---")

    # SCANNER EM TEMPO REAL
    scanner_placeholder = st.empty()
    grafico_placeholder = st.empty()
    status_placeholder = st.empty()
    
    if not st.session_state["BOT_ATIVO"]:
        scanner_placeholder.markdown(f"""
            <div class="scanner-box" style="padding: 30px;">
                <div class="radar-pulse"></div>
                <span style='color:#00ffcc; font-size:18px; font-weight:bold; display:block; margin-top:10px;'>📡 ANTENA SCANNER AGUARDANDO COMANDO</span>
                <span style='color:#9ca3af; font-size:13px;'>Clique no botão abaixo para iniciar o radar de varredura.</span>
            </div>
        """, unsafe_allow_html=True)
        grafico_placeholder.line_chart(pd.DataFrame([0]*20))
    else:
        scanner_placeholder.markdown(f"""
            <div class="scanner-box">
                <div class="radar-pulse"></div>
                <span style='color:#00ffcc; font-size:16px; font-weight:bold; display:block;'>📡 RADAR DE ANTENA ATIVO E RODANDO</span>
                <div class="ativo-grande">{st.session_state["ATIVO_ATUAL"]}</div>
                <span class="radar-text">🔍 Filtrando Padrões: {st.session_state["ESTRATEGIA"]} | Timeframe: M{st.session_state["TIMEFRAME"]}</span>
            </div>
        """, unsafe_allow_html=True)
        
        if len(st.session_state["PRECOS_GRAFICO"]) > 0:
            grafico_placeholder.line_chart(pd.DataFrame(st.session_state["PRECOS_GRAFICO"][-20:]))
        else:
            grafico_placeholder.line_chart(pd.DataFrame([0]*20))

    # Painel de Controle de Varredura
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 INICIAR ANALISADOR", use_container_width=True, key="btn_start_scan"):
            st.session_state["BOT_ATIVO"] = True
            st.session_state["SINAL_DISPLAY"] = "📡 Procurando oportunidades nos mercados..."
            st.rerun()
    with col2:
        if st.button("🛑 PAUSAR ANALISADOR", use_container_width=True, key="btn_stop_scan"):
            st.session_state["BOT_ATIVO"] = False
            st.session_state["SINAL_DISPLAY"] = "Scanner Pausado."
            st.session_state["ATIVO_ATUAL"] = "Pausado"
            st.session_state["PRECOS_GRAFICO"] = []
            st.session_state["PRE_ALERTA_ATIVO"] = None
            st.session_state["PRE_ALERTA_SINAL"] = None
            st.rerun()

    status_placeholder.info(st.session_state["SINAL_DISPLAY"])

    # Painel de Resultados Manuais
    if st.session_state["AG_RESULTADO"]:
        st.warning("Aguardando verificação do resultado da operação:")
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("✅ WIN", use_container_width=True, key="btn_win"):
            db_atualizar_ultimo_sinal("Win")
            db_atualizar_estatisticas(st.session_state["USER"], True)
            apagar_telegram(st.session_state.get("TG_MSG_ID"))
            st.session_state["TG_MSG_ID"] = None
            limpar_alerta_tela()
            st.rerun()
        if c2.button("🔄 GALE 1", use_container_width=True, key="btn_gale"):
            db_atualizar_ultimo_sinal("Win G1")
            db_atualizar_estatisticas(st.session_state["USER"], True)
            apagar_telegram(st.session_state.get("TG_MSG_ID"))
            st.session_state["TG_MSG_ID"] = None
            limpar_alerta_tela()
            st.rerun()
        if c3.button("❌ RED", use_container_width=True, key="btn_red"):
            db_atualizar_ultimo_sinal("Red")
            db_atualizar_estatisticas(st.session_state["USER"], False)
            apagar_telegram(st.session_state.get("TG_MSG_ID"))
            st.session_state["TG_MSG_ID"] = None
            limpar_alerta_tela()
            st.rerun()
        if c4.button("⛔ CANCELAR", use_container_width=True, key="btn_cancel"):
            db_atualizar_ultimo_sinal("Cancelado")
            apagar_telegram(st.session_state.get("TG_MSG_ID"))
            st.session_state["TG_MSG_ID"] = None
            limpar_alerta_tela()
            st.rerun()

    # Filtros operacionais (BUG DO TIMEFRAME FIXADO AQUI)
    with st.expander("⚙️ Configurações de Ativos e Filtros"):
        idx_mercado = ["TODOS", "FOREX", "CRIPTO"].index(st.session_state["MODO_MERCADO"]) if st.session_state["MODO_MERCADO"] in ["TODOS", "FOREX", "CRIPTO"] else 0
        st.session_state["MODO_MERCADO"] = st.radio("Mercado Alvo", ["TODOS", "FOREX", "CRIPTO"], index=idx_mercado)
        
        opcoes_tf = [1, 5, 15]
        idx_tf = opcoes_tf.index(st.session_state["TIMEFRAME"]) if st.session_state["TIMEFRAME"] in opcoes_tf else 1
        st.session_state["TIMEFRAME"] = st.selectbox("Timeframe (Minutos)", opcoes_tf, index=idx_tf)
        
        opcoes_est = ["TODAS", "MHI1", "LOGICA_DO_PRECO", "RSI + MACD + MA", "REVERSÃO / RETRAÇÃO"]
        idx_est = opcoes_est.index(st.session_state["ESTRATEGIA"]) if st.session_state["ESTRATEGIA"] in opcoes_est else 0
        st.session_state["ESTRATEGIA"] = st.selectbox("Estratégia", opcoes_est, index=idx_est)

    # Histórico de Sinais obtidos do Supabase
    st.markdown("---")
    if st.button("📋 Ver Histórico de Sinais", use_container_width=True):
        st.session_state["MOSTRAR_HISTORICO"] = not st.session_state["MOSTRAR_HISTORICO"]
        
    if st.session_state["MOSTRAR_HISTORICO"]:
        st.subheader("📋 Histórico Recente de Sinais")
        historico = db_obter_historico()
        if historico:
            for h in historico:
                st.text(f"🕒 {h['sinal']} -> {h['resultado']}")
        else:
            st.caption("Nenhum registro encontrado no banco de dados Supabase.")

    # ================= PAINEL ADMINISTRATIVO MASTER =================
    if st.session_state["USER"] == ADMIN_EMAIL:
        st.markdown("---")
        with st.expander("👥 PAINEL ADMINISTRATIVO MASTER", expanded=True):
            
            if st.session_state["ADM_MSG_SUCESSO"]:
                st.success(st.session_state["ADM_MSG_SUCESSO"])
            if st.session_state["ADM_MSG_ERRO"]:
                st.error(st.session_state["ADM_MSG_ERRO"])
            if st.session_state["ADM_MSG_SUCESSO"] or st.session_state["ADM_MSG_ERRO"]:
                if st.button("🧹 Limpar Notificação", key="btn_limpar_notif"):
                    st.session_state["ADM_MSG_SUCESSO"] = None
                    st.session_state["ADM_MSG_ERRO"] = None
                    st.rerun()

            with st.form(key="form_cadastro_cliente"):
                st.markdown("### ➕ Cadastrar Novo Cliente")
                novo_email_adm = st.text_input("E-mail do Cliente", key="adm_input_novo_email")
                nova_senha_adm = st.text_input("Senha de Acesso", type="password", key="adm_input_nova_senha")
                novo_whatsapp_adm = st.text_input("WhatsApp do Cliente (Apenas números com DDD)", key="adm_input_novo_whatsapp")
                botao_salvar_adm = st.form_submit_button("Salvar e Liberar Acesso")
                
                if botao_salvar_adm:
                    if novo_email_adm and nova_senha_adm and novo_whatsapp_adm:
                        if db_salvar_usuario(novo_email_adm, nova_senha_adm, novo_whatsapp_adm):
                            st.session_state["ADM_MSG_SUCESSO"] = f"Usuário {novo_email_adm.strip().lower()} cadastrado com sucesso!"
                            st.session_state["ADM_MSG_ERRO"] = None
                        else:
                            st.session_state["ADM_MSG_ERRO"] = f"Não foi possível cadastrar. Verifique se o e-mail '{novo_email_adm.strip().lower()}' já existe ou configure o RLS no painel do Supabase."
                            st.session_state["ADM_MSG_SUCESSO"] = None
                        st.rerun()
                    else:
                        st.warning("Preencha todos os campos para cadastrar.")
            
            st.markdown("---")
            st.markdown("### ⚙️ Gerenciar Clientes Cadastrados")
            alvo = st.text_input("E-mail do Cliente Alvo", key="admin_target_user_input")
            cc1, cc2 = st.columns(2)
            if cc1.button("Renovar Assinatura (+30 Dias)", key="btn_renew_user"):
                if alvo:
                    if db_renovar_usuario(alvo):
                        st.success(f"Acesso de {alvo} renovado!")
                    else:
                        st.error("Falha ao renovar assinatura.")
                else:
                    st.warning("Insira o e-mail do cliente.")
            if cc2.button("Excluir Cliente Permanentemente", type="primary", key="btn_delete_user"):
                if alvo:
                    if db_excluir_usuario(alvo):
                        st.error(f"Usuário {alvo} deletado com sucesso do banco!")
                    else:
                        st.error("Falha ao deletar usuário.")
                else:
                    st.warning("Insira o e-mail do cliente.")

    # ================= LOOP DINÂMICO DE VARREDURA (Trava Integrada) =================
    if st.session_state["BOT_ATIVO"] and not st.session_state["AG_RESULTADO"]:
        FUSO = pytz.timezone("America/Sao_Paulo")
        agora = datetime.now(FUSO)
        tf = st.session_state["TIMEFRAME"]
        
        # Verifica se estamos no último minuto do timeframe escolhido
        is_last_minute = (agora.minute % tf) == (tf - 1)
        
        # 1. JANELA DE PRÉ-ALERTA (Avisa com antecedência aos 40s da vela -> Segundo 20 a 54)
        if is_last_minute and 20 <= agora.second < 55:
            if st.session_state.get("PRE_ALERTA_ATIVO") is None:
                ativos = ATIVOS_BASE["FOREX"] + ATIVOS_BASE["CRIPTO"] if st.session_state["MODO_MERCADO"] == "TODOS" else ATIVOS_BASE[st.session_state["MODO_MERCADO"]]
                
                for ativo in ativos:
                    ticker = MAPA_TICKERS.get(ativo, ativo)
                    st.session_state["ATIVO_ATUAL"] = f"Analisando {ativo}..."
                    
                    data = get_data_v2(ticker, tf)
                    if data and len(data["close"]) >= 60:
                        sinal = analisar_estrategia(data, st.session_state["ESTRATEGIA"])
                        if sinal:
                            st.session_state["PRE_ALERTA_ATIVO"] = ativo
                            st.session_state["PRE_ALERTA_SINAL"] = sinal
                            st.session_state["PRECOS_GRAFICO"] = list(data["close"][-20:])
                            
                            direcao_txt = "verde>compra" if sinal == "CALL" else "vermelho>venda"
                            h_ent = (agora + timedelta(minutes=1)).replace(second=0).strftime('%H:%M')
                            h_exp = (datetime.strptime(h_ent, '%H:%M') + timedelta(minutes=tf)).strftime('%H:%M')
                            
                            st.session_state["SINAL_DISPLAY"] = f"⚠️ **PRÉ-ALERTA:** Preparando {ativo}\n**Direção:** {direcao_txt}\n**Entrada:** {h_ent} | **Saída:** {h_exp}\n**Estratégia:** {st.session_state['ESTRATEGIA']}"
                            st.rerun()
                            break
                    time.sleep(0.1)
                time.sleep(1.0)
                st.rerun()
            else:
                # Se já tem pré-alerta, a tela congela aguardando o final da vela (sem piscar)
                time.sleep(1.0)
                st.rerun()
                
        # 2. JANELA DE CONFIRMAÇÃO (Faltando exatos 5 segundos -> Segundo 55 a 59)
        elif is_last_minute and agora.second >= 55:
            if st.session_state.get("PRE_ALERTA_ATIVO") is not None:
                ativo = st.session_state["PRE_ALERTA_ATIVO"]
                sinal_esperado = st.session_state["PRE_ALERTA_SINAL"]
                ticker = MAPA_TICKERS.get(ativo, ativo)
                
                data = get_data_v2(ticker, tf)
                if data and len(data["close"]) >= 60:
                    sinal_confirmado = analisar_estrategia(data, st.session_state["ESTRATEGIA"])
                    
                    if sinal_confirmado == sinal_esperado:
                        direcao_txt = "verde>compra" if sinal_confirmado == "CALL" else "vermelho>venda"
                        h_ent = (agora + timedelta(minutes=1)).replace(second=0).strftime('%H:%M')
                        h_exp = (datetime.strptime(h_ent, '%H:%M') + timedelta(minutes=tf)).strftime('%H:%M')
                        sinal_txt = f"{h_ent} | {h_exp} | {ativo}"
                        
                        st.session_state["ATIVO_ATUAL"] = ativo
                        st.session_state["SINAL_DISPLAY"] = f"🎯 **SINAL CONFIRMADO**\n\n**Ativo:** {ativo}\n**Direção:** {direcao_txt}\n**Time:** M{tf}\n**Entrada:** {h_ent} | **Saída:** {h_exp}\n**Estratégia:** {st.session_state['ESTRATEGIA']}"
                        
                        db_Salvar_sinal(sinal_txt)
                        
                        # Disparo para o Telegram exclusivo do ADMIN
                        if st.session_state["USER"] == ADMIN_EMAIL:
                            msg_tel = f"🎯 <b>SINAL CONFIRMADO</b>\n\n📈 Ativo: {ativo}\n🧭 Direção: {direcao_txt}\n🕒 Time: M{tf}\n⚙️ Estratégia: {st.session_state['ESTRATEGIA']}\n📥 Entrada: {h_ent}\n⌛ Saída: {h_exp}"
                            msg_id = enviar_telegram(msg_tel)
                            st.session_state["TG_MSG_ID"] = msg_id
                            
                        st.session_state["AG_RESULTADO"] = True
                        st.session_state["PRE_ALERTA_ATIVO"] = None
                        st.session_state["PRE_ALERTA_SINAL"] = None
                        st.rerun()
                    else:
                        st.session_state["SINAL_DISPLAY"] = f"❌ **ENTRADA CANCELADA em {ativo}:** Análise não confirmada. Voltando a varredura."
                        st.session_state["PRE_ALERTA_ATIVO"] = None
                        st.session_state["PRE_ALERTA_SINAL"] = None
                        time.sleep(3)
                        st.session_state["SINAL_DISPLAY"] = "📡 Procurando oportunidades nos mercados..."
                        st.rerun()
            else:
                time.sleep(1.0)
                st.rerun()
                
        # 3. MODO DE ESPERA (Fora da janela de análise, o sistema aguarda pacientemente sem piscar)
        else:
            if st.session_state.get("PRE_ALERTA_ATIVO") is not None:
                st.session_state["PRE_ALERTA_ATIVO"] = None
                st.session_state["PRE_ALERTA_SINAL"] = None
                
            st.session_state["ATIVO_ATUAL"] = "Aguardando janela..."
            st.session_state["SINAL_DISPLAY"] = f"📡 Scanner M{tf} ativo. O pré-alerta inicia aos 40s da vela..."
            st.session_state["PRECOS_GRAFICO"] = []
            
            time.sleep(1.0)
            st.rerun()
