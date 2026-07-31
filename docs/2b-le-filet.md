# 2b — Le Filet : l'intégration continue, mais pour le CRM

*Réponse au volet 2b du challenge (« l'outil GTM que tu as toujours voulu avoir »). Le livrable demandé : un raisonnement + un schéma + en option un prototype rugueux. Les trois sont ici — le prototype tourne dans `filet/`.*

## Le problème

Cette semaine l'a prouvé : 8 ans sans entretien, et il faut 12 étapes de nettoyage et 119 contrôles pour retrouver la vérité. Mais le nettoyage est un **événement** ; la dérive est un **processus**. Dès lundi, chaque écriture — un sales pressé, un import marketing, un workflow mal branché — peut recréer la salissure qu'on vient de gratter. Le marché ne propose que deux parades : la validation à la saisie (un champ mal formaté) et l'audit périodique — mensuel ou trimestriel, c'est le rythme que les vendeurs d'outils recommandent eux-mêmes. Entre les deux, rien ne surveille en continu, et surtout : **rien ne bloque**. L'envoi vers un désabonné part, puis un rapport le déplore trois semaines plus tard.

L'outil qui me manque : un filet qui attrape la faute **au moment où elle arrive**, pas au prochain audit.

## Pourquoi maintenant

On commence à laisser des agents IA écrire dans les CRM — enrichissement, séquences, mises à jour automatiques. La dérive qui prenait 8 ans à des humains prendra 8 semaines à des machines, parce que personne ne relit ce qu'elles écrivent. Ce n'est pas de la méfiance envers l'IA : c'est précisément **parce qu'on va laisser des machines écrire qu'il faut des machines qui relisent**. Le filet est la condition pour accélérer sans peur, pas un frein.

## Comment ça marche

```mermaid
flowchart LR
    subgraph E["Qui écrit dans le CRM"]
        S1[Sales] --> CRM[(CRM)]
        S2[Imports / workflows] --> CRM
        S3[Agents IA] --> CRM
    end
    R[("filet_rules.yaml<br/>1 règle = 1 ligne métier")] -.-> F{{"LE FILET<br/>à chaque run, à chaque écriture"}}
    CRM --> F
    F -->|compter| M["🧮 Métrique au rapport<br/>(tendance, seuils)"]
    F -->|sonner| A["🔔 Alerte Slack<br/>(le run continue)"]
    F -->|bloquer| B["⛔ La sortie ne part pas<br/>envoi bloqué · build cassé"]
```

Trois principes, tous hérités de la machine construite cette semaine :

- **Une règle = une ligne en langage métier**, dans une config (« un désabonné ne reçoit jamais un envoi »). Pas de SQL, pas de notebook : la personne qui possède la règle est un RevOps, pas un data engineer. Config, pas code — comme le scoring.
- **Trois réactions graduées** : `compter` (métrique), `sonner` (alerte), `bloquer` (la sortie ne part pas — exit 1, le build casse). C'est la différence avec tout ce qui existe : le filet n'écrit pas un rapport, il **arrête l'envoi**.
- **Continu** : le filet tourne à chaque exécution du pipeline et, en cible, à chaque écriture CRM (webhook). Pas d'audit trimestriel — une vérité constatée à chaque run, jamais déclarée.

## Le prototype (rugueux, volontairement)

`filet/run_filet.py` + `filet/filet_rules.yaml` : 6 règles branchées sur les sorties réelles de la machine (hot list, scores, companies, contacts). Trois en `bloquer` (désabonnés, contradictions churned/deal non arbitrées, bots dans les scores), deux en `sonner`, une en `compter` avec seuil qui monte d'un cran s'il déborde.

```bash
python3 filet/run_filet.py               # vert aujourd'hui, exit 0 -> filet/filet_report.md
python3 filet/run_filet.py --demo-panne  # injecte 2 pannes en mémoire -> FILET ROUGE, exit 1
```

Le filet est **vert aujourd'hui** — normal, le nettoyage vient de passer ; sa valeur, c'est demain. Le mode démo injecte deux pannes réalistes (un désabonnement arrivé *après* la construction de la hot list, une contradiction qui sort de la file de review) et montre le blocage en live, violations nommées.

Ce proto n'est pas sorti de nulle part : c'est la **généralisation des 119 contrôles internes** qui cassent déjà le build du pipeline. La V0 existait en germe toute la semaine — le filet la rend configurable et la tourne vers l'action (l'envoi), plus seulement vers le build.

## Où ça casse (dit avant qu'on me le demande)

1. **La fatigue d'alerte** — le cimetière de tous ces outils. Un filet qui sonne dix fois par jour est débranché en deux semaines. Parade dans la doctrine V0 : une règle qui sonne sans provoquer d'action redescend en `compter` — ou meurt.
2. **Bloquer a un coût.** Un blocage à tort sur une campagne urgente, et on débranche le filet. D'où : `bloquer` est réservé aux règles à zéro faux positif connu (désabonné, bot, contradiction non arbitrée) ; tout le reste naît en `sonner` et doit mériter sa promotion.
3. **Une règle sans owner est un dogme.** Chaque règle porte un responsable qui peut la défendre ou l'enterrer ; sinon la config devient le nouveau CRM sale.
4. **Le filet repose sur le modèle de données.** Il ne vaut que si `entity_id`, `opted_out`, les statuts d'email sont fiables — donc il vient *après* un cleanup, jamais à sa place.

## Le marché en trois lignes (vérifié le 31/07)

- **Côté data** : la discipline existe — observabilité et data contracts (Monte Carlo, Soda, tests dbt) — mais tout vit sur le warehouse, en SQL, pour des équipes data.
- **Côté CRM** : nettoyage et validation de saisie (Insycle, Validity, règles natives HubSpot/Salesforce), avec des audits mensuels ou trimestriels.
- **Le trou** : du **continu** + en **langage métier** + qui **bloque l'action**. Personne n'est posé dessus.

Sources : [ZUUZ — CRM data quality tools 2026](https://zuuz.ai/blogs/crm-data-quality-tools/) · [FastSlowMotion — data quality audits HubSpot](https://www.fastslowmotion.com/data-quality-audits-hubspot/) · [Datacoves — beyond dbt tests](https://datacoves.com/post/dbt-data-quality-tools) · [dbt Labs — data observability](https://www.getdbt.com/blog/data-observability) · [Landbase — CRM data audit RevOps 2026](https://www.landbase.com/blog/crm-data-audit-2026-step-by-step-revops)
