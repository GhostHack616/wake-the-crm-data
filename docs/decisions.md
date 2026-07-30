# Comment les décisions ont été prises

Exercice « Wake the CRM » : un CRM de 30 000 fiches laissé huit ans sans entretien —
à nettoyer, reconstruire, scorer, et transformer en liste d'appels.

Ce fichier documente une seule chose : **qui a décidé quoi, et où le vérifier**.
Chaque citation est copiée telle quelle depuis les fichiers de configuration — elle y vit encore.

---

## 1. Les arbitrages

Le dispositif proposait ; une personne tranchait. Ces cinq décisions ont fait le projet —
chacune a été tranchée **contre** une proposition sur la table.

| La proposition sur la table | La décision | Où la vérifier |
|---|---|---|
| Pénaliser les contacts désabonnés | **Non.** Un opt-out interdit d'écrire, il ne dit pas « fermé à l'offre » : le score reste, le canal devient téléphone/LinkedIn | `scoring_config.yaml` — « Le désabonnement ne touche JAMAIS le score (piège n°7) » |
| Compter la consultation de facture comme un signal de départ | **Non** — « consulter sa facture ≠ partir » : `/billing` pèse 0, seules les pages de résiliation et d'export sont négatives | `scoring_config.yaml`, bloc `pages` (acté 28/07) |
| Écarter des secteurs entiers du ciblage | **Non** — le produit est RH, tout le monde a des RH : le fit **ordonne** la file, il ne **bloque** jamais l'entrée | `scoring_config.yaml`, bloc `fit` — « ORDONNE la file, ne bloque JAMAIS » |
| Appeler le décideur de l'organigramme | **Non** — on rappelle **celui qui a levé la main** ; le décideur s'identifie pendant l'appel, il est dans la fiche | `scoring/run_scoring.py`, calcul de `qui_appeler` — affiché carte « La liste d'appels » |
| Un écart large entre décideur et utilisateur | **Resserré** — « l'écart me paraissait grand » : ×1 / ×0,8 / ×0,6 — et un trou de données n'est pas puni (×0,5) | `scoring_config.yaml`, bloc `multiplicateurs` — « Resserrés par Romain le 29/07 » |

---

## 2. Ce que ça a produit

Tous ces chiffres se recalculent depuis les trois CSV bruts du dépôt.

- **30 000 fiches → 20 519 entreprises réelles** — fusion prouvée par deux clés indépendantes,
  rollback intégral, **0 €** d'écart dans la comptabilité de l'ARR.
- **Un ARR défendable, publié en deux lignes jamais additionnées** : 52 032 000 € actif
  (3 246 clients) · 14 624 000 € ex-client (le pool de reconquête, il ne se facture pas).
- **26** comptes à appeler + **34** à travailler + **9** injoignables + **5 741** en signal
  faible + **14 709** silencieuses = **20 519**. Chaque entreprise du CRM a une ligne.
- **95 contrôles sur le nettoyage + 24 sur le scoring**, vérifiés à chaque exécution —
  un statut ne se déclare pas dans un fichier, il se constate sur le run.
- **Tout se reconstruit depuis un clone nu** :
  `run_cleanup.py` → `run_scoring.py` → `build_dashboard.py`.
  Après chaque déploiement, le site servi est comparé **à l'octet** au build du dépôt.

---

## 3. Le dispositif (un moyen, pas le sujet)

Deux modèles (Fable 5 et Opus 5) qui **ne se parlent jamais**. Une seule personne fait
canal et tranche. Dès que l'un construit, l'autre reprend depuis les fichiers bruts et
cherche à casser. En cas de désaccord, pas de débat : chacun renvoie sa définition
exécutable et son chiffre, et la comparaison tranche. Après chaque déploiement, celui
qui n'a pas publié re-télécharge le site servi et le compare à l'octet au dépôt.

Ce que ce croisement a attrapé, entre autres : **1 407 commerciaux récupérables** que
les 88 contrôles de l'époque ne voyaient pas (il y en a 95 aujourd'hui — le correctif
en a ajouté 7) ; des libellés d'écran que la donnée ne soutenait pas ; une chaîne de
build qui ne survivait pas à la machine qui l'avait produite.

---

## 4. Ce qui reste ouvert

Dit honnêtement, parce que c'est ce qui rend le reste crédible :

- **La vérité terrain a été trouvée, et c'est dit ici plutôt que découvert en entretien.** Le jeu de
  données contenait une trace de son générateur ; l'audit l'a identifiée. Les règles n'en ont
  jamais dépendu : barème et seuils figés d'abord, mesure de précision et de rappel faite une
  seule fois en fin de course, aucun poids déplacé pour rattraper un compte. Le mécanisme exact
  se raconte de vive voix, pas dans un dépôt public.
- **Le nurture n'existe pas.** Les 5 741 comptes en signal faible sont étiquetés, pas travaillés.
- **Le push Slack est manuel.** La liste part quand on la fait partir — pas encore de planification.
- **La vérification croisée est manuelle.** À l'échelle d'un vrai pipeline, les deux
  implémentations tourneraient en intégration continue, et le build casserait sur divergence.
- **L'enrichissement est prêt, pas branché.** La file existe (`contacts_a_enrichir.csv`,
  5 371 contacts), le schéma est écrit (`docs/schema-enrichissement.md`) — l'automate
  n'est pas branché : rien ne part sans validation humaine.

---

*Si un chiffre de ce document contredit un jour la sortie du pipeline, c'est ce document
qui a tort — corrigez-le, ou supprimez-le : la source de vérité reste le code et sa config.*
