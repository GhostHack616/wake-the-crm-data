# Rapport d'audit du cleanup — Wake the CRM

Généré par `cleanup/run_cleanup.py` le 2026-07-27 (référence temporelle du dataset : 2026-07-22).

Principe : rien n'est supprimé — réparations en colonnes neuves, originaux intacts.

## Étape 1 — Dates : 3 formats → ISO

Règle : ISO tel quel · année à 2 chiffres = MM/DD/YY (américain) · année à 4 chiffres = DD/MM/YYYY (français). Aucune date devinée : illisible → vide + format `error`.

### accounts.csv (30000 lignes)

| Colonne | ISO | MM/DD/YY | DD/MM/YYYY | Vides | Erreurs | Hors bornes |
|---|---|---|---|---|---|---|
| created_date | 9869 | 10079 | 10052 | 0 | 0 | 0 |
| last_activity_date | 8028 | 8195 | 8010 | 5767 | 0 | 0 |
| renewal_date | 1161 | 1090 | 1135 | 26614 | 0 | 0 |

Exemples created_date : `21/03/2022` → `2022-03-21` (dmy) · `08/01/19` → `2019-08-01` (mdy)
Exemples last_activity_date : `05/19/24` → `2024-05-19` (mdy) · `16/05/2026` → `2026-05-16` (dmy)
Exemples renewal_date : `28/03/2027` → `2027-03-28` (dmy) · `05/07/2026` → `2026-07-05` (dmy)

### contacts.csv (77199 lignes)

| Colonne | ISO | MM/DD/YY | DD/MM/YYYY | Vides | Erreurs | Hors bornes |
|---|---|---|---|---|---|---|
| created_date | 25790 | 25693 | 25716 | 0 | 0 | 0 |

Exemples created_date : `04/01/19` → `2019-04-01` (mdy) · `09/26/21` → `2021-09-26` (mdy)

## Étape 2 — Pays : 30 graphies → 8 codes ISO 3166

Table de correspondance en config (cleanup_config.yaml). Une graphie absente de la table n'est jamais devinée : vide + listée ici.

| Pays | Code | Fiches |
|---|---|---|
| France | FR | 13517 |
| Belgique | BE | 3535 |
| Pays-Bas | NL | 3080 |
| Allemagne | DE | 3021 |
| Italie | IT | 1751 |
| Espagne | ES | 2317 |
| Suisse | CH | 1552 |
| Royaume-Uni | GB | 1227 |

Graphies distinctes reconnues : 24 · fiches mappées : 30000/30000 · non mappées : 0

## Étape 3 — Domaines : nettoyage + racine (clé de dédup n°1) + inférence tracée

domain_clean = minuscules sans préfixe www. · domain_root = partie avant l'extension, ou déduite des emails pro des contacts quand ils sont UNANIMES · domain_source trace l'origine (declared / inferred_from_contacts / none) · has_domain = flag final. Validation de l'inférence : sur les comptes ayant domaine ET emails pro, racine(domaine) = racine(emails) dans 25 785 cas sur 25 785 (0 divergence) — déduire n'est pas deviner.

- Préfixes www. retirés : **1825** (attendu audit : 1 825)
- Domaines déclarés : **27329** · racine déduite des contacts : **2538** (attendu : 2 538) · sans racine : **133** (attendu : 133 = 94 sans contact + 39 emails perso) {'aucun contact': 94, 'emails perso/vides seulement': 39}
- Déductions ambiguës (plusieurs racines candidates) : **0** (attendu : 0)
- Racines vides alors qu'un domaine existe : **0** (attendu : 0)
- Extensions rencontrées : .co (3865), .com (7847), .eu (4006), .fr (7836), .io (3775)
- Extensions hors liste attendue : aucune
- Exemples nettoyage : `www.brionexpartners.io` → `brionexpartners.io` · `www.cendradata.eu` → `cendradata.eu`
- Exemples inférence : PrimofinSoft & Co → racine `primofinsoft` · Cendravialogic Group → racine `cendravialogic`

