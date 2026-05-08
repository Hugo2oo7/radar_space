import streamlit as st
import requests
import pandas as pd
import re
import time
import math
import urllib3
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DISCORD_WEBHOOK = (
    "https://discord.com/api/webhooks/1499765998377635900/"
    "FBUhSnXY4kBk7fSepXKJvCsIMe47njutPe31ttYURvfcW21Vz4ZxVu5xLweC1n6HgeOJ"
)

SCOUT_API        = "https://ssd-api.jpl.nasa.gov/scout.api"
NASA_CAD         = "https://ssd-api.jpl.nasa.gov/cad.api"
NASA_SBDB        = "https://ssd-api.jpl.nasa.gov/sbdb.api"
HORIZONS_API     = "https://ssd.jpl.nasa.gov/api/horizons.api"
ROCHESTER_SN     = "https://rochesterastronomy.org/supernova.html"
ROCHESTER_SN26   = "https://rochesterastronomy.org/sn2026/index.html"
TNS_SEARCH       = "https://www.wis-tns.org/search"
COMET_URL        = "http://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt"
MPC_PREV_JSON    = "https://data.minorplanetcenter.net/api/get-neocp-objects-removed"
SNEWS_ALERT      = "https://snews2.org/"

VESP_SHORT  = 14.5
VESP_MEDIUM = 16.0
VESP_LONG   = 17.5
VESP_LIMIT  = 19.0

SN_TYPE_INFO = {
    "Ia":    {"emoji": "💥", "desc": "Naine blanche thermonucléaire", "duree": "~60j", "couleur": "#ff6b6b"},
    "Ib":    {"emoji": "🌀", "desc": "Effondrement — étoile dépouillée H", "duree": "~40j", "couleur": "#ff9f43"},
    "Ic":    {"emoji": "🌀", "desc": "Effondrement — étoile dépouillée H+He", "duree": "~35j", "couleur": "#ff9f43"},
    "Ic-BL": {"emoji": "⚡", "desc": "Ic hypernova — liée à un GRB", "duree": "~30j", "couleur": "#ff4757"},
    "II":    {"emoji": "💫", "desc": "Effondrement cœur — supergéante rouge", "duree": "~100j", "couleur": "#54a0ff"},
    "II-P":  {"emoji": "💫", "desc": "Type II à plateau (hydrogène riche)", "duree": "~120j", "couleur": "#54a0ff"},
    "IIn":   {"emoji": "🌊", "desc": "Interaction avec enveloppe circumstellaire", "duree": "~200j+", "couleur": "#5f27cd"},
    "IIb":   {"emoji": "🔀", "desc": "Transition II→Ib (perte partielle H)", "duree": "~80j", "couleur": "#00d2d3"},
    "SLSN-I":{"emoji": "🚀", "desc": "Super-lumineuse sans H (magnétar?)", "duree": "~200j+", "couleur": "#ffd32a"},
    "SLSN-II":{"emoji":"🚀", "desc": "Super-lumineuse avec H", "duree": "~200j+", "couleur": "#ffd32a"},
    "TDE":   {"emoji": "🕳️", "desc": "Disruption par marées (trou noir)", "duree": "variable", "couleur": "#ff6b81"},
    "Nova":  {"emoji": "✨", "desc": "Nova (naine blanche + compagnon)", "duree": "~weeks", "couleur": "#eccc68"},
    "?":     {"emoji": "❓", "desc": "Type non classifié", "duree": "?", "couleur": "#747d8c"},
}

def sn_type_info(t: str) -> dict:
    if not t or t in ("", "None", "nan"): return SN_TYPE_INFO["?"]
    t = str(t).strip()
    for k in SN_TYPE_INFO:
        if k.lower() in t.lower(): return SN_TYPE_INFO[k]
    return SN_TYPE_INFO["?"]

st.set_page_config(page_title="Deep Space Radar", layout="wide", page_icon="🛰️")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&family=Exo+2:wght@300;400;600&display=swap');
:root{--bg:#07090f;--surface:#0d1120;--surface2:#131829;--border:#1e2a45;
      --accent:#00d4ff;--accent2:#ff4b4b;--accent3:#f7b731;--green:#00ff88;
      --purple:#b44eff;--pink:#ff6b9d;
      --text:#c8d8f0;--muted:#5a7090;
      --mono:'Share Tech Mono',monospace;--ui:'Rajdhani',sans-serif;--body:'Exo 2',sans-serif;}
html,body,[class*="css"]{font-family:var(--body);background-color:var(--bg)!important;color:var(--text);}
.stApp::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(ellipse 80% 50% at 20% 10%,rgba(0,212,255,.06) 0%,transparent 60%),
             radial-gradient(ellipse 60% 40% at 80% 80%,rgba(255,75,75,.05) 0%,transparent 60%),
             radial-gradient(ellipse 40% 30% at 50% 50%,rgba(180,78,255,.03) 0%,transparent 60%);}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#0a0e1a,#0d1323)!important;border-right:1px solid var(--border)!important;}
.radar-logo{font-family:var(--mono);font-size:2.2em;letter-spacing:-2px;color:var(--accent);text-shadow:0 0 20px rgba(0,212,255,.5);}
.radar-sub{font-family:var(--ui);font-size:.8em;color:var(--muted);letter-spacing:3px;text-transform:uppercase;}
.sync-pill{background:var(--surface2);border:1px solid var(--border);border-radius:50px;padding:5px 16px;
           font-family:var(--mono);font-size:.82em;color:var(--accent);display:inline-flex;align-items:center;gap:7px;}
.sync-dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);animation:blink 1.2s infinite;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
@keyframes pulse-red{0%,100%{box-shadow:0 0 0 0 rgba(255,75,75,.4)}70%{box-shadow:0 0 0 8px rgba(255,75,75,0)}}
@keyframes nova-glow{0%,100%{text-shadow:0 0 8px rgba(255,215,0,.6)}50%{text-shadow:0 0 20px rgba(255,215,0,1),0 0 40px rgba(255,100,0,.8)}}
.metric-grid{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap;}
.metric-card{flex:1;min-width:115px;background:var(--surface);border:1px solid var(--border);
             border-top:3px solid var(--accent);border-radius:10px;padding:12px 16px;}
.metric-card.w{border-top-color:var(--accent2);} .metric-card.c{border-top-color:var(--accent3);}
.metric-card.g{border-top-color:var(--green);} .metric-card.p{border-top-color:var(--purple);}
.metric-card.pk{border-top-color:var(--pink);}
.metric-val{font-family:var(--mono);font-size:1.9em;color:var(--accent);line-height:1.1;}
.metric-card.w .metric-val{color:var(--accent2);} .metric-card.c .metric-val{color:var(--accent3);}
.metric-card.g .metric-val{color:var(--green);} .metric-card.p .metric-val{color:var(--purple);}
.metric-card.pk .metric-val{color:var(--pink);}
.metric-label{font-family:var(--ui);font-size:.72em;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-top:3px;}
.stTabs [data-baseweb="tab-list"]{background:transparent;border-bottom:1px solid var(--border);}
.stTabs [data-baseweb="tab"]{font-family:var(--ui);font-weight:600;font-size:.88em;color:var(--muted)!important;
                               padding:9px 20px;border-bottom:2px solid transparent;background:transparent!important;}
.stTabs [aria-selected="true"]{color:var(--accent)!important;border-bottom:2px solid var(--accent)!important;}
.sec{font-family:var(--ui);font-size:.95em;font-weight:700;letter-spacing:2px;text-transform:uppercase;
     color:var(--accent);margin-bottom:10px;display:flex;align-items:center;gap:7px;}
.sec::before{content:'';display:inline-block;width:4px;height:16px;background:var(--accent);border-radius:2px;}
.sec.sn{color:var(--purple);} .sec.sn::before{background:var(--purple);}
.empty{background:var(--surface2);border:1px dashed var(--border);border-radius:8px;padding:20px;
       text-align:center;color:var(--muted);font-family:var(--mono);font-size:.82em;}
.sidebar-sec{font-family:var(--ui);font-size:.68em;letter-spacing:3px;text-transform:uppercase;color:var(--muted);
             margin:16px 0 5px;padding-top:10px;border-top:1px solid var(--border);}
.sn-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
         padding:16px 18px;margin-bottom:10px;position:relative;overflow:hidden;}
.sn-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;}
.sn-card.vespera::before{background:linear-gradient(90deg,var(--green),var(--accent));}
.sn-card.marginal::before{background:linear-gradient(90deg,var(--accent3),var(--accent2));}
.sn-card.outofrange::before{background:var(--muted);}
.sn-card.galactic{animation:pulse-red 2s infinite;border-color:var(--accent2)!important;}
.sn-card.galactic::before{background:linear-gradient(90deg,var(--accent2),var(--accent3)) !important;}
.sn-name{font-family:var(--mono);font-size:1.1em;color:var(--accent3);font-weight:bold;}
.sn-name.galactic-name{animation:nova-glow 1.5s infinite;color:#ffd700 !important;}
.sn-host{color:var(--muted);font-size:.82em;font-family:var(--body);}
.sn-badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:.72em;
          font-family:var(--mono);border:1px solid;margin-right:4px;}
.sn-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:6px;margin-top:10px;}
.sn-stat{background:var(--surface2);border-radius:6px;padding:6px 10px;}
.sn-stat-k{font-size:.68em;color:var(--muted);font-family:var(--mono);text-transform:uppercase;}
.sn-stat-v{font-size:.9em;color:var(--text);font-weight:600;}
.trans-card{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--accent3);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
.dc-row{display:flex;gap:10px;align-items:baseline;padding:3px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:.8em;}
.dc-row:last-child{border-bottom:none;}
.dc-ts{color:var(--muted);font-family:var(--mono);min-width:65px;}
.dc-ok{color:var(--green);min-width:80px;font-family:var(--mono);}
.dc-w{color:var(--accent3);min-width:80px;font-family:var(--mono);}
.dc-err{color:var(--accent2);min-width:80px;font-family:var(--mono);}
.dc-msg{color:var(--text);opacity:.65;}
.jpl-box{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:16px 18px;margin-top:10px;}
.jpl-title{font-family:var(--ui);font-size:.95em;font-weight:700;color:var(--accent3);margin-bottom:10px;}
.jpl-f{margin-bottom:6px;font-family:var(--mono);font-size:.8em;color:var(--muted);}
.jpl-v{color:var(--text);font-weight:bold;}
.fun-fact{background:linear-gradient(135deg,rgba(180,78,255,.08),rgba(0,212,255,.05));
          border:1px solid rgba(180,78,255,.25);border-radius:10px;padding:14px 16px;margin-top:10px;}
.fun-fact-title{font-family:var(--mono);font-size:.75em;color:var(--purple);letter-spacing:2px;margin-bottom:6px;}
.fun-fact-text{font-size:.85em;color:var(--text);line-height:1.6;}
.galactic-alert{background:linear-gradient(135deg,rgba(255,75,75,.15),rgba(247,183,49,.1));
                border:2px solid var(--accent2);border-radius:12px;padding:20px;
                text-align:center;animation:pulse-red 2s infinite;}
.galactic-alert-title{font-family:var(--mono);font-size:1.4em;color:#ff4b4b;
                       text-shadow:0 0 20px rgba(255,75,75,.8);margin-bottom:8px;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding-top:1.4rem!important;}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════════════════════
def _init(k, v):
    if k not in st.session_state: st.session_state[k] = v

_init('obj_history',        {})
_init('nasa_cache',         pd.DataFrame())
_init('comet_cache',        pd.DataFrame())
_init('scout_cache',        pd.DataFrame())
_init('sn_cache',           pd.DataFrame())
_init('last_nasa_req',      datetime.now() - timedelta(minutes=5))
_init('last_scout_req',     datetime.now() - timedelta(minutes=5))
_init('last_comet_req',     datetime.now() - timedelta(hours=3))
_init('last_sn_req',        datetime.now() - timedelta(hours=2))
_init('last_alert_time',    datetime.now() - timedelta(hours=2))
_init('last_refresh',       datetime.now())
_init('discord_log',        [])
_init('discord_queue',      [])
_init('alerted_new',        set())
_init('alerted_gone',       set())
_init('alerted_sn',         set())
_init('alerted_sn_vespera', set())
_init('alerted_galactic',   set())
_init('score_palier',       {})
_init('prev_top5',          [])
_init('prev_noms',          set())
_init('recognized_objects', {})
_init('prev_neocp_cache',   {})
_init('last_prev_req',      datetime.now() - timedelta(hours=2))
_init('archived',           set())
_init('fun_fact_idx',       0)
_init('sn_history',         {})

FUN_FACTS = [
    ("🌟 SN 2023ixf", "Découverte par un astronome amateur japonais dans M101 à mag ~11 — visible aux jumelles pendant des semaines."),
    ("💥 Énergie d'une supernova", "En quelques secondes, une supernova libère autant d'énergie que le Soleil en 10 milliards d'années. 99% part en neutrinos."),
    ("🔭 Apophis 2029", "Le 13 avril 2029, l'astéroïde Apophis (340m) passera à seulement 32 000 km — plus près que certains satellites géostationnaires."),
    ("☄️ Ceinture de Kuiper", "La ceinture de Kuiper contient plus d'un trillion d'objets. La sonde New Horizons y vogue encore aujourd'hui."),
    ("🌌 Supernova galactique", "La dernière supernova visible à l'œil nu dans la Voie Lactée date de 1604 (Kepler). La prochaine pourrait être Bételgeuse."),
    ("🪨 NEOCP", "En moyenne, 5 à 10 nouveaux objets apparaissent chaque jour sur le NEOCP. La plupart disparaissent en 48h une fois leur orbite contrainte."),
    ("⚡ Vitesse des neutrinos SN", "Les neutrinos de SN 1987A ont atteint la Terre 3 heures AVANT la lumière visible."),
    ("🌠 Comète interstellaire", "2I/Borisov (2019) est la première comète interstellaire confirmée — elle venait d'un autre système solaire."),
    ("🛰️ Vespera II", "Ton Vespera II peut capturer des objets jusqu'à mag ~19 en une nuit — soit des millions de galaxies et d'astéroïdes potentiels."),
    ("🔴 Bételgeuse", "Bételgeuse a diminué de 35% en luminosité en 2019-2020. Quand elle explosera, elle sera visible en plein jour."),
    ("💫 Type Ia standard", "Les supernovæ de type Ia sont des 'chandelles standard' : elles ont permis de découvrir l'énergie sombre en 1998."),
    ("🌍 MOID critique", "Un MOID < 0.05 UA ET H < 22 classe automatiquement un objet comme PHO. Il en existe ~2300 connus."),
    ("📡 SNEWS", "Le réseau SNEWS relie des détecteurs de neutrinos mondiaux : il peut alerter les astronomes AVANT qu'une SN galactique soit visible !"),
    ("🕳️ GW170817", "En 2017, une fusion d'étoiles à neutrons détectée en ondes gravitationnelles ET en lumière — naissance de l'astronomie multi-messagers."),
    ("🌊 Kilonova", "Les fusions d'étoiles à neutrons sont la principale source d'or, de platine et d'uranium. Chaque bijou en or vient d'une telle explosion."),
]

# ═══════════════════════════════════════════════════════════════════════════════
# SCORES & UTILS
# ═══════════════════════════════════════════════════════════════════════════════
def compute_score(h, n_obs, arc, moid=99, neo_score=0):
    s_h    = max(0.0, min(35.0, (25.0 - h) / 25.0 * 35.0))
    s_arc  = max(0.0, min(25.0, (30.0 - arc) / 30.0 * 25.0))
    s_obs  = max(0.0, min(20.0, (50.0 - n_obs) / 50.0 * 20.0))
    s_moid = max(0.0, min(10.0, (0.1 - min(moid, 0.1)) / 0.1 * 10.0)) if moid < 99 else 0.0
    s_neo  = neo_score / 100.0 * 10.0
    return round(s_h + s_arc + s_obs + s_moid + s_neo, 1)

def vespera_score(mag):
    try: mag = float(mag)
    except: return 0, "⛔ Hors portée"
    if mag <= 10:          return 100, "👁️ Trivial"
    if mag <= VESP_SHORT:  return 90,  "🟢 Excellent (10 min)"
    if mag <= VESP_MEDIUM: return 70,  "🟡 Bon (30 min)"
    if mag <= VESP_LONG:   return 45,  "🟠 Limite (nuit entière)"
    if mag <= VESP_LIMIT:  return 15,  "🔴 Très difficile"
    return 0, "⛔ Hors portée"

def score_label(s):
    if s >= 80: return "🔴 CRITIQUE"
    if s >= 50: return "🟡 ÉLEVÉ"
    return "🟢 FAIBLE"

def classify_size(h):
    if h < 18: return ">1 km"
    if h < 22: return "100m–1km"
    if h < 25: return "10–100m"
    return "<10m"

def get_trend(name, score):
    h = st.session_state.obj_history.get(name, [])
    if len(h) < 2: return "➡️"
    d = score - h[-2]["S"]
    return "↗️" if d > 0.5 else "↘️" if d < -0.5 else "➡️"

def is_galactic(ra_deg, dec_deg):
    try:
        ra_r  = math.radians(float(ra_deg))
        dec_r = math.radians(float(dec_deg))
        ra_gp = math.radians(192.8595)
        dec_gp= math.radians(27.1284)
        sin_b = (math.sin(dec_r)*math.sin(dec_gp) +
                 math.cos(dec_r)*math.cos(dec_gp)*math.cos(ra_r - ra_gp))
        b = math.degrees(math.asin(max(-1, min(1, sin_b))))
        return abs(b) < 15, round(b, 1)
    except:
        return False, 0

def ra_hms_to_deg(ra_str):
    try:
        parts = str(ra_str).replace('h',' ').replace('m',' ').replace('s','').split()
        if len(parts) == 3:
            return (float(parts[0]) + float(parts[1])/60 + float(parts[2])/3600) * 15
        return float(ra_str)
    except:
        return None

def dec_dms_to_deg(dec_str):
    try:
        dec_str = str(dec_str).strip()
        sign = -1 if dec_str.startswith('-') else 1
        dec_str = dec_str.lstrip('+-')
        parts = dec_str.replace('°',' ').replace("'",' ').replace('"','').split()
        if len(parts) == 3:
            return sign * (float(parts[0]) + float(parts[1])/60 + float(parts[2])/3600)
        return float(dec_str)
    except:
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# DISCORD
# ═══════════════════════════════════════════════════════════════════════════════
def _discord(content: str):
    ts = datetime.now().strftime("%H:%M:%S")
    prev = content[:90].replace("\n", " ")
    try:
        r = requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=5)
        status_str = "✅ OK" if r.status_code in (200, 204) else f"⚠️ HTTP {r.status_code}"
        if r.status_code not in (200, 204):
            st.session_state.discord_queue.append({"content": content, "attempt": 1,
                "next_try": datetime.now() + timedelta(seconds=60)})
    except Exception as e:
        status_str = f"❌ {type(e).__name__}"
        st.session_state.discord_queue.append({"content": content, "attempt": 1,
            "next_try": datetime.now() + timedelta(seconds=60)})
    st.session_state.discord_log.append((ts, status_str, prev))
    if len(st.session_state.discord_log) > 30:
        st.session_state.discord_log = st.session_state.discord_log[-30:]

def _process_discord_queue():
    now = datetime.now()
    remaining = []
    for item in st.session_state.discord_queue:
        if now < item["next_try"]:
            remaining.append(item); continue
        if item["attempt"] >= 5:
            st.session_state.discord_log.append((now.strftime("%H:%M:%S"),
                "❌ Abandon", item["content"][:60])); continue
        try:
            r = requests.post(DISCORD_WEBHOOK, json={"content": item["content"]}, timeout=5)
            if r.status_code in (200, 204):
                st.session_state.discord_log.append((now.strftime("%H:%M:%S"),
                    f"✅ Retry#{item['attempt']}", item["content"][:60]))
            else:
                item["attempt"] += 1; item["next_try"] = now + timedelta(seconds=60)
                remaining.append(item)
        except:
            item["attempt"] += 1; item["next_try"] = now + timedelta(seconds=60)
            remaining.append(item)
    st.session_state.discord_queue = remaining

# ═══════════════════════════════════════════════════════════════════════════════
# FETCH SUPERNOVÆ — CHARGEMENT DIFFÉRÉ (ne bloque pas le boot)
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_supernovae() -> pd.DataFrame:
    now = datetime.now()
    td = (now - st.session_state.last_sn_req).total_seconds()
    if td < 1800 and not st.session_state.sn_cache.empty:
        return st.session_state.sn_cache.copy()

    rows = []
    for url in [ROCHESTER_SN, ROCHESTER_SN26]:
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "DeepSpaceRadar/28"})
            if r.status_code != 200: continue
            text = re.sub(r'<[^>]+>', ' ', r.text)
            text = re.sub(r'\s+', ' ', text)

            # Pattern principal : "discovered YYYY/MM/DD.d at R.A. = HHhMMmSS.ss, Decl. = ±DD°MM'SS.ss Mag NN.N:M/D, Type XX (host GALAXY)"
            pattern2 = re.compile(
                r'((?:AT|SN)20\d{2}\w+)'
                r'.*?discovered\s+[\d/]+\s+at\s+R\.A\.\s*=\s*([\d]+h[\d]+m[\d.]+s?)'
                r',\s*Decl\.\s*=\s*([+\-]?\d+[°\s][\d\'".\s]+)'
                r'\s+Mag\s+([\d.]+)'
                r'(?:.*?Type\s+([A-Za-z\-]+))?'
                r'(?:.*?\(host\s+(.*?)\))?',
                re.IGNORECASE
            )
            for m in pattern2.finditer(text[:120000]):
                try:
                    nom     = m.group(1).strip()
                    if any(row["Nom"] == nom for row in rows): continue
                    ra_deg  = ra_hms_to_deg(m.group(2))
                    dec_deg = dec_dms_to_deg(m.group(3))
                    mag     = float(m.group(4))
                    sn_t    = (m.group(5) or "?").strip()
                    host    = (m.group(6) or "?").strip()[:50]
                    if ra_deg is None or dec_deg is None: continue
                    galactic, b_lat = is_galactic(ra_deg, dec_deg)
                    vs, vl = vespera_score(mag)
                    ti = sn_type_info(sn_t)
                    rows.append({
                        "Nom": nom, "Type": sn_t, "Type emoji": ti["emoji"],
                        "Type desc": ti["desc"], "Durée": ti["duree"],
                        "Mag": mag, "Vespera": vs, "Obs. Vespera": vl,
                        "Galaxie hôte": host,
                        "RA (°)": round(ra_deg, 4), "DEC (°)": round(dec_deg, 4),
                        "Lat. gal. (°)": b_lat,
                        "Galactique ?": "🌌 OUI !!!" if galactic else "Non",
                        "Lien TNS": f"https://www.wis-tns.org/object/{nom.replace('SN','').replace('AT','').strip()}",
                        "Lien Rochester": f"https://rochesterastronomy.org/sn2026/{nom.lower()}.html",
                        "Source": url.split('/')[-1],
                    })
                except: continue

            # Fallback pattern simple si pattern2 ne trouve rien
            if not rows:
                for m in re.finditer(r'((?:SN|AT)\s?20\d{2}\w{1,6}).*?Mag\s+([\d.]+)', text[:80000]):
                    try:
                        nom = m.group(1).replace(' ', '')
                        if any(row["Nom"] == nom for row in rows): continue
                        mag = float(m.group(2))
                        vs, vl = vespera_score(mag)
                        ti = sn_type_info("?")
                        rows.append({
                            "Nom": nom, "Type": "?", "Type emoji": "❓",
                            "Type desc": "?", "Durée": "?",
                            "Mag": mag, "Vespera": vs, "Obs. Vespera": vl,
                            "Galaxie hôte": "?", "RA (°)": None, "DEC (°)": None,
                            "Lat. gal. (°)": None, "Galactique ?": "?",
                            "Lien TNS": f"https://www.wis-tns.org/object/{nom[2:]}",
                            "Lien Rochester": ROCHESTER_SN, "Source": "fallback"
                        })
                    except: continue
        except: continue

    if not rows:
        return st.session_state.sn_cache.copy()

    df = pd.DataFrame(rows).drop_duplicates(subset=["Nom"])
    df = df.sort_values("Mag", ascending=True)

    for _, row in df.iterrows():
        nm = row["Nom"]
        if nm not in st.session_state.sn_history:
            st.session_state.sn_history[nm] = []
        st.session_state.sn_history[nm].append({"T": now.strftime("%H:%M"), "Mag": row["Mag"]})
        if len(st.session_state.sn_history[nm]) > 48:
            st.session_state.sn_history[nm].pop(0)

    st.session_state.sn_cache = df
    st.session_state.last_sn_req = now
    return df

# ═══════════════════════════════════════════════════════════════════════════════
# ALERTES SUPERNOVÆ
# ═══════════════════════════════════════════════════════════════════════════════
def alert_supernovae(df_sn: pd.DataFrame):
    if df_sn.empty: return
    events = []
    for _, row in df_sn.iterrows():
        nom  = row["Nom"]
        mag  = row["Mag"]
        snt  = row.get("Type", "?")
        host = row.get("Galaxie hôte", "?")
        vs   = row.get("Vespera", 0)
        vl   = row.get("Obs. Vespera", "?")
        gal  = row.get("Galactique ?", "Non")
        lat  = row.get("Lat. gal. (°)", "?")

        if "OUI" in str(gal) and nom not in st.session_state.alerted_galactic:
            events.append(
                f"🚨🌌 **SUPERNOVA GALACTIQUE DÉTECTÉE !!!**\n"
                f"   Nom : `{nom}` | Magnitude : **{mag}**\n"
                f"   Latitude galactique : **b = {lat}°**\n"
                f"   Hôte : {host} | Type : {row.get('Type emoji','')} {snt}\n"
                f"   🔭 Vespera II : {vl}\n"
                f"   ⚠️ ÉVÉNEMENT ASTRONOMIQUE EXCEPTIONNEL — 1 fois par siècle !"
            )
            st.session_state.alerted_galactic.add(nom)

        if vs >= 45 and nom not in st.session_state.alerted_sn_vespera:
            events.append(
                f"🌟 **SUPERNOVA OBSERVABLE VESPERA II :**\n"
                f"   `{nom}` ({row.get('Type emoji','')} {snt}) | Mag **{mag}**\n"
                f"   Hôte : {host} | Score Vespera : {vs}/100 → {vl}\n"
                f"   🔗 TNS : {row.get('Lien TNS','')}"
            )
            st.session_state.alerted_sn_vespera.add(nom)
        elif nom not in st.session_state.alerted_sn:
            if mag <= 19.0:
                events.append(f"🔔 **NOUVELLE SN :** `{nom}` ({snt}) | Mag {mag} | Hôte : {host} | {vl}")
            st.session_state.alerted_sn.add(nom)

    if events:
        _discord("🌟 **RADAR SUPERNOVÆ**\n" + "\n".join(events))

# ═══════════════════════════════════════════════════════════════════════════════
# FETCH NEOCP PREVIOUS
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_prev_neocp() -> dict:
    now = datetime.now()
    td = (now - st.session_state.last_prev_req).total_seconds()
    if td < 600 and st.session_state.prev_neocp_cache:
        return st.session_state.prev_neocp_cache
    result = {}
    for url in ["https://www.minorplanetcenter.net/iau/NEO/pccp_tabular.html",
                "https://www.minorplanetcenter.net/iau/NEO/toconfirm_tabular.html"]:
        try:
            r = requests.get(url, timeout=6, headers={"User-Agent": "DeepSpaceRadar/28"})
            if r.status_code != 200: continue
            for row in re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.DOTALL | re.IGNORECASE):
                cells = [re.sub(r'<[^>]+>', '', c).strip()
                         for c in re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)]
                if len(cells) < 2: continue
                tdes = cells[0].strip()
                if not tdes or not re.match(r'^[A-Za-z0-9]{4,10}$', tdes): continue
                reason = " ".join(cells).strip()
                designation = None
                for cell in cells[1:]:
                    m = re.search(r'\b(20\d{2}\s+[A-Z]{1,2}\d{1,4})\b', cell)
                    if m: designation = m.group(1); break
                    m2 = re.search(r'\((\d{4,6})\)', cell)
                    if m2: designation = m2.group(1); break
                    if 'pccp' in cell.lower() or 'comet' in cell.lower():
                        designation = f"[PCCP] {tdes}"; break
                if designation or 'moved' in reason.lower() or 'designated' in reason.lower():
                    result[tdes] = {"designation": designation or "?", "reason": reason[:80],
                                    "date": now.strftime("%Y-%m-%d %H:%M"), "source": url.split('/')[-1]}
        except: continue
    if result:
        st.session_state.prev_neocp_cache = {**st.session_state.prev_neocp_cache, **result}
        st.session_state.last_prev_req = now
    return st.session_state.prev_neocp_cache

# ═══════════════════════════════════════════════════════════════════════════════
# DÉTECTION TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════════════
def detect_transitions(prev_noms, cur_noms, df_nasa):
    gone = prev_noms - cur_noms
    if not gone: return []
    transitions = []
    prev_neocp = fetch_prev_neocp()
    for tdes in gone:
        if tdes in st.session_state.alerted_gone: continue
        result = {"tdes": tdes, "nom_officiel": None, "methode": None, "details": {}}
        if tdes in prev_neocp:
            info_prev = prev_neocp[tdes]
            desig = info_prev.get("designation", "?")
            is_pccp = desig.startswith("[PCCP]")
            result["nom_officiel"] = desig if not is_pccp else "Comète potentielle (PCCP)"
            result["methode"] = "Page MPC Previous NEOCP (officielle)"
            result["details"] = {"Désignation": desig, "Raison MPC": info_prev.get("reason","?")[:60],
                                  "Confiance": "✅ Officielle", "PCCP": "Oui" if is_pccp else "Non"}
            transitions.append(result); st.session_state.alerted_gone.add(tdes); continue
        try:
            r = requests.get(NASA_SBDB, params={"sstr": tdes, "phys-par": "1"}, timeout=5)
            data = r.json()
            if "object" in data:
                obj = data["object"]; orb = data.get("orbit", {})
                phy = {p["name"]: p.get("value") for p in data.get("phys_par", []) if isinstance(p, dict)}
                elems = orb.get("elements", {})
                if isinstance(elems, list): elems = {e["name"]: e.get("value") for e in elems}
                result["nom_officiel"] = obj.get("fullname", obj.get("des", "?"))
                result["methode"] = "SBDB direct (tdes trouvé)"
                result["details"] = {"H": phy.get("H","?"), "q": elems.get("q","?"),
                                      "e": elems.get("e","?"), "i": elems.get("i","?"),
                                      "classe": obj.get("orbit_class",{}).get("name","?"),
                                      "neo": "✅" if obj.get("neo") else "❌"}
                transitions.append(result); st.session_state.alerted_gone.add(tdes); continue
        except: pass
        hist = st.session_state.obj_history.get(tdes, [])
        if hist and not df_nasa.empty and 'h' in df_nasa.columns:
            h_ref = hist[-1].get("H")
            if h_ref is not None:
                try:
                    df_n = df_nasa.copy()
                    df_n['h_num'] = pd.to_numeric(df_n['h'], errors='coerce')
                    candidates = df_n[abs(df_n['h_num'] - h_ref) < 0.5]
                    if not candidates.empty:
                        best = candidates.iloc[0]
                        result["nom_officiel"] = best.get("des", "?")
                        result["methode"] = f"Correspondance H={h_ref:.1f}±0.5 dans NASA CAD"
                        result["details"] = {"H NASA": best.get("h","?"), "dist": best.get("dist","?"),
                                              "date": best.get("cd","?"), "confiance": "Moyenne"}
                        transitions.append(result); st.session_state.alerted_gone.add(tdes); continue
                except: pass
        result["nom_officiel"] = None
        result["methode"] = "Retiré du NEOCP (non confirmé)"
        result["details"] = {"raison": "Orbite non contrainte, fausse détection, ou objet artificiel"}
        transitions.append(result); st.session_state.alerted_gone.add(tdes)
    return transitions

# ═══════════════════════════════════════════════════════════════════════════════
# ALERTES NÉOS
# ═══════════════════════════════════════════════════════════════════════════════
def monitor_and_alert(df_anom, df_nasa, transitions):
    now = datetime.now()
    cur_noms = set(df_anom['Nom'].tolist()) if not df_anom.empty else set()
    events = []
    new_objs = cur_noms - st.session_state.alerted_new
    for n in new_objs:
        row = df_anom[df_anom['Nom'] == n].iloc[0]
        vs, vl = vespera_score(row.get('Vmag', 99))
        events.append(f"🆕 **NOUVEL OBJET :** `{n}` | H={row.get('H','?')} | Vmag={row.get('Vmag','?')} | Score={row['Score']} | {vl}")
    st.session_state.alerted_new.update(new_objs)
    for t in transitions:
        tdes = t["tdes"]; nom = t["nom_officiel"]; meth = t["methode"]
        if nom:
            events.append(f"🎯 **DÉSIGNÉ :** `{tdes}` → `{nom}`\n   {meth}\n   {t['details']}")
            st.session_state.recognized_objects[tdes] = {"nom_officiel": nom, "methode": meth,
                "details": t["details"], "date": now.strftime("%Y-%m-%d %H:%M")}
        else:
            events.append(f"👻 **DISPARU :** `{tdes}` — {t['details'].get('raison','')}")
    if not df_anom.empty:
        for r in df_anom.itertuples():
            palier = st.session_state.score_palier.get(r.Nom)
            tr = get_trend(r.Nom, r.Score)
            vs, vl = vespera_score(getattr(r, 'Vmag', 99))
            if r.Score >= 80 and palier != 80:
                events.append(f"🚨 **CRITIQUE ≥80 :** `{r.Nom}` {tr} Score={r.Score} | H={getattr(r,'H','?')} | {vl}")
                st.session_state.score_palier[r.Nom] = 80
            elif 50 <= r.Score < 80 and palier not in (50, 80):
                events.append(f"🔥 **SEUIL ≥50 :** `{r.Nom}` {tr} Score={r.Score} | {vl}")
                st.session_state.score_palier[r.Nom] = 50
            elif 50 <= r.Score < 80 and palier == 80:
                st.session_state.score_palier[r.Nom] = 50
            elif r.Score < 50:
                if palier in (50, 80):
                    events.append(f"📉 **RETOMBÉ :** `{r.Nom}` Score={r.Score}")
                st.session_state.score_palier[r.Nom] = None
    if not df_anom.empty:
        new_top5 = df_anom.sort_values("Score", ascending=False).head(5)['Nom'].tolist()
        if st.session_state.prev_top5 and new_top5 != st.session_state.prev_top5:
            entrants = [n for n in new_top5 if n not in st.session_state.prev_top5]
            sortants  = [n for n in st.session_state.prev_top5 if n not in new_top5]
            if entrants or sortants:
                msg = "📊 **CHANGEMENT TOP 5 :**\n"
                for i, n in enumerate(new_top5, 1):
                    s = df_anom[df_anom['Nom'] == n]['Score'].values[0]
                    msg += f"  {i}. `{n}` (Score: {s})\n"
                if entrants: msg += f"  ↑ `{', '.join(entrants)}`\n"
                if sortants:  msg += f"  ↓ `{', '.join(sortants)}`"
                events.append(msg)
        st.session_state.prev_top5 = new_top5
    if events:
        _discord("📡 **RADAR SENTINELLE**\n" + "\n".join(events))
    if (now - st.session_state.last_alert_time).total_seconds() > 3600:
        msg = f"📊 **BILAN HORAIRE ({now.strftime('%H:%M')})**\n"
        if not df_anom.empty:
            for row in df_anom.sort_values("Score", ascending=False).head(10).itertuples():
                vs2, vl2 = vespera_score(getattr(row, 'Vmag', 99))
                msg += f"- `{row.Nom}` {get_trend(row.Nom, row.Score)} S={row.Score} H={getattr(row,'H','?')} | {vl2}\n"
        else:
            msg += "Aucune anomalie active."
        _discord(msg)
        st.session_state.last_alert_time = now

# ═══════════════════════════════════════════════════════════════════════════════
# FETCH SCOUT
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_scout() -> pd.DataFrame:
    now = datetime.now()
    if (now - st.session_state.last_scout_req).total_seconds() < 60 and not st.session_state.scout_cache.empty:
        return st.session_state.scout_cache.copy()
    df = pd.DataFrame()
    try:
        res = requests.get(SCOUT_API, timeout=8)
        res.raise_for_status()
        raw = res.json()
        if isinstance(raw, list): data_list = raw
        elif isinstance(raw, dict):
            data_list = None
            for key in ("data", "result", "objects", "neocp"):
                if key in raw and isinstance(raw[key], list):
                    data_list = raw[key]; break
            if data_list is None:
                data_list = [raw] if "objectName" in raw or "tdes" in raw else []
        else: data_list = []
        if not data_list: return st.session_state.scout_cache.copy()
        rows = []
        for obj in data_list:
            try:
                tdes    = obj.get("objectName", obj.get("tdes", ""))
                if not tdes: continue
                h_val   = float(obj.get("H", 25))
                n_obs   = int(float(obj.get("nObs", 5)))
                arc     = float(obj.get("arc", 0))
                vmag    = float(obj.get("Vmag", 99))
                moid    = float(obj.get("moid", 99))
                ca_dist = float(obj.get("caDist", 99)) if obj.get("caDist") else 99
                v_inf   = obj.get("vInf", "?")
                neo_sc  = float(obj.get("neoScore", 0))
                ra      = obj.get("ra", "?"); dec = obj.get("dec", "?")
                elong   = obj.get("elong", "?"); rate = obj.get("rate", "?")
                unc     = obj.get("unc", "?"); last = obj.get("lastRun", "?")
                tiss    = float(obj.get("tisserandScore", 0))
                geo_sc  = float(obj.get("geocentricScore", 0))
                ieo_sc  = float(obj.get("ieoScore", 0))
                if tiss > 50:      obj_type = "🌠 Comète prob."
                elif geo_sc > 50:  obj_type = "🛰️ Satellite art."
                elif ieo_sc > 50:  obj_type = "🌍 IEO (inner)"
                elif neo_sc >= 80: obj_type = "☄️ NEO candidat"
                else:              obj_type = "🪨 Indéterminé"
                is_catalogued = (neo_sc < 10 and n_obs > 15 and arc > 3.0)
                score = compute_score(h_val, n_obs, arc, moid, neo_sc)
                vs, vl = vespera_score(vmag)
                rows.append({"Nom": tdes, "Type": obj_type, "H": round(h_val, 1),
                    "Vmag": round(vmag, 1), "NObs": n_obs, "Arc (j)": round(arc, 2),
                    "MOID (UA)": round(moid, 4) if moid < 99 else ">0.1",
                    "CA min (LD)": round(ca_dist, 3) if ca_dist < 99 else "?",
                    "Vit. ∞": v_inf, "R.A.": ra, "Déc.": dec,
                    "Élong.": elong, "Rate \"/m": rate, "Unc. \"": unc,
                    "Score NEO": int(neo_sc), "Score": score,
                    "Statut": score_label(score), "Taille": classify_size(h_val),
                    "Vespera": vs, "Obs. Vespera": vl, "MàJ": last,
                    "_catalogued": is_catalogued})
            except: continue
        if rows:
            df = pd.DataFrame(rows)
            df = df[~df['Nom'].isin(st.session_state.archived)]
            st.session_state.scout_cache = df
            st.session_state.last_scout_req = now
        elif not st.session_state.scout_cache.empty:
            df = st.session_state.scout_cache.copy()
            df = df[~df['Nom'].isin(st.session_state.archived)]
    except:
        try:
            resp = requests.get("https://minorplanetcenter.net/iau/NEO/neocp.txt", timeout=12)
            rows = []
            for line in resp.text.strip().split('\n'):
                parts = line.split()
                if len(parts) < 10 or parts[0] in ('Temp', 'Score', '---'): continue
                try:
                    tdes = parts[0]; vmag = float(parts[5]) if len(parts) > 5 else 99.0
                    h_val = float(parts[-2]); n_arc = float(parts[-3]); n_obs = int(float(parts[-4]))
                    score = compute_score(h_val, n_obs, n_arc, 99, 0)
                    vs, vl = vespera_score(vmag)
                    rows.append({"Nom": tdes, "H": round(h_val,1), "Vmag": round(vmag,1),
                        "NObs": n_obs, "Arc (j)": round(n_arc,2), "MOID (UA)": ">0.1",
                        "CA min (LD)": "?", "Vit. ∞": "?", "R.A.": "?", "Déc.": "?",
                        "Élong.": "?", "Rate \"/m": "?", "Unc. \"": "?", "Score NEO": 0,
                        "Score": score, "Statut": score_label(score), "Taille": classify_size(h_val),
                        "Vespera": vs, "Obs. Vespera": vl, "MàJ": "Fallback .txt"})
                except: continue
            if rows:
                df = pd.DataFrame(rows)
                df = df[~df['Nom'].isin(st.session_state.archived)]
        except:
            df = st.session_state.scout_cache.copy()
    return df

# ═══════════════════════════════════════════════════════════════════════════════
# FETCH NASA CAD
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_nasa_cad(radius, days):
    now = datetime.now()
    td = (now - st.session_state.last_nasa_req).total_seconds()
    if td > 60:
        try:
            url = (f"{NASA_CAD}?dist-max={radius}LD"
                   f"&date-min={now.strftime('%Y-%m-%d')}"
                   f"&date-max={(now+timedelta(days=days)).strftime('%Y-%m-%d')}"
                   f"&fullname=true&diameter=true")
            res = requests.get(url, timeout=8).json()
            if "data" in res:
                st.session_state.nasa_cache = pd.DataFrame(res["data"], columns=res["fields"])
                st.session_state.last_nasa_req = now
        except: pass
    return st.session_state.nasa_cache.copy(), max(0, int(60 - td))

# ═══════════════════════════════════════════════════════════════════════════════
# FETCH COMÈTES
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_comets() -> pd.DataFrame:
    now = datetime.now()
    td = (now - st.session_state.last_comet_req).total_seconds()
    if td < 10800 and not st.session_state.comet_cache.empty:
        return st.session_state.comet_cache.copy()
    rows = []
    try:
        rc = requests.get(COMET_URL, timeout=8)
        rc.raise_for_status()
        for line in rc.text.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'): continue
            parts = line.split()
            if len(parts) < 12: continue
            try:
                yr = int(parts[1]); mo = int(parts[2]); dy = float(parts[3])
                q  = float(parts[4]); e  = float(parts[5])
                i  = float(parts[8]); g  = float(parts[10]); k = float(parts[11])
                nom = " ".join(parts[12:]).strip() if len(parts) > 12 else parts[0]
                if q <= 0 or q > 50 or e < 0 or g > 30: continue
                if e < 1.0:
                    a = q / (1.0 - e); periode_ans = round(a ** 1.5, 2)
                    periode_str = f"{periode_ans} ans"; periode_jours = periode_ans * 365.25
                else:
                    periode_ans = None; periode_str = "Non périodique"; periode_jours = None
                try:
                    t_last = datetime(yr, mo, max(1, int(dy)))
                    days_since = (now - t_last).days
                    if days_since >= 0:
                        dernier_str = f"{t_last.strftime('%Y-%m-%d')} (il y a {days_since}j)"
                        if periode_jours:
                            n_p = math.ceil(days_since / periode_jours)
                            t_next = t_last + timedelta(days=n_p * periode_jours)
                            prochain_str = f"{t_next.strftime('%Y-%m-%d')} (dans {(t_next-now).days}j)"
                        else: prochain_str = "N/A"
                    else:
                        prochain_str = f"{t_last.strftime('%Y-%m-%d')} (dans {abs(days_since)}j)"
                        if periode_jours:
                            t_prev = t_last - timedelta(days=periode_jours)
                            dernier_str = f"{t_prev.strftime('%Y-%m-%d')} (il y a {(now-t_prev).days}j)"
                        else: dernier_str = "N/A"
                except:
                    dernier_str = f"{yr}-{mo:02d}-{int(dy):02d}"; prochain_str = "?"
                r_peri = max(0.01, q); delta_p = max(0.1, abs(q - 1.0))
                mag_peri = round(g + 5*math.log10(delta_p) + k*math.log10(r_peri), 1)
                mag_peri = max(-10.0, min(25.0, mag_peri))
                v_sc, v_lb = vespera_score(mag_peri)
                rows.append({"Nom": nom[:60], "Dernier peri.": dernier_str, "Prochain peri.": prochain_str,
                    "Période": periode_str, "q (UA)": round(q, 4), "e": round(e, 5),
                    "i (°)": round(i, 2), "g": round(g, 1), "k": round(k, 1),
                    "Mag.@peri": mag_peri, "Mag.actuelle": "?", "Élong. (°)": "?",
                    "Observable ?": "?", "Vespera@peri": v_sc, "Obs.@peri": v_lb,
                    "Vespera act.": "?", "Obs. actuelle": "?"})
            except: continue
    except:
        return st.session_state.comet_cache.copy()
    if not rows: return st.session_state.comet_cache.copy()
    df = pd.DataFrame(rows)

    today_str = now.strftime("%Y-%m-%d"); tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    def _horizons_query(idx_nom):
        idx, nom_comet = idx_nom
        m_des = re.match(r'^([CP]/\d{4}\s+\w+)', nom_comet)
        if not m_des: return idx, None
        try:
            rh = requests.get(HORIZONS_API, params={"format":"json","COMMAND":f"'{m_des.group(1).strip()}'",
                "EPHEM_TYPE":"OBSERVER","CENTER":"500@399","START_TIME":today_str,
                "STOP_TIME":tomorrow_str,"STEP_SIZE":"1d","QUANTITIES":"9,23"}, timeout=6)
            txt = rh.text
            if "$$SOE" in txt and "$$EOE" in txt:
                block = txt[txt.index("$$SOE")+5:txt.index("$$EOE")].strip()
                lines = [l.strip() for l in block.split('\n') if l.strip()]
                if lines:
                    p = lines[0].split()
                    if len(p) >= 4:
                        v_act = float(p[-2]); elong = float(p[-1])
                        vs, vl = vespera_score(v_act)
                        obs = ("✅ Oui" if elong > 20 and v_act < 17.5 else
                               "🟡 Difficile" if elong > 15 and v_act < 19 else "❌ Non")
                        return idx, {"v":round(v_act,1),"e":round(elong,1),"obs":obs,"vs":vs,"vl":vl}
        except: pass
        return idx, None

    bright = [(i,r["Nom"]) for i,r in df.iterrows() if pd.to_numeric(r.get("Mag.@peri",99),errors='coerce') < 18]
    if bright:
        try:
            with ThreadPoolExecutor(max_workers=4) as ex:
                for fut in as_completed({ex.submit(_horizons_query,ic):ic for ic in bright}, timeout=12):
                    try:
                        idx, data = fut.result()
                        if data:
                            df.at[idx,"Mag.actuelle"]=data["v"]; df.at[idx,"Élong. (°)"]=data["e"]
                            df.at[idx,"Observable ?"]=data["obs"]; df.at[idx,"Vespera act."]=data["vs"]
                            df.at[idx,"Obs. actuelle"]=data["vl"]
                    except: continue
        except FuturesTimeout: pass

    st.session_state.comet_cache = df; st.session_state.last_comet_req = now
    return df

# ═══════════════════════════════════════════════════════════════════════════════
# PARSE SBDB
# ═══════════════════════════════════════════════════════════════════════════════
def parse_sbdb(res):
    obj=res.get("object",{}); orb=res.get("orbit",{}); phy=res.get("phys_par",[]); ca=res.get("close_approach_data",[])
    elems=orb.get("elements",{})
    if isinstance(elems,list): elems={e["name"]:e.get("value","?") for e in elems}
    if isinstance(phy,list): phy_d={p["name"]:p.get("value") for p in phy if isinstance(p,dict) and "name" in p}
    else: phy_d={k:(v.get("value") if isinstance(v,dict) else v) for k,v in phy.items()}
    def _p(k): return phy_d.get(k) or "N/A"
    return {"fullname":obj.get("fullname","?"),"spkid":obj.get("spkid","?"),
            "neo":"✅" if obj.get("neo") else "❌","pha":"⚠️ OUI" if obj.get("pha") else "non",
            "orbit_class":obj.get("orbit_class",{}).get("name","?"),"condition_code":orb.get("condition_code","?"),
            "first_obs":orb.get("first_obs","?"),"soln_date":orb.get("soln_date","?"),
            "e":elems.get("e","?"),"a":elems.get("a","?"),"q":elems.get("q","?"),
            "i":elems.get("i","?"),"per_y":elems.get("per_y",orb.get("per_y","?")),"moid":orb.get("moid","?"),
            "H":_p("H"),"G":_p("G"),"albedo":_p("albedo"),"diameter":_p("diameter"),"density":_p("density"),
            "rot_per":_p("rot_per"),"spec_T":_p("spec_T"),"ps_cum":_p("ps_cum"),"ts_max":_p("ts_max"),"ca":ca}

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        "<div style='text-align:center;padding:14px 0 6px'>"
        "<span style='font-family:var(--mono);font-size:1.4em;color:var(--accent);"
        "text-shadow:0 0 12px rgba(0,212,255,.6)'>DEEP SPACE</span><br>"
        "<span style='font-family:var(--ui);font-size:.68em;letter-spacing:4px;color:var(--muted)'>RADAR SYSTEM V28</span>"
        "</div>", unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sec">⏱ ACTUALISATION</div>', unsafe_allow_html=True)
    refresh_rate = st.slider("Rafraîchissement (s)", 30, 300, 60)
    st.markdown('<div class="sidebar-sec">🔭 CHAMP NASA CAD</div>', unsafe_allow_html=True)
    radius_ld    = st.slider("Rayon (Distance Lunaire)", 1, 2500, 500)
    horizon_days = st.slider("Horizon temporel (jours)", 1, 90, 30)
    st.markdown('<div class="sidebar-sec">🌟 FILTRES SUPERNOVÆ</div>', unsafe_allow_html=True)
    sn_mag_limit  = st.slider("Magnitude max SN", 10.0, 22.0, 19.0, 0.5)
    sn_vespera_only = st.toggle("Seulement observables Vespera", value=False)
    sn_show_galactic_alert = st.toggle("Alerte galactique prioritaire", value=True)
    st.markdown('<div class="sidebar-sec">🎛 FILTRES VESPERA</div>', unsafe_allow_html=True)
    vespera_mode = st.toggle("Filtre Vespera II (NASA+Comètes)", value=False)
    mag_limit    = st.slider("Magnitude H max", 5.0, 30.0, 19.0)
    st.markdown(
        f"<div style='font-size:.72em;color:var(--muted);font-family:var(--body);line-height:1.6'>"
        f"Sources : NASA Scout · JPL CAD · MPC · Rochester Astronomy<br>"
        f"Session : {st.session_state.last_refresh.strftime('%H:%M:%S')}</div>",
        unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# CHARGEMENT DONNÉES (SN en différé — ne bloque pas le boot)
# ═══════════════════════════════════════════════════════════════════════════════
status_ph = st.empty()
status_ph.info("⏳ Connexion Scout NASA…")
df_scout = fetch_scout()
status_ph.info("⏳ Connexion NASA JPL CAD…")
df_nasa, timer_nasa = fetch_nasa_cad(radius_ld, horizon_days)
status_ph.empty()

# SN depuis le cache uniquement au boot
df_sn_all = st.session_state.sn_cache.copy() if not st.session_state.sn_cache.empty else pd.DataFrame()
df_comets = st.session_state.comet_cache.copy() if not st.session_state.comet_cache.empty else pd.DataFrame()

if vespera_mode:
    if not df_nasa.empty and 'h' in df_nasa.columns:
        df_nasa = df_nasa[pd.to_numeric(df_nasa['h'], errors='coerce') <= mag_limit].copy()
    if not df_comets.empty and 'Mag.@peri' in df_comets.columns:
        df_comets = df_comets[pd.to_numeric(df_comets['Mag.@peri'], errors='coerce') <= mag_limit].copy()

df_sn = df_sn_all.copy()
if not df_sn.empty:
    df_sn = df_sn[pd.to_numeric(df_sn['Mag'], errors='coerce') <= sn_mag_limit]
    if sn_vespera_only:
        df_sn = df_sn[df_sn['Vespera'] >= 45]

if not df_scout.empty and '_catalogued' in df_scout.columns:
    df_catalogued_scout = df_scout[df_scout['_catalogued']].copy()
    df_scout_anom       = df_scout[~df_scout['_catalogued']].copy()
    df_catalogued_scout.drop(columns=['_catalogued'], inplace=True, errors='ignore')
    df_scout_anom.drop(columns=['_catalogued'], inplace=True, errors='ignore')
else:
    df_catalogued_scout = pd.DataFrame()
    df_scout_anom = df_scout.copy()
    if '_catalogued' in df_scout_anom.columns:
        df_scout_anom.drop(columns=['_catalogued'], inplace=True)

if not df_scout_anom.empty:
    for r in df_scout_anom.itertuples():
        nm = r.Nom
        if nm not in st.session_state.obj_history: st.session_state.obj_history[nm] = []
        st.session_state.obj_history[nm].append({
            "T": datetime.now().strftime("%H:%M"), "S": r.Score, "H": r.H,
            "NObs": r.NObs, "Arc": getattr(r,"Arc (j)",0), "Vmag": r.Vmag,
            "moid": getattr(r,"MOID (UA)",99)})
        if len(st.session_state.obj_history[nm]) > 30: st.session_state.obj_history[nm].pop(0)

active_noms = set(df_scout_anom['Nom'].tolist()) if not df_scout_anom.empty else set()
reconnus = set(st.session_state.recognized_objects.keys())
keys_to_keep = (active_noms | reconnus) - st.session_state.archived
for k in list(st.session_state.obj_history.keys()):
    if k not in keys_to_keep: del st.session_state.obj_history[k]

prev_noms = st.session_state.prev_noms
transitions = detect_transitions(prev_noms, active_noms, df_nasa)
st.session_state.prev_noms = active_noms
monitor_and_alert(df_scout_anom, df_nasa, transitions)
alert_supernovae(df_sn)
_process_discord_queue()

# ═══════════════════════════════════════════════════════════════════════════════
# HEADER + MÉTRIQUES
# ═══════════════════════════════════════════════════════════════════════════════
c1, c2 = st.columns([4, 1])
with c1:
    st.markdown(
        "<div style='padding:16px 0 6px;border-bottom:1px solid var(--border);margin-bottom:18px'>"
        "<div class='radar-logo'>🛰️ DEEP SPACE RADAR</div>"
        "<div class='radar-sub'>Surveillance NEOCP · Scout NASA · Supernovæ · V28.0</div></div>",
        unsafe_allow_html=True)
with c2:
    st.markdown(
        f"<div style='display:flex;justify-content:flex-end;align-items:center;height:100%;padding-top:24px'>"
        f"<div class='sync-pill'><div class='sync-dot'></div>LIVE {timer_nasa}s</div></div>",
        unsafe_allow_html=True)

n_anom = len(df_scout_anom)
n_crit = len(df_scout_anom[df_scout_anom['Score'] >= 80]) if not df_scout_anom.empty else 0
n_nasa = len(df_nasa) if not df_nasa.empty else 0
n_com  = len(df_comets) if not df_comets.empty else 0
n_rec  = len(st.session_state.recognized_objects)
n_sn   = len(df_sn) if not df_sn.empty else 0
n_sn_vesp = len(df_sn[df_sn['Vespera'] >= 45]) if not df_sn.empty else 0
n_gal  = len(df_sn[df_sn['Galactique ?'].str.contains('OUI', na=False)]) if not df_sn.empty else 0

if n_gal > 0 and sn_show_galactic_alert:
    gal_row = df_sn[df_sn['Galactique ?'].str.contains('OUI', na=False)].iloc[0]
    st.markdown(f"""
<div class="galactic-alert">
  <div class="galactic-alert-title">🚨 SUPERNOVA GALACTIQUE DÉTECTÉE 🚨</div>
  <div style="font-family:var(--mono);color:var(--accent3);font-size:1.1em">
    {gal_row['Nom']} · Mag {gal_row['Mag']} · b = {gal_row.get('Lat. gal. (°)','?')}°
  </div>
  <div style="color:var(--text);margin-top:8px;font-size:.9em">
    Hôte : {gal_row.get('Galaxie hôte','?')} · Type : {gal_row.get('Type emoji','')} {gal_row.get('Type','?')}
  </div>
  <div style="color:var(--muted);font-size:.8em;margin-top:6px">
    ⚠️ Événement exceptionnel — vérifier immédiatement sur TNS et ATel
  </div>
</div>""", unsafe_allow_html=True)

st.markdown(f"""
<div class="metric-grid">
  <div class="metric-card w"><div class="metric-val">{n_anom}</div><div class="metric-label">Candidats Scout</div></div>
  <div class="metric-card {'w' if n_crit else 'g'}"><div class="metric-val">{n_crit}</div><div class="metric-label">Critiques ≥80</div></div>
  <div class="metric-card"><div class="metric-val">{n_nasa}</div><div class="metric-label">Objets NASA proches</div></div>
  <div class="metric-card g"><div class="metric-val">{n_com}</div><div class="metric-label">Comètes actives</div></div>
  <div class="metric-card p"><div class="metric-val">{n_sn}</div><div class="metric-label">Supernovæ ({n_sn_vesp} Vespera)</div></div>
  <div class="metric-card c"><div class="metric-val">{n_rec}</div><div class="metric-label">Désignés (session)</div></div>
  {'<div class="metric-card pk"><div class="metric-val">🌌 ' + str(n_gal) + '</div><div class="metric-label">SN Galactiques !!!</div></div>' if n_gal > 0 else ''}
</div>
""", unsafe_allow_html=True)

ff = FUN_FACTS[st.session_state.fun_fact_idx % len(FUN_FACTS)]
st.markdown(f"""
<div class="fun-fact">
  <div class="fun-fact-title">💡 LE SAVIEZ-VOUS ? — {ff[0]}</div>
  <div class="fun-fact-text">{ff[1]}</div>
</div>""", unsafe_allow_html=True)
st.session_state.fun_fact_idx += 1

# ═══════════════════════════════════════════════════════════════════════════════
# ONGLETS
# ═══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🔭  SCOUT NEOCP", "🌟  SUPERNOVÆ", "🎯  DÉSIGNÉS", "🚀  NASA CAD", "🌠  COMÈTES", "📘  LEXIQUE",
])

# ── TAB 1 : SCOUT ─────────────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="sec">Candidats NEO Actifs · NASA Scout (NEOCP)</div>', unsafe_allow_html=True)
    if not df_scout_anom.empty:
        disp = df_scout_anom.copy()
        disp['Tr.']  = disp.apply(lambda r: get_trend(r['Nom'], r['Score']), axis=1)
        disp['Rang'] = range(1, len(disp) + 1)
        cols = ["Rang","Nom","Type","H","Vmag","Obs. Vespera","NObs","Arc (j)","MOID (UA)",
                "CA min (LD)","Score NEO","Score","Statut","Taille","Tr."]
        cols = [c for c in cols if c in disp.columns]
        st.dataframe(disp[cols].style.background_gradient(cmap="YlOrRd", subset=["Score"]),
                     use_container_width=True, hide_index=True)
        st.caption("H = mag absolue · Vmag = mag visuelle · NObs = observations · Arc = arc orbital (j) · "
                   "MOID = dist min Terre-objet (UA) · CA min = dist min approche (LD)")
    else:
        st.markdown('<div class="empty">// AUCUN CANDIDAT ACTIF — API SCOUT EN ATTENTE //</div>', unsafe_allow_html=True)

    if not df_catalogued_scout.empty:
        with st.expander(f"📋 Objets bien connus / déjà catalogués ({len(df_catalogued_scout)})"):
            cols_cat = [c for c in ["Nom","Type","H","Vmag","NObs","Arc (j)","Score NEO","Score","Obs. Vespera"] if c in df_catalogued_scout.columns]
            st.dataframe(df_catalogued_scout[cols_cat], use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown('<div class="sec" style="color:var(--accent3)">🗃️ Archivage Manuel</div>', unsafe_allow_html=True)
    all_scout_noms = (df_scout_anom['Nom'].tolist() if not df_scout_anom.empty else []) + \
                     (df_catalogued_scout['Nom'].tolist() if not df_catalogued_scout.empty else [])
    col_sel, col_btn = st.columns([3, 1])
    with col_sel:
        to_archive = st.selectbox("Objet à archiver :", ["— sélectionner —"] + sorted(all_scout_noms), key="archive_sel")
    with col_btn:
        if st.button("🗃️ Archiver", use_container_width=True):
            if to_archive != "— sélectionner —":
                st.session_state.archived.add(to_archive)
                if to_archive in st.session_state.obj_history: del st.session_state.obj_history[to_archive]
                st.rerun()
    if st.session_state.archived:
        with st.expander(f"📦 Archivés ({len(st.session_state.archived)})"):
            for a in sorted(st.session_state.archived):
                col_a, col_b = st.columns([3, 1])
                with col_a: st.text(a)
                with col_b:
                    if st.button("↩️", key=f"restore_{a}"):
                        st.session_state.archived.discard(a); st.rerun()

# ── TAB 2 : SUPERNOVÆ ─────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="sec sn">Supernovæ Récentes · Rochester Astronomy + TNS</div>', unsafe_allow_html=True)

    sn_cache_ok = not st.session_state.sn_cache.empty
    sn_age = (datetime.now() - st.session_state.last_sn_req).total_seconds()

    # Bouton chargement / rafraîchissement
    if not sn_cache_ok:
        st.warning("⚠️ Supernovæ non chargées — cliquez pour démarrer.")
        if st.button("🌟 Charger les supernovæ", key="load_sn"):
            with st.spinner("Chargement Rochester (~10s)…"):
                result = fetch_supernovae()
                if not result.empty: st.session_state.sn_cache = result
            st.rerun()
        st.stop()
    else:
        col_ref, col_age = st.columns([1, 3])
        with col_ref:
            if st.button("🔄 Rafraîchir", key="refresh_sn"):
                with st.spinner("Mise à jour…"):
                    st.session_state.last_sn_req = datetime.now() - timedelta(hours=3)
                    result = fetch_supernovae()
                    if not result.empty: st.session_state.sn_cache = result
                st.rerun()
        with col_age:
            st.markdown(f"<div style='font-size:.78em;color:var(--muted);padding-top:8px'>"
                        f"Cache : {int(sn_age//60)}min {int(sn_age%60)}s · "
                        f"Mise à jour : {st.session_state.last_sn_req.strftime('%H:%M:%S')}</div>",
                        unsafe_allow_html=True)

    col_info1, col_info2, col_info3 = st.columns(3)
    with col_info1:
        st.markdown(f"<div style='background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px;text-align:center'>"
                    f"<div style='font-family:var(--mono);font-size:1.6em;color:var(--purple)'>{n_sn}</div>"
                    f"<div style='font-size:.72em;color:var(--muted);text-transform:uppercase;letter-spacing:2px'>Supernovæ trouvées</div></div>", unsafe_allow_html=True)
    with col_info2:
        st.markdown(f"<div style='background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px;text-align:center'>"
                    f"<div style='font-family:var(--mono);font-size:1.6em;color:var(--green)'>{n_sn_vesp}</div>"
                    f"<div style='font-size:.72em;color:var(--muted);text-transform:uppercase;letter-spacing:2px'>Observables Vespera II</div></div>", unsafe_allow_html=True)
    with col_info3:
        st.markdown(f"<div style='background:var(--surface);border:1px solid {'var(--accent2)' if n_gal > 0 else 'var(--border)'};border-radius:8px;padding:12px;text-align:center'>"
                    f"<div style='font-family:var(--mono);font-size:1.6em;color:{'#ff4b4b' if n_gal > 0 else 'var(--muted)'}'>{'🌌 '+str(n_gal) if n_gal > 0 else '0'}</div>"
                    f"<div style='font-size:.72em;color:var(--muted);text-transform:uppercase;letter-spacing:2px'>Galactiques !!!</div></div>", unsafe_allow_html=True)

    st.markdown("---")

    if df_sn.empty:
        st.info(f"Aucune SN dans les critères (mag ≤ {sn_mag_limit}). {len(df_sn_all)} SN disponibles sans filtre.")
    else:
        df_sn_sorted = df_sn.sort_values("Mag", ascending=True)

        for _, row in df_sn_sorted.iterrows():
            nom  = row["Nom"]
            mag  = row["Mag"]
            snt  = row.get("Type","?")
            ti   = sn_type_info(snt)
            host = row.get("Galaxie hôte","?")
            vs   = row.get("Vespera", 0)
            vl   = row.get("Obs. Vespera","?")
            gal  = "OUI" in str(row.get("Galactique ?",""))
            lat  = row.get("Lat. gal. (°)","?")
            ra   = row.get("RA (°)","?")
            dec  = row.get("DEC (°)","?")
            lien_tns = row.get("Lien TNS","#")

            card_class = ("sn-card galactic" if gal else
                         "sn-card vespera" if vs >= 45 else
                         "sn-card marginal" if vs >= 15 else "sn-card outofrange")
            name_class = "sn-name galactic-name" if gal else "sn-name"
            type_color = ti.get("couleur","#747d8c")

            if vs >= 90:   badge_v = "<span class='sn-badge' style='color:#00ff88;border-color:#00ff88'>🟢 EXCELLENT</span>"
            elif vs >= 70: badge_v = "<span class='sn-badge' style='color:#f7b731;border-color:#f7b731'>🟡 BON</span>"
            elif vs >= 45: badge_v = "<span class='sn-badge' style='color:#ff9f43;border-color:#ff9f43'>🟠 LIMITE</span>"
            elif vs >= 15: badge_v = "<span class='sn-badge' style='color:#ff4b4b;border-color:#ff4b4b'>🔴 DIFFICILE</span>"
            else:          badge_v = "<span class='sn-badge' style='color:#5a7090;border-color:#5a7090'>⛔ HORS PORTÉE</span>"
            badge_gal = "<span class='sn-badge' style='color:#ff4b4b;border-color:#ff4b4b'>🌌 GALACTIQUE</span>" if gal else ""

            hist_mag = st.session_state.sn_history.get(nom, [])
            if len(hist_mag) >= 2:
                delta = hist_mag[-1]["Mag"] - hist_mag[0]["Mag"]
                trend_sn = f"📈 +{delta:.1f} (fading)" if delta > 0.1 else (f"📉 {delta:.1f} (brightening)" if delta < -0.1 else "➡️ stable")
            else: trend_sn = "➡️ —"

            st.markdown(f"""
<div class="{card_class}">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
    <div>
      <span class="{name_class}">{nom}</span>
      <span style="color:var(--muted);margin:0 8px;font-size:.8em">dans</span>
      <span style="font-family:var(--ui);font-size:1em;font-weight:700;color:var(--accent)">🌌 {host}</span>
    </div>
    <div style="font-family:var(--mono);font-size:1.3em;color:{'#ffd700' if gal else 'var(--accent3)'}">✦ mag {mag}</div>
  </div>
  <div>
    <span class='sn-badge' style='color:{type_color};border-color:{type_color}'>{ti['emoji']} {snt}</span>
    {badge_v}{badge_gal}
  </div>
  <div class="sn-grid">
    <div class="sn-stat"><div class="sn-stat-k">Galaxie hôte</div><div class="sn-stat-v" style="color:var(--accent)">{host}</div></div>
    <div class="sn-stat"><div class="sn-stat-k">Description</div><div class="sn-stat-v" style="font-size:.78em">{ti['desc']}</div></div>
    <div class="sn-stat"><div class="sn-stat-k">Durée typique</div><div class="sn-stat-v">{ti['duree']}</div></div>
    <div class="sn-stat"><div class="sn-stat-k">Score Vespera</div><div class="sn-stat-v">{vs}/100</div></div>
    <div class="sn-stat"><div class="sn-stat-k">RA / DEC</div><div class="sn-stat-v" style="font-size:.78em">{ra}° / {dec}°</div></div>
    <div class="sn-stat"><div class="sn-stat-k">Lat. galactique</div><div class="sn-stat-v">b = {lat}°</div></div>
    <div class="sn-stat"><div class="sn-stat-k">Évolution mag.</div><div class="sn-stat-v" style="font-size:.78em">{trend_sn}</div></div>
    <div class="sn-stat"><div class="sn-stat-k">Galactique ?</div><div class="sn-stat-v">{'🌌 OUI !!!' if gal else 'Non'}</div></div>
  </div>
  <div style="margin-top:10px;display:flex;gap:12px;font-size:.78em">
    <a href="{lien_tns}" target="_blank" style="color:var(--accent);font-family:var(--mono)">→ TNS ↗</a>
    <a href="https://rochesterastronomy.org/supernova.html" target="_blank" style="color:var(--accent3);font-family:var(--mono)">→ Rochester ↗</a>
    <a href="https://www.astronomerstelegram.org" target="_blank" style="color:var(--purple);font-family:var(--mono)">→ ATel ↗</a>
    <a href="https://theskylive.com/supernova-{nom.lower()}" target="_blank" style="color:var(--green);font-family:var(--mono)">→ TheSkyLive ↗</a>
  </div>
</div>""", unsafe_allow_html=True)

        # ── Tableau compact avec magnitude ──
        with st.expander("📊 Vue tableau compact"):
            cols_sn = [c for c in ["Nom","Mag","Type","Obs. Vespera","Galaxie hôte",
                                    "RA (°)","DEC (°)","Lat. gal. (°)","Galactique ?"] if c in df_sn_sorted.columns]
            st.dataframe(df_sn_sorted[cols_sn], use_container_width=True, hide_index=True)

    # Guide des types SN
    st.markdown("---")
    st.markdown('<div class="sec sn">📚 Guide des Types de Supernovæ</div>', unsafe_allow_html=True)
    cols_types = st.columns(3)
    for idx, (snt_key, snt_val) in enumerate(SN_TYPE_INFO.items()):
        with cols_types[idx % 3]:
            st.markdown(f"""
<div style="background:var(--surface2);border:1px solid var(--border);border-left:3px solid {snt_val['couleur']};
     border-radius:8px;padding:10px 12px;margin-bottom:6px">
  <div style="font-family:var(--mono);font-size:.9em;color:{snt_val['couleur']}">{snt_val['emoji']} Type {snt_key}</div>
  <div style="font-size:.78em;color:var(--text);margin-top:4px">{snt_val['desc']}</div>
  <div style="font-size:.72em;color:var(--muted);margin-top:2px">⏱ {snt_val['duree']}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div class="sec sn">🔗 Sources & Ressources</div>', unsafe_allow_html=True)
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.markdown("""
**Alertes temps réel :**
- 🌐 [Rochester Astronomy](https://rochesterastronomy.org/supernova.html)
- 📡 [Transient Name Server (TNS)](https://www.wis-tns.org)
- 📰 [The Astronomer's Telegram](https://www.astronomerstelegram.org)
- 🔭 [TheSkyLive Supernovae](https://theskylive.com/supernovae)
- ⚡ [SNEWS — Early Warning System](https://snews2.org)
""")
    with col_r2:
        st.markdown("""
**Suivi & données :**
- 📈 [AAVSO](https://www.aavso.org)
- 🔬 [WISeREP](https://wiserep.weizmann.ac.il)
- 🌍 [Open Supernova Catalog](https://sne.space)

**Apps mobiles :**
- 📱 Sirius — alertes transients
- 📱 Stellarium — localiser la cible
- 📱 Telescopius — planification
""")

# ── TAB 3 : DÉSIGNÉS ──────────────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="sec">Objets Récemment Désignés · Transition NEOCP → NASA</div>', unsafe_allow_html=True)
    if st.session_state.recognized_objects:
        for tdes, info in sorted(st.session_state.recognized_objects.items(),
                                  key=lambda x: x[1].get("date",""), reverse=True):
            nom_off = info.get("nom_officiel","?"); meth = info.get("methode","?")
            det = info.get("details",{}); date = info.get("date","?")
            border_color = ("var(--green)" if "SBDB direct" in meth else
                           "var(--accent3)" if "Correspondance H" in meth else "var(--muted)")
            det_html = "".join(
                f"<div style='display:flex;gap:12px;font-size:.8em;padding:2px 0'>"
                f"<span style='color:var(--muted);font-family:var(--mono);min-width:120px'>{k}</span>"
                f"<span>{v}</span></div>" for k,v in det.items())
            sstr = nom_off.replace(" ","%20")
            st.markdown(f"""
<div style="background:var(--surface);border:1px solid var(--border);border-left:4px solid {border_color};
     border-radius:10px;padding:14px 16px;margin-bottom:10px;">
  <div style="display:flex;justify-content:space-between;margin-bottom:8px">
    <div>
      <span style="font-family:var(--mono);font-size:1.05em;color:var(--accent3)">{tdes}</span>
      <span style="color:var(--muted);margin:0 10px">→</span>
      <span style="font-family:var(--ui);font-size:1.1em;font-weight:700;color:var(--green)">{nom_off}</span>
    </div>
    <span style="font-size:.75em;color:var(--muted);font-family:var(--mono)">{date}</span>
  </div>
  <div style="font-size:.78em;color:var(--muted);margin-bottom:8px">🔬 {meth}</div>
  {det_html}
  <div style="margin-top:10px">
    <a href="https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr={sstr}" target="_blank"
       style="color:var(--accent);font-family:var(--mono);font-size:.8em">→ Fiche JPL ↗</a>
  </div>
</div>""", unsafe_allow_html=True)
    else:
        st.markdown('<div class="empty">// AUCUN OBJET DÉSIGNÉ CETTE SESSION //</div>', unsafe_allow_html=True)

# ── TAB 4 : NASA CAD ──────────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="sec">Objets à Approche Rapprochée · NASA JPL CAD</div>', unsafe_allow_html=True)
    if not df_nasa.empty:
        df_n = df_nasa.copy()
        df_n['H_n'] = pd.to_numeric(df_n.get('h', pd.Series(dtype=float)), errors='coerce')
        df_n['Mag. est.'] = df_n['H_n'].apply(lambda x: round(x+2.5,1) if pd.notna(x) else 99)
        df_n['Taille'] = df_n['H_n'].apply(lambda x: classify_size(x) if pd.notna(x) else "?")
        df_n['Vespera II'] = df_n['Mag. est.'].apply(lambda m: f"{vespera_score(m)[0]} {vespera_score(m)[1]}")
        def _nasa_type(des):
            d = str(des)
            if d.startswith('C/') or d.startswith('P/'): return "🌠 Comète"
            if d.startswith('A/'): return "☄️ Interstellaire"
            return "🪨 Astéroïde NEO"
        df_n['Type'] = df_n.get('des', pd.Series()).apply(_nasa_type)
        cols_n = [c for c in ['des','Type','cd','dist','v_rel','H_n','Mag. est.','Taille','Vespera II','diameter'] if c in df_n.columns]
        df_show = df_n[cols_n].rename(columns={'des':'Désignation','cd':'Date','dist':'Dist (LD)',
                                               'v_rel':'Vit km/s','H_n':'H','diameter':'Diam. km'})
        if 'Dist (LD)' in df_show.columns: df_show = df_show.sort_values('Dist (LD)')
        st.dataframe(df_show, use_container_width=True, hide_index=True)
    else:
        st.markdown('<div class="empty">// CATALOGUE NASA VIDE //</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div class="sec">🔍 Fiche Détaillée · NASA JPL SBDB</div>', unsafe_allow_html=True)
    ci, cb = st.columns([3, 1])
    with ci: lq = st.text_input("Désignation :", label_visibility="collapsed", placeholder="Ex : 2024 YR4 · Apophis · 99942")
    with cb: do_l = st.button("🔍 Rechercher", use_container_width=True)
    if do_l and lq.strip():
        with st.spinner("Interrogation NASA JPL SBDB…"):
            try:
                raw = requests.get(NASA_SBDB, params={"sstr":lq.strip(),"phys-par":"1",
                                                       "ca-data":"1","ca-time":"both"}, timeout=20).json()
                if "object" in raw:
                    d = parse_sbdb(raw)
                    st.markdown(f"""
<div class="jpl-box">
<div class="jpl-title">📋 {d['fullname']}</div>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px 16px">
  <div class="jpl-f">SPK-ID <span class="jpl-v">{d['spkid']}</span></div>
  <div class="jpl-f">Classe <span class="jpl-v">{d['orbit_class']}</span></div>
  <div class="jpl-f">NEO <span class="jpl-v">{d['neo']}</span></div>
  <div class="jpl-f">PHO <span class="jpl-v">{d['pha']}</span></div>
  <div class="jpl-f">Cond. code <span class="jpl-v">{d['condition_code']}</span></div>
  <div class="jpl-f">1ère obs. <span class="jpl-v">{d['first_obs']}</span></div>
  <div class="jpl-f">H <span class="jpl-v">{d['H']}</span></div>
  <div class="jpl-f">Albédo <span class="jpl-v">{d['albedo']}</span></div>
  <div class="jpl-f">Diamètre <span class="jpl-v">{d['diameter']} km</span></div>
  <div class="jpl-f">Densité <span class="jpl-v">{d['density']} g/cm³</span></div>
  <div class="jpl-f">Rotation <span class="jpl-v">{d['rot_per']} h</span></div>
  <div class="jpl-f">Spec. <span class="jpl-v">{d['spec_T']}</span></div>
  <div class="jpl-f">e <span class="jpl-v">{d['e']}</span></div>
  <div class="jpl-f">a (UA) <span class="jpl-v">{d['a']}</span></div>
  <div class="jpl-f">q (UA) <span class="jpl-v">{d['q']}</span></div>
  <div class="jpl-f">i (°) <span class="jpl-v">{d['i']}</span></div>
  <div class="jpl-f">Période <span class="jpl-v">{d['per_y']} ans</span></div>
  <div class="jpl-f">MOID (UA) <span class="jpl-v">{d['moid']}</span></div>
  <div class="jpl-f">Palermo <span class="jpl-v">{d['ps_cum']}</span></div>
  <div class="jpl-f">Turin <span class="jpl-v">{d['ts_max']}</span></div>
</div></div>""", unsafe_allow_html=True)
                    if d['ca']:
                        st.markdown("<div style='margin-top:10px;font-family:var(--ui);font-size:.82em;color:var(--accent3)'>PROCHAINES APPROCHES</div>", unsafe_allow_html=True)
                        ca_df = pd.DataFrame(d['ca'][:8])
                        ca_c = [c for c in ['cd','dist','dist_min','dist_max','v_rel','t_sigma_f'] if c in ca_df.columns]
                        st.dataframe(ca_df[ca_c].rename(columns={'cd':'Date','dist':'LD','dist_min':'Min LD',
                                     'dist_max':'Max LD','v_rel':'Vit km/s','t_sigma_f':'Incert.'}),
                                     use_container_width=True, hide_index=True)
                    se = lq.strip().replace(" ","%20")
                    st.markdown(f"<a href='https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr={se}' target='_blank' style='color:var(--accent);font-family:var(--mono);font-size:.8em'>→ Fiche complète JPL ↗</a>", unsafe_allow_html=True)
                elif "message" in raw: st.warning(f"NASA JPL : {raw['message']}")
                else: st.warning("Objet non trouvé.")
            except Exception as ex:
                st.error(f"Erreur : {ex}")

# ── TAB 5 : COMÈTES ───────────────────────────────────────────────────────────
with tab5:
    st.markdown('<div class="sec">Comètes Actives · MPC + NASA Horizons</div>', unsafe_allow_html=True)
    st.info("**Mag.actuelle** via Horizons · **Élong.** >20° = observable · Scores Vespera : 90=excellent · 70=bon · 45=limite")
    if st.session_state.comet_cache.empty:
        st.warning("Données comètes non chargées.")
        if st.button("🌠 Charger les comètes"):
            with st.spinner("Chargement MPC + Horizons (~15s)…"):
                result = fetch_comets()
                if not result.empty: st.session_state.comet_cache = result
            st.rerun()
    else:
        if (datetime.now() - st.session_state.last_comet_req).total_seconds() > 10800:
            if st.button("🔄 Rafraîchir les comètes"):
                with st.spinner("Mise à jour…"):
                    st.session_state.comet_cache = pd.DataFrame()
                    result = fetch_comets()
                    if not result.empty: st.session_state.comet_cache = result
                st.rerun()
        df_comets_show = st.session_state.comet_cache.copy()
        if not df_comets_show.empty:
            df_comets_show['_sort'] = pd.to_numeric(df_comets_show.get('Vespera act.', pd.Series(dtype=float)), errors='coerce').fillna(
                pd.to_numeric(df_comets_show.get('Vespera@peri', pd.Series(dtype=float)), errors='coerce').fillna(0))
            df_comets_show = df_comets_show.sort_values('_sort', ascending=False).drop(columns=['_sort'])
            cols_c = [c for c in ["Nom","Dernier peri.","Prochain peri.","Période",
                                   "Mag.actuelle","Élong. (°)","Observable ?","Vespera act.","Obs. actuelle",
                                   "Mag.@peri","Vespera@peri","Obs.@peri","g","k","q (UA)","e","i (°)"] if c in df_comets_show.columns]
            st.dataframe(df_comets_show[cols_c], use_container_width=True, hide_index=True)

# ── TAB 6 : LEXIQUE ───────────────────────────────────────────────────────────
with tab6:
    st.markdown('<div class="sec">Lexique & Ordres de Grandeur</div>', unsafe_allow_html=True)
    def lx(title, entries, color="#00d4ff"):
        rows_html = "".join(
            f"<div style='display:flex;gap:10px;padding:3px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:.8em'>"
            f"<span style='color:var(--muted);min-width:115px;font-family:var(--mono)'>{k}</span>"
            f"<span style='color:var(--text)'>{v}</span></div>" for k,v in entries)
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:13px 15px;background:var(--surface);"
            f"border-radius:10px;border:1px solid var(--border);margin-bottom:5px'>"
            f"<div style='font-family:var(--ui);font-weight:700;font-size:.87em;letter-spacing:2px;"
            f"text-transform:uppercase;color:{color};margin-bottom:9px'>{title}</div>{rows_html}</div>",
            unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        lx("🌟 Supernovæ · Types & Physique", [
            ("Type Ia",    "Naine blanche thermonucléaire — chandelle standard cosmologique"),
            ("Type II",    "Effondrement cœur d'étoile massive (≥8 M☉)"),
            ("Type Ib/c",  "Idem II — étoile ayant perdu H (Ib) ou H+He (Ic)"),
            ("SLSN",       "Super-lumineuse : 10-100× plus brillante qu'une SN normale"),
            ("TDE",        "Disruption par marées : étoile déchiquetée par un trou noir"),
            ("Galactique", "Lat. gal. |b| < 15° — dans le plan de la Voie Lactée"),
            ("SNEWS",      "Réseau neutrinos — alerte AVANT la lumière visible"),
            ("Kilonova",   "Fusion étoiles à neutrons — forge l'or, le platine, l'uranium"),
        ], color="#b44eff")
        lx("🛰️ NASA Scout API", [
            ("URL",        "ssd-api.jpl.nasa.gov/scout.api (mode S)"),
            ("Avantage",   "Vmag, MOID, CA dist, score NEO, elong, rate"),
            ("Transition", "Objet désigné → disparaît de Scout"),
            ("Rate limit", "60s minimum entre requêtes"),
        ])
        lx("📐 H · Magnitude Absolue", [
            ("H < 18",  "Géant >1 km — extinction de masse"),
            ("H 18–22", "Régional 100m–1km — destruction d'une ville"),
            ("H 22–25", "Local 10–100m — cratère Barringer"),
            ("H > 25",  "Mineur <10m — désintégration atmosphérique"),
        ])
        lx("🚨 Score Dangerosité", [
            ("H×35", "Taille"), ("Arc×25", "Incertitude orbitale"),
            ("NObs×20", "Fraîcheur"), ("MOID×10", "Proximité orbitale"), ("NEO×10", "Score MPC"),
        ], color="#ff4b4b")
    with c2:
        lx("🔭 Score Vespera II", [
            ("Instrument",   "50mm f/5, Sony IMX585, stacking live"),
            ("100 trivial",  "Mag ≤ 10 — œil nu"), ("90 excellent", "Mag ≤ 14.5 — 10 min"),
            ("70 bon",       "Mag ≤ 16.0 — 30 min"), ("45 limite", "Mag ≤ 17.5 — nuit entière"),
            ("15 difficile", "Mag ≤ 19.0"), ("0 impossible", "Mag > 19.0"),
        ], color="#f7b731")
        lx("📏 Distances & Vitesses", [
            ("1 LD",   "384 400 km = Terre–Lune"), ("MOID", "Distance min orbitale (UA)"),
            ("CA min", "Dist min approche (LD)"), ("v_inf", "Vitesse relative (km/s)"),
            ("Rate",   "Vitesse angulaire (\"/min)"), ("Unc.", "Incertitude position (\" arc)"),
        ], color="#00ff88")
        lx("🌠 Paramètres Cométaires", [
            ("g", "Magnitude absolue (typiq. 4–12)"), ("k", "Pente (standard≈4)"),
            ("q (UA)", "Périhélie — <1 UA = géocroisante"), ("e", "≥1 = hyperbolique"),
            ("i (°)", ">90° = rétrograde"),
        ], color="#00ff88")
        lx("🔔 Alertes Discord", [
            ("🚨 Galactique",  "SN dans plan galactique — événement du siècle"),
            ("🌟 Vespera SN",  "SN observable Vespera II (score ≥45)"),
            ("🔔 Nouvelle SN", "SN < mag 19 détectée"),
            ("🆕 Nouvel NEO",  "Apparu dans Scout"),
            ("🎯 Désigné",     "Transition NEOCP→NASA"),
            ("👻 Disparu",     "Retiré sans désignation"),
            ("🔥 ≥50",         "Score NEO franchit 50"),
            ("🚨 ≥80",         "Score critique"),
            ("📊 Horaire",     "Bilan toutes les heures"),
        ], color="#ff4b4b")

# ═══════════════════════════════════════════════════════════════════════════════
# BAS DE PAGE
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
cs, ci2 = st.columns([1.3, 1])

with cs:
    tab_sismo_neo, tab_sismo_sn = st.tabs(["📈 Sismographe NEO", "🌟 Évolution SN"])
    with tab_sismo_neo:
        hist_keys = sorted(st.session_state.obj_history.keys())
        if hist_keys:
            prev_sismo = st.session_state.get("_sismo_prev", hist_keys[0])
            default_idx = hist_keys.index(prev_sismo) if prev_sismo in hist_keys else 0
            target = st.selectbox("Objet actif :", hist_keys, index=default_idx, key="sismo")
            st.session_state["_sismo_prev"] = target
            hdf = pd.DataFrame(st.session_state.obj_history[target]).set_index("T")
            st.line_chart(hdf[["S"]], color="#00d4ff")
            last = st.session_state.obj_history[target][-1]
            st.caption(f"Score={last['S']} | H={last.get('H','?')} | Vmag={last.get('Vmag','?')} | NObs={last.get('NObs','?')} | Arc={last.get('Arc','?')}j")
        else:
            st.markdown('<div class="empty">// PAS D\'OBJETS DANS L\'HISTORIQUE //</div>', unsafe_allow_html=True)
    with tab_sismo_sn:
        sn_hist_keys = [k for k,v in st.session_state.sn_history.items() if len(v) >= 2]
        if sn_hist_keys:
            target_sn = st.selectbox("Supernova :", sn_hist_keys, key="sismo_sn")
            sn_hdf = pd.DataFrame(st.session_state.sn_history[target_sn]).set_index("T")
            st.line_chart(sn_hdf[["Mag"]], color="#b44eff")
            last_sn = st.session_state.sn_history[target_sn][-1]
            first_sn = st.session_state.sn_history[target_sn][0]
            delta_mag = last_sn["Mag"] - first_sn["Mag"]
            st.caption(f"Mag actuelle : {last_sn['Mag']} | Évolution : {'📈 +' if delta_mag > 0 else '📉 '}{delta_mag:.2f} mag")
        else:
            st.markdown('<div class="empty">// PAS ASSEZ DE DONNÉES SN ENCORE //</div>', unsafe_allow_html=True)

with ci2:
    st.markdown('<div class="sec">⏱ Statut Système</div>', unsafe_allow_html=True)
    elapsed = (datetime.now() - st.session_state.last_refresh).total_seconds()
    pct = min(100, int(elapsed / refresh_rate * 100))
    st.progress(pct, text=f"Prochain refresh dans {max(0, refresh_rate - int(elapsed))}s")
    st.markdown(
        f"<div style='font-family:var(--mono);font-size:.78em;color:var(--muted);margin-top:8px;line-height:2'>"
        f"🕐 {datetime.now().strftime('%H:%M:%S')} · 🔄 {refresh_rate}s<br>"
        f"🌍 {radius_ld} LD · 📅 {horizon_days}j<br>"
        f"🌟 SN : {n_sn} ({n_sn_vesp} Vespera)<br>"
        f"🔭 Vespera {'ON H≤'+str(mag_limit) if vespera_mode else 'OFF'}</div>",
        unsafe_allow_html=True)

    st.markdown('<div class="sec" style="margin-top:18px">🔔 Journal Discord</div>', unsafe_allow_html=True)
    if st.session_state.discord_log:
        rows_dc = ""
        for ts, stat, prev in reversed(st.session_state.discord_log[-12:]):
            cls = "dc-ok" if "OK" in stat else ("dc-w" if "HTTP" in stat else "dc-err")
            rows_dc += (f"<div class='dc-row'><span class='dc-ts'>{ts}</span>"
                        f"<span class='{cls}'>{stat}</span>"
                        f"<span class='dc-msg'>{prev[:45]}</span></div>")
        st.markdown(
            f"<div style='background:var(--surface);border:1px solid var(--border);"
            f"border-radius:8px;padding:10px 12px;max-height:180px;overflow-y:auto'>{rows_dc}</div>",
            unsafe_allow_html=True)
    else:
        st.markdown("<div class='empty' style='font-size:.76em'>Aucune alerte cette session</div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-REFRESH
# ═══════════════════════════════════════════════════════════════════════════════
st.session_state.last_refresh = datetime.now()
time.sleep(refresh_rate)
st.rerun()
