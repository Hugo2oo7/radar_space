import streamlit as st
import requests
import pandas as pd
import re
import time
import math
import urllib3
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DISCORD_WEBHOOK = (
    "https://discord.com/api/webhooks/1499765998377635900/"
    "FBUhSnXY4kBk7fSepXKJvCsIMe47njutPe31ttYURvfcW21Vz4ZxVu5xLweC1n6HgeOJ"
)

# ── Sources ────────────────────────────────────────────────────────────────────
# Scout = API NASA officielle listant TOUS les objets NEOCP actifs (mode S sans tdes)
# Avantages : données riches (vmag, moid, caDist, neoScore MPC, elong, rate...)
# + quand un objet est désigné, il disparaît de Scout → signal propre de transition
SCOUT_API   = "https://ssd-api.jpl.nasa.gov/scout.api"
SCOUT_OBJ   = "https://ssd-api.jpl.nasa.gov/scout.api?tdes={}"  # détail par objet
NASA_CAD    = "https://ssd-api.jpl.nasa.gov/cad.api"
NASA_SBDB   = "https://ssd-api.jpl.nasa.gov/sbdb.api"
MPC_COMET   = "https://www.minorplanetcenter.net/iau/Ephemerides/Comets/Soft00Cmt.txt"
# Page "Previous NEOCP" : liste les objets récemment retirés avec raison + désignation officielle
# Format JSON disponible via l'API MPC
MPC_PREV_API = "https://www.minorplanetcenter.net/iau/NEO/pccp_tabular.html"
MPC_PREV_JSON = "https://data.minorplanetcenter.net/api/get-neocp-objects-removed"

# Vespera II — specs
VESP_SHORT  = 14.5   # session 10 min
VESP_MEDIUM = 16.0   # session 30 min
VESP_LONG   = 17.5   # nuit entière, ciel sombre
VESP_LIMIT  = 19.0   # limite absolue instrument

st.set_page_config(page_title="Deep Space Radar", layout="wide", page_icon="🛰️")

# ═══════════════════════════════════════════════════════════════════════════════
# CSS — identique V26 (compact)
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&family=Exo+2:wght@300;400;600&display=swap');
:root{--bg:#07090f;--surface:#0d1120;--surface2:#131829;--border:#1e2a45;
      --accent:#00d4ff;--accent2:#ff4b4b;--accent3:#f7b731;--green:#00ff88;
      --text:#c8d8f0;--muted:#5a7090;
      --mono:'Share Tech Mono',monospace;--ui:'Rajdhani',sans-serif;--body:'Exo 2',sans-serif;}
html,body,[class*="css"]{font-family:var(--body);background-color:var(--bg)!important;color:var(--text);}
.stApp::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(ellipse 80% 50% at 20% 10%,rgba(0,212,255,.06) 0%,transparent 60%),
             radial-gradient(ellipse 60% 40% at 80% 80%,rgba(255,75,75,.05) 0%,transparent 60%);}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#0a0e1a,#0d1323)!important;border-right:1px solid var(--border)!important;}
.radar-logo{font-family:var(--mono);font-size:2.2em;letter-spacing:-2px;color:var(--accent);text-shadow:0 0 20px rgba(0,212,255,.5);}
.radar-sub{font-family:var(--ui);font-size:.8em;color:var(--muted);letter-spacing:3px;text-transform:uppercase;}
.sync-pill{background:var(--surface2);border:1px solid var(--border);border-radius:50px;padding:5px 16px;
           font-family:var(--mono);font-size:.82em;color:var(--accent);display:inline-flex;align-items:center;gap:7px;}
.sync-dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);animation:blink 1.2s infinite;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
.metric-grid{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap;}
.metric-card{flex:1;min-width:115px;background:var(--surface);border:1px solid var(--border);
             border-top:3px solid var(--accent);border-radius:10px;padding:12px 16px;}
.metric-card.w{border-top-color:var(--accent2);} .metric-card.c{border-top-color:var(--accent3);} .metric-card.g{border-top-color:var(--green);}
.metric-val{font-family:var(--mono);font-size:1.9em;color:var(--accent);line-height:1.1;}
.metric-card.w .metric-val{color:var(--accent2);} .metric-card.c .metric-val{color:var(--accent3);} .metric-card.g .metric-val{color:var(--green);}
.metric-label{font-family:var(--ui);font-size:.72em;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-top:3px;}
.stTabs [data-baseweb="tab-list"]{background:transparent;border-bottom:1px solid var(--border);}
.stTabs [data-baseweb="tab"]{font-family:var(--ui);font-weight:600;font-size:.88em;color:var(--muted)!important;
                               padding:9px 20px;border-bottom:2px solid transparent;background:transparent!important;}
.stTabs [aria-selected="true"]{color:var(--accent)!important;border-bottom:2px solid var(--accent)!important;}
.sec{font-family:var(--ui);font-size:.95em;font-weight:700;letter-spacing:2px;text-transform:uppercase;
     color:var(--accent);margin-bottom:10px;display:flex;align-items:center;gap:7px;}
.sec::before{content:'';display:inline-block;width:4px;height:16px;background:var(--accent);border-radius:2px;}
.empty{background:var(--surface2);border:1px dashed var(--border);border-radius:8px;padding:20px;
       text-align:center;color:var(--muted);font-family:var(--mono);font-size:.82em;}
.sidebar-sec{font-family:var(--ui);font-size:.68em;letter-spacing:3px;text-transform:uppercase;color:var(--muted);
             margin:16px 0 5px;padding-top:10px;border-top:1px solid var(--border);}
/* carte transition */
.trans-card{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--accent3);
            border-radius:10px;padding:14px 16px;margin-bottom:8px;}
.trans-title{font-family:var(--ui);font-weight:700;font-size:.95em;color:var(--accent3);margin-bottom:8px;}
.trans-row{display:flex;gap:12px;font-size:.8em;padding:2px 0;color:var(--text);}
.trans-k{color:var(--muted);font-family:var(--mono);min-width:120px;}
/* discord */
.dc-row{display:flex;gap:10px;align-items:baseline;padding:3px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:.8em;}
.dc-row:last-child{border-bottom:none;}
.dc-ts{color:var(--muted);font-family:var(--mono);min-width:65px;}
.dc-ok{color:var(--green);min-width:80px;font-family:var(--mono);}
.dc-w{color:var(--accent3);min-width:80px;font-family:var(--mono);}
.dc-err{color:var(--accent2);min-width:80px;font-family:var(--mono);}
.dc-msg{color:var(--text);opacity:.65;}
/* jpl lookup */
.jpl-box{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:16px 18px;margin-top:10px;}
.jpl-title{font-family:var(--ui);font-size:.95em;font-weight:700;color:var(--accent3);margin-bottom:10px;}
.jpl-f{margin-bottom:6px;font-family:var(--mono);font-size:.8em;color:var(--muted);}
.jpl-v{color:var(--text);font-weight:bold;}
#MainMenu,footer,header{visibility:hidden;}
.block-container{padding-top:1.4rem!important;}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════════════════════════════════
def _init(k, v):
    if k not in st.session_state: st.session_state[k] = v

_init('obj_history',        {})   # tdes → [{T, S, H, NObs, Arc, Vmag, moid}]
_init('nasa_cache',         pd.DataFrame())
_init('comet_cache',        pd.DataFrame())
_init('scout_cache',        pd.DataFrame())
_init('last_nasa_req',      datetime.now() - timedelta(minutes=5))
_init('last_scout_req',     datetime.now() - timedelta(minutes=5))
_init('last_comet_req',     datetime.now() - timedelta(hours=3))
_init('last_alert_time',    datetime.now() - timedelta(hours=2))
_init('last_refresh',       datetime.now())
_init('discord_log',        [])
_init('alerted_new',        set())
_init('alerted_gone',       set())
_init('alerted_recognized', set())
_init('score_palier',       {})
_init('prev_top5',          [])
_init('prev_noms',          set())
# Objets reconnus (tdes → info de transition)
_init('recognized_objects', {})   # tdes → {nom_officiel, H, q, e, i, dist_nasa, date, source}
# Cache de la liste des objets retirés du NEOCP (Previous NEOCP page MPC)
_init('prev_neocp_cache',   {})   # tdes → {designation, reason, date}
_init('last_prev_req',      datetime.now() - timedelta(hours=2))
# Objets archivés manuellement (retirés de l'affichage et de l'historique)
_init('archived',           set())

# ═══════════════════════════════════════════════════════════════════════════════
# CALCUL SCORES
# ═══════════════════════════════════════════════════════════════════════════════
def compute_score(h: float, n_obs: int, arc: float, moid: float = 99, neo_score: float = 0) -> float:
    """
    Score de dangerosité/intérêt (0–100) enrichi avec les données Scout.
      H (taille)              : 35 pts  — H<18 → max, H=25 → 0
      Arc court (incertitude) : 25 pts  — arc<0.5j → max, arc≥30j → 0
      Peu d'observations      : 20 pts  — ≤5 obs → max, ≥50 → 0
      MOID proche             : 10 pts  — moid<0.01 UA → max, ≥0.1 → 0
      Score NEO MPC           : 10 pts  — neoScore 0–100 → 0–10 pts
    """
    s_h    = max(0.0, min(35.0, (25.0 - h) / 25.0 * 35.0))
    s_arc  = max(0.0, min(25.0, (30.0 - arc) / 30.0 * 25.0))
    s_obs  = max(0.0, min(20.0, (50.0 - n_obs) / 50.0 * 20.0))
    s_moid = max(0.0, min(10.0, (0.1 - min(moid, 0.1)) / 0.1 * 10.0)) if moid < 99 else 0.0
    s_neo  = neo_score / 100.0 * 10.0
    return round(s_h + s_arc + s_obs + s_moid + s_neo, 1)


def vespera_score(mag: float) -> tuple:
    """Score d'observabilité Vespera II (0–100) + label."""
    if mag <= 10:          return 100, "👁️ Trivial"
    if mag <= VESP_SHORT:  return 90,  "🟢 Excellent (10 min)"
    if mag <= VESP_MEDIUM: return 70,  "🟡 Bon (30 min)"
    if mag <= VESP_LONG:   return 45,  "🟠 Limite (nuit entière)"
    if mag <= VESP_LIMIT:  return 15,  "🔴 Très difficile"
    return 0, "⛔ Hors portée"

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ═══════════════════════════════════════════════════════════════════════════════
def get_trend(name: str, score: float) -> str:
    h = st.session_state.obj_history.get(name, [])
    if len(h) < 2: return "➡️"
    d = score - h[-2]["S"]
    return "↗️" if d > 0.5 else "↘️" if d < -0.5 else "➡️"

def score_label(s: float) -> str:
    if s >= 80: return "🔴 CRITIQUE"
    if s >= 50: return "🟡 ÉLEVÉ"
    return "🟢 FAIBLE"

def classify_size(h: float) -> str:
    if h < 18: return ">1 km"
    if h < 22: return "100m–1km"
    if h < 25: return "10–100m"
    return "<10m"

_init('discord_queue', [])  # messages en attente de retry : [(content, attempt, next_try)]

def _discord(content: str):
    """Envoie sur Discord. Si échec, met en queue pour retry toutes les 60s."""
    ts = datetime.now().strftime("%H:%M:%S")
    prev = content[:90].replace("\n", " ")
    try:
        r = requests.post(DISCORD_WEBHOOK, json={"content": content}, timeout=5)
        if r.status_code in (200, 204):
            status_str = "✅ OK"
        else:
            status_str = f"⚠️ HTTP {r.status_code}"
            # Mettre en queue pour retry
            st.session_state.discord_queue.append({
                "content": content, "attempt": 1,
                "next_try": datetime.now() + timedelta(seconds=60)
            })
    except Exception as e:
        status_str = f"❌ {type(e).__name__}"
        st.session_state.discord_queue.append({
            "content": content, "attempt": 1,
            "next_try": datetime.now() + timedelta(seconds=60)
        })
    st.session_state.discord_log.append((ts, status_str, prev))
    if len(st.session_state.discord_log) > 25:
        st.session_state.discord_log = st.session_state.discord_log[-25:]


def _process_discord_queue():
    """Appelé à chaque refresh — retente les messages en échec."""
    now = datetime.now()
    remaining = []
    for item in st.session_state.discord_queue:
        if now < item["next_try"]:
            remaining.append(item)
            continue
        if item["attempt"] >= 5:  # abandon après 5 tentatives
            ts = now.strftime("%H:%M:%S")
            st.session_state.discord_log.append((ts, "❌ Abandon (5 essais)", item["content"][:60]))
            continue
        try:
            r = requests.post(DISCORD_WEBHOOK, json={"content": item["content"]}, timeout=5)
            if r.status_code in (200, 204):
                ts = now.strftime("%H:%M:%S")
                st.session_state.discord_log.append((ts, f"✅ Retry#{item['attempt']} OK", item["content"][:60]))
                # Succès → ne pas remettre en queue
            else:
                item["attempt"] += 1
                item["next_try"] = now + timedelta(seconds=60)
                remaining.append(item)
        except Exception:
            item["attempt"] += 1
            item["next_try"] = now + timedelta(seconds=60)
            remaining.append(item)
    st.session_state.discord_queue = remaining

# ═══════════════════════════════════════════════════════════════════════════════
# FETCH "PREVIOUS NEOCP" — Source la plus fiable pour les désignations officielles
# La page MPC liste tous les objets retirés du NEOCP avec leur désignation officielle
# C'est exactement ce qu'on voit dans la capture : "Moved to PCCP", "Designated 2026 XY1"...
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_prev_neocp() -> dict:
    """
    Récupère la liste des objets récemment retirés du NEOCP via la page HTML MPC.
    On parse le tableau HTML pour extraire : tdes temporaire → désignation officielle + raison.
    Refresh : toutes les 10 minutes max (données semi-statiques).
    Retourne un dict : {tdes: {designation, reason, date}}
    """
    now = datetime.now()
    td = (now - st.session_state.last_prev_req).total_seconds()
    if td < 600 and st.session_state.prev_neocp_cache:
        return st.session_state.prev_neocp_cache

    result = {}
    # URL de la page "Elsewhere" (Previous NEOCP objects) — liste avec raisons de retrait
    urls_to_try = [
        "https://www.minorplanetcenter.net/iau/NEO/pccp_tabular.html",  # PCCP → comètes potentielles
        "https://www.minorplanetcenter.net/iau/NEO/toconfirm_tabular.html",  # NEOCP principal
    ]
    for url in urls_to_try:
        try:
            r = requests.get(url, timeout=6, headers={"User-Agent": "DeepSpaceRadar/27"})
            if r.status_code != 200:
                continue
            html = r.text
            # Chercher les patterns de désignation : "Moved to PCCP", "Designated YYYY XY1", etc.
            # Patterns dans le HTML MPC :
            # - Lignes avec un tdes + "Moved to the PCCP" → objet possible comète
            # - Lignes avec un tdes + une désignation officielle type "2026 AB1"
            # Pattern tdes MPC : lettres+chiffres, typiq. 6-8 chars (ex: C1EN9T5, A11BRI6)
            # Désignation officielle : "YYYY Xnn" ou numéro
            import re as _re
            # Chercher les paires (tdes temporaire, désignation)
            # Dans le HTML brut, chaque ligne ressemble à :
            # <tr><td>C1EN9T5</td><td>...</td><td>Moved to the PCCP</td>...</tr>
            rows_html = _re.findall(r'<tr[^>]*>(.*?)</tr>', html, _re.DOTALL | _re.IGNORECASE)
            for row in rows_html:
                cells = _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.DOTALL | _re.IGNORECASE)
                cells = [_re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                if len(cells) < 2:
                    continue
                tdes_cand = cells[0].strip()
                # Valider que c'est un tdes MPC (6-8 chars alphanumériques)
                if not tdes_cand or not _re.match(r'^[A-Za-z0-9]{4,10}$', tdes_cand):
                    continue
                reason = " ".join(cells).strip()
                # Chercher une désignation officielle dans les cellules
                designation = None
                for cell in cells[1:]:
                    # Désignation provisoire : "2026 AB1", "2025 YR4", etc.
                    m = _re.search(r'\b(20\d{2}\s+[A-Z]{1,2}\d{1,4})\b', cell)
                    if m:
                        designation = m.group(1)
                        break
                    # Désignation numérotée : "(12345)"
                    m2 = _re.search(r'\((\d{4,6})\)', cell)
                    if m2:
                        designation = m2.group(1)
                        break
                    # "Moved to PCCP" → objet potentiellement cométaire
                    if 'pccp' in cell.lower() or 'comet' in cell.lower():
                        designation = f"[PCCP] {tdes_cand}"
                        break

                if designation or 'moved' in reason.lower() or 'designated' in reason.lower():
                    result[tdes_cand] = {
                        "designation": designation or "?",
                        "reason": reason[:80],
                        "date": now.strftime("%Y-%m-%d %H:%M"),
                        "source": url.split('/')[-1],
                    }
        except Exception:
            continue

    if result:
        # Fusionner avec le cache existant (les anciens restent)
        merged = {**st.session_state.prev_neocp_cache, **result}
        st.session_state.prev_neocp_cache = merged
        st.session_state.last_prev_req = now

    return st.session_state.prev_neocp_cache


# ═══════════════════════════════════════════════════════════════════════════════
# DÉTECTION TRANSITION NEOCP → NASA  (algorithme principal)
# ═══════════════════════════════════════════════════════════════════════════════
def detect_transitions(prev_noms: set, cur_noms: set, df_nasa: pd.DataFrame) -> list:
    """
    Stratégie multi-couches pour détecter qu'un objet NEOCP a été officiellement désigné :

    1. SCOUT-SBDB direct : quand un objet disparaît de Scout, on tente immédiatement
       une requête SBDB avec son tdes — si NASA le connaît → désignation trouvée.

    2. Correspondance orbitale avec NASA CAD : si l'objet disparu a des caractéristiques
       orbitales enregistrées (H, q, e) similaires à un objet NASA CAD récemment apparu,
       on matche avec un score de similarité.

    3. Correspondance temporelle : si l'objet disparaît dans la fenêtre de temps
       couverte par le CAD, il est probablement dedans.

    Retourne une liste de dicts {tdes, nom_officiel, methode, details}.
    """
    gone = prev_noms - cur_noms
    if not gone:
        return []

    transitions = []
    nasa_des_list = df_nasa['des'].tolist() if not df_nasa.empty and 'des' in df_nasa.columns else []
    # Récupérer la liste des retraits MPC (refresh max toutes les 10 min)
    prev_neocp = fetch_prev_neocp()

    for tdes in gone:
        if tdes in st.session_state.alerted_gone:
            continue

        result = {"tdes": tdes, "nom_officiel": None, "methode": None, "details": {}}

        # ── Méthode 0 : Page "Previous NEOCP" MPC — source officielle ──
        # C'est exactement ce qu'affiche la capture : "Moved to PCCP", désignations officielles
        if tdes in prev_neocp:
            info_prev = prev_neocp[tdes]
            desig = info_prev.get("designation", "?")
            reason = info_prev.get("reason", "?")
            is_pccp = desig.startswith("[PCCP]")
            result["nom_officiel"] = desig if not is_pccp else f"Comète potentielle (PCCP)"
            result["methode"] = "Page MPC Previous NEOCP (officielle)"
            result["details"] = {
                "Désignation": desig,
                "Raison MPC":  reason[:60],
                "Confiance":   "✅ Officielle (source MPC directe)",
                "PCCP":        "Oui — probablement une comète" if is_pccp else "Non",
            }
            transitions.append(result)
            st.session_state.alerted_gone.add(tdes)
            continue


        try:
            r = requests.get(NASA_SBDB, params={"sstr": tdes, "phys-par": "1"}, timeout=5)
            data = r.json()
            if "object" in data:
                obj = data["object"]
                orb = data.get("orbit", {})
                phy = {p["name"]: p.get("value") for p in data.get("phys_par", []) if isinstance(p, dict)}
                elems = orb.get("elements", {})
                if isinstance(elems, list):
                    elems = {e["name"]: e.get("value") for e in elems}
                result["nom_officiel"] = obj.get("fullname", obj.get("des", "?"))
                result["methode"]      = "SBDB direct (tdes trouvé)"
                result["details"]      = {
                    "H":    phy.get("H", "?"),
                    "q":    elems.get("q", "?"),
                    "e":    elems.get("e", "?"),
                    "i":    elems.get("i", "?"),
                    "classe": obj.get("orbit_class", {}).get("name", "?"),
                    "neo":  "✅" if obj.get("neo") else "❌",
                }
                transitions.append(result)
                st.session_state.alerted_gone.add(tdes)
                continue
        except Exception:
            pass

        # ── Méthode 2 : Correspondance H similaire dans NASA CAD (fenêtre ±0.5 mag) ──
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
                        result["nom_officiel"] = best.get("des", best.get("fullname", "?"))
                        result["methode"]      = f"Correspondance H={h_ref:.1f}±0.5 dans NASA CAD"
                        result["details"]      = {
                            "H NASA":  best.get("h", "?"),
                            "dist":    best.get("dist", "?"),
                            "date":    best.get("cd", "?"),
                            "confiance": "Moyenne (H similaire)"
                        }
                        transitions.append(result)
                        st.session_state.alerted_gone.add(tdes)
                        continue
                except Exception:
                    pass

        # ── Méthode 3 : Disparu sans correspondance — fausse alerte / non confirmé ──
        result["nom_officiel"] = None
        result["methode"]      = "Retiré du NEOCP (non confirmé)"
        result["details"]      = {"raison": "Orbite non contrainte, fausse détection, ou objet artificiel"}
        transitions.append(result)
        st.session_state.alerted_gone.add(tdes)

    return transitions

# ═══════════════════════════════════════════════════════════════════════════════
# ALERTES DISCORD
# ═══════════════════════════════════════════════════════════════════════════════
def monitor_and_alert(df_anom: pd.DataFrame, df_nasa: pd.DataFrame, transitions: list):
    now = datetime.now()
    cur_noms = set(df_anom['Nom'].tolist()) if not df_anom.empty else set()
    events = []

    # 1. Nouveaux objets
    new_objs = cur_noms - st.session_state.alerted_new
    for n in new_objs:
        row = df_anom[df_anom['Nom'] == n].iloc[0]
        events.append(f"🆕 **NOUVEL OBJET :** `{n}` — H={row.get('H','?')} | Vmag={row.get('Vmag','?')} | Score={row['Score']}")
    st.session_state.alerted_new.update(new_objs)

    # 2. Transitions (résultat de detect_transitions)
    for t in transitions:
        tdes = t["tdes"]
        nom  = t["nom_officiel"]
        meth = t["methode"]
        if nom:
            msg = (f"🎯 **DÉSIGNÉ OFFICIELLEMENT :** `{tdes}` → `{nom}`\n"
                   f"   Méthode : {meth}\n"
                   f"   Détails : {t['details']}")
            events.append(msg)
            st.session_state.recognized_objects[tdes] = {
                "nom_officiel": nom, "methode": meth,
                "details": t["details"], "date": now.strftime("%Y-%m-%d %H:%M")
            }
        else:
            events.append(f"👻 **DISPARU :** `{tdes}` retiré du NEOCP — {t['details'].get('raison','')}")

    # 3. Seuils de score avec reset
    if not df_anom.empty:
        for r in df_anom.itertuples():
            palier = st.session_state.score_palier.get(r.Nom)
            tr = get_trend(r.Nom, r.Score)
            if r.Score >= 80 and palier != 80:
                events.append(f"🚨 **CRITIQUE ≥80 :** `{r.Nom}` {tr} Score={r.Score} | H={getattr(r,'H','?')}")
                st.session_state.score_palier[r.Nom] = 80
            elif 50 <= r.Score < 80 and palier not in (50, 80):
                events.append(f"🔥 **SEUIL ≥50 :** `{r.Nom}` {tr} Score={r.Score}")
                st.session_state.score_palier[r.Nom] = 50
            elif 50 <= r.Score < 80 and palier == 80:
                st.session_state.score_palier[r.Nom] = 50
            elif r.Score < 50:
                if palier in (50, 80):
                    events.append(f"📉 **RETOMBÉ :** `{r.Nom}` Score={r.Score} (alerte réinitialisée)")
                st.session_state.score_palier[r.Nom] = None

    # 4. Changement Top 5
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
                if entrants: msg += f"  ↑ Entrants : `{', '.join(entrants)}`\n"
                if sortants:  msg += f"  ↓ Sortants : `{', '.join(sortants)}`"
                events.append(msg)
        st.session_state.prev_top5 = new_top5

    if events:
        _discord("📡 **RADAR SENTINELLE**\n" + "\n".join(events))

    # 5. Bilan horaire
    if (now - st.session_state.last_alert_time).total_seconds() > 3600:
        msg = f"📊 **BILAN HORAIRE ({now.strftime('%H:%M')})**\n"
        if not df_anom.empty:
            for row in df_anom.sort_values("Score", ascending=False).head(10).itertuples():
                msg += f"- `{row.Nom}` {get_trend(row.Nom, row.Score)} S={row.Score} H={getattr(row,'H','?')}\n"
        else:
            msg += "Aucune anomalie active."
        _discord(msg)
        st.session_state.last_alert_time = now

# ═══════════════════════════════════════════════════════════════════════════════
# ACQUISITION
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_scout() -> pd.DataFrame:
    """
    API NASA Scout (mode S) : liste tous les objets NEOCP actifs.
    Retourne le cache immédiatement si < 60s, sinon tente une mise à jour
    en arrière-plan avec timeout court pour ne pas bloquer l'UI.
    """
    now = datetime.now()
    time_diff = (now - st.session_state.last_scout_req).total_seconds()
    if time_diff < 60 and not st.session_state.scout_cache.empty:
        return st.session_state.scout_cache.copy()

    df = pd.DataFrame()
    try:
        res = requests.get(SCOUT_API, timeout=8)   # timeout court : 8s max
        res.raise_for_status()
        raw = res.json()
        # Mode S (liste complète) : Scout retourne directement une liste JSON à la racine
        # Ex: [{"objectName":"A11BRI6","H":"20.3","nObs":"4",...}, ...]
        # Certaines versions encapsulent dans {"data":[...], "signature":{...}}
        if isinstance(raw, list):
            data_list = raw
        elif isinstance(raw, dict):
            # Chercher la liste dans tous les champs possibles
            data_list = None
            for key in ("data", "result", "objects", "neocp"):
                if key in raw and isinstance(raw[key], list):
                    data_list = raw[key]
                    break
            if data_list is None:
                # Dernière chance : si le dict lui-même est un objet unique
                data_list = [raw] if "objectName" in raw or "tdes" in raw else []
        else:
            data_list = []

        if not data_list:
            return st.session_state.scout_cache.copy()

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
                ra      = obj.get("ra", "?")
                dec     = obj.get("dec", "?")
                elong   = obj.get("elong", "?")
                rate    = obj.get("rate", "?")   # vitesse angulaire "/min
                unc     = obj.get("unc", "?")    # incertitude position "
                last    = obj.get("lastRun", "?")

                # Dériver le type d'objet depuis les scores Scout
                # tisserandScore > 0 → probable comète ; ieoScore → IEO ; geocentricScore → satellite
                tiss   = float(obj.get("tisserandScore", 0))
                geo_sc = float(obj.get("geocentricScore", 0))
                ieo_sc = float(obj.get("ieoScore", 0))
                if tiss > 50:
                    obj_type = "🌠 Comète prob."
                elif geo_sc > 50:
                    obj_type = "🛰️ Satellite art."
                elif ieo_sc > 50:
                    obj_type = "🌍 IEO (inner)"
                elif neo_sc >= 80:
                    obj_type = "☄️ NEO candidat"
                else:
                    obj_type = "🪨 Indéterminé"

                # Objets "déjà catalogués" : bien connus, peu d'intérêt pour suivi NEOCP
                # Critère : score NEO ~0 ET beaucoup d'obs ET arc long → à envoyer dans catalogués
                is_catalogued = (neo_sc < 10 and n_obs > 15 and arc > 3.0)

                score = compute_score(h_val, n_obs, arc, moid, neo_sc)

                rows.append({
                    "Nom":         tdes,
                    "Type":        obj_type,
                    "H":           round(h_val, 1),
                    "Vmag":        round(vmag, 1),
                    "NObs":        n_obs,
                    "Arc (j)":     round(arc, 2),
                    "MOID (UA)":   round(moid, 4) if moid < 99 else ">0.1",
                    "CA min (LD)": round(ca_dist, 3) if ca_dist < 99 else "?",
                    "Vit. ∞":      v_inf,
                    "R.A.":        ra,
                    "Déc.":        dec,
                    "Élong.":      elong,
                    "Rate \"/m":   rate,
                    "Unc. \"":     unc,
                    "Score NEO":   int(neo_sc),
                    "Score":       score,
                    "Statut":      score_label(score),
                    "Taille":      classify_size(h_val),
                    "MàJ":         last,
                    "_catalogued": is_catalogued,
                })
            except Exception:
                continue

        if rows:
            df = pd.DataFrame(rows)
            # Ne pas stocker les archivés dans le cache non plus
            df = df[~df['Nom'].isin(st.session_state.archived)]
            st.session_state.scout_cache = df
            st.session_state.last_scout_req = now
        elif not st.session_state.scout_cache.empty:
            df = st.session_state.scout_cache.copy()
            df = df[~df['Nom'].isin(st.session_state.archived)]

    except Exception:
        # Fallback : MPC NEOCP .txt si Scout API inaccessible
        # Format .txt : colonnes séparées par espaces, header sur ligne 1
        # Temp Desig | Score | Discovery | R.A. | Decl. | V | Updated | Note | NObs | Arc | H | Not Seen/dys
        # (correspond exactement à la capture d'écran de l'utilisateur)
        try:
            resp = requests.get("https://minorplanetcenter.net/iau/NEO/neocp.txt", timeout=12)
            rows = []
            lines = resp.text.strip().split('\n')
            for line in lines:
                parts = line.split()
                if len(parts) < 10 or parts[0] in ('Temp', 'Score', '---'):
                    continue
                try:
                    tdes  = parts[0]
                    # V (magnitude visuelle) est col 5 (0-indexé)
                    vmag  = float(parts[5]) if len(parts) > 5 else 99.0
                    # NObs est l'avant-dernière colonne numérique avant Arc et H
                    # D'après capture : Temp Desig | Score | Discovery | R.A.(2) | Decl.(2) | V | Updated(3) | Note | NObs | Arc | H | Not Seen
                    # On cherche H et Arc depuis la fin
                    h_val  = float(parts[-2])
                    n_arc  = float(parts[-3])
                    n_obs  = int(float(parts[-4]))
                    score  = compute_score(h_val, n_obs, n_arc, 99, 0)
                    rows.append({
                        "Nom": tdes, "H": round(h_val,1), "Vmag": round(vmag,1),
                        "NObs": n_obs, "Arc (j)": round(n_arc,2),
                        "MOID (UA)": ">0.1", "CA min (LD)": "?",
                        "Vit. ∞": "?", "R.A.": "?", "Déc.": "?",
                        "Élong.": "?", "Rate \"/m": "?", "Unc. \"": "?",
                        "Score NEO": 0, "Score": score,
                        "Statut": score_label(score),
                        "Taille": classify_size(h_val), "MàJ": "Fallback .txt",
                    })
                except (ValueError, IndexError):
                    continue
            if rows:
                df = pd.DataFrame(rows)
                df = df[~df['Nom'].isin(st.session_state.archived)]
                # On ne met PAS en cache le fallback pour reessayer Scout au prochain refresh
        except Exception:
            df = st.session_state.scout_cache.copy()

    return df


def fetch_nasa_cad(radius: int, days: int) -> tuple:
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
        except Exception:
            pass
    return st.session_state.nasa_cache.copy(), max(0, int(60 - td))


def fetch_comets() -> pd.DataFrame:
    """
    Parse CometEls.txt (format MPC officiel, espace-séparé) :
    Col 0      : désignation packée (ex: PJ96R020)
    Col 1      : année périhélie
    Col 2      : mois périhélie
    Col 3      : jour.dddd périhélie
    Col 4      : q (distance périhélie, UA)
    Col 5      : e (excentricité)
    Col 6      : ω (argument périhélie, °)
    Col 7      : Ω (longitude nœud ascendant, °)
    Col 8      : i (inclinaison, °)
    Col 9      : epoch (YYYYMMDD)
    Col 10     : g (magnitude absolue)
    Col 11     : k (pente magnitude)
    Col 12+    : nom complet (P/..., C/..., etc.)
    Source : http://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt
    """
    now = datetime.now()
    td = (now - st.session_state.last_comet_req).total_seconds()
    if td < 10800 and not st.session_state.comet_cache.empty:
        return st.session_state.comet_cache.copy()

    # Utiliser CometEls.txt plutôt que Soft00Cmt.txt — même format, plus fiable
    COMET_URL = "http://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt"
    rows = []
    try:
        rc = requests.get(COMET_URL, timeout=8)
        rc.raise_for_status()
        for line in rc.text.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) < 12:
                continue
            try:
                yr   = int(parts[1])
                mo   = int(parts[2])
                dy   = float(parts[3])
                q    = float(parts[4])
                e    = float(parts[5])
                w    = float(parts[6])
                node = float(parts[7])
                i    = float(parts[8])
                g    = float(parts[10])
                k    = float(parts[11])
                nom  = " ".join(parts[12:]).strip() if len(parts) > 12 else parts[0]

                if q <= 0 or q > 50 or e < 0 or g > 30: continue

                # ── Période orbitale (3ème loi de Kepler) ──
                # Pour e < 1 (elliptique) : a = q/(1-e), T = a^1.5 années
                # Pour e >= 1 (hyperbolique/parabolique) : pas de période
                if e < 1.0:
                    a = q / (1.0 - e)
                    periode_ans = round(a ** 1.5, 2)
                    periode_str = f"{periode_ans} ans"
                    periode_jours = periode_ans * 365.25
                else:
                    periode_ans   = None
                    periode_str   = "Non périodique"
                    periode_jours = None

                # ── Dernier et prochain périhélie ──
                try:
                    t_last = datetime(yr, mo, max(1, int(dy)))
                    days_since = (now - t_last).days

                    if days_since >= 0:
                        # Le passage enregistré est passé
                        dernier_str = f"{t_last.strftime('%Y-%m-%d')} (il y a {days_since}j)"
                        if periode_jours:
                            # Calculer le prochain passage en ajoutant N périodes
                            n_periods = math.ceil(days_since / periode_jours)
                            t_next = t_last + timedelta(days=n_periods * periode_jours)
                            days_to_next = (t_next - now).days
                            prochain_str = f"{t_next.strftime('%Y-%m-%d')} (dans {days_to_next}j)"
                        else:
                            prochain_str = "N/A (non périodique)"
                    else:
                        # Le passage enregistré est dans le futur = c'est déjà le prochain
                        days_to = abs(days_since)
                        prochain_str = f"{t_last.strftime('%Y-%m-%d')} (dans {days_to}j)"
                        if periode_jours:
                            t_prev = t_last - timedelta(days=periode_jours)
                            days_prev = (now - t_prev).days
                            dernier_str = f"{t_prev.strftime('%Y-%m-%d')} (il y a {days_prev}j)"
                        else:
                            dernier_str = "N/A"
                except Exception:
                    dernier_str  = f"{yr}-{mo:02d}-{int(dy):02d}"
                    prochain_str = "?"

                # ── Magnitude au prochain périhélie (formule cométaire standard corrigée) ──
                # m = g + 5·log10(Δ) + k·log10(r)
                # Au périhélie : r = q, Δ ≈ |q - 1| si q > 1, sinon Δ ≈ 1 - q
                # Eviter log(0) : Δ minimum = 0.1 UA
                r_peri  = max(0.01, q)
                delta_p = max(0.1, abs(q - 1.0))
                mag_peri = round(g + 5*math.log10(delta_p) + k*math.log10(r_peri), 1)
                # Clamp : magnitude physiquement impossible en dehors de -10..25
                mag_peri = max(-10.0, min(25.0, mag_peri))
                v_sc, v_lb = vespera_score(mag_peri)

                rows.append({
                    "Nom":           nom[:60],
                    "Dernier peri.": dernier_str,
                    "Prochain peri.":prochain_str,
                    "Période":       periode_str,
                    "q (UA)":        round(q, 4),
                    "e":             round(e, 5),
                    "i (°)":         round(i, 2),
                    "g":             round(g, 1),
                    "k":             round(k, 1),
                    "Mag.@peri":     mag_peri,
                    "Mag.actuelle":  "?",
                    "Élong. (°)":    "?",
                    "Observable ?":  "?",
                    "Vespera@peri":  v_sc,
                    "Obs.@peri":     v_lb,
                    "Vespera act.":  "?",
                    "Obs. actuelle": "?",
                })
            except (ValueError, IndexError):
                continue
    except Exception:
        return st.session_state.comet_cache.copy()

    if not rows:
        return st.session_state.comet_cache.copy()

    df = pd.DataFrame(rows)

    # ── Enrichissement Horizons (parallèle, comètes brillantes seulement) ──
    HORIZONS    = "https://ssd.jpl.nasa.gov/api/horizons.api"
    today_str   = now.strftime("%Y-%m-%d")
    tomorrow_str= (now + timedelta(days=1)).strftime("%Y-%m-%d")

    def _horizons_query(idx_nom):
        idx, nom_comet = idx_nom
        # Format attendu Horizons : "C/2024 G3" ou "P/2023 A1" etc.
        m_des = re.match(r'^([CP]/\d{4}\s+\w+)', nom_comet)
        if not m_des:
            return idx, None
        des_short = m_des.group(1).strip()
        try:
            params_h = {
                "format":     "json",
                "COMMAND":    f"'{des_short}'",
                "EPHEM_TYPE": "OBSERVER",
                "CENTER":     "500@399",
                "START_TIME": today_str,
                "STOP_TIME":  tomorrow_str,
                "STEP_SIZE":  "1d",
                "QUANTITIES": "9,23",  # V magnitude + elongation
            }
            rh = requests.get(HORIZONS, params=params_h, timeout=6)
            txt = rh.text
            if "$$SOE" in txt and "$$EOE" in txt:
                block  = txt[txt.index("$$SOE")+5 : txt.index("$$EOE")].strip()
                line_h = [l.strip() for l in block.split('\n') if l.strip()]
                if line_h:
                    p = line_h[0].split()
                    if len(p) >= 4:
                        v_act  = float(p[-2])
                        elong  = float(p[-1])
                        vs, vl = vespera_score(v_act)
                        obs    = "✅ Oui" if elong > 20 and v_act < 17.5 else \
                                 "🟡 Difficile" if elong > 15 and v_act < 19 else "❌ Non"
                        return idx, {"v": round(v_act,1), "e": round(elong,1), "obs": obs, "vs": vs, "vl": vl}
        except Exception:
            pass
        return idx, None

    bright = [(i, r["Nom"]) for i, r in df.iterrows()
              if pd.to_numeric(r.get("Mag.@peri", 99), errors='coerce') < 18]
    if bright:
        try:
            with ThreadPoolExecutor(max_workers=4) as ex:
                futures = {ex.submit(_horizons_query, ic): ic for ic in bright}
                for fut in as_completed(futures, timeout=12):
                    try:
                        idx, data = fut.result()
                        if data:
                            df.at[idx, "Mag.actuelle"]   = data["v"]
                            df.at[idx, "Élong. (°)"]     = data["e"]
                            df.at[idx, "Observable ?"]   = data["obs"]
                            df.at[idx, "Vespera act."]   = data["vs"]
                            df.at[idx, "Obs. actuelle"]  = data["vl"]
                    except Exception:
                        continue
        except FuturesTimeout:
            pass

    st.session_state.comet_cache    = df
    st.session_state.last_comet_req = now
    return df

    st.session_state.comet_cache = df
    st.session_state.last_comet_req = now
    return df

# ═══════════════════════════════════════════════════════════════════════════════
# PARSE SBDB
# ═══════════════════════════════════════════════════════════════════════════════
def parse_sbdb(res: dict) -> dict:
    obj  = res.get("object", {})
    orb  = res.get("orbit", {})
    phy  = res.get("phys_par", [])
    ca   = res.get("close_approach_data", [])
    elems = orb.get("elements", {})
    if isinstance(elems, list):
        elems = {e["name"]: e.get("value","?") for e in elems}
    if isinstance(phy, list):
        phy_d = {p["name"]: p.get("value") for p in phy if isinstance(p,dict) and "name" in p}
    else:
        phy_d = {k: (v.get("value") if isinstance(v,dict) else v) for k,v in phy.items()}
    def _p(k): return phy_d.get(k) or "N/A"
    return {
        "fullname":    obj.get("fullname","?"), "spkid": obj.get("spkid","?"),
        "neo":         "✅" if obj.get("neo") else "❌",
        "pha":         "⚠️ OUI" if obj.get("pha") else "non",
        "orbit_class": obj.get("orbit_class",{}).get("name","?"),
        "condition_code": orb.get("condition_code","?"),
        "first_obs":   orb.get("first_obs","?"), "soln_date": orb.get("soln_date","?"),
        "e": elems.get("e","?"), "a": elems.get("a","?"), "q": elems.get("q","?"),
        "i": elems.get("i","?"), "per_y": elems.get("per_y", orb.get("per_y","?")),
        "moid": orb.get("moid","?"),
        "H": _p("H"), "G": _p("G"), "albedo": _p("albedo"),
        "diameter": _p("diameter"), "density": _p("density"),
        "rot_per": _p("rot_per"), "spec_T": _p("spec_T"),
        "ps_cum": _p("ps_cum"), "ts_max": _p("ts_max"), "ca": ca,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        "<div style='text-align:center;padding:14px 0 6px'>"
        "<span style='font-family:var(--mono);font-size:1.4em;color:var(--accent);"
        "text-shadow:0 0 12px rgba(0,212,255,.6)'>DEEP SPACE</span><br>"
        "<span style='font-family:var(--ui);font-size:.68em;letter-spacing:4px;color:var(--muted)'>RADAR SYSTEM V27</span>"
        "</div>", unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sec">⏱ ACTUALISATION</div>', unsafe_allow_html=True)
    refresh_rate = st.slider("Rafraîchissement (s)", 30, 300, 60)
    st.markdown('<div class="sidebar-sec">🔭 CHAMP NASA CAD</div>', unsafe_allow_html=True)
    radius_ld    = st.slider("Rayon (Distance Lunaire)", 1, 2500, 500)
    horizon_days = st.slider("Horizon temporel (jours)", 1, 90, 30)
    st.markdown('<div class="sidebar-sec">🎛 FILTRES VESPERA (NASA + Comètes seulement)</div>', unsafe_allow_html=True)
    vespera_mode = st.toggle("Filtre Vespera II (magnitude)", value=False)
    mag_limit    = st.slider("Magnitude H max", 5.0, 30.0, 19.0)
    st.markdown(
        f"<div style='font-size:.72em;color:var(--muted);font-family:var(--body);line-height:1.6'>"
        f"⚠️ Ce filtre ne s'applique PAS aux anomalies NEOCP<br>"
        f"Sources : NASA Scout · JPL CAD · MPC Comètes<br>"
        f"Session : {st.session_state.last_refresh.strftime('%H:%M:%S')}</div>",
        unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# CHARGEMENT DONNÉES
# Stratégie : chargement en deux passes pour éviter la page noire
#   Passe 1 (rapide, bloquante)  : Scout + NASA CAD → affichage immédiat
#   Passe 2 (différée, légère)   : Comètes → chargées uniquement si tab actif
# ═══════════════════════════════════════════════════════════════════════════════

# Passe 1 : sources principales, toujours chargées
status_ph = st.empty()
status_ph.info("⏳ Connexion Scout NASA…")
df_scout = fetch_scout()

status_ph.info("⏳ Connexion NASA JPL CAD…")
df_nasa, timer_nasa = fetch_nasa_cad(radius_ld, horizon_days)

status_ph.empty()  # Effacer le message — la page s'affiche maintenant

# Comètes : chargées depuis le cache si dispo, sinon différé (pas bloquant)
df_comets = st.session_state.comet_cache.copy() if not st.session_state.comet_cache.empty else pd.DataFrame()

# Filtres Vespera UNIQUEMENT sur NASA et comètes — JAMAIS sur Scout/anomalies
if vespera_mode:
    if not df_nasa.empty and 'h' in df_nasa.columns:
        df_nasa = df_nasa[pd.to_numeric(df_nasa['h'], errors='coerce') <= mag_limit].copy()
    if not df_comets.empty and 'Mag. est.' in df_comets.columns:
        df_comets = df_comets[pd.to_numeric(df_comets['Mag. est.'], errors='coerce') <= mag_limit].copy()

# Séparer : anomalies (vrais candidats) vs déjà catalogués (bien connus, score NEO faible)
if not df_scout.empty and '_catalogued' in df_scout.columns:
    df_catalogued_scout = df_scout[df_scout['_catalogued']].copy()
    df_scout_anom       = df_scout[~df_scout['_catalogued']].copy()
    # Retirer la colonne interne des deux
    df_catalogued_scout.drop(columns=['_catalogued'], inplace=True, errors='ignore')
    df_scout_anom.drop(columns=['_catalogued'], inplace=True, errors='ignore')
else:
    df_catalogued_scout = pd.DataFrame()
    df_scout_anom       = df_scout.copy()
    if '_catalogued' in df_scout_anom.columns:
        df_scout_anom.drop(columns=['_catalogued'], inplace=True)

# Historique — synchronisé avec les objets actifs (anomalies uniquement)
if not df_scout_anom.empty:
    for r in df_scout_anom.itertuples():
        nm = r.Nom
        if nm not in st.session_state.obj_history:
            st.session_state.obj_history[nm] = []
        st.session_state.obj_history[nm].append({
            "T": datetime.now().strftime("%H:%M"), "S": r.Score,
            "H": r.H, "NObs": r.NObs, "Arc": getattr(r, "Arc (j)", 0),
            "Vmag": r.Vmag, "moid": getattr(r, "MOID (UA)", 99)
        })
        if len(st.session_state.obj_history[nm]) > 30:
            st.session_state.obj_history[nm].pop(0)

# Purger historique : ne garder que les objets actifs + reconnus (pas archivés)
active_noms = set(df_scout_anom['Nom'].tolist()) if not df_scout_anom.empty else set()
reconnus    = set(st.session_state.recognized_objects.keys())
keys_to_keep = (active_noms | reconnus) - st.session_state.archived
for k in list(st.session_state.obj_history.keys()):
    if k not in keys_to_keep:
        del st.session_state.obj_history[k]

# Détection transitions (objets disparus de Scout)
prev_noms = st.session_state.prev_noms
transitions = detect_transitions(prev_noms, active_noms, df_nasa)
st.session_state.prev_noms = active_noms

monitor_and_alert(df_scout_anom, df_nasa, transitions)
_process_discord_queue()

# ═══════════════════════════════════════════════════════════════════════════════
# HEADER + MÉTRIQUES
# ═══════════════════════════════════════════════════════════════════════════════
c1, c2 = st.columns([4, 1])
with c1:
    st.markdown(
        "<div style='padding:16px 0 6px;border-bottom:1px solid var(--border);margin-bottom:18px'>"
        "<div class='radar-logo'>🛰️ DEEP SPACE RADAR</div>"
        "<div class='radar-sub'>Surveillance NEOCP · Scout NASA · V27.0</div></div>",
        unsafe_allow_html=True)
with c2:
    st.markdown(
        f"<div style='display:flex;justify-content:flex-end;align-items:center;height:100%;padding-top:24px'>"
        f"<div class='sync-pill'><div class='sync-dot'></div>SCOUT+NASA {timer_nasa}s</div></div>",
        unsafe_allow_html=True)

n_anom = len(df_scout_anom)
n_crit = len(df_scout_anom[df_scout_anom['Score'] >= 80]) if not df_scout_anom.empty else 0
n_nasa = len(df_nasa) if not df_nasa.empty else 0
n_com  = len(df_comets) if not df_comets.empty else 0
n_rec  = len(st.session_state.recognized_objects)

st.markdown(f"""
<div class="metric-grid">
  <div class="metric-card w"><div class="metric-val">{n_anom}</div><div class="metric-label">Candidats Scout</div></div>
  <div class="metric-card {'w' if n_crit else 'g'}"><div class="metric-val">{n_crit}</div><div class="metric-label">Critiques ≥80</div></div>
  <div class="metric-card"><div class="metric-val">{n_nasa}</div><div class="metric-label">Objets NASA proches</div></div>
  <div class="metric-card g"><div class="metric-val">{n_com}</div><div class="metric-label">Comètes actives</div></div>
  <div class="metric-card c"><div class="metric-val">{n_rec}</div><div class="metric-label">Désignés (session)</div></div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# ONGLETS
# ═══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔭  SCOUT NEOCP",
    "🎯  DÉSIGNÉS NASA",
    "🚀  CATALOGUE NASA",
    "🌠  COMÈTES",
    "📘  LEXIQUE"
])

# ── TAB 1 : SCOUT ─────────────────────────────────────────────────────────────
with tab1:
    st.markdown('<div class="sec">Candidats NEO Actifs · NASA Scout (NEOCP)</div>', unsafe_allow_html=True)
    st.caption("Source : API NASA Scout — données riches · Filtre magnitude désactivé sur ce tableau")

    if not df_scout_anom.empty:
        disp = df_scout_anom.copy()
        disp['Tr.']  = disp.apply(lambda r: get_trend(r['Nom'], r['Score']), axis=1)
        disp['Rang'] = range(1, len(disp) + 1)
        cols = ["Rang","Nom","Type","H","Vmag","NObs","Arc (j)","MOID (UA)",
                "CA min (LD)","Score NEO","Score","Statut","Taille","Tr."]
        cols = [c for c in cols if c in disp.columns]
        st.dataframe(
            disp[cols].style.background_gradient(cmap="YlOrRd", subset=["Score"]),
            use_container_width=True, hide_index=True)
        st.caption(
            "H = mag absolue · Vmag = mag visuelle · NObs = observations · Arc = arc orbital (j) · "
            "MOID = dist min Terre-objet (UA) · CA min = dist min approche (LD) · "
            "Score NEO = probabilité d'être un NEO selon MPC (≠ dangerosité)")
    else:
        st.markdown('<div class="empty">// AUCUN CANDIDAT ACTIF — API SCOUT EN ATTENTE //</div>', unsafe_allow_html=True)

    # Objets catalogués (bien connus, faible intérêt)
    if not df_catalogued_scout.empty:
        with st.expander(f"📋 Objets bien connus / déjà catalogués ({len(df_catalogued_scout)}) — faible priorité"):
            st.caption("Score NEO faible + beaucoup d'observations + arc long → orbite bien connue, peu d'intérêt pour suivi")
            cols_cat = [c for c in ["Nom","Type","H","Vmag","NObs","Arc (j)","Score NEO","Score"] if c in df_catalogued_scout.columns]
            st.dataframe(df_catalogued_scout[cols_cat], use_container_width=True, hide_index=True)

    # Archivage manuel
    st.markdown("---")
    st.markdown('<div class="sec" style="color:var(--accent3)">🗃️ Archivage Manuel</div>', unsafe_allow_html=True)
    st.caption("Retire un objet de tous les tableaux ET de l'historique une fois étudié.")
    all_scout_noms = (df_scout_anom['Nom'].tolist() if not df_scout_anom.empty else []) + \
                     (df_catalogued_scout['Nom'].tolist() if not df_catalogued_scout.empty else [])
    col_sel, col_btn = st.columns([3, 1])
    with col_sel:
        to_archive = st.selectbox(
            "Objet à archiver :", ["— sélectionner —"] + sorted(all_scout_noms),
            key="archive_sel")
    with col_btn:
        if st.button("🗃️ Archiver", use_container_width=True, key="archive_btn"):
            if to_archive != "— sélectionner —":
                st.session_state.archived.add(to_archive)
                if to_archive in st.session_state.obj_history:
                    del st.session_state.obj_history[to_archive]
                st.rerun()

    if st.session_state.archived:
        with st.expander(f"📦 Objets archivés ({len(st.session_state.archived)})"):
            for a in sorted(st.session_state.archived):
                col_a, col_b = st.columns([3, 1])
                with col_a: st.text(a)
                with col_b:
                    if st.button("↩️ Restaurer", key=f"restore_{a}"):
                        st.session_state.archived.discard(a)
                        st.rerun()

# ── TAB 2 : DÉSIGNÉS ──────────────────────────────────────────────────────────
with tab2:
    st.markdown('<div class="sec">Objets Récemment Désignés · Transition NEOCP → NASA</div>', unsafe_allow_html=True)
    st.caption(
        "Ces objets étaient sur le NEOCP et ont reçu une désignation officielle. "
        "La correspondance est établie via : (1) query SBDB directe par tdes, "
        "(2) similarité H dans le CAD, (3) contexte temporel."
    )

    if st.session_state.recognized_objects:
        for tdes, info in sorted(st.session_state.recognized_objects.items(),
                                  key=lambda x: x[1].get("date",""), reverse=True):
            nom_off = info.get("nom_officiel", "?")
            meth    = info.get("methode", "?")
            det     = info.get("details", {})
            date    = info.get("date", "?")

            # Couleur selon méthode de détection
            border_color = "var(--green)" if "SBDB direct" in meth else \
                           "var(--accent3)" if "Correspondance H" in meth else "var(--muted)"

            det_html = "".join(
                f"<div class='trans-row'><span class='trans-k'>{k}</span><span>{v}</span></div>"
                for k, v in det.items()
            )

            # Lien JPL direct vers la désignation officielle
            sstr = nom_off.replace(" ", "%20")
            lien = f"https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr={sstr}"

            st.markdown(f"""
<div style="background:var(--surface);border:1px solid var(--border);border-left:4px solid {border_color};
     border-radius:10px;padding:14px 16px;margin-bottom:10px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <div>
      <span style="font-family:var(--mono);font-size:1.05em;color:var(--accent3)">{tdes}</span>
      <span style="color:var(--muted);margin:0 10px">→</span>
      <span style="font-family:var(--ui);font-size:1.1em;font-weight:700;color:var(--green)">{nom_off}</span>
    </div>
    <span style="font-size:.75em;color:var(--muted);font-family:var(--mono)">{date}</span>
  </div>
  <div style="font-size:.78em;color:var(--muted);margin-bottom:8px">🔬 Méthode : {meth}</div>
  {det_html}
  <div style="margin-top:10px">
    <a href="{lien}" target="_blank"
       style="color:var(--accent);font-family:var(--mono);font-size:.8em">
      → Fiche complète NASA JPL ↗
    </a>
  </div>
</div>""", unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="empty">// AUCUN OBJET DÉSIGNÉ CETTE SESSION<br>'
            'Les désignations apparaissent ici lorsqu\'un candidat Scout reçoit un nom officiel //</div>',
            unsafe_allow_html=True)

# ── TAB 3 : NASA CAD + LOOKUP ─────────────────────────────────────────────────
with tab3:
    st.markdown('<div class="sec">Objets à Approche Rapprochée · NASA JPL CAD</div>', unsafe_allow_html=True)
    if not df_nasa.empty:
        df_n = df_nasa.copy()
        df_n['H_n']       = pd.to_numeric(df_n.get('h', pd.Series(dtype=float)), errors='coerce')
        df_n['Mag. est.'] = df_n['H_n'].apply(lambda x: round(x+2.5,1) if pd.notna(x) else 99)
        df_n['Taille']    = df_n['H_n'].apply(lambda x: classify_size(x) if pd.notna(x) else "?")
        df_n['Vespera II']= df_n['Mag. est.'].apply(lambda m: f"{vespera_score(m)[0]} {vespera_score(m)[1]}")
        # Type : les désignations commençant par C/ ou P/ sont des comètes
        def _nasa_type(des):
            d = str(des)
            if d.startswith('C/') or d.startswith('P/'): return "🌠 Comète"
            if d.startswith('A/'): return "☄️ Astéroïde interstellaire"
            return "🪨 Astéroïde NEO"
        df_n['Type'] = df_n.get('des', pd.Series()).apply(_nasa_type)
        rename = {'des':'Désignation','cd':'Date approche','dist':'Dist (LD)','v_rel':'Vit km/s','h':'H'}
        cols_n = [c for c in ['des','Type','cd','dist','v_rel','H_n','Mag. est.','Taille','Vespera II','diameter'] if c in df_n.columns]
        df_show = df_n[cols_n].rename(columns={**rename,'H_n':'H','diameter':'Diam. km'})
        if 'Dist (LD)' in df_show.columns:
            df_show = df_show.sort_values('Dist (LD)')
        st.dataframe(df_show, use_container_width=True, hide_index=True)
        st.markdown("🔗 [Ouvrir NASA JPL SBDB Lookup](https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html)")
    else:
        st.markdown('<div class="empty">// CATALOGUE NASA VIDE — SYNC EN ATTENTE //</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div class="sec">🔍 Fiche Détaillée · NASA JPL SBDB</div>', unsafe_allow_html=True)
    ci, cb = st.columns([3, 1])
    with ci: lq = st.text_input("Désignation :", label_visibility="collapsed", placeholder="Ex : 2024 YR4 · Apophis · 99942")
    with cb: do_l = st.button("🔍 Rechercher", use_container_width=True)

    if do_l and lq.strip():
        with st.spinner("Interrogation NASA JPL SBDB…"):
            try:
                raw = requests.get(NASA_SBDB, params={"sstr": lq.strip(), "phys-par":"1",
                                                       "ca-data":"1", "ca-time":"both"}, timeout=20).json()
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
  <div class="jpl-f">Rot. <span class="jpl-v">{d['rot_per']} h</span></div>
  <div class="jpl-f">Type spectral <span class="jpl-v">{d['spec_T']}</span></div>
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
                        st.markdown("<div style='margin-top:10px;font-family:var(--ui);font-size:.82em;"
                                    "color:var(--accent3);letter-spacing:1px'>PROCHAINES APPROCHES</div>",
                                    unsafe_allow_html=True)
                        ca_df = pd.DataFrame(d['ca'][:8])
                        ca_c = [c for c in ['cd','dist','dist_min','dist_max','v_rel','t_sigma_f'] if c in ca_df.columns]
                        st.dataframe(ca_df[ca_c].rename(columns={'cd':'Date','dist':'LD','dist_min':'Min LD',
                                     'dist_max':'Max LD','v_rel':'Vit km/s','t_sigma_f':'Incert.'}),
                                     use_container_width=True, hide_index=True)
                    se = lq.strip().replace(" ","%20")
                    st.markdown(f"<a href='https://ssd.jpl.nasa.gov/tools/sbdb_lookup.html#/?sstr={se}' "
                                f"target='_blank' style='color:var(--accent);font-family:var(--mono);font-size:.8em'>"
                                f"→ Fiche complète JPL ↗</a>", unsafe_allow_html=True)
                elif "message" in raw:
                    st.warning(f"NASA JPL : {raw['message']}")
                else:
                    st.warning("Objet non trouvé.")
            except Exception as ex:
                st.error(f"Erreur JPL SBDB : {ex}")

# ── TAB 4 : COMÈTES ───────────────────────────────────────────────────────────
with tab4:
    st.markdown('<div class="sec">Comètes Actives · MPC + NASA Horizons</div>', unsafe_allow_html=True)
    st.info(
        "**Mag.actuelle** = magnitude réelle ce soir via NASA Horizons (comètes g<18 seulement) · "
        "**Élong.** = angle Soleil–comète vu depuis la Terre (>20° = observable) · "
        "**Mag.@peri** = proxy magnitude au périhélie ⚠️ approximatif · "
        "Scores Vespera : 100=trivial · 90=excellent · 70=bon (30min) · 45=limite · 15=difficile · 0=impossible"
    )

    comet_cache_ok = not st.session_state.comet_cache.empty

    if not comet_cache_ok:
        st.warning("⚠️ Données comètes non chargées au démarrage (évite le blocage initial).")
        if st.button("🌠 Charger les comètes", key="load_comets"):
            with st.spinner("Chargement MPC + Horizons (~15s)…"):
                st.session_state.comet_cache = pd.DataFrame()  # forcer rechargement
                result = fetch_comets()
                if not result.empty:
                    st.session_state.comet_cache = result
            st.rerun()
    else:
        comet_cache_age = (datetime.now() - st.session_state.last_comet_req).total_seconds()
        if comet_cache_age > 10800:
            if st.button("🔄 Rafraîchir les comètes", key="refresh_comets"):
                with st.spinner("Mise à jour MPC + Horizons…"):
                    st.session_state.comet_cache = pd.DataFrame()
                    result = fetch_comets()
                    if not result.empty:
                        st.session_state.comet_cache = result
                st.rerun()

        df_comets_show = st.session_state.comet_cache.copy()
        if not df_comets_show.empty:
            df_comets_show['_sort'] = pd.to_numeric(
                df_comets_show.get('Vespera act.', pd.Series(dtype=float)), errors='coerce'
            ).fillna(pd.to_numeric(
                df_comets_show.get('Vespera@peri', pd.Series(dtype=float)), errors='coerce'
            ).fillna(0))
            df_comets_show = df_comets_show.sort_values('_sort', ascending=False).drop(columns=['_sort'])
            cols_c = [c for c in [
                "Nom",
                "Dernier peri.", "Prochain peri.", "Période",
                "Mag.actuelle", "Élong. (°)", "Observable ?", "Vespera act.", "Obs. actuelle",
                "Mag.@peri", "Vespera@peri", "Obs.@peri",
                "g", "k", "q (UA)", "e", "i (°)"
            ] if c in df_comets_show.columns]
            st.dataframe(df_comets_show[cols_c], use_container_width=True, hide_index=True)
            st.caption(
                "Dernier peri. = dernier passage au périhélie · "
                "Prochain peri. = prochain passage calculé (Kepler) · "
                "Période = durée d'une révolution · "
                "Mag.actuelle via Horizons (comètes g<18) · "
                "Élong. >20° requis · g = mag absolue · k = pente · q = périhélie (UA)"
            )
        else:
            st.markdown('<div class="empty">// AUCUNE COMÈTE CHARGÉE //</div>', unsafe_allow_html=True)

# ── TAB 5 : LEXIQUE ───────────────────────────────────────────────────────────
with tab5:
    st.markdown('<div class="sec">Lexique & Ordres de Grandeur</div>', unsafe_allow_html=True)

    def lx(title, entries, color="#00d4ff"):
        rows = "".join(
            f"<div style='display:flex;gap:10px;padding:3px 0;border-bottom:1px solid rgba(255,255,255,.04);font-size:.8em'>"
            f"<span style='color:var(--muted);min-width:115px;font-family:var(--mono)'>{k}</span>"
            f"<span style='color:var(--text)'>{v}</span></div>"
            for k, v in entries
        )
        st.markdown(
            f"<div style='border-left:4px solid {color};padding:13px 15px;background:var(--surface);"
            f"border-radius:10px;border:1px solid var(--border);margin-bottom:5px'>"
            f"<div style='font-family:var(--ui);font-weight:700;font-size:.87em;letter-spacing:2px;"
            f"text-transform:uppercase;color:{color};margin-bottom:9px'>{title}</div>{rows}</div>",
            unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        lx("🛰️ Source : NASA Scout API", [
            ("URL",       "ssd-api.jpl.nasa.gov/scout.api (mode S = liste complète)"),
            ("Avantage",  "Données riches : Vmag, MOID, CA dist, score NEO MPC, elong, rate"),
            ("Transition","Quand un objet est désigné officiellement, il disparaît de Scout → signal propre"),
            ("Rate limit","60s minimum entre requêtes (partagé avec CAD)"),
        ])
        lx("📐 H · Magnitude Absolue", [
            ("H < 18",  "Géant >1 km — extinction de masse si impact"),
            ("H 18–22", "Régional 100m–1km — destruction d'une ville"),
            ("H 22–25", "Local 10–100m — cratère Barringer (1.2 km)"),
            ("H > 25",  "Mineur <10m — désintégration atmosphérique"),
        ])
        lx("🚨 Score de Dangerosité", [
            ("H×35",      "Taille (H<18 → max, H=25 → 0)"),
            ("Arc×25",    "Incertitude orbitale (arc<0.5j → max)"),
            ("NObs×20",   "Fraîcheur (<5 obs → max, découverte récente)"),
            ("MOID×10",   "Proximité orbitale Terre (MOID<0.01 UA → max)"),
            ("ScoreNEO×10","Probabilité d'être un NEO selon MPC"),
            ("Reset",     "Alerte réinitialisée si score retombe sous 50"),
        ], color="#ff4b4b")
        lx("🎯 Algorithme Détection Transition", [
            ("Méthode 1", "SBDB direct : query NASA par tdes → désignation officielle immédiate"),
            ("Méthode 2", "Similarité H ±0.5 dans NASA CAD → correspondance probable"),
            ("Méthode 3", "Disparu sans correspondance = non confirmé ou fausse détection"),
            ("Limite",    "Le renommage change toujours le tdes → méthode 1 est la plus fiable"),
            ("Confiance", "Méthode 1 = certaine · Méthode 2 = probable · Méthode 3 = inconnue"),
        ], color="#f7b731")

    with c2:
        lx("🔭 Score Vespera II", [
            ("Instrument",  "50mm f/5, Sony IMX585, stacking live"),
            ("100 trivial",  "Mag ≤ 10 — visible à l'œil nu"),
            ("90 excellent", "Mag ≤ 14.5 — session 10 min"),
            ("70 bon",       "Mag ≤ 16.0 — 30 min stacking"),
            ("45 limite",    "Mag ≤ 17.5 — nuit entière, ciel sombre"),
            ("15 difficile", "Mag ≤ 19.0 — conditions optimales"),
            ("0 impossible", "Mag > 19.0 — hors portée instrument"),
            ("⚠️",          "Mag estimée ≠ mag réelle (position, activité, LP)"),
        ], color="#f7b731")
        lx("📏 Distances & Vitesses", [
            ("1 LD",     "384 400 km = distance Terre–Lune"),
            ("MOID",     "Distance minimale orbitale Terre–objet (UA)"),
            ("CA min",   "Distance minimale d'approche dans la fenêtre (LD)"),
            ("v_inf",    "Vitesse à l'infini (km/s) — relative à la Terre"),
            ("Rate",     "Vitesse angulaire au ciel (\"/min) — utile pour l'observation"),
            ("Unc.",     "Incertitude de position (\" arc) — orbite mal contrainte si élevée"),
        ], color="#00ff88")
        lx("🌠 Paramètres Cométaires", [
            ("g",       "Magnitude absolue cométaire (typiq. 4–12)"),
            ("k",       "Pente d'évolution (standard ≈ 4, hyperactif > 10)"),
            ("q (UA)",  "Périhélie — < 1 UA = géocroisante"),
            ("e",       "Excentricité — ≥ 1 = orbite hyperbolique (comète interstellaire ?)"),
            ("i (°)",   "> 90° = orbite rétrograde"),
        ], color="#00ff88")
        lx("🔔 Alertes Discord", [
            ("🆕 Nouvel",  "Apparu dans Scout (une fois)"),
            ("🎯 Désigné", "Transition NEOCP→NASA détectée (méthode 1/2/3)"),
            ("👻 Disparu", "Retiré sans désignation (non confirmé)"),
            ("🔥 ≥50",    "Score franchit 50 (reset si redescend)"),
            ("🚨 ≥80",    "Score critique"),
            ("📊 Top 5",  "Changement de classement"),
            ("📊 Horaire","Bilan chaque heure"),
        ], color="#ff4b4b")

# ═══════════════════════════════════════════════════════════════════════════════
# BAS DE PAGE : SISMOGRAPHE + STATUT
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
cs, ci2 = st.columns([1.3, 1])

with cs:
    st.markdown('<div class="sec">📈 Sismographe de Score</div>', unsafe_allow_html=True)
    # Sismographe = UNIQUEMENT les objets encore dans obj_history (purgé automatiquement)
    hist_keys = sorted(st.session_state.obj_history.keys())
    if hist_keys:
        # Si la sélection précédente n'existe plus → forcer le premier élément
        prev_sismo = st.session_state.get("_sismo_prev", hist_keys[0])
        default_idx = hist_keys.index(prev_sismo) if prev_sismo in hist_keys else 0
        target = st.selectbox("Objet actif :", hist_keys, index=default_idx, key="sismo")
        st.session_state["_sismo_prev"] = target
        hdf = pd.DataFrame(st.session_state.obj_history[target]).set_index("T")
        st.line_chart(hdf[["S"]], color="#00d4ff")
        last = st.session_state.obj_history[target][-1]
        st.caption(f"Score={last['S']} | H={last.get('H','?')} | Vmag={last.get('Vmag','?')} | "
                   f"NObs={last.get('NObs','?')} | Arc={last.get('Arc','?')}j | MOID={last.get('moid','?')}")
    else:
        st.session_state["_sismo_prev"] = None
        st.markdown('<div class="empty">// PAS D\'OBJETS ACTIFS DANS L\'HISTORIQUE //</div>', unsafe_allow_html=True)

with ci2:
    st.markdown('<div class="sec">⏱ Statut Système</div>', unsafe_allow_html=True)
    elapsed = (datetime.now() - st.session_state.last_refresh).total_seconds()
    pct = min(100, int(elapsed / refresh_rate * 100))
    st.progress(pct, text=f"Prochain refresh dans {max(0, refresh_rate - int(elapsed))}s")
    st.markdown(
        f"<div style='font-family:var(--mono);font-size:.78em;color:var(--muted);margin-top:8px;line-height:2'>"
        f"🕐 {datetime.now().strftime('%H:%M:%S')} · 🔄 {refresh_rate}s<br>"
        f"🌍 {radius_ld} LD · 📅 {horizon_days}j<br>"
        f"🔭 Vespera {'ON H≤'+str(mag_limit) if vespera_mode else 'OFF (Scout non filtré)'}</div>",
        unsafe_allow_html=True)

    st.markdown('<div class="sec" style="margin-top:18px">🔔 Journal Discord</div>', unsafe_allow_html=True)
    if st.session_state.discord_log:
        rows = ""
        for ts, stat, prev in reversed(st.session_state.discord_log[-10:]):
            cls = "dc-ok" if "OK" in stat else ("dc-w" if "HTTP" in stat else "dc-err")
            rows += (f"<div class='dc-row'><span class='dc-ts'>{ts}</span>"
                     f"<span class='{cls}'>{stat}</span>"
                     f"<span class='dc-msg'>{prev[:45]}</span></div>")
        st.markdown(
            f"<div style='background:var(--surface);border:1px solid var(--border);"
            f"border-radius:8px;padding:10px 12px;max-height:160px;overflow-y:auto'>{rows}</div>",
            unsafe_allow_html=True)
    else:
        st.markdown("<div class='empty' style='font-size:.76em'>Aucune alerte cette session</div>",
                    unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# AUTO-REFRESH
# ═══════════════════════════════════════════════════════════════════════════════
time.sleep(refresh_rate)
st.rerun()
