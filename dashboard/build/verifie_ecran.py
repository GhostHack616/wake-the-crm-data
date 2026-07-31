#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L'INTERDIT D'ÉCRAN, vérifié plutôt qu'annoncé.

Ce qui ne doit jamais atteindre le tableau de bord :

  1. la CLÉ qui permet d'extraire la vérité terrain du jeu de données : le
     numéro seuil, la colonne technique, la plage d'identifiants. Le fait
     qu'elle existe est assumé à l'écran (voir plus bas) ; la clé pour la
     reconstituer n'a pas à être distribuée.
  2. les notes internes de travail : brouillons, versions rejetées, jargon de
     chantier.

CE QUI EST AU CONTRAIRE ASSUMÉ, décidé par Romain le 30/07 :

  - Le registre des erreurs. Il montre ce qui a été corrigé, et c'est le
    critère « alertes-tu toi-même sur où ça casse » du barème.
  - Le fait d'avoir trouvé la trace de la vérité terrain, et l'ordre dans
    lequel les choses ont été faites. L'énoncé de Gab écrit lui-même que les
    comptes chauds « ont ete plantes dans les donnees » : le cacher serait
    protéger un secret que l'auteur du sujet annonce dans son propre brief.
  - Les formulations préparées pour l'oral. La vue Process EST le support de
    présentation : les phrases qu'elle porte sont faites pour être dites.

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
    # event_id est interdit EN PHRASE, pas comme intitulé de colonne. La table
    # des événements est publiée telle quelle : son en-tête affiche déjà
    # « event_id » à l'exécution. Interdire le mot jusque dans le dictionnaire
    # qui explique chaque colonne laisserait la seule colonne technique sans
    # explication, ce qui la désigne au lieu de la banaliser. Ce qui reste
    # interdit, et qui est la vraie clé, c'est le numéro seuil : il a sa propre
    # ligne ci-dessous et elle ne bouge pas.
    (r"\bevent_id\b(?!\"\s*:)",
     "nomme la colonne technique du jeu de données dans une phrase"),
    (r"\bantis[èe]che",
     "le mot lui-même n'a rien à faire à l'écran, même si la préparation est assumée"),
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
