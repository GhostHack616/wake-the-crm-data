# Le tableau de bord

Fichier unique, sans dépendance : `index.html`. Les données sont chargées à côté —
`wtc.json` pour les vues Macro / Logique / Ops / Process, `tables/<table>.json`
pour l'explorateur, une table à la fois.

    dashboard/
      index.html                     le rendu (5 vues : Macro · Logique · Ops · Données · Process)
      _headers                       en-têtes Netlify (types MIME, cache des tables)
      _redirects                     /sphere/* -> / (l'ancienne préversion)
      build/
        build_dashboard.py           dashboard_data/  ->  dist/wtc.json + dist/tables/
        verifie_ecran.py             l'interdit d'écran, en test bloquant
        steps_all.json               les 12 étapes du nettoyage
      dist/                          produit par le build, jamais versionné

## Qui déploie quoi

**Celui qui possède le fichier possède son déploiement.** La règle est
structurelle, pas décidée au cas par cas :

1. **`dashboard/` appartient au rendu** — donc **le déploiement Netlify lui
   appartient aussi**. Personne d'autre ne publie un écran.
2. **`dashboard_data/` appartient au moteur** — il pousse des données, jamais un
   écran. C'est le build du rendu qui les lit.
3. **Après chaque déploiement, l'autre certifie** : il retélécharge le fichier
   servi et vérifie qu'il est identique **à l'octet** au build du dépôt. L'un
   déploie, l'autre atteste. Chacun un seul chapeau.

## La procédure, en trois commandes

    git pull
    python3 dashboard/build/build_dashboard.py     # -> dashboard/dist/
    # puis publier le contenu de dashboard/dist/

Aucune passe manuelle, aucune dépendance à une machine. Le build **ne calcule
aucun score** : il lit ce que le moteur a décidé, met en forme, et **refuse
d'écrire** si l'écran ne dirait pas la même chose que le moteur — sept contrôles
avant la première ligne écrite. Deux exécutions produisent le même fichier.

Publié sur https://wake-the-crm.netlify.app — chaque déploiement est conservé,
le retour arrière est immédiat.
