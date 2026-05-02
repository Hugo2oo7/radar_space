import streamlit as st
import requests
import pandas as pd
import re
import math
import json
import os
from datetime import datetime, timedelta
import pytz
import time
import random
import urllib3

# Désactivation des alertes SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning())

# ==========================================
# CONFIGURATION & STYLE
# ==========================================
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1499765998377635900/FBUhSnXY4kBk7fSepXKJvCsIMe47njutPe31ttYURvfcW21Vz4ZxVu5xLweC1n6HgeOJ"
MPC_NEOCP = "https://minorplanetcenter.net/iau/NEO/neocp.txt"
NASA_CAD = "https://ssd-api.jpl.nasa.gov/cad.api"
DB_FILE = "radar_history.json"

st.set_page_config(page_title="Radar Spatial V20.0", layout="wide", page_icon="🛰️")

# CSS Personnalisé pour aérer l'interface
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border-left: 5px solid #ff4b4b; }
    div[data-testid="stExpander"] { border: none !important; box-shadow: none !important; background-color: #161b22; border-radius: 15px; }
    .stDataFrame { border-radius: 10px; overflow: hidden; }
    h1, h2, h3 { color: #ffffff; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    </style>
    """, unsafe_allow_html=True) # <-- C'est ici que j'avais mis 'value' au lieu de 'html'

# Initialisation des états
if 'nasa_cache' not in st.session_state: st.session_state.nasa_cache = pd.DataFrame()
if 'last_nasa_request' not in st.session_state: st.session_state.last_nasa_request = datetime.now() - timedelta(minutes=5)
if 'last_alert_time' not in st.session_state: st.session_state.last_alert_time = datetime.now() - timedelta(hours=2)
if 'old_anomalies' not in st.session_state: st.session_state.old_anomalies = []
if 'old_identified' not in st.session_state: st.session_state.old_identified = []
if 'alerted_high_score' not in st.session_state: st.session_state.alerted_high_score = []
if 'alerted_critical_score' not in st.session_state: st.session_state.alerted_critical_score = []

# ==========================================
# FONCTIONS LOGIQUES & ALERTES
# ==========================================

def get_detailed_type(name, fullname=""):
    n, f = str(name).upper(), str(fullname).upper()
    if any(x in (f + n) for x in ["/", "PCCP", "COMET", "C/", "P/"]): return "🌠 Comète"
    if any(x in (f + n) for x in ["R/B", "DEBRIS", "SAT", "SL-", "TELESAT"]): return "🛰️ Artificiel"
    return "☄️ Astéroïde"

def get_trend_icon(name, current_score):
    hist = st.session_state.obj_history.get(name, [])
    if len(hist) < 2: return "➡️"
    diff = current_score - hist[-2]["S"]
    return "↗️" if diff > 0.5 else "↘️" if diff < -0.5 else "➡️"

def monitor_and_alert(df_u, df_i):
    paris_tz = pytz.timezone('Europe/Paris')
    now = datetime.now(paris_tz).strftime("%H:%M:%S")
    cur_names = df_u['Nom'].tolist()
    cur_identified = df_i['Nom'].tolist() if not df_i.empty else []
    events = []

    for r in df_u.itertuples():
        tr = get_trend_icon(r.Nom, r.Score)
        # Alertes Niveaux
        if r.Score >= 80 and r.Nom not in st.session_state.alerted_critical_score:
            events.append(f"🚨 **CRITIQUE (80+) :** `{r.Nom}` {tr} Score: {r.Score}")
            st.session_state.alerted_critical_score.append(r.Nom)
        elif r.Score >= 50 and r.Nom not in st.session_state.alerted_high_score:
            events.append(f"🔥 **SEUIL 50 :** `{r.Nom}` {tr} Score: {r.Score}")
            st.session_state.alerted_high_score.append(r.Nom)
        
        # Mouvements brusques
        hist = st.session_state.obj_history.get(r.Nom, [])
        if len(hist) >= 2:
            diff = r.Score - hist[-2]["S"]
            if abs(diff) >= 2.0:
                events.append(f"{'📈' if diff>0 else '📉'} **VARIATION :** `{r.Nom}` {tr} ({diff:+.1f})")

    # Flux (Nouveaux / Promotions)
    new = [n for n in cur_names if n not in st.session_state.old_anomalies and n not in st.session_state.old_identified]
    if new: events.append(f"🆕 **NOUVEAU :** `{', '.join(new)}` est apparu !")
    
    promoted = [n for n in cur_identified if n in st.session_state.old_anomalies]
    if promoted: events.append(f"🎓 **PROMOTION :** `{', '.join(promoted)}` identifié NASA !")

    if events:
        try: requests.post(DISCORD_WEBHOOK, json={"content": "🛰️ **RADAR SENTINELLE**\n" + "\n".join(events)}, timeout=5)
        except: pass

    # Recap Horaire
    if (now - st.session_state.last_alert_time).total_seconds() > 3600:
        if not df_u.empty:
            recap = f"📊 **RECAP HORAIRE ({now.strftime('%H:%M')})**\n"
            for row in df_u.sort_values("Score", ascending=False).head(5).itertuples():
                recap += f"- {row.Nom} {get_trend_icon(row.Nom, row.Score)} (S:{row.Score} | m:{row.m})\n"
            requests.post(DISCORD_WEBHOOK, json={"content": recap})
            st.session_state.last_alert_time = now

    st.session_state.old_anomalies = cur_names
    st.session_state.old_identified = cur_identified

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/e/e5/NASA_logo.svg", width=80)
    st.title("Contrôle Radar")
    if st.button("🚨 TEST DISCORD"):
        monitor_and_alert(pd.DataFrame([{"Nom": "TEST_OBJ", "Score": 99.0, "m": 12.0}]), pd.DataFrame())
    
    st.divider()
    refresh = st.slider("Rafraîchissement (s)", 10, 300, 30)
    days = st.slider("Horizon (Jours)", 1, 90, 30)
    radius = st.slider("Rayon (LD)", 1, 1000, 300)
    
    st.divider()
    vespera = st.toggle("Mode Vespera", value=True)
    mag_limit = st.slider("Magnitude Max", 5.0, 22.0, 15.5, disabled=not vespera)

# ==========================================
# DATA FETCHING
# ==========================================

def fetch_data():
    # Fetch MPC
    df_u = pd.DataFrame()
    try:
        r = requests.get(MPC_NEOCP, timeout=10).text
        data = []
        for l in r.split('\n'):
            p = re.split(r'\s+', l.strip())
            if len(p) >= 10:
                sc = round((max(0,(25-float(p[-3]))/25)*35) + (max(0,(15-float(p[-2]))/15)*35) + (min(1,float(p[-1])/10)*15), 1)
                data.append([p[0], get_detailed_type(p[0]), float(p[5]), sc])
        df_u = pd.DataFrame(data, columns=["Nom", "Type", "m", "Score"])
    except: pass

    # Fetch NASA (Cache)
    paris_tz = pytz.timezone('Europe/Paris')
    now = datetime.now(paris_tz).strftime("%H:%M:%S")
    df_n = st.session_state.nasa_cache
    if (now - st.session_state.last_nasa_request).total_seconds() > 60:
        try:
            url = f"{NASA_CAD}?dist-max={radius}LD&date-min={now.strftime('%Y-%m-%d')}&date-max={(now+timedelta(days=days)).strftime('%Y-%m-%d')}&fullname=true"
            res = requests.get(url, timeout=20).json()
            if "data" in res:
                df_n = pd.DataFrame(res["data"], columns=res["fields"])
                st.session_state.nasa_cache, st.session_state.last_nasa_request = df_n, now
        except: pass
    return df_u, df_n

def fetch_comets():
    if 'comet_cache' in st.session_state and (datetime.now() - st.session_state.get('last_comet_time', datetime.now())).total_seconds() < 3600:
        return st.session_state.comet_cache
    try:
        r = requests.get("https://www.minorplanetcenter.net/iau/Ephemerides/Comets/Soft00Cmt.txt", timeout=15, verify=False)
        data = [{"Nom": l[0:43].strip(), "Mag": float(l[123:129])} for l in r.text.split('\n') if len(l) > 130 and l[123:129].strip()]
        df = pd.DataFrame(data)
        st.session_state.comet_cache, st.session_state.last_comet_time = df, datetime.now()
        return df
    except: return st.session_state.get('comet_cache', pd.DataFrame())

# ==========================================
# INTERFACE PRINCIPALE
# ==========================================
df_mpc, df_nasa = fetch_data()
df_comets = fetch_comets()

# Historique
if 'obj_history' not in st.session_state: st.session_state.obj_history = {}
if not df_mpc.empty:
    for r in df_mpc.itertuples():
        if r.Nom not in st.session_state.obj_history: st.session_state.obj_history[r.Nom] = []
        st.session_state.obj_history[r.Nom].append({"H": datetime.now().strftime("%H:%M"), "S": r.Score})

# Separation Anomalies / Identifiés
nasa_list = df_nasa['des'].tolist() if not df_nasa.empty else []
df_anom = df_mpc[~df_mpc['Nom'].isin(nasa_list)].sort_values("Score", ascending=False)
df_id = df_mpc[df_mpc['Nom'].isin(nasa_list)]

# Lancement Alertes
monitor_and_alert(df_anom, df_id)

# --- HEADER ---
c_h1, c_h2, c_h3 = st.columns([2,1,1])
with c_h1: st.title("🛰️ Deep Space Radar V20.0")
with c_h2: st.metric("📡 État MPC", "Connecté", delta="Live")
with c_h3: st.metric("🔭 État NASA", "Synchronisé", delta="OK")

# --- TABLEAUX PRINCIPAUX ---
tab1, tab2, tab3 = st.tabs(["🔭 SURVEILLANCE CRITIQUE", "☄️ CATALOGUE NASA", "🌠 COMÈTES"])

with tab1:
    col_a, col_b = st.columns([1.5, 1])
    with col_a:
        st.subheader("Anomalies Détectées (Non Identifiées)")
        if not df_anom.empty:
            df_disp = df_anom.copy()
            df_disp['Tendance'] = df_disp.apply(lambda r: get_trend_icon(r['Nom'], r['Score']), axis=1)
            st.dataframe(df_disp[["Nom", "Tendance", "Score", "m", "Type"]], width="stretch", hide_index=True)
        else: st.success("Aucune anomalie suspecte détectée.")
    
    with col_b:
        st.subheader("Objets en Cours d'Identification")
        st.dataframe(df_id[["Nom", "Score", "m"]], use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Objets Confirmés par le JPL (NASA)")
    if not df_nasa.empty:
        df_nasa['h'] = pd.to_numeric(df_nasa['h'], errors='coerce')
        df_nasa['m_est'] = df_nasa.apply(lambda r: round(float(r['h']) + 5 * math.log10(max(0.1, float(r['v_rel']))/10) + 0.5, 1) if not pd.isna(r['h']) else 99, axis=1)
        df_nasa['Type'] = df_nasa.apply(lambda r: get_detailed_type(r['des']), axis=1)
        if vespera: df_nasa = df_nasa[df_nasa['m_est'] <= mag_limit]
        cols = ["des", "Type", "h", "cd", "dist", "v_rel", "m_est"]
        st.dataframe(df_nasa[cols].sort_values("dist"), use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Comètes Actives")
    if not df_comets.empty:
        st.dataframe(df_comets[df_comets['Mag'] <= (mag_limit if vespera else 20)].sort_values("Mag"), use_container_width=True, hide_index=True)
    else: st.warning("Données cométaires indisponibles.")

# --- ANALYSE & LEXIQUE ---
st.divider()
c_low1, c_low2 = st.columns([1, 1.2])

with c_low1:
    st.subheader("📈 Sismographe de Score")
    target = st.selectbox("Sélectionner un objet à suivre :", list(st.session_state.obj_history.keys()))
    if target:
        h_df = pd.DataFrame(st.session_state.obj_history[target]).set_index("H")
        st.line_chart(h_df, color="#ff4b4b")

with c_low2:
    st.subheader("📘 Lexique & Ordres de Grandeur")
    col_odg1, col_odg2 = st.columns(2)
    with col_odg1:
        st.markdown("""
        **📏 Taille (H)**
        - `< 18` : **Monstre** (+1 km)
        - `22` : **Régional** (~140 m)
        - `> 26` : **Local** (< 20 m)
        """)
    with col_odg2:
        st.markdown("""
        **🔆 Brillance (m)**
        - `< 6` : Oeil nu
        - `10-15` : **Cible Vespera**
        - `> 19` : Télescopes Pro
        """)
    st.info("💡 **Distance** : 1 LD = 384 400 km (Terre-Lune).")

# Loop
time.sleep(refresh)
st.rerun()
