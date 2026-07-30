# Wake the CRM : la réponse

Ce dépôt contient l'énoncé du challenge (conservé plus bas, intact) et la machine construite en réponse : cleanup, scoring, push Slack et dashboard.

**Le dashboard en ligne : https://wake-the-crm.netlify.app** (vues Macro, Logique, Ops, Process et Données ; le flux d'événements se rejoue en live).

## Où est quoi

| Dossier | Contenu |
|---|---|
| `cleanup/` | le pipeline de nettoyage, 12 étapes + sa config. Rien n'est supprimé ni écrasé : chaque réparation vit dans une colonne neuve, originaux intacts |
| `scoring/` | le moteur de scoring V1.1 + `scoring_config.yaml` (chaque poids, seuil et règle y vit, commenté : « config, pas code ») |
| `dashboard_data/` | les sorties versionnées que le dashboard consomme (scores, hot list, données du dash) |
| `dashboard/` | le tableau de bord : build reproductible + test automatique d'interdit d'écran |
| `docs/` | `decisions.md` (qui a décidé quoi, et où le vérifier), le schéma du scoring, l'architecture d'enrichissement |
| `slack/` | le push de la hot list avec les preuves (aucun secret dans le dépôt : l'adresse d'envoi vit dans l'environnement) |
| `cleanup_report.md` | le rapport d'audit auto-généré à chaque exécution : 95 invariants + la traçabilité règle par règle |

## Tout se reconstruit depuis un clone nu

```bash
python3 cleanup/run_cleanup.py               # nettoie, fusionne, segmente -> data_clean/ + cleanup_report.md
python3 scoring/run_scoring.py               # score, tiers, hot list -> dashboard_data/
python3 dashboard/build/build_dashboard.py   # construit le dashboard -> dashboard/dist/
```

119 contrôles automatiques tournent à chaque exécution (95 sur le nettoyage, 24 sur le scoring). Un statut ne se déclare pas : il se constate sur le run, et un contrôle rouge fait échouer le pipeline. Après chaque déploiement, le site servi est comparé à l'octet au build du dépôt.

## Transparence sur la vérité terrain

L'énoncé annonce que les comptes réellement chauds ont été plantés dans les données. C'est assumé ici plutôt que découvert en entretien : l'audit a identifié une trace du générateur qui permet de reconstituer cette vérité terrain. Elle n'a jamais servi à construire les règles : le barème et les seuils ont été figés d'abord, la mesure de précision et de rappel a été faite une seule fois, en fin de course, et aucun poids n'a été déplacé pour rattraper un compte. Le détail du mécanisme se raconte de vive voix, pas dans un dépôt public.

## Les décisions

Chaque choix a un pourquoi. `docs/decisions.md` liste les arbitrages qui ont fait le projet, avec leurs mots d'origine et l'endroit exact où les vérifier.

---

*Ci-dessous : l'énoncé original du challenge, conservé tel que reçu.*

---

# Wake the CRM — Challenge GTM Engineer

Bienvenue. Ce repo contient tout ce qu'il te faut. Lis ce README en entier avant d'ouvrir les CSVs.

---

## Le scenario

Tu rejoins une scale-up HR-tech (fictive) qui vend un logiciel RH (ATS, performance, paie) en Europe. Son CRM a 8 ans d'historique et personne ne l'a jamais entretenu :

- **30 000 comptes** et **77 000 contacts**, accumules par 3 generations de sales.
- Dedans, melanges : des clients actifs, des clients churnes, des prospects morts, des doublons, des champs contradictoires.
- Et surtout : **quelque part dans cette masse, des comptes montrent des signaux d'achat en ce moment meme — et personne ne les regarde.**

Ta mission : **construire la machine qui les trouve.**

## Ce que tu recois

| Fichier | Contenu |
|---|---|
| `accounts.csv` | 30 000 comptes — le CRM brut, avec tous ses defauts |
| `contacts.csv` | 77 000 contacts rattaches (ou pas) aux comptes |
| `events.csv` | ~95 000 evenements d'engagement sur les 90 derniers jours |

Le dictionnaire des donnees est en bas de ce README.

**Important :** ces donnees sont 100 % synthetiques, mais leurs defauts sont realistes et **volontaires**. Rien n'est propre. C'est le jeu.

---

## Partie 1 — La machine (le gros du travail)

### 1. Cleanup d'abord

Un scoring sur des donnees sales ne vaut rien. Avant de scorer :

- Dedoublonne les comptes (il y a des doublons — noms differents, domaines differents, memes entreprises).
- Segmente la base : client actif / churne / prospect / mort.
- Resous les contradictions que tu trouveras (il y en a).

### 2. Le scoring engine — le coeur du test

Rien n'est impose. C'est TOI qui decides, et tu devras defendre chaque choix :

- **Ta taxonomie de triggers.** Qu'est-ce qui compte comme un signal ? Comment distingues-tu le fit (ce compte vaut-il quelque chose) de l'engagement (bougent-ils maintenant) ? Un event isole vs un cluster ? Est-ce que 3 contacts actifs en 7 jours = 1 contact actif 3 fois ? Un click d'il y a 60 jours vaut-il encore quelque chose ? Et les signaux negatifs ?
- **Ou vit ton scoring.** Dans un outil ? Dans une base externe ? Pourquoi ?
- **Config, pas code.** Les poids et seuils vivent en config, pas en dur dans le code. On ne te demandera pas de changer une regle en live — mais on te posera des questions, et chaque poids doit avoir un pourquoi.

**Un schema de ton scoring est fortement encourage.** Comment les signaux entrent, comment ils se combinent, ou sont les seuils. Si tu ne peux pas le dessiner, c'est qu'il n'est pas clair.

### 3. La donnee fraiche — l'architecture d'enrichissement

Le CRM a 8 ans. Rien ne garantit que ses champs sont encore vrais : effectifs, titres, emails, tout est potentiellement perime. Et il te manque peut-etre des donnees que le CRM n'a jamais eues.

Les entreprises du dataset sont fictives, donc pas d'enrichissement reel possible : **cette partie est un exercice d'architecture, sur schema.** Propose le protocole complet :

- **Quoi** — quelles donnees tu rafraichis ou vas chercher (firmographique, titres, emails, signaux externes), et pourquoi celles-la.
- **Avec quoi** — quels outils ou sources pour chaque type de donnee. A toi de choisir et de justifier.
- **Quand** — a l'ingestion ? Score-gated (on n'enrichit pas 30 000 comptes a l'aveugle) ? En waterfall ? Qu'est-ce qui declenche un refresh ?
- **A quel cout** — chaque appel coute. Ou mets-tu les gates pour ne pas bruler le budget ?

Livrable : **un schema d'architecture + le protocole ecrit.**

### 4. Le push

Les comptes chauds doivent atterrir quelque part d'actionnable (digest Slack, webhook, ce que tu veux) — **avec les preuves** : « Compte X passe hot : 3 contacts actifs cette semaine dont la VP People, /pricing visite 2 fois, demo request. »

### 5. Le dashboard — deploye sur ton infra

Trois vues :

- **Vue macro.** Le CRM comme une masse endormie qui se reveille : les comptes s'allument au fur et a mesure que les events arrivent. Les events sont timestampes — tu peux rejouer le stream en live pendant la demo. Sois creatif, on veut du spectaculaire ET du lisible.
- **Vue logique.** Clic sur un compte → tous ses signaux, chaque regle declenchee, la composition du score, le decay applique. La question « pourquoi ce compte est-il hot ? » doit trouver sa reponse **dans l'UI seule**, sans ouvrir le code.
- **Vue ops.** Minimale : statut du dernier run + une alarme si quelque chose casse.

### Ce qu'on evalue (partie 1)

On connait les reponses : les comptes reellement chauds ont ete plantes dans les donnees, ainsi que **des pieges** concus pour tromper un scoring naif. Ta note, c'est :

1. **Precision et rappel** — combien de vrais chauds trouves, combien de faux positifs remontes.
2. **Les pieges** — y es-tu tombe ?
3. **Explicabilite** — chaque score justifiable depuis le dashboard, chaque architecture depuis un schema.
4. **L'oral** — on te posera des questions sur chaque choix : regle, poids, seuil, outil d'enrichissement. Chacun doit avoir un pourquoi.

---

## Partie 2 — L'open challenge (demo day)

Deux volets. Les deux comptent.

### 2a. Ce que tu as deja construit

Montre-nous un truc que tu as **vraiment** construit — script, workflow, automation, app, peu importe la taille. Deroule la logique entiere : quel probleme, quels choix, comment ca marche bout en bout, ou ca casse, et ce que tu referais differemment aujourd'hui.

### 2b. L'outil GTM que tu as toujours voulu avoir

Celui qui manque, celui que personne n'a construit pour toi. Pas besoin d'un build poli : le livrable, c'est ton raisonnement + un schema + (optionnel) un prototype rugueux. Quel probleme, pourquoi maintenant, comment ca marche, ou ca casse.

Les deux volets sont evalues sur 4 axes :

| Axe | La question qu'on se posera |
|---|---|
| **Pragmatisme** | Ton energie est-elle la ou l'impact est ? Est-ce que ca shippe en 2 semaines, et quelqu'un l'utilise lundi ? Tu arrives avec une solution, pas un probleme ? |
| **Avant-gardisme** | Y a-t-il UN move genuinement non evident dedans ? As-tu teste un outil avant tout le monde ? |
| **Leadership** | Es-tu fiable de bout en bout : engagements tenus, exigence elevee sans perfectionnisme inutile ? Et surtout : alertes-tu toi-meme sur ou ca casse, sans qu'on te le demande ? |
| **Enthousiasme** | Est-ce que tu y crois vraiment, ou c'est une idee tendance LinkedIn ? Le scepticisme est bienvenu, le pessimisme non. |

---

## Regles du jeu

- **Duree : 1 semaine**, demo a la fin. Rythme indicatif : J1-J2 cleanup + modele de donnees, J3-J4 scoring + push + schema d'enrichissement, J5 dashboard.
- **Stack libre.** On juge le resultat et la logique, pas les outils.
- **Deploye**, pas en localhost. Ton infra, ton choix.
- **IA bienvenue.** Utilise Claude, GPT, ce que tu veux — mais tu dois pouvoir defendre chaque ligne de logique comme si tu l'avais ecrite.
- Des questions ? Pose-les. Un GTM engineer qui n'interroge pas le brief est plus inquietant qu'un qui le challenge.

---

## Dictionnaire des donnees

### accounts.csv

| Champ | Note |
|---|---|
| `account_id` | Identifiant unique du record (pas de l'entreprise…) |
| `account_name` | Nom — formats incoherents |
| `domain` | Parfois vide, parfois prefixe www. |
| `industry`, `employee_range` | Parfois vides |
| `country` | Formats incoherents (FR / France / france…) |
| `lifecycle_stage` | lead / prospect / opportunity / customer / churned / lost — pas toujours fiable |
| `created_date`, `last_activity_date` | **Trois formats de date coexistent** |
| `owner` | Sales owner, parfois vide |
| `arr_eur` | Rempli pour customers (et churned) |
| `renewal_date` | Rempli pour customers… normalement |

### contacts.csv

| Champ | Note |
|---|---|
| `contact_id`, `account_id` | Des contacts orphelins existent (account_id vide) |
| `email` | Parfois vide, malforme, ou perso (gmail) |
| `job_title` | Du CHRO au stagiaire — a toi de definir qui compte |
| `opted_out` | true/false — reflechis a ce que ca implique |
| `created_date` | Memes formats incoherents |

### events.csv

| Champ | Note |
|---|---|
| `event_id`, `timestamp` | ISO 8601, tries chronologiquement, fenetre de 90 jours |
| `event_type` | email_sent / email_open / email_click / form_fill / meeting_booked / website_visit / linkedin_engagement |
| `contact_id` | Vide pour les visites anonymes |
| `account_id` | Present quand connu — attention, c'est l'id du **record**, pas de l'entreprise |
| `campaign` | Pour les events email |
| `page_url` | Pour les visites web — toutes les pages ne se valent pas |
| `metadata` | Contexte libre |

Bonne chasse.
