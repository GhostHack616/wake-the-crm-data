#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNE SEULE VÉRITÉ PAR ÉCRAN.

Le tableau de bord classait 68 entités en « Suspect » : 66 sont des T3 dont le
play vaut « risque » — un compte à rappeler, pas un compte écarté — et les 9
vrais PERDUS (canal mort) n'apparaissaient nulle part : ni couleur, ni filtre,
ni détail. Le mot voulait dire l'inverse de ce qu'il désignait.

Ce passage dérive l'état de chaque entité d'UNE source, `dashboard_data.json` :

    tier T1    -> k=2      dans top[]
    tier T2    -> k=1
    tier PERDU -> k=3      dans perdus[] + un détail cliquable
    le reste   -> k=0

`play = risque` redevient ce qu'il est — une consigne d'appel affichée dans le
détail — et non une classe qui collide avec « écarté ».
"""
import json, os

def g17_ok(g, n): return g["SC17"]["attendu"] == n

W = "/tmp/claude-0/-home-user-RomainPro/b68d9eed-9ab6-5ca4-b9df-696bc9953de5/wtc/"
MOTEUR = "/workspace/wake-the-crm-data/dashboard_data/dashboard_data.json"

d = json.load(open(W + "wtc.json", encoding="utf-8"))
eng = json.load(open(MOTEUR, encoding="utf-8"))

ents, detail = d["ents"], d["detail"]
idx = {}
for i, e in enumerate(ents):
    idx.setdefault(e[0], i)

etat = {x["n"]: x for x in eng["tous_scores"]}          # nom -> {s, t}
K = {"T1": 2, "T2": 1, "PERDU": 3}
SEUIL_T2 = d["config"]["thresholds"]["warm"]

avant = {}
for e in ents:
    avant[e[10]] = avant.get(e[10], 0) + 1

# ---------- 1. un seul état par entité, dérivé du moteur ----------
inconnues = 0
for i, e in enumerate(ents):
    st = etat.get(e[0])
    if st is None:
        e[10] = 0                                       # jamais scorée : froide, point
        inconnues += 1
        continue
    e[10] = K.get(st["t"], 0)
    e[6] = round(st["s"], 1)

# ---------- 2. les 9 perdus deviennent visibles et cliquables ----------
gr = {c["e"]: c for c in eng["graphe"]["comptes"]}
ent_de_nom = {}
for c in eng["graphe"]["comptes"]:
    pass
# le bloc graphe est indexé par entity_id ; on retrouve le nom via tous_scores
nom_de_ent = {x["e"]: x["n"] for x in eng["tous_scores"]}

perdus = []
desaccords = []
for c in eng["graphe"]["comptes"]:
    if c["tier"] != "PERDU":
        continue
    nom = nom_de_ent.get(c["e"])
    i = idx.get(nom)
    if i is None:
        continue
    perdus.append(i)
    # Le moteur porte maintenant le tag lui-même (option C : la règle ne bouge pas,
    # le tag voyage dans les données). On l'affiche, on ne le re-déduit pas — mais
    # on vérifie qu'il dit la même chose que le score, sinon l'écran mentirait.
    vraie_perte = c["perte"] == "seche"
    if vraie_perte != (c["score"] >= SEUIL_T2):
        desaccords.append((nom, c["perte"], round(c["score"], 2)))
    detail[str(i)] = {
        "name": nom, "score": round(c["score"], 1), "brut": round(c["score"], 1),
        "tier": "PERDU", "porte": c.get("porte") or "", "play": c.get("play") or "",
        "segment": "PERTE SÈCHE" if vraie_perte else "CANAL MORT, COMPTE FROID", "fit": "—",
        "qui": "—", "titre": "aucun canal ouvert",
        "canal": "aucun — tous les cliqueurs désabonnés, aucun autre contact joignable",
        "preuve": ("perte sèche — score %.1f, au-dessus du seuil de travail (%s)"
                   % (c["score"], SEUIL_T2)) if vraie_perte else
                  ("canal mort sur un compte déjà froid — score %.1f, sous le seuil (%s) : rien n'a été perdu"
                   % (c["score"], SEUIL_T2)),
        "comite": str(len(c.get("personnes", []))), "sponsor": "—", "neg": c.get("neg", 0),
        "personnes": [[p["n"], "", p["p"], round(p["s"], 1), ""] for p in c.get("personnes", [])],
    }

d["perdus"] = sorted(perdus, key=lambda i: -ents[i][6])
d["suspects"] = d["perdus"]                              # l'ancien nom, gardé pour le rendu
d["counts"]["risk"] = len(perdus)

# ---------- 3. contrôles ----------
apres = {}
for e in ents:
    apres[e[10]] = apres.get(e[10], 0) + 1
print("répartition k  avant :", dict(sorted(avant.items())))
print("répartition k  après :", dict(sorted(apres.items())), " (0 froid · 1 T2 · 2 T1 · 3 perdu)")
print("entités jamais scorées, remises en froid :", inconnues)
print()
c = eng["compteurs"]
ok = True
for lbl, att, obt in (("Tier 1", c["tier1"], apres.get(2, 0)),
                      ("Tier 2", c["tier2"], apres.get(1, 0)),
                      ("perdus", c["perdus"], apres.get(3, 0)),
                      ("top[]", c["tier1"], len(d["top"])),
                      ("perdus[]", c["perdus"], len(d["perdus"])),
                      ("counts.risk", c["perdus"], d["counts"]["risk"])):
    bon = att == obt
    ok &= bon
    print("  %s %-12s moteur %-4s écran %-4s" % ("OK   " if bon else "ECHEC", lbl, att, obt))

sansdetail = [i for i, e in enumerate(ents) if e[10] in (1, 2, 3) and str(i) not in detail]
print("\n  %s toute entité colorée est cliquable — sans détail : %d"
      % ("OK   " if not sansdetail else "ECHEC", len(sansdetail)))
risque = [i for i, e in enumerate(ents) if str(i) in detail and detail[str(i)].get("play") == "risque"]
print("  info  comptes dont le play est « risque » : %d — affichés dans leur vrai tier, plus en « écarté »"
      % len(risque))

# contrôle croisé : son tag « perte » contre le score, indépendamment
seche = [i for i in perdus if detail[str(i)]["segment"].startswith("PERTE")]
froid = [i for i in perdus if not detail[str(i)]["segment"].startswith("PERTE")]
g16 = {x["id"]: x for x in eng["ops"]["gardes"]}
print("\n  %s tag « perte » du moteur == ma dérivation par le score — désaccords : %d %s"
      % ("OK   " if not desaccords else "ECHEC", len(desaccords), desaccords[:3]))
print("  %s pertes sèches : moteur %s (SC16) · écran %d"
      % ("OK   " if g16["SC16"]["attendu"] == len(seche) else "ECHEC", g16["SC16"]["attendu"], len(seche)))
print("  %s canaux morts froids : moteur %s (SC17) · écran %d"
      % ("OK   " if g17_ok(g16, len(froid)) else "ECHEC", g16["SC17"]["attendu"], len(froid)))

json.dump(d, open(W + "wtc.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("\nwtc.json réécrit : %.2f Mo" % (os.path.getsize(W + "wtc.json") / 1e6))
