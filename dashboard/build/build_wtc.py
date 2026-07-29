#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Construit le dataset du dashboard "Wake the CRM" a partir des 3 CSV bruts.
Sortie : wtc.json  (dataset unique consomme par le dashboard, aucun appel reseau)

Seuls le contenu et la date d'un evenement entrent dans le score. Aucun
identifiant technique n'est utilise comme signal, a aucune etape.
"""
import csv, json, re, os, unicodedata
from collections import defaultdict, Counter
from datetime import datetime, date

SRC = "/workspace/wake-the-crm-data"
OUT = "/tmp/claude-0/-home-user-RomainPro/b68d9eed-9ab6-5ca4-b9df-696bc9953de5/scratchpad/wtc.json"

# ---------------------------------------------------------------- dates (etape 1)
def parse_date(s):
    s = (s or "").strip()
    if not s: return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        try: return date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
        except: return None
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2})$", s)      # annee 2 chiffres -> MM/DD/YY
    if m:
        mm, dd, yy = int(m.group(1)), int(m.group(2)), 2000 + int(m.group(3))
        try: return date(yy, mm, dd)
        except: return None
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)      # annee 4 chiffres -> DD/MM/YYYY
    if m:
        dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try: return date(yy, mm, dd)
        except: return None
    return None

# ---------------------------------------------------------------- pays (etape 2)
COUNTRY = {
    "fr":"FR","france":"FR","fra":"FR","fr ":"FR",
    "de":"DE","germany":"DE","deutschland":"DE","allemagne":"DE",
    "es":"ES","spain":"ES","espana":"ES","espagne":"ES",
    "it":"IT","italy":"IT","italia":"IT","italie":"IT",
    "nl":"NL","netherlands":"NL","nederland":"NL","pays-bas":"NL",
    "be":"BE","belgium":"BE","belgique":"BE",
    "uk":"UK","gb":"UK","united kingdom":"UK","royaume-uni":"UK","england":"UK",
    "ch":"CH","switzerland":"CH","suisse":"CH",
    "pt":"PT","portugal":"PT",
}
def norm_country(s):
    k = unicodedata.normalize("NFKD", (s or "").strip().lower())
    k = "".join(c for c in k if not unicodedata.combining(c))
    return COUNTRY.get(k, k.upper()[:2] if k else "")

# ---------------------------------------------------------------- domaines (etape 3)
PUBLIC = {"gmail.com","yahoo.com","yahoo.fr","hotmail.com","hotmail.fr","outlook.com",
          "outlook.fr","free.fr","orange.fr","wanadoo.fr","laposte.net","icloud.com",
          "protonmail.com","gmx.de","web.de","live.com","msn.com","aol.com","sfr.fr"}
def norm_domain(d):
    d = (d or "").strip().lower()
    if not d: return ""
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    d = d.split("/")[0].split("?")[0].strip().strip(".")
    return d
def root(d):
    """racine = label significatif (sans TLD ni ccSLD)."""
    d = norm_domain(d)
    if not d: return ""
    p = d.split(".")
    if len(p) >= 3 and p[-2] in ("co","com","org","net","gov","ac") and len(p[-1]) == 2:
        return ".".join(p[-3:-2])
    return p[-2] if len(p) >= 2 else p[0]

# ---------------------------------------------------------------- noms (etape 4)
LEGAL = r"\b(sa|sas|sarl|sasu|eurl|gmbh|ag|ug|bv|nv|ltd|limited|llc|inc|plc|srl|spa|s\.p\.a|oy|ab|as|aps|kg|co|corp|company|group|groupe|holding|holdings|international|france|europe|deutschland|iberia|italia|benelux|uk)\b"
def norm_name(n):
    s = unicodedata.normalize("NFKD", (n or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(LEGAL, " ", s)
    return re.sub(r"\s+", "", s)

# ================================================================ chargement
accounts = list(csv.DictReader(open(os.path.join(SRC,"accounts.csv"), encoding="utf-8")))
contacts = list(csv.DictReader(open(os.path.join(SRC,"contacts.csv"), encoding="utf-8")))
events   = list(csv.DictReader(open(os.path.join(SRC,"events.csv"),   encoding="utf-8")))
print("accounts %d / contacts %d / events %d" % (len(accounts), len(contacts), len(events)))

# domaine email majoritaire par account (etape 5 : signal de rattachement)
mail_dom = defaultdict(Counter)
for c in contacts:
    aid = (c["account_id"] or "").strip()
    em  = (c["email"] or "").strip().lower()
    if not aid or "@" not in em: continue
    d = em.split("@")[-1].strip()
    if not d or d in PUBLIC: continue
    mail_dom[aid][root(d)] += 1

# ================================================================ entity resolution (union-find)
parent = {}
def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[ra] = rb

for a in accounts:
    aid = a["account_id"]
    find("A:" + aid)
    r = root(a["domain"])
    if r: union("A:" + aid, "D:" + r)
    n = norm_name(a["account_name"])
    if len(n) >= 4: union("A:" + aid, "N:" + n)
    md = mail_dom.get(aid)
    if md:
        top, cnt = md.most_common(1)[0]
        if top and cnt >= 2: union("A:" + aid, "D:" + top)   # >=2 pour ne pas fusionner sur un email isole

ent_of_acc = {}
members = defaultdict(list)
for a in accounts:
    aid = a["account_id"]
    e = find("A:" + aid)
    ent_of_acc[aid] = e
    members[e].append(a)
print("entites =", len(members))

# ================================================================ agregation entite
D0 = date(2026, 4, 23)
NDAYS = 91
RANK_SIZE = {"1-10":1,"11-50":2,"51-200":3,"201-500":4,"501-1000":5,"1001-5000":6,"5000+":7,"5001+":7}
STAGE_RANK = {"lost":0,"lead":1,"prospect":2,"opportunity":3,"customer":4,"churned":5}

ents = {}
for e, rows in members.items():
    # champ le plus renseigne / plus avance gagne (resolution de contradictions, etape 9)
    name = max((r["account_name"] for r in rows), key=lambda s: (len(s or "")))
    dom  = ""
    for r in rows:
        if norm_domain(r["domain"]): dom = norm_domain(r["domain"]); break
    ctry = Counter(norm_country(r["country"]) for r in rows if norm_country(r["country"])).most_common(1)
    size = Counter(r["employee_range"] for r in rows if r["employee_range"]).most_common(1)
    ind  = Counter(r["industry"] for r in rows if r["industry"]).most_common(1)
    stage = max((r["lifecycle_stage"] or "" for r in rows), key=lambda s: STAGE_RANK.get(s, -1))
    arr = 0.0
    for r in rows:
        try: arr = max(arr, float(r["arr_eur"] or 0))
        except: pass
    created = min([d for d in (parse_date(r["created_date"]) for r in rows) if d] or [D0])
    ents[e] = dict(
        id=e, name=name, dom=dom,
        ctry=(ctry[0][0] if ctry else ""), size=(size[0][0] if size else ""),
        ind=(ind[0][0] if ind else ""), stage=stage, arr=arr,
        dups=len(rows), accs=[r["account_id"] for r in rows], created=created.isoformat(),
    )

# contacts par entite
ent_contacts = defaultdict(list)
for c in contacts:
    aid = (c["account_id"] or "").strip()
    if aid in ent_of_acc:
        ent_contacts[ent_of_acc[aid]].append(c)

SENIOR = [
    (r"\b(chro|cpo|chief people|chief human)\b", 3),
    (r"\b(vp|vice president|head of|director|directeur|directrice)\b", 3),
    (r"\b(ceo|coo|cfo|cto|founder|fondateur|president|gerant|managing director)\b", 3),
    (r"\b(manager|responsable|lead)\b", 2),
    (r"\b(specialist|officer|partner|generalist|analyst|charge)\b", 1),
    (r"\b(intern|stagiaire|assistant|apprenti|trainee|junior)\b", 0),
]
def seniority(t):
    s = (t or "").lower()
    for rx, w in SENIOR:
        if re.search(rx, s): return w
    return 1

ctc_info = {}
for e, cs in ent_contacts.items():
    ctc_info[e] = {c["contact_id"]: dict(
        n=(c["first_name"] + " " + c["last_name"]).strip(),
        t=c["job_title"], sen=seniority(c["job_title"]),
        opt=(c["opted_out"] or "").strip().lower() == "true",
    ) for c in cs}
acc_ent = ent_of_acc

# ================================================================ events -> entites
HOT_PAGES = ("/pricing", "/demo", "/tarifs", "/contact", "/request", "/trial", "/comparison", "/vs-")
ev_by_ent = defaultdict(list)
anon = 0
for ev in events:
    ts = ev["timestamp"]
    try: d = (date(int(ts[0:4]), int(ts[5:7]), int(ts[8:10])) - D0).days
    except: continue
    if d < 0 or d >= NDAYS: continue
    aid = (ev["account_id"] or "").strip()
    e = acc_ent.get(aid)
    if not e:
        anon += 1
        continue
    ev_by_ent[e].append(dict(d=d, t=ev["event_type"], c=(ev["contact_id"] or "").strip(),
                             u=(ev["page_url"] or ""), cp=(ev["campaign"] or ""),
                             m=(ev["metadata"] or "")))
print("events rattaches a une entite :", sum(len(v) for v in ev_by_ent.values()), "/ orphelins :", anon)

# ================================================================ scoring v0 (config, pas code)
CONFIG = {
    "version": "v0-brouillon",
    "half_life_days": 14,
    "window_days": 30,
    "engagement": {
        "meeting_booked":     {"w": 40, "why": "demande explicite de temps commercial — le seul event où le prospect engage SA ressource"},
        "form_fill":          {"w": 25, "why": "action volontaire avec un coût (la saisie) — intention déclarée, pas subie"},
        "pricing_visit":      {"w": 18, "why": "visite /pricing ou /demo : étape d'évaluation, pas de découverte"},
        "email_click":        {"w": 8,  "why": "action volontaire mais coût nul, et cliquable par un scanner de sécurité"},
        "website_visit":      {"w": 4,  "why": "visite d'une page non commerciale — de la présence, pas de l'intention"},
        "linkedin_engagement":{"w": 3,  "why": "signal social : faible corrélation avec l'achat, forte corrélation avec le bruit"},
        "email_open":         {"w": 1,  "why": "quasi nul : un pixel déclenchable par un proxy, non attribuable à un humain"},
        "email_sent":         {"w": 0,  "why": "ZÉRO — c'est NOTRE action, pas la leur. Le piège classique du scoring naïf."}
    },
    "multipliers": {
        "senior_contact":     {"w": 1.6, "why": "un VP People qui bouge ne vaut pas un stagiaire qui bouge"},
        "multi_contact_7d":   {"w": 1.8, "why": "3 contacts distincts en 7 j = un comité d'achat qui se forme ; 1 contact × 3 = une personne curieuse"},
        "cluster_burst":      {"w": 1.3, "why": "densité temporelle : 5 events sur 3 jours ne dit pas la même chose que 5 events sur 60 jours"}
    },
    "negative": {
        "opted_out_actor":    {"w": "filtre", "why": "un contact opted_out qui « clique » n'est ni exploitable ni légal : ses events sortent du calcul, ils ne pénalisent pas. Tuer le compte entier ferait perdre ses autres contacts, eux valides."},
        "all_contacts_opted": {"w": -60,  "why": "plus personne à qui parler légalement — le compte est injoignable, quel que soit son signal"},
        "bounce_or_unsub":    {"w": -25,  "why": "signal négatif explicite dans les métadonnées (bounce, désinscription, plainte)"},
        "bot_pattern":        {"w": -80,  "why": "cadence machine (plus de 60 events dominés par des ouvertures) = crawler, pas humain"},
        "churned":            {"w": -20,  "why": "churné : c'est un cycle de win-back, pas un cycle d'achat neuf — autre séquence, autre owner"}
    },
    "fit": {
        "size_rank":          {"w": 6,  "why": "ICP HR-tech = 51 salariés minimum ; en dessous, le budget ATS n'existe pas"},
        "has_arr":            {"w": 10, "why": "client actif : upsell à cycle court, aucun risque de qualification"},
        "renewal_90d":        {"w": 12, "why": "fenêtre de renouvellement : le moment où la conversation est légitime sans prétexte"}
    },
    "thresholds": {"hot": 70, "warm": 35, "risk_pct_negative": 0}
}

HL = CONFIG["half_life_days"]
def decay(age): return 0.5 ** (age / HL)

TODAY = NDAYS - 1
scored = []
for e, meta in ents.items():
    evs = ev_by_ent.get(e, [])
    ci = ctc_info.get(e, {})
    n_ct = len(ci)
    opted = sum(1 for v in ci.values() if v["opt"])
    neutralised = []      # events retires du calcul (et pourquoi)


    # --- garde-fous negatifs (evalues AVANT l'engagement : ils invalident le signal)
    neg = []
    actors = Counter(x["c"] for x in evs if x["c"])
    ghost = [c for c in actors if c in ci and ci[c]["opt"]]
    n_ghost = sum(actors[c] for c in ghost)
    if ghost:
        neutralised.append(("opted_out_actor", n_ghost,
                    "%d contact(s) opted_out generent %d events -> retires du calcul" % (len(ghost), n_ghost)))
    if n_ct > 0 and opted == n_ct:
        neg.append(("all_contacts_opted", CONFIG["negative"]["all_contacts_opted"]["w"],
                    "%d/%d contacts opted_out" % (opted, n_ct)))
    bad = sum(1 for x in evs if re.search(r"bounce|unsub|complaint|spam", (x["m"] or "") + (x["u"] or ""), re.I))
    if bad:
        neg.append(("bounce_or_unsub", CONFIG["negative"]["bounce_or_unsub"]["w"], "%d event(s) negatifs" % bad))
    opens = sum(1 for x in evs if x["t"] == "email_open")
    if len(evs) >= 60 and opens >= 0.6 * len(evs):
        neg.append(("bot_pattern", CONFIG["negative"]["bot_pattern"]["w"],
                    "%d events dont %d opens (%.0f%%)" % (len(evs), opens, 100.0 * opens / max(1, len(evs)))))
    if meta["stage"] == "churned":
        neg.append(("churned", CONFIG["negative"]["churned"]["w"], "lifecycle_stage = churned"))

    # --- engagement decaye
    by_type = Counter()
    eng = 0.0
    ghost_set = set(ghost)
    for x in evs:
        if x["c"] and x["c"] in ghost_set: continue     # signal non exploitable : opt-out
        t = x["t"]
        if t == "website_visit" and any(h in x["u"].lower() for h in HOT_PAGES): t = "pricing_visit"
        w = CONFIG["engagement"].get(t, {}).get("w", 0)
        if not w:
            by_type[t] += 1
            continue
        pts = w * decay(TODAY - x["d"])
        eng += pts
        by_type[t] += 1

    # --- multiplicateurs
    mult = 1.0; mused = []
    recent = [x for x in evs if TODAY - x["d"] <= 7 and not (x["c"] and x["c"] in ghost_set)]
    distinct7 = len(set(x["c"] for x in recent if x["c"]))
    if distinct7 >= 3:
        mult *= CONFIG["multipliers"]["multi_contact_7d"]["w"]; mused.append(("multi_contact_7d", distinct7))
    sen = [c for c in set(x["c"] for x in recent if x["c"]) if ci.get(c, {}).get("sen", 0) >= 3]
    if sen:
        mult *= CONFIG["multipliers"]["senior_contact"]["w"]; mused.append(("senior_contact", len(sen)))
    if len(recent) >= 5:
        mult *= CONFIG["multipliers"]["cluster_burst"]["w"]; mused.append(("cluster_burst", len(recent)))

    # --- fit
    fit = 0.0; fused = []
    sr = RANK_SIZE.get(meta["size"], 0)
    if sr >= 3:
        v = CONFIG["fit"]["size_rank"]["w"] * (sr - 2); fit += v; fused.append(("size_rank", meta["size"], round(v, 1)))
    if meta["arr"] > 0:
        fit += CONFIG["fit"]["has_arr"]["w"]; fused.append(("has_arr", int(meta["arr"]), CONFIG["fit"]["has_arr"]["w"]))

    negsum = sum(w for _, w, _ in neg)
    score = max(0.0, eng * mult + fit + negsum)
    # "suspect" = piege avere (fantome / bot / injoignable), PAS un simple churned
    trap = [n for n in neg if n[0] in ("bot_pattern", "all_contacts_opted")]

    scored.append(dict(e=e, meta=meta, score=score, eng=eng, mult=mult, fit=fit, neg=neg, trap=trap,
                       neutralised=neutralised,
                       mused=mused, fused=fused, by_type=dict(by_type), nev=len(evs),
                       n_ct=n_ct, opted=opted, evs=evs, ci=ci))

scored.sort(key=lambda r: -r["score"])
hot  = [r for r in scored if r["score"] >= CONFIG["thresholds"]["hot"] and not r["trap"]]
warm = [r for r in scored if CONFIG["thresholds"]["warm"] <= r["score"] < CONFIG["thresholds"]["hot"] and not r["trap"]]
risk = sorted([r for r in scored if r["trap"]], key=lambda r: -(r["eng"] * r["mult"]))
print("hot %d / warm %d / suspects %d" % (len(hot), len(warm), len(risk)))

# ================================================================ export
idx = {}
E = []
for i, r in enumerate(scored):
    idx[r["e"]] = i
    m = r["meta"]
    E.append([m["name"], m["dom"], m["ctry"], m["size"], m["stage"],
              int(m["arr"]), round(r["score"], 1), r["nev"], r["n_ct"], m["dups"],
              3 if r["trap"] else (2 if r["score"] >= 70 else (1 if r["score"] >= 35 else 0))])

# stream : par jour, paires (idx entite, poids brut de l'event)
TW = {"meeting_booked":4, "form_fill":3, "pricing_visit":3, "email_click":2,
      "website_visit":1, "linkedin_engagement":1, "email_open":1, "email_sent":0}
stream = [[] for _ in range(NDAYS)]
for r in scored:
    i = idx[r["e"]]
    per = defaultdict(int)
    for x in r["evs"]:
        t = x["t"]
        if t == "website_visit" and any(h in x["u"].lower() for h in HOT_PAGES): t = "pricing_visit"
        per[x["d"]] = max(per[x["d"]], TW.get(t, 1))
    for d, w in per.items():
        stream[d].append(i); stream[d].append(w)

# detail complet pour les 40 premiers + les suspects (vue logique)
def detail(r):
    m = r["meta"]
    evs = sorted(r["evs"], key=lambda x: -x["d"])[:40]
    tl = [[x["d"], x["t"], (r["ci"].get(x["c"], {}) or {}).get("n", ""),
           (r["ci"].get(x["c"], {}) or {}).get("t", ""), x["u"] or x["cp"] or x["m"]] for x in evs]
    contribs = []
    # ordonne par POIDS decroissant : ce qui pese en haut, le bruit en bas
    for t, n in sorted(r["by_type"].items(),
                       key=lambda kv: (-CONFIG["engagement"].get(kv[0], {}).get("w", 0), -kv[1])):
        cfg = CONFIG["engagement"].get(t)
        if cfg: contribs.append([t, n, cfg["w"], cfg["why"]])
    return dict(
        name=m["name"], dom=m["dom"], ctry=m["ctry"], size=m["size"], ind=m["ind"],
        stage=m["stage"], arr=int(m["arr"]), dups=m["dups"], accs=m["accs"][:8],
        score=round(r["score"], 1), eng=round(r["eng"], 1), mult=round(r["mult"], 2),
        fit=round(r["fit"], 1), neg=[[k, w, d] for k, w, d in r["neg"]],
        mused=[[k, v] for k, v in r["mused"]], fused=r["fused"],
        contribs=contribs, nev=r["nev"], n_ct=r["n_ct"], opted=r["opted"], tl=tl,
        contacts=sorted([[v["n"], v["t"], v["sen"], v["opt"]] for v in r["ci"].values()],
                        key=lambda x: -x[2])[:12],
    )

DETAIL = {}
for r in scored[:40]: DETAIL[str(idx[r["e"]])] = detail(r)
for r in risk[:20]:   DETAIL[str(idx[r["e"]])] = detail(r)

steps = json.load(open("/tmp/claude-0/-home-user-RomainPro/b68d9eed-9ab6-5ca4-b9df-696bc9953de5/scratchpad/steps_all.json"))

# permutation deterministe : sur le globe, la position ne doit rien dire du score
perm = list(range(len(E)))
for i in range(len(perm) - 1, 0, -1):
    j = (i * 1103515245 + 12345) % (i + 1)
    perm[i], perm[j] = perm[j], perm[i]

# courbe de distribution : justifie le seuil par la rupture, pas par un chiffre rond
curve = [round(r["score"], 1) for r in scored[:400]]

out = dict(
    perm=perm, curve=curve,
    d0=D0.isoformat(), days=NDAYS,
    counts=dict(accounts=len(accounts), contacts=len(contacts), events=len(events),
                entities=len(ents), merged=len(accounts) - len(ents),
                anon_events=anon,
                hot=len(hot), warm=len(warm), risk=len(risk),
                dormant=sum(1 for r in scored if not r["evs"])),
    ents=E, stream=stream, detail=DETAIL, config=CONFIG,
    top=[idx[r["e"]] for r in hot[:25]],
    suspects=[idx[r["e"]] for r in risk[:15]],
    steps=steps,
)
json.dump(out, open(OUT, "w"), separators=(",", ":"), ensure_ascii=False)
print("ecrit", OUT, os.path.getsize(OUT) // 1024, "KB")
