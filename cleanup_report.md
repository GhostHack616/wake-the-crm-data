# Rapport d'audit du cleanup — Wake the CRM

Généré par `cleanup/run_cleanup.py` le 2026-07-27 (référence temporelle du dataset : 2026-07-22).

Principe : rien n'est supprimé — réparations en colonnes neuves, originaux intacts.

## Étape 1 — Dates : 3 formats → ISO

Règle : ISO tel quel · année à 2 chiffres = MM/DD/YY (américain) · année à 4 chiffres = DD/MM/YYYY (français). Aucune date devinée : illisible → vide + format `error`.

### accounts.csv → data_clean/accounts_clean.csv (30000 lignes)

| Colonne | ISO | MM/DD/YY | DD/MM/YYYY | Vides | Erreurs | Hors bornes |
|---|---|---|---|---|---|---|
| created_date | 9869 | 10079 | 10052 | 0 | 0 | 0 |
| last_activity_date | 8028 | 8195 | 8010 | 5767 | 0 | 0 |
| renewal_date | 1161 | 1090 | 1135 | 26614 | 0 | 0 |

Exemples created_date : `21/03/2022` → `2022-03-21` (dmy) · `08/01/19` → `2019-08-01` (mdy)
Exemples last_activity_date : `05/19/24` → `2024-05-19` (mdy) · `16/05/2026` → `2026-05-16` (dmy)
Exemples renewal_date : `28/03/2027` → `2027-03-28` (dmy) · `05/07/2026` → `2026-07-05` (dmy)

### contacts.csv → data_clean/contacts_clean.csv (77199 lignes)

| Colonne | ISO | MM/DD/YY | DD/MM/YYYY | Vides | Erreurs | Hors bornes |
|---|---|---|---|---|---|---|
| created_date | 25790 | 25693 | 25716 | 0 | 0 | 0 |

Exemples created_date : `04/01/19` → `2019-04-01` (mdy) · `09/26/21` → `2021-09-26` (mdy)

