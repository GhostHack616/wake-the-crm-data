# Rapport d'audit du cleanup — Wake the CRM

Généré par `cleanup/run_cleanup.py` le 2026-07-28 (référence temporelle du dataset : 2026-07-22).

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

## Étape 4 — Noms : normalisation (clé de dédup n°2) + marqueurs

name_norm = minuscules, sans marqueurs de doublon ni mentions juridiques (liste en config), sans ponctuation. dup_marker mémorise l'étiquette trouvée — une fiche marquée ne sera jamais fiche maîtresse.

- Marqueurs détectés : **234** (attendu audit : 234) — (old) 80, - import 80, ' 2' 74
- Noms vides après normalisation : **0** (attendu : 0)
- **Concordance nom↔racine (domaines déclarés) : 27329/27329** (attendu : 27 329/27 329 — c'est LE test de validation du geste)
- Concordance nom↔racine (racines déduites des emails) : 2538/2538 (contrôle indépendant bonus)
- Noms normalisés distincts : **20519** (borne de sanité : 19 000 - 22 000 = future taille de la table entreprises)

## Étape 5 — Emails : réparation mécanique + statut + doublons de personnes

email_clean = espaces retirés, @@ → @ (rien d'inventé) · email_status = ok/repaired/missing/personal · doublons d'adresse flagués (même adresse = même personne, interdit de la compter deux fois dans un buying committee).

- Réparées : **1544** (attendu : 1 544 = 769 `@@` + 775 espaces) — @@ : 769, espaces : 775
- **Encore invalides au regex après réparation : 0** (attendu : 0 — LE contrôle qui prouve)
- Sans adresse : **3065** (attendu : 3 065) · Perso (gmail) : **2359** (attendu : 2 359) · OK : 70231
- Adresses partagées par ≥2 contacts : **783** (attendu : 783) · porteurs flagués : **1940** (attendu : 1 940, dont 1 157 copies excédentaires)
- Freemails hors config détectés : aucun (gmail reste le seul domaine perso)
- Exemples : `pierre .durand@doriopradigital.com` → `pierre.durand@doriopradigital.com` · `antoine.boyer@@estevavenlabs.fr` → `antoine.boyer@estevavenlabs.fr`

> 📌 Honnêteté (mesuré) : cette étape n'améliore la joignabilité d'AUCUN compte chaud (0 des 25 signaux forts avait un email cassé ; 1 est sans adresse, 2 en gmail). C'est du nettoyage de fond, pas de la récupération de rappel — ça change le canal, pas le score.

## Étape 6 — Dates impossibles & cohérence

Une date fausse n'entre jamais dans un calcul : neutralisée (parsée vidée) + flag. Jamais 'corrigée' (vraie valeur inconnaissable), originale conservée. Les events ne sont jamais touchés — seule la fiabilité de la date est jugée.

- Contacts créés dans le futur : **6321** (attendu : 6 321) → date neutralisée + flag
- Contacts ayant REÇU des emails avant leur création (impossible → date corrompue) : **414** (attendu : 414)
- Contacts avec seulement visites/linkedin avant création (attribution rétroactive possible, bénéfice du doute) : **20** (attendu : 20)
- Comptes avec dernière activité future : **3** (attendu : 3) → neutralisée + flag

## 🛡️ Filet d'invariants — vérifié à chaque exécution

| ID | Invariant | Attendu | Mesuré | Statut |
|---|---|---|---|---|
| C1 | fiches accounts | 30000 | 30000 | 🟢 |
| C2 | contacts | 77199 | 77199 | 🟢 |
| C3 | events | 94838 | 94838 | 🟢 |
| C4 | domaines d'origine non vides (colonne intacte) | 27329 | 27329 | 🟢 |
| C5 | graphies pays d'origine distinctes (colonne intacte) | 30 | 30 | 🟢 |
| C6 | noms d'origine non vides (colonne intacte) | 30000 | 30000 | 🟢 |
| K1 | erreurs de parsing de dates | 0 | 0 | 🟢 |
| K2 | renewal_date remplies (= customers + churned contradictoires) | 3386 | 3386 | 🟢 |
| K3 | form_fill présents | 16 | 16 | 🟢 |
| K4 | meeting_booked présents | 9 | 9 | 🟢 |
| K5 | concordance nom normalisé ↔ racine de domaine (déclarés) | 27329 | 27329 | 🟢 |
| S1 | domaines déclarés | 27329 | 27329 | 🟢 |
| S2 | racines déduites des contacts | 2538 | 2538 | 🟢 |
| S3 | fiches sans racine | 133 | 133 | 🟢 |
| S4 | longueur minimale des racines (anti-collision) | >= 6 | 6 | 🟢 |
| S5 | préfixes www. dans la colonne d'origine (recomptés) | 1825 | 1825 | 🟢 |
| S6 | fiches marquées (old)/- import/' 2' | 234 | 234 | 🟢 |
| S7 | noms normalisés distincts (future table entreprises) | 19000-22000 | 20519 | 🟢 |
| S8 | emails réparés | 1544 | 1544 | 🟢 |
| S9 | emails invalides après réparation | 0 | 0 | 🟢 |
| S10 | adresses email partagées (doublons de personnes) | 783 | 783 | 🟢 |
| S11 | contacts créés dans le futur (neutralisés + flag) | 6321 | 6321 | 🟢 |
| S12 | contacts avec emails reçus avant création (date corrompue) | 414 | 414 | 🟢 |
| S13 | contacts en attribution rétroactive possible | 20 | 20 | 🟢 |
| S14 | comptes à dernière activité future (neutralisés + flag) | 3 | 3 | 🟢 |
| S15 | dates parsées encore au futur après neutralisation | 0 | 0 | 🟢 |

À armer avec leurs étapes : étape 7 : entités finales entre 19 000 et 22 000 · étape 7 : aucune entité ne regroupe plus de 5 fiches · étape 7 : écart de somme ARR = exactement les doublons écartés, listés · étape 8 : chaque event rattaché à exactement une entité · étape 9 : events dédupliqués flagués, jamais supprimés (94 838 conservés) · étape 10 : le bot CON-077194 toujours flagué · étape 11+ : ACC-027283 (pages résiliation) jamais en HOT · étape 11+ : aucun contact opted_out dans une liste d'envoi

