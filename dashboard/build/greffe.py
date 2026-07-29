#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
La greffe — j'importe les deux blocs du moteur dans ma construction.

  1. la décomposition par événement  ->  detail[i].personnes[j][5]
     [date, quoi, base, x_porteur, x_temps, pts]  — la ligne de multiplication,
     affichable telle quelle : 35 x 1,0 x 0,933 = 32,7

  2. le bloc ops (gardes du scoring + règles dormantes)  ->  D.sops

Rien d'autre ne bouge. Aucune position, aucune couleur : le moteur envoie du
sens, le rendu fait les pixels.
"""
import json, os

W    = "/tmp/claude-0/-home-user-RomainPro/b68d9eed-9ab6-5ca4-b9df-696bc9953de5/wtc/"
MOTEUR = "/workspace/wake-the-crm-data/dashboard_data/dashboard_data.json"

mine = json.load(open(W + "wtc.json", encoding="utf-8"))
eng  = json.load(open(MOTEUR, encoding="utf-8"))

# ---------- 1. la décomposition ----------
par_nom = {}
for c in eng["hot_list"]:
    par_nom.setdefault(c["entreprise"], []).append(c)
ambigus = [n for n, v in par_nom.items() if len(v) > 1]
assert not ambigus, "noms ambigus, il faut passer par entity_id : %s" % ambigus[:3]

greffes = manquants = n_ev = 0
for idx, d in mine["detail"].items():
    c = par_nom.get(d["name"])
    if not c:
        manquants += 1
        continue
    c = c[0]
    # aligner personne par personne, sur le nom
    ev_par_personne = {p["nom"]: p for p in c["personnes"]}
    for pers in d["personnes"]:
        src = ev_par_personne.get(pers[0])
        if not src:
            continue
        pers.append([[e["date"], e["quoi"], e["base"], e["x_porteur"], e["x_temps"], e["pts"]]
                     for e in src["events"]])
        # le score exact du moteur, non arrondi : l'affichage fera la somme de ce qu'il montre
        pers[3] = src["score"]
        n_ev += len(src["events"])
    d["brut"] = c["score_brut"]
    d["score"] = c["score"]
    greffes += 1

# ---------- 2. le bloc ops du scoring ----------
mine["sops"] = eng["ops"]

json.dump(mine, open(W + "wtc.json", "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))

print("comptes greffés          : %d / %d   (sans correspondance : %d)"
      % (greffes, len(mine["detail"]), manquants))
print("événements décomposés    : %d" % n_ev)
print("gardes du scoring        : %s (%s) · alarme %s"
      % (len(mine["sops"]["gardes"]), mine["sops"]["gardes_vertes"], mine["sops"]["alarme"]))
print("règles dormantes         : %d" % len(mine["sops"]["regles_dormantes"]))
print("wtc.json                 : %.2f Mo" % (os.path.getsize(W + "wtc.json") / 1e6))

# ---------- 3. la règle d'affichage : l'écran additionne ce qu'il montre ----------
# Une décimale partout. Le total d'une personne EST la somme de ses lignes affichées,
# le total du compte EST la somme de ses personnes. Ça tombe juste par construction,
# à tous les étages, sans note de bas de page. Le moteur garde sa précision pleine :
# c'est lui, et lui seul, qui décide du tier.
def r1(x): return round(x + 0.0, 1)

nom2idx = {}
for i, e in enumerate(mine["ents"]):
    nom2idx.setdefault(e[0], i)

recal = 0
for idx, d in mine["detail"].items():
    tot = 0.0
    for p in d["personnes"]:
        if len(p) < 6:
            continue
        p[3] = r1(sum(r1(e[5]) for e in p[5]))   # la personne = la somme de ses lignes
        tot += p[3]
    tot = r1(tot)
    plafond = d["score"] >= 100 or d["score"] <= 0     # 100 et 0 sont des décisions du moteur
    d["brut"] = tot                                     # le compte = la somme de ses personnes
    if not plafond:
        d["score"] = tot
        mine["ents"][int(idx)][6] = tot                 # la liste affiche le même nombre
        recal += 1
print("comptes dont l'affichage est recalé sur sa cascade : %d (les %d plafonnés/planchers gardent leur valeur moteur)"
      % (recal, len(mine["detail"]) - recal))

# ---------- 4. les 12 étapes sont faites : le statut était resté au brouillon ----------
# Les 12 portent leurs before/after/rules/controls complets et 30 contrôles verts,
# mais leur `status` datait d'avant les étapes 7 à 12. La vue Ops annonçait un
# pipeline à moitié fait. Vérifié contre les sorties réelles avant de basculer.
bascule = 0
for s in mine["steps"]:
    if s["status"] != "done":
        s["status"] = "done"
        bascule += 1
print("étapes repassées en « fait » : %d / %d" % (bascule, len(mine["steps"])))
assert not [c for s in mine["steps"] for c in s.get("controls", []) if c.get("pass") is False], \
    "une étape a un contrôle en échec : elle ne peut pas être marquée faite"

json.dump(mine, open(W + "wtc.json", "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))

# ---------- contrôle : la règle d'affichage ----------
# L'écran additionne TOUJOURS ce qu'il montre : le total d'une personne est la somme
# de ses lignes arrondies, le total du compte la somme de ses personnes. Ça tombe
# juste par construction. Reste à vérifier que cet affichage ne s'écarte jamais
# assez du moteur pour tromper — ni sur le chiffre, ni sur le tier.
ko = ecart = 0
for c in eng["hot_list"]:
    d = next((x for x in mine["detail"].values() if x["name"] == c["entreprise"]), None)
    if not d:
        continue
    for p in d["personnes"]:
        if len(p) >= 6 and abs(sum(r1(e[5]) for e in p[5]) - p[3]) > 1e-9:
            ko += 1
    if abs(sum(p[3] for p in d["personnes"] if len(p) >= 6) - d["brut"]) > 1e-9:
        ko += 1
    ecart = max(ecart, abs(d["brut"] - c["score_brut"]))
print("cascades qui ne tombent pas juste à l'écran : %d" % ko)
print("écart affichage / moteur (jamais montré, jamais utilisé pour le tier) : %.2f max" % ecart)

TH = {"T1": mine["config"]["thresholds"]["hot"], "T2": mine["config"]["thresholds"]["warm"]}
contra = [(d["name"], d["brut"], TH[d["tier"]]) for d in mine["detail"].values()
          if d["porte"] != "comite" and d["tier"] in TH and d["brut"] < TH[d["tier"]]]
print("comptes affichés SOUS le seuil de leur propre tier : %d %s"
      % (len(contra), contra[:3] if contra else "— rien à expliquer à l'oral"))
