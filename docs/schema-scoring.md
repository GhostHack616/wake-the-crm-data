# Le scoring en un schéma — Wake the CRM (V1.1)

> Le brief : *« Un schéma de ton scoring est fortement encouragé. Si tu ne peux pas le dessiner, c'est qu'il n'est pas clair. »* Le voici.

**La logique en une phrase** : un compte devient chaud par **accumulation de preuves**, portées par les
**bonnes personnes**, **récentes** — l'entrée en liste chaude passe par deux **portes sémantiques**
(des règles, pas des points), et le score **ordonne** les files. Tout paramètre vit dans
`scoring/scoring_config.yaml`, chaque poids avec son pourquoi.

```mermaid
flowchart TD
    EV[events_clean.csv<br/>94 838 événements] --> F{Flux NET}
    F -->|"doublon flagué (1 988)"| X1[écarté]
    F -->|"bot CON-077194 (420)"| X1
    F -->|"anonymes (4 000, non rattachables)"| X1
    F --> PERS["Par PERSONNE<br/>(copies duplicate_of → fiche principale)"]

    PERS --> W["POINTS par événement<br/>RDV 40 · formulaire 35 · visite pricing/démo 10<br/>clic 8 · commentaire LinkedIn 6 · page produit 4 · like 2<br/>pages résiliation/export −15 · opens/envois/carrières/blog 0"]
    W --> M["× MULTIPLICATEUR porteur<br/>décideur ×1 · champion ×0,8 · utilisateur ×0,6<br/>inconnu ×0,5 · bruit ×0<br/>(conversions et négatifs : plein poids)"]
    M --> DK["× DÉCROISSANCE<br/>gestes : demi-vie 10 j · preuves : 30 j<br/>plancher 25 % sur les 21 derniers jours"]

    DK --> ETAGE["ÉTAGE PERSONNE<br/>un score par personne<br/>(l'explicabilité : qui a fait quoi, quand)"]
    ETAGE -->|somme| COMPTE["SCORE DU COMPTE<br/>(garde : somme des étages = score, à l'arrondi près)"]

    COMPTE --> P1{"PORTE 1<br/>conversion ≤ 45 j ?"}
    COMPTE --> P2{"PORTE 2<br/>≥ 3 personnes actives<br/>sur les 14 DERNIERS jours<br/>dont un décideur ?"}
    P1 -->|oui : 25 comptes| T1["TIER 1 — appeler cette semaine<br/>26 comptes"]
    P2 -->|"oui : 1 compte (l'ex-client<br/>qui regarde la sortie → play risque)"| T1
    COMPTE --> S{"score ≥ 8 ?"}
    S -->|"oui : 34 comptes"| T2["TIER 2 — à travailler"]
    S -->|non| T3["TIER 3 — nurture auto"]

    PERDU["PERDU — canal mort (9)<br/>jamais client + rien d'autre ne vit<br/>+ plus personne de joignable"] -.->|hors des files| T3

    T1 --> LIGNE["LA LIGNE DE HOT LIST<br/>score · tier · porte · fit A/B/C · play<br/>QUI APPELER (la personne qui a converti) · son canal<br/>comité N pers/14 j · sponsor oui/non · n_records"]
    T2 --> LIGNE
```

## Les règles qui ne se voient pas sur le dessin

- **Fit A/B/C** (taille dans la cible + décideur identifié) : **ordonne** la file, ne bloque jamais
  l'entrée — un C avec un RDV reste Tier 1. Départage : fit → n_records → score.
- **Le désabonnement ne touche jamais le score** : il ferme un canal (on n'écrit plus à la personne,
  on l'appelle), il ne refroidit pas un compte. Seul le cas extrême « plus personne de joignable et
  rien d'autre ne vit » sort le compte des files (9 comptes, étiquetés).
- **4 règles dormantes** documentées en config avec leurs mesures : présentes pour un vrai CRM,
  inactives ici — jamais présentées comme des protections qui auraient servi.

## Pourquoi c'est robuste

- **15 gardes automatiques** à chaque exécution (couverture des poids, flux net, somme des étages,
  unicité de la hot list, joignabilité du Tier 1, désabonné jamais en canal email…) — exécution
  rouge si une seule casse.
- **Test ±30 %** : 38 variations de poids — le **Tier 1 est stable à 100 %** (les portes sont des
  règles) ; le Tier 2 respire par construction (file de nurture à bords sensibles au seuil, assumé).
- **Où vit le scoring** : un script Python sans dépendance exotique + un YAML. Pas de base de
  données : 20 519 comptes tiennent en mémoire, le CRM reste la source de vérité, le moteur est
  re-exécutable partout (CI, cron, laptop) et chaque run régénère toutes ses sorties.
