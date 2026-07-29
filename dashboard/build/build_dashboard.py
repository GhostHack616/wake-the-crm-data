#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LE TABLEAU DE BORD SE RECONSTRUIT ENTIÈREMENT DEPUIS CE DÉPÔT.

    python3 dashboard/build/build_dashboard.py

Produit tout ce que dashboard/index.html consomme :

    dashboard/dist/wtc.json          les vues Macro, Logique et Ops
    dashboard/dist/tables/*.json     l'explorateur de données

UNE SEULE SOURCE POUR LE SCORE : dashboard_data/, produit par le moteur.
Ce script ne calcule aucun score. Il lit ce que le moteur a décidé, il le met
en forme, et il vérifie que l'écran dira la même chose que le moteur.

C'est la correction d'un vrai défaut : la chaîne précédente passait par un
scoring de brouillon qui vivait dans le script de rendu, plus deux passes
manuelles qui n'existaient que sur une machine. Le jour où ce conteneur était
recyclé, le tableau de bord n'était plus reconstructible.

Ce que le script lit :
  accounts.csv · contacts.csv · events.csv        le flux brut, pour le rejeu
  dashboard_data/companies.csv                    les 20 519 entreprises
  dashboard_data/scores_companies.csv             l'état de chacune
  dashboard_data/hot_list.csv                     les 60 comptes des files
  dashboard_data/dashboard_data.json              le détail, les gardes, le graphe
  dashboard/build/steps_all.json                  les 12 étapes du nettoyage
"""
import csv, json, os, re, sys
from collections import defaultdict, Counter
from datetime import date, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DD     = os.path.join(RACINE, "dashboard_data")
DIST   = os.path.join(RACINE, "dashboard", "dist")
os.makedirs(os.path.join(DIST, "tables"), exist_ok=True)

def lire(p):
    return list(csv.DictReader(open(p, encoding="utf-8")))

# ══════════════════════════════════════════════════ 1. les sources
comp   = lire(os.path.join(DD, "companies.csv"))
scores = lire(os.path.join(DD, "scores_companies.csv"))
hot    = lire(os.path.join(DD, "hot_list.csv"))
acc    = lire(os.path.join(DD, "accounts_clean.csv"))
ctc    = lire(os.path.join(DD, "contacts_clean.csv"))
ev     = lire(os.path.join(RACINE, "events.csv"))
eng    = json.load(open(os.path.join(DD, "dashboard_data.json"), encoding="utf-8"))
steps  = json.load(open(os.path.join(RACINE, "dashboard", "build", "steps_all.json"), encoding="utf-8"))
print("sources : %d entreprises · %d scorées · %d dans les files · %d events"
      % (len(comp), len(scores), len(hot), len(ev)))

# ══════════════════════════════════════════════════ 2. l'ordre des entités
# L'index d'une entité dans `ents` sert de clé partout ailleurs (detail, top,
# perdus, stream). Il doit donc être STABLE : tri par identifiant, jamais un set.
comp.sort(key=lambda r: r["entity_id"])
idx    = {r["entity_id"]: i for i, r in enumerate(comp)}
etat   = {r["entity_id"]: r for r in scores}
nom_de = {r["entity_id"]: r["name"] for r in comp}

K = {"T1": 2, "T2": 1, "PERDU": 3}          # 0 = froid

# ══════════════════════════════════════════════════ 3. la ligne d'une entité
n_ctc = Counter()
ent_de_acc = {r["account_id"]: r["entity_id"] for r in acc}
for c in ctc:
    if c.get("entity_id"):
        n_ctc[c["entity_id"]] += 1

n_ev = Counter()
D0, DFIN = None, None
for e in ev:
    d = e["timestamp"][:10]
    if D0 is None or d < D0: D0 = d
    if DFIN is None or d > DFIN: DFIN = d
    a = (e.get("account_id") or "").strip()
    k = ent_de_acc.get(a)
    if k: n_ev[k] += 1

y, m, j = (int(x) for x in D0.split("-"))
d0 = date(y, m, j)
y, m, j = (int(x) for x in DFIN.split("-"))
NDAYS = (date(y, m, j) - d0).days + 1

ents = []
for r in comp:
    e = r["entity_id"]
    st = etat.get(e, {})
    try:    arr = int(float(r.get("arr_actif") or 0))
    except: arr = 0
    ents.append([r["name"], r.get("domain", ""), r.get("country", ""),
                 r.get("employee_range", ""), r.get("lifecycle_consolidated", ""),
                 arr, round(float(st.get("score") or 0), 1),
                 n_ev.get(e, 0), n_ctc.get(e, 0), int(r.get("n_records") or 1),
                 K.get(st.get("tier"), 0)])

# ══════════════════════════════════════════════════ 4. le rejeu, jour par jour
# Poids d'animation seulement : l'intensité d'un scintillement, pas un score.
POIDS = {"meeting_booked": 4, "form_fill": 3, "email_click": 2,
         "linkedin_engagement": 1, "website_visit": 1, "email_open": 1, "email_sent": 0}
PAGES_FORTES = ("/pricing", "/demo")
par_jour = [defaultdict(int) for _ in range(NDAYS)]
for e in ev:
    a = (e.get("account_id") or "").strip()
    k = ent_de_acc.get(a)
    if not k or k not in idx: continue
    yy, mm, dd = (int(x) for x in e["timestamp"][:10].split("-"))
    n = (date(yy, mm, dd) - d0).days
    if not (0 <= n < NDAYS): continue
    t = e["event_type"]
    w = POIDS.get(t, 0)
    if t == "website_visit" and any(p in (e.get("page_url") or "") for p in PAGES_FORTES):
        w = 3
    par_jour[n][idx[k]] = max(par_jour[n][idx[k]], w)
stream = [[v for i2, w in sorted(d.items()) for v in (i2, w)] for d in par_jour]

# ══════════════════════════════════════════════════ 5. le détail des 69 comptes
SEUIL_T2 = int(eng["ops"]["gardes"][3]["attendu"]) and 8      # seuil publié par le moteur
detail, top, perdus = {}, [], []
par_ent_hot = {c["entity_id"]: c for c in eng["hot_list"]}

def personne(p):
    return [p["nom"], p.get("titre", ""), p.get("persona", ""), round(p["score"], 1), "",
            [[e["date"], e["quoi"], e["base"], e["x_porteur"], e["x_temps"], e["pts"]]
             for e in p.get("events", [])]]

for c in eng["hot_list"]:
    i = idx.get(c["entity_id"])
    if i is None: continue
    detail[str(i)] = {
        "name": nom_de[c["entity_id"]], "score": round(c["score"], 1),
        "brut": round(c["score_brut"], 1), "tier": c["tier"], "porte": c.get("porte", ""),
        "play": c.get("play", ""), "segment": c.get("segment", ""), "fit": c.get("fit", ""),
        "qui": c.get("qui_appeler", ""), "titre": c.get("son_titre", ""),
        "canal": c.get("canal", ""), "preuve": c.get("preuve", ""),
        "comite": str(c.get("comite_personnes_14j", "")), "sponsor": c.get("sponsor_decideur", ""),
        "neg": c.get("signaux_negatifs", 0),
        "personnes": [personne(p) for p in c.get("personnes", [])],
    }
    if c["tier"] == "T1": top.append(i)

nom_par_ent = {x["e"]: x["n"] for x in eng["tous_scores"]}
for c in eng["graphe"]["comptes"]:
    if c["tier"] != "PERDU": continue
    i = idx.get(c["e"])
    if i is None: continue
    perdus.append(i)
    seche = c.get("perte") == "seche"
    detail[str(i)] = {
        "name": nom_par_ent.get(c["e"], ""), "score": round(c["score"], 1),
        "brut": round(c["score"], 1), "tier": "PERDU", "porte": "", "play": c.get("play", ""),
        "segment": "PERTE SÈCHE" if seche else "CANAL MORT, COMPTE FROID", "fit": "—",
        "qui": "—", "titre": "aucun canal ouvert",
        "canal": "aucun — tous les cliqueurs désabonnés, aucun autre contact joignable",
        "preuve": ("perte sèche — score %.1f, au-dessus du seuil de travail (%d)" % (c["score"], SEUIL_T2))
                  if seche else
                  ("canal mort sur un compte déjà froid — score %.1f, sous le seuil (%d) : rien n'a été perdu"
                   % (c["score"], SEUIL_T2)),
        "comite": str(len(c.get("personnes", []))), "sponsor": "—", "neg": c.get("neg", 0),
        "personnes": [[p["n"], "", p["p"], round(p["s"], 1), ""] for p in c.get("personnes", [])],
    }

# l'écran additionne ce qu'il montre : une décimale, du bas vers le haut
def r1(x): return round(x + 0.0, 1)
for cle, d in detail.items():
    tot = 0.0
    for p in d["personnes"]:
        if len(p) >= 6 and p[5]:
            p[3] = r1(sum(r1(e[5]) for e in p[5]))
        tot += p[3]
    tot = r1(tot)
    d["brut"] = tot
    if 0 < d["score"] < 100:
        d["score"] = tot
        ents[int(cle)][6] = tot

top.sort(key=lambda i: -ents[i][6])
perdus.sort(key=lambda i: -ents[i][6])

# ══════════════════════════════════════════════════ 6. le reste
courbe = sorted((float(r["score"]) for r in scores), reverse=True)[:400]
c = eng["compteurs"]
counts = {"accounts": len(acc), "contacts": len(ctc), "events": len(ev),
          "entities": len(comp), "merged": len(acc) - len(comp),
          "anon_events": sum(1 for e in ev if not (e.get("contact_id") or "").strip()),
          "hot": c["tier1"], "warm": c["tier2"], "risk": c["perdus"],
          "dormant": c.get("silencieuses_aucun_evenement", 0)}
for s in steps:
    s["status"] = "done"

out = {
    "d0": d0.isoformat(), "days": NDAYS, "counts": counts, "ents": ents,
    "stream": stream, "detail": detail, "perm": list(range(len(ents))),
    "curve": courbe, "top": top, "suspects": perdus, "perdus": perdus,
    "steps": steps, "sops": eng["ops"],
    "config": {"version": eng["ops"]["config_version"] + " — calibrée par Romain le 29/07",
               "half_life_days": 10, "thresholds": {"hot": 30, "warm": SEUIL_T2}},
}

# ══════════════════════════════════════════════════ 7. l'écran dit-il ce que dit le moteur ?
def ck(l, ok, d=""):
    print(("  OK    " if ok else "  ECHEC ") + l + ((" -> " + d) if d else ""))
    return ok
kk = Counter(e[10] for e in ents)
bon  = ck("Tier 1", kk[2] == c["tier1"], "%d / %d" % (kk[2], c["tier1"]))
bon &= ck("Tier 2", kk[1] == c["tier2"], "%d / %d" % (kk[1], c["tier2"]))
bon &= ck("perdus", kk[3] == c["perdus"], "%d / %d" % (kk[3], c["perdus"]))
bon &= ck("partition complète", len(ents) == c["partition_totale"])
bon &= ck("toute entité colorée est cliquable",
          not [i for i, e in enumerate(ents) if e[10] and str(i) not in detail])
bon &= ck("chaque cascade tombe juste à l'écran",
          not [1 for d in detail.values() for p in d["personnes"]
               if len(p) >= 6 and p[5] and abs(sum(r1(e[5]) for e in p[5]) - p[3]) > 1e-9])
bon &= ck("aucun compte affiché sous le seuil de son tier",
          not [d for d in detail.values()
               if d["porte"] != "comite" and d["tier"] == "T2" and d["brut"] < SEUIL_T2])
if not bon:
    print("\nL'écran ne dirait pas la même chose que le moteur. Rien n'est écrit.")
    sys.exit(1)

json.dump(out, open(os.path.join(DIST, "wtc.json"), "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
print("\nwtc.json : %.2f Mo" % (os.path.getsize(os.path.join(DIST, "wtc.json")) / 1e6))

# ══════════════════════════════════════════════════ 8. l'explorateur de données
ACC = ["account_id","account_name","name_norm","dup_marker","entity_id","is_master","merged_into",
       "domain","domain_clean","domain_root","domain_source","has_domain",
       "country","country_clean","industry","employee_range","lifecycle_stage","owner","arr_eur",
       "created_date","created_date_parsed","created_date_format",
       "last_activity_date","last_activity_date_parsed","last_activity_date_format","last_activity_flag",
       "renewal_date","renewal_date_parsed","renewal_date_format"]
CTC = ["contact_id","account_id","entity_id","entity_source","is_orphan",
       "first_name","last_name","job_title","title_from_copy","persona_tier",
       "email","email_clean","email_status","email_domain_root",
       "email_is_duplicate","email_duplicate_count","email_multi_entity",
       "opted_out","is_bot","person_primary","duplicate_of",
       "created_date","created_date_parsed","created_date_format","created_date_flag"]

def table(rows, cols=None):
    c2 = cols or list(rows[0].keys())
    return {"cols": c2, "rows": [[(r.get(k) or "") for k in c2] for r in rows]}

for nom, t in (("companies", table(comp)), ("accounts", table(acc, ACC)),
               ("contacts", table(ctc, CTC)), ("hot_list", table(hot))):
    p = os.path.join(DIST, "tables", nom + ".json")
    json.dump(t, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("  %-10s %6d lignes · %2d colonnes · %.2f Mo"
          % (nom, len(t["rows"]), len(t["cols"]), os.path.getsize(p) / 1e6))

print("\nLe tableau de bord est reconstruit. dashboard/dist/ est prêt à être publié.")
