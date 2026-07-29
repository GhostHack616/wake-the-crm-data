#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L'INTERDIT D'ÉCRAN, vérifié plutôt qu'annoncé.

Trois familles ne doivent jamais atteindre le tableau de bord, quel que soit
le build :

  1. tout ce qui touche au générateur du jeu de données — mécanisme, colonne,
     seuil, bloc. Cela se dit de vive voix, au moment choisi, jamais à l'écran.
  2. les antisèches d'oral : formulations préparées, réponses apprises.
  3. les notes internes de travail : brouillons, versions rejetées.

Le registre des erreurs, lui, est assumé : il montre ce qui a été corrigé.

Ce contrôle lit le fichier tel qu'il est dans le dépôt. Il ne dépend d'aucun
chemin absolu et se rejoue depuis n'importe quel checkout :

    python3 dashboard/build/verifie_ecran.py

Code de sortie 1 si une interdiction est violée — utilisable en intégration
continue.
"""
import os, re, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIBLES = [os.path.join(RACINE, "index.html")]

# Motifs interdits. Chacun porte la raison de son interdiction : un interdit
# sans raison finit par sauter au premier build pressé.
INTERDITS = [
    (r"\bevent_id\b",
     "nomme la colonne technique du jeu de données"),
    (r"corrig[ée]s?\s+(plant|du\s+g[ée]n[ée]rateur|dans\s+le\s+jeu)",
     "nomme le bloc de référence planté dans les données"),
    (r"\bplant[ée]e?s?\s+dans\s+(le\s+jeu|les\s+donn[ée]es)\b",
     "décrit le mécanisme du générateur"),
    (r"\bantis[èe]che",
     "une antisèche d'oral n'a rien à faire à l'écran"),
    (r"\b92\s?969\b",
     "le seuil du bloc de référence"),
    (r"\bbrouillon\s+(interne|de\s+travail)\b",
     "note interne de travail"),
]

# Ce qui doit AU CONTRAIRE être présent : le registre des erreurs est assumé.
ATTENDUS = [
    (r"var\s+PROC\s*=\s*\[", "le déroulé du Process"),
    (r'data-v="proc"', "l'onglet Process"),
]


def controle(chemin):
    if not os.path.exists(chemin):
        return ["fichier absent : " + chemin]
    txt = open(chemin, encoding="utf-8").read()
    fautes = []
    for motif, raison in INTERDITS:
        for m in re.finditer(motif, txt, re.I):
            ligne = txt.count("\n", 0, m.start()) + 1
            extrait = txt[max(0, m.start() - 45):m.end() + 45].replace("\n", " ")
            fautes.append("ligne %d — %s : %s\n        …%s…"
                          % (ligne, raison, m.group(0), extrait))
    for motif, quoi in ATTENDUS:
        if not re.search(motif, txt):
            fautes.append("manquant : " + quoi)
    return fautes


def main():
    total = 0
    for c in CIBLES:
        fautes = controle(c)
        nom = os.path.relpath(c, RACINE)
        if fautes:
            total += len(fautes)
            print("ECHEC  %s" % nom)
            for f in fautes:
                print("   !! " + f)
        else:
            print("OK     %s — aucune interdiction violée, %d motifs testés"
                  % (nom, len(INTERDITS)))
    if total:
        print("\n%d violation(s). Le tableau de bord ne doit pas être publié en l'état." % total)
        sys.exit(1)
    print("\nL'interdit d'écran tient.")


if __name__ == "__main__":
    main()
