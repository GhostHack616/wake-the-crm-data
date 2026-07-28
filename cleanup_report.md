# Rapport d'audit du cleanup — Wake the CRM

Généré par `cleanup/run_cleanup.py` le 2026-07-28 (référence temporelle du dataset : 2026-07-22).

Principe : rien n'est supprimé — réparations en colonnes neuves, originaux intacts.

## 📋 Résumé exécutif — l'état du CRM après cleanup

| Avant | Après |
|---|---|
| 30 000 fiches comptes (1/3 de doublons) | **20519 entreprises réelles** (fusion prouvée par 2 clés indépendantes, rollback intégral) |
| 3 formats de dates, 30 graphies de pays, 2 671 domaines vides | 0 erreur de parsing, 8 pays ISO, 133 fiches sans racine (95 % récupérées) |
| ARR invérifiable (69,7 M€ bruts, 21,9 % fantôme) | **ARR actif 52,032,000 €** (3246 clients) · ex-client 14,624,000 € (win-back) · écarté doublons 3 025 000 €, décomposé ci-dessous |
| 77 199 contacts, doublons de personnes invisibles | 77 146 rattachés, 99 doublons flagués, 53 comptes à créer, 4 tiers persona produit |
| 94 838 events en vrac | 90 838 rattachés aux entités, 1 988 doublons flagués, 1 bot isolé (420 events), 4 000 anonymes tracés |

**Segments** : 22 prospects chauds · 5232 tièdes · 3037 clients actifs · 209 renewals échues · 36 churns contradictoires · 870 ex-clients réactifs · 769 lost réactifs · 5393 muets.

**Décomposition de l'ARR écarté (3 025 000 €, à l'euro près, sous invariant)** :
| Raison | Fiches | Montant |
|---|---|---|
| Conflits bi-customer (2 montants, règle contrat le plus tardif) — 89 groupes | 89 | 1,420,000 € |
| Churned écartés (le customer prime) | 153 | 1,081,000 € |
| Churned doublons | 46 | 356,000 € |
| Customer doublons, même montant | 11 | 168,000 € |

NB : la règle « contrat le plus tardif » ne maximise pas l'ARR affiché (616 000 € de moins qu'une règle « max ») — elle suit le contrat en cours.

**Livrables** : `companies.csv` (20 519 entreprises, segments, plays, flags) · `accounts_clean.csv` / `contacts_clean.csv` / `events_clean.csv` · `accounts_to_create.csv` (53) · `cleanup_config.yaml` (toutes les règles) · ce rapport (auto-généré à chaque exécution).

---

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

## Étape 7 — LA FUSION : 30 000 fiches → entreprises

Clé = name_norm (partitions identiques prouvées par 2 clés indépendantes). Élection marqueur-exclu → cascade de statuts → ARR rempli → ancienneté. Statut consolidé = le plus avancé du GROUPE. ARR+renewal ensemble (customer puis churned, renewal la plus tardive). Dernière activité = MAX, création = MIN. Conflits → flags, jamais tranchés en silence. Commercial : si la fiche élue n'en a pas, hérité d'une jumelle (cascade d'élection, provenance tracée dans owner_source_account). Rien n'est supprimé : merged_into sur chaque doublon.

- **Entités : 20519** (attendu : 20 519) — tailles : 1 fiches × 11888, 2 fiches × 7809, 3 fiches × 794, 4 fiches × 28
- Fiches étiquetées élues maîtresses : **0** (attendu : 0)
- Comptabilité ARR : total fiches **69,681,000 €** = conservé **66,656,000 €** + écarté (doublons) **3,025,000 €** — écart : **0 €** (attendu : 0)
- Conflits flagués : pays **5947** (attendu 5 947) · ARR **251** (251) · owner **5067** (5 067) · lifecycle **6858** (6 858)
- Arbitrages churned-vs-opportunity : **80** (attendu : 80)
- Commerciaux hérités d'une fiche jumelle : **1407** (attendu : 1 407)
- Entités sans commercial (à router) : **2729** (attendu : 2 729)

## Étape 8 — Ré-attachement : contacts et events rejoignent leurs entités

entity_id partout · orphelins rattachés par le domaine de leur email quand il désigne UNE entité (tracé inferred_from_email, même geste que l'étape 3) · vrais inconnus → liste 'comptes à créer' · dédup des personnes (même email dans la même entité = une personne : primaire + copies tracées) · rien de supprimé.

- Contacts rattachés : **76599** par leur compte + **547** par leur email (attendu : 547) = 77146
- Vrais inconnus : **53** (attendu : 53) → `accounts_to_create.csv` — dont events portés : 0 (attendu : 0)
- Events : **90838** rattachés + **4000** anonymes conservés = 94838
- Re-parentés (fiche non-maîtresse → entité) : **29184** events (32,1 % des rattachables) · **24230** contacts
- Dédup personnes : **99** couples (entité, email) → 99 copies flaguées `duplicate_of` (attendu : 97/97)

## Étape 9 — Dédup des events (flags, jamais de suppression)

Clé stricte (contact, type, campagne, PAGE, jour) — la page protège le pattern /pricing puis /demo. Anonymes intouchés (l'appliquer supprimerait 2 872 lignes à tort — mesuré). Première occurrence conservée.

- Lignes flaguées : **1988** (attendu : 1 988) dans **1860** groupes (attendu : 1 860)
- Conversions touchées : **0** (attendu : 0) · anonymes flagués : **0** (attendu : 0)

## Étape 10 — Le bot : détection au chronomètre, sur le flux brut

Définition verrouillée : délai open → dernier envoi antérieur (même campagne), bot = médiane ≤ 60 s sur ≥ 5 emails. Sur le flux BRUT — la dédup efface le motif mécanique (3+3 par envoi → 1+1). Flag, jamais suppression : le bot est une information sur le compte, pas un déchet.

- Bots détectés : **1** — CON-077194 (médiane 4 s) (attendu : 1, CON-077194 à 4 s)
- Events flagués from_bot : **420** (attendu : 420)
- Témoins humains flagués à tort : **0** (attendu : 0) — CON-077195 : médiane 84258 s = 23.4 h

## Étape 11 — Segmentation : 10 états factuels → 7 plays

Règles en ordre strict sur les FAITS (statut consolidé, renewal, engagement NET). MORT/DORMANT : champ déclaré en dernier recours, hors scoring, flagué. Décision architecturale : la hot list finale est UNIQUE, tous segments, avec le play — 3 des 25 entités les plus chaudes vivent hors des segments prospects.

| Segment | Entités | Play |
|---|---|---|
| CLIENT_ACTIF | 3037 | retention |
| CLIENT_RENEWAL_ECHUE | 209 | risque |
| CHURN_CONTRADICTOIRE | 36 | audit |
| EX_CLIENT_REACTIF | 870 | win_back |
| EX_CLIENT | 1188 | win_back_froid |
| PROSPECT_CHAUD | 22 | new_business |
| PROSPECT_TIEDE | 5232 | new_business |
| LOST_REACTIF | 769 | reactivation |
| TOUCHE_EMAIL_SEULEMENT | 3763 | nurture |
| MORT | 3474 | aucun |
| DORMANT | 1919 | aucun |

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
| S16 | équilibre clé↔marqueurs : noms (marqueurs inclus) − marqueurs = entités | 20753 − 234 = 20519 | 20753 − 234 = 20519 | 🟢 |
| S15 | dates parsées encore au futur après neutralisation | 0 | 0 | 🟢 |
| F1 | entités (exact, triple-prouvé) | 20519 | 20519 | 🟢 |
| F2 | taille max d'un groupe de doublons | 4 | 4 | 🟢 |
| F3 | fiches étiquetées élues maîtresses (absolu) | 0 | 0 | 🟢 |
| F4 | fiches rattachées à exactement une entité | 30000 | 30000 | 🟢 |
| F5 | conservation ARR totale (fiches) | 69681000 | 69681000 | 🟢 |
| F6 | comptabilité ARR : total − conservé − écarté | 0 | 0 | 🟢 |
| F7 | conflits de pays flagués | 5947 | 5947 | 🟢 |
| F8 | conflits d'ARR flagués | 251 | 251 | 🟢 |
| F9 | conflits de commercial flagués | 5067 | 5067 | 🟢 |
| F10 | conflits de statut flagués | 6858 | 6858 | 🟢 |
| F11 | arbitrages churned-vs-opportunity | 80 | 80 | 🟢 |
| F12 | corroboration des fusions par marqueur (racine déclarée) | 226 | 226 | 🟢 |
| F13 | corroboration des fusions par marqueur (racine déduite) | 8 | 8 | 🟢 |
| F14 | fusions reposant sur le SEUL marqueur | 0 | 0 | 🟢 |
| F15 | ARR actif (customers uniquement) | 52032000 | 52032000 | 🟢 |
| F16 | ARR ex-client (churned, pool win-back) | 14624000 | 14624000 | 🟢 |
| F17 | ARR actif + ex-client = ARR conservé | 66656000 | 66656000 | 🟢 |
| F18 | commerciaux hérités d'une jumelle | 1407 | 1407 | 🟢 |
| F19 | entités sans commercial après héritage | 2729 | 2729 | 🟢 |
| F20 | owner vide ⟺ à router (double sens) | 0 | 0 | 🟢 |
| P1 | buyers (périmètre produit) | 16561 | 16561 | 🟢 |
| P2 | champions | 19701 | 19701 | 🟢 |
| P3 | utilisateurs | 25573 | 25573 | 🟢 |
| P4 | bruit (×0 sur signaux faibles, jamais sur conversions) | 10799 | 10799 | 🟢 |
| P5 | sans titre | 4565 | 4565 | 🟢 |
| P6 | libellés fantômes dans le mapping (double sens, aller) | 0 | 0 | 🟢 |
| P7 | titres du recensement non classés (double sens, retour) | 0 | 0 | 🟢 |
| R1 | contacts avec entité | 77146 | 77146 | 🟢 |
| R2 | orphelins rattachés par email (tracés) | 547 | 547 | 🟢 |
| R3 | vrais inconnus (liste comptes à créer) | 53 | 53 | 🟢 |
| R4 | events portés par un vrai inconnu | 0 | 0 | 🟢 |
| R5 | events avec entité | 90838 | 90838 | 🟢 |
| R6 | events anonymes conservés | 4000 | 4000 | 🟢 |
| R7 | events re-parentés (32,1 % des rattachables) | 29184 | 29184 | 🟢 |
| R8 | contacts re-parentés | 24230 | 24230 | 🟢 |
| R9 | copies de personnes flaguées (duplicate_of) | 99 | 99 | 🟢 |
| R10 | emails présents sur >= 2 entités (flag, jamais fusionnés) | 678 | 678 | 🟢 |
| G1 | segment CLIENT_ACTIF | 3037 | 3037 | 🟢 |
| G2 | segment CLIENT_RENEWAL_ECHUE | 209 | 209 | 🟢 |
| G3 | segment CHURN_CONTRADICTOIRE | 36 | 36 | 🟢 |
| G4 | segment EX_CLIENT_REACTIF | 870 | 870 | 🟢 |
| G5 | segment EX_CLIENT | 1188 | 1188 | 🟢 |
| G6 | segment PROSPECT_CHAUD | 22 | 22 | 🟢 |
| G7 | segment PROSPECT_TIEDE | 5232 | 5232 | 🟢 |
| G8 | segment LOST_REACTIF | 769 | 769 | 🟢 |
| G9 | segment TOUCHE_EMAIL_SEULEMENT | 3763 | 3763 | 🟢 |
| G10 | segment MORT | 3474 | 3474 | 🟢 |
| G11 | segment DORMANT | 1919 | 1919 | 🟢 |
| G12 | partition complète (somme des segments) | 20519 | 20519 | 🟢 |
| G13 | cohérence : CLIENT_ACTIF + RENEWAL_ECHUE = entités customer | 3246 | 3246 | 🟢 |
| G14 | cohérence : segments churned = entités churned | 2094 | 2094 | 🟢 |
| G15 | DORMANT sur champ déclaré = tous flagués segment_evidence | 1919 | 1919 | 🟢 |
| A1 | ARR écarté — conflits_bi_customer | 1420000 | 1420000 | 🟢 |
| A2 | ARR écarté — churned_sous_customer | 1081000 | 1081000 | 🟢 |
| A3 | ARR écarté — churned_doublons | 356000 | 356000 | 🟢 |
| A4 | ARR écarté — customer_doublons_meme_montant | 168000 | 168000 | 🟢 |
| A5 | ARR écarté — la décomposition ferme sur le total | 3025000 | 3025000 | 🟢 |
| D1 | events flagués doublons (jamais supprimés) | 1988 | 1988 | 🟢 |
| D2 | conversions flaguées doublons | 0 | 0 | 🟢 |
| D3 | events anonymes flagués doublons | 0 | 0 | 🟢 |
| B1 | bots détectés (CON-077194, et lui seul) | 1 | 1 | 🟢 |
| B2 | events from_bot | 420 | 420 | 🟢 |
| B3 | témoins humains flagués bot (non-régression) | 0 | 0 | 🟢 |
| R11 | faux clusters restants (2 primaires, même email, même entité) | 0 | 0 | 🟢 |

À armer avec leurs étapes : résultat : ENT-16714 (pages résiliation) jamais dans la hot list — garantie devenue paramétrique · garde de config : poids des pages cancel/billing/export STRICTEMENT négatifs (dérive statistiquement invisible : 14 events/94 838, tous sur ENT-16714) · garde de config : /careers et /blog = 0 · email_sent = 0 · plancher conversions actif · couverture données→config : chaque type d'event (7) et chaque page (18) a un poids DÉCLARÉ — valeur nouvelle = alarme, jamais un défaut silencieux · flux : le scoring lit 0 from_bot et 0 is_duplicate_event ; le détecteur lit 94 838 — deux compteurs, deux alarmes · hot list : UNIQUE, tous segments confondus, colonne play — les files sont des vues · push : aucun contact opted_out dans une liste d'envoi

## 🧭 Traçabilité — chaque règle actée a-t-elle son contrôle automatique ?

| Règle actée | Implémentée où | Invariant garant | Statut |
|---|---|---|---|
| Dates 3 formats, année 2 ch.=US / 4 ch.=FR, jamais devinées | étape 1 | K1, S15 | 🟢 garantie |
| Pays normalisés ISO, graphie inconnue jamais devinée | étape 2 | C5 + contrôle non-mappées=0 | 🟢 garantie |
| Racine de domaine = clé n°1 ; inférence UNANIME tracée | étape 3 | S1-S5 | 🟢 garantie |
| Nom normalisé = clé n°2 ; marqueurs jamais maîtres | étapes 4+7 | S6, S7, K5, S16, F3 | 🟢 garantie |
| Emails : réparation mécanique seule ; doublons de personnes flagués | étape 5 | S8-S10 | 🟢 garantie |
| Date fausse neutralisée + tracée, jamais corrigée | étape 6 | S11-S15 | 🟢 garantie |
| Fusion : 20 519 entités, conflits flagués jamais tranchés en silence | étape 7 | F1-F14 | 🟢 garantie |
| ARR comptable = customers uniquement (piège n°11) | étape 7 (arr_actif) | F15-F17 | 🟢 garantie |
| Rien n'est supprimé, rollback intégral | toutes | C1-C6, F4 + merged_into | 🟢 garantie |
| Le routage lit les FAITS (a_ete_client/deal_en_cours), pas l'étiquette | étapes 7+11 (faits + play) | G13-G14 | 🟢 garantie |
| Segmentation : 10 états factuels sur flux net, partition complète ; MORT/DORMANT en dernier recours assumé | étape 11 | G1-G15 | 🟢 garantie |
| Hot list UNIQUE tous segments + colonne play (les files = des vues) | scoring (à venir) | — | 🔴 à armer avec son étape |
| email_sent pèse 0, opens ≈ 0 dans le score | scoring (à venir) | — | 🔴 à armer avec son étape |
| /careers et /blog à poids nul | scoring (à venir) | — | 🔴 à armer avec son étape |
| Pages négatives (cancel/billing/export) à poids négatif | scoring (à venir) | — | 🔴 à armer avec son étape |
| Opt-out : interdit d'écrire ≠ signal annulé (suppression list) | scoring/push (à venir) | — | 🔴 à armer avec son étape |
| Aucun filtre dur avant scoring (test d'amputation) | scoring (à venir) | — | 🔴 à armer avec son étape |
| Decay demi-vie courte + plancher 21 j | scoring (à venir) | — | 🔴 à armer avec son étape |
| Le silence des clients EST un score (file risque churn) | routage (à venir) | — | 🔴 à armer avec son étape |
| Bot détecté au chronomètre (cadence), jamais au volume — sur le flux BRUT | étape 10 | B1-B3 | 🟢 garantie |
| Dédup events : clé stricte page incluse, anonymes intouchés | étape 9 | D1-D3 | 🟢 garantie |
| Récence = events uniquement, jamais last_activity_date | scoring (à venir) | — | 🔴 à armer avec son étape |
| Buying committee = personnes distinctes (dédup email) | étape 8 | R9-R11 | 🟢 garantie |
| Chaque event/contact rattaché à exactement une entité (anonymes/inconnus tracés) | étape 8 | R1-R8 | 🟢 garantie |
| Mapping persona produit, partition complète double sens | config personas | P1-P7 | 🟢 garantie |
| Plancher conversions : form_fill/meeting_booked à poids plein quel que soit le porteur | scoring (à venir) | — | 🔴 à armer avec son étape |

