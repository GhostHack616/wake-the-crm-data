# L'architecture d'enrichissement — schéma + protocole

> Le brief : *« Le CRM a 8 ans. Rien ne garantit que ses champs sont encore vrais… Cette partie est
> un exercice d'architecture, sur schéma. »* Données fictives → aucun appel réel n'a été fait ;
> tout ce qui suit est dimensionné sur les volumes **mesurés** dans ce CRM.

**Le principe directeur, hérité du cleanup : un trou de données se répare, un refus se respecte.**
Et rien ne s'écrase jamais : chaque donnée enrichie arrive dans une colonne neuve, avec sa source
et sa date — exactement comme les colonnes `_clean` du pipeline.

```mermaid
flowchart TD
    subgraph DETECTE["1 · DÉTECTER (gratuit — déjà fait par le pipeline)"]
        A["contacts_a_enrichir.csv — 5 371 contacts<br/>3 031 sans adresse + 2 340 en adresse perso<br/>dont 912 avec historique email (l'adresse a existé)<br/>et 63 vus sur LinkedIn"]
        B["4 554 contacts sans titre<br/>(multiplicateur en aveugle ×0,5)"]
        C["firmographique périmé : effectifs, secteur<br/>(8 ans d'âge, 89 % de contradiction sur le secteur)"]
        D["2 729 comptes sans commercial"]
    end

    subgraph GATE["2 · LES GATES (on n'enrichit JAMAIS 20 519 comptes à l'aveugle)"]
        G1{"Le compte est-il<br/>dans une file de travail ?"}
        G1 -->|"Tier 1 (26)"| GO1["enrichissement IMMÉDIAT<br/>toutes données, tous providers"]
        G1 -->|"Tier 2 (34)"| GO2["enrichissement HEBDO<br/>adresses + titres seulement"]
        G1 -->|"Tier 3"| GO3["JAMAIS d'enrichissement auto<br/>refresh uniquement si le compte<br/>repasse une porte"]
    end

    subgraph WATER["3 · LE WATERFALL (s'arrêter au premier qui trouve)"]
        W1["Dropcontact<br/>(adresses pro, RGPD-first, ~0,02 €)"] --> W2["BetterContact / Kaspr<br/>(fallback multi-sources, ~0,15 €)"]
        W2 --> W3["LinkedIn Sales Navigator<br/>(titres + les 63 déjà vus, manuel assisté)"]
    end

    subgraph SIGNAUX["4 · SIGNAUX EXTERNES (le manque n°1 mesuré)"]
        S1["Tracking des liens email + rattrapage<br/>rétroactif au formulaire<br/>= ×10 à ×24 de signal d'intention identifié<br/>(41 087 envois partent déjà — coût ≈ 0)"]
        S2["Dé-anonymisation IP (Leadfeeder/Albacross)<br/>taux réels 30-75 % au niveau entreprise<br/>— les 4 000 visites anonymes du fichier"]
        S3["Offres d'emploi publiées (scraping ATS/job boards)<br/>une boîte qui recrute a besoin d'un ATS :<br/>LE signal de timing de la verticale RH — V2"]
    end

    DETECTE --> GATE
    GO1 --> WATER
    GO2 --> WATER
    WATER --> MAJ["5 · ÉCRITURE<br/>colonnes neuves : valeur + source + date<br/>jamais d'écrasement — rollback possible"]
    SIGNAUX --> MAJ
    MAJ --> INV["6 · INVARIANTS<br/>compteurs de la file sous garde (E1)<br/>+ hygiène mensuelle : une base se périme à 2-3 %/mois"]
    MAJ --> SCORE["…et le moteur de scoring relit<br/>des données fraîches au run suivant"]
```

## Le protocole écrit — quoi, avec quoi, quand, à quel coût

**QUOI (par ordre de valeur mesurée)**
1. **Adresses email pro** — 5 371 contacts en file, priorisés par les colonnes du livrable :
   `adresse_a_existe` (912 — les plus faciles : le CRM l'a perdue), `linkedin_vu` (63),
   `persona_tier` (décideurs d'abord), `nb_events_net` (actifs d'abord).
2. **Titres manquants** — 4 554 contacts scorés en aveugle (×0,5) ; chaque titre récupéré
   précise le multiplicateur ET le comité d'achat.
3. **Signal d'intention identifié** — le manque structurel n°1 : 95 %+ des visites d'intention
   sont anonymes. Tracking des liens + rattrapage rétroactif = ×10-24 ; dé-anonymisation IP en
   complément (30-75 % de reconnaissance réelle, pas les 90 % des plaquettes).
4. **Firmographique** (effectifs, secteur) — en dernier : utile au fit, jamais au score.

**AVEC QUOI** — waterfall « s'arrêter au premier qui trouve » : Dropcontact (RGPD, pas de base
propriétaire, idéal Europe) → BetterContact/Kaspr (fallback) → LinkedIn (titres, manuel assisté).
Signaux : n8n pour l'orchestration (tracking, webhooks), Leadfeeder/Albacross pour l'IP.

**QUAND** — jamais de batch aveugle. Les déclencheurs : entrée en Tier 1 (immédiat, complet) ·
présence en Tier 2 (hebdo, adresses+titres) · nouveau contact entrant (à l'ingestion) ·
hygiène mensuelle sur les comptes ACTIFS uniquement. Tier 3 : rien, jamais — c'est le gate
qui protège le budget.

**À QUEL COÛT** — dimensionné sur NOS volumes : file complète ≈ 5 371 × 0,02-0,15 € ≈
**110-800 € one-shot** si on la vidait — donc on ne la vide pas : gates par file →
Tier 1+2 ≈ 60 comptes ≈ **quelques euros par semaine** en régime de croisière. Le tracking
email : **coût ≈ 0** (les envois partent déjà). Budget mensuel borné en config, compteur
sous invariant — un dépassement est une alarme, pas une surprise.

**LA RÈGLE QUI NE BOUGE JAMAIS** — l'opt-out est individuel et définitif pour le canal email :
l'enrichissement peut trouver une NOUVELLE personne (et rouvrir un compte « perdu — canal mort »
proprement), il ne « répare » jamais un refus.
