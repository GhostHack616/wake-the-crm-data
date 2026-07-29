#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Le push Slack — la hot list arrive là où l'équipe travaille, pas dans un CSV qu'il faut ouvrir.

Lit  : dashboard_data/hot_list.csv + dashboard_data/companies.csv
Écrit: slack/digest.json (Block Kit, prêt à POSTer) + slack/digest.txt (relecture humaine)
Poste: seulement si SLACK_WEBHOOK_URL est dans l'environnement (jamais dans le repo).

    python3 slack/push_hot_list.py            # génère et affiche
    python3 slack/push_hot_list.py --post     # génère et envoie

Règle : chaque ligne porte sa preuve datée. Un compte sans preuve ne part pas.
"""
import csv, json, os, sys, urllib.request
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "dashboard_data")
OUT  = os.path.dirname(os.path.abspath(__file__))
DASH = "https://wake-the-crm.netlify.app"

MAX_T1 = 8          # ce qu'une personne lit vraiment dans Slack le matin
MAX_T2 = 3

PLAY = {"new_business":"nouvelle affaire","retention":"rétention","win_back":"reconquête",
        "risque":"risque","reactivation":"réactivation","nurture":"nurturing"}


def load():
    hot  = list(csv.DictReader(open(os.path.join(DATA,"hot_list.csv"), encoding="utf-8")))
    comp = {r["entity_id"]: r for r in csv.DictReader(open(os.path.join(DATA,"companies.csv"), encoding="utf-8"))}
    for r in hot:
        c = comp.get(r["entity_id"], {})
        r["_pays"] = c.get("country","") or "—"
        r["_arr"]  = c.get("arr_actif","") or ""
        r["_taille"] = c.get("employee_range","") or ""
    return hot


def euro(v):
    try:    n = int(float(v))
    except: return ""
    return format(n, ",d").replace(",", " ") + " €" if n > 0 else ""


def preuve(r):
    """La preuve telle que la donnée la soutient.

    `hot_list.preuve` écrit « membre le plus actif du comité » sur les 34 lignes Tier 2 —
    or 28 d'entre elles n'ont QU'UNE personne active. Le mot « comité » a une définition
    gravée (≥ 3 personnes distinctes, dont un décideur, sur 14 jours) : on ne l'imprime que
    lorsqu'elle est vérifiée. Sinon on dit ce qui s'est réellement passé.
    """
    n = int(r["comite_personnes_14j"] or 0)
    if "comit" not in r["preuve"]:
        return r["preuve"], True                # formulaire / RDV : preuve datée, on la garde telle quelle
    if n >= 3:
        return "comité actif : %d personnes en 14 j" % n, False
    return "%d personne%s active%s en 14 j, sans demande (score %s)" % (
           n, "s" if n > 1 else "", "s" if n > 1 else "", r["score"]), False


def ligne(r):
    """Une entreprise = une ligne actionnable : qui, sa preuve, par où, et le sens de l'appel."""
    bits = ["*%s*" % r["entreprise"]]
    ctx = " · ".join(x for x in (r["_pays"], r["_taille"], euro(r["_arr"])) if x)
    if ctx: bits.append("_%s_" % ctx)
    tete = "  ".join(bits)
    qui  = "%s — %s" % (r["qui_appeler"], r["son_titre"]) if r["son_titre"] else r["qui_appeler"]
    n = int(r["comite_personnes_14j"] or 0)
    txt, compter = preuve(r)
    meta = []
    if compter:                                  # la preuve ne dit pas déjà combien ils sont
        meta.append("%d personne%s active%s / 14 j" % (n, "s" if n > 1 else "", "s" if n > 1 else ""))
    meta += ["sponsor décideur %s" % ("✅" if r["sponsor_decideur"] == "oui" else "❌"), r["canal"]]
    if r["play"] and r["play"] != "new_business":
        meta.append(PLAY.get(r["play"], r["play"]))
    out = "%s\n> 📞 %s\n> 🔎 %s · %s" % (tete, qui, txt, " · ".join(meta))
    # un compte qui part ne s'appelle pas comme un compte qui arrive
    try:    neg = float(r["signaux_negatifs"] or 0)
    except: neg = 0.0
    if neg < 0:
        out += "\n> ⛔ *signaux de départ* (%.0f pts) · %s — appel de rétention, pas de prospection" % (
               neg, r["segment"].replace("_", " ").lower())
    return out


def sec(txt):
    return {"type":"section","text":{"type":"mrkdwn","text":txt}}


def build(hot):
    T1 = sorted([r for r in hot if r["tier"]=="T1"], key=lambda r:-float(r["score"]))
    T2 = sorted([r for r in hot if r["tier"]=="T2"], key=lambda r:-float(r["score"]))
    comite  = [r for r in T1 if r["porte"] == "comite"]
    convers = [r for r in T1 if r["porte"] != "comite"]
    mort    = [r for r in hot if r["canal"] != "email"]

    b = [
      {"type":"header","text":{"type":"plain_text","text":"☎️  La liste d'appels du jour","emoji":True}},
      {"type":"context","elements":[{"type":"mrkdwn",
        "text":"*%d comptes à travailler* sur 20 519 · Tier 1 : *%d* · Tier 2 : *%d* — chaque ligne porte sa preuve datée."
               % (len(hot), len(T1), len(T2))}]},
      {"type":"divider"},
      sec("*🔴  Tier 1 — ils ont levé la main*  ·  _%d comptes, les %d premiers_" % (len(convers), min(MAX_T1,len(convers)))),
    ]
    for r in convers[:MAX_T1]:
        b.append(sec(ligne(r)))
    if len(convers) > MAX_T1:
        b.append({"type":"context","elements":[{"type":"mrkdwn",
            "text":"…et *%d autres* en Tier 1 dans le tableau de bord." % (len(convers)-MAX_T1)}]})

    for r in comite:
        b += [{"type":"divider"},
              sec("*🟣  Personne n'a rien demandé — et c'est le plus urgent*\n" + ligne(r)),
              {"type":"context","elements":[{"type":"mrkdwn",
               "text":"Aucun formulaire, aucun RDV : son score est à *%s*. C'est le comité qui le sort — %s personnes "
                      "actives en 14 jours, dont un décideur. Un filtre sur le score ne l'aurait jamais vu."
                      % (r["score"], r["comite_personnes_14j"])}]}]

    if T2:
        b += [{"type":"divider"},
              sec("*🟠  Tier 2 — ça chauffe, sans demande*  ·  _%d comptes_" % len(T2))]
        for r in T2[:MAX_T2]:
            b.append(sec(ligne(r)))
        b.append({"type":"context","elements":[{"type":"mrkdwn",
            "text":"…et *%d autres*. À travailler en séquence, pas au téléphone." % max(0,len(T2)-MAX_T2)}]})

    if mort:
        c = Counter(r["canal"] for r in mort)
        b += [{"type":"divider"},
              sec("*⚠️  %d comptes injoignables par email*\n%s\nIls restent dans la liste : le canal est mort, "
                  "pas l'intérêt. Téléphone ou LinkedIn."
                  % (len(mort), "\n".join("• %s — *%d*" % (k, v) for k, v in c.most_common())))]

    b += [{"type":"divider"},
          {"type":"actions","elements":[{"type":"button","style":"primary",
            "text":{"type":"plain_text","text":"Ouvrir le tableau de bord","emoji":True},"url":DASH}]},
          {"type":"context","elements":[{"type":"mrkdwn",
            "text":"Généré depuis `dashboard_data/hot_list.csv` · scoring V1.1 · 2 portes (conversion ∪ comité 14 j)"}]}]
    return {"text":"La liste d'appels du jour — %d comptes (%d Tier 1)" % (len(hot),len(T1)), "blocks":b}


def apercu(payload):
    out=[]
    for bl in payload["blocks"]:
        t=bl.get("type")
        if t=="header":  out.append("\n=== %s ===" % bl["text"]["text"])
        elif t=="divider": out.append("-"*72)
        elif t=="section": out.append(bl["text"]["text"])
        elif t=="context": out.append("   " + " ".join(e["text"] for e in bl["elements"]))
        elif t=="actions": out.append("   [ %s ] -> %s" % (bl["elements"][0]["text"]["text"], bl["elements"][0]["url"]))
    return "\n".join(out).replace("*","")


def main():
    hot = load()
    payload = build(hot)
    json.dump(payload, open(os.path.join(OUT,"digest.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    txt = apercu(payload)
    open(os.path.join(OUT,"digest.txt"),"w",encoding="utf-8").write(txt+"\n")
    print(txt)
    print("\n%d blocs · digest.json + digest.txt écrits" % len(payload["blocks"]))
    if "--post" in sys.argv:
        url = os.environ.get("SLACK_WEBHOOK_URL")
        if not url:
            print("\n!! SLACK_WEBHOOK_URL absent de l'environnement — rien n'a été envoyé.")
            sys.exit(1)
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type":"application/json"})
        print("\nSlack :", urllib.request.urlopen(req, timeout=20).read().decode())


if __name__ == "__main__":
    main()
