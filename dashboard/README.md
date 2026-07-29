# Le tableau de bord

Fichier unique, sans dépendance : `index.html` (~74 ko). Les données sont chargées
à côté — `wtc.json` pour les vues Macro / Logique / Ops, `tables/<table>.json`
pour l'explorateur, une table à la fois.

    dashboard/
      index.html          le rendu (4 vues : Macro · Logique · Ops · Données)
      _headers            en-têtes Netlify (types MIME, cache des tables)
      build/
        build_tables.py   dashboard_data/*.csv  ->  tables/<table>.json
        build_wtc.py      dashboard_data/       ->  wtc.json

Publié sur https://wake-the-crm.netlify.app — chaque déploiement est conservé,
le retour arrière est immédiat.

**Ce fichier n'était versionné nulle part jusqu'ici : il ne vivait que dans le
répertoire de travail d'une session.** Un conteneur recyclé et le rendu était
perdu, alors que les données, elles, étaient à l'abri depuis le début.
