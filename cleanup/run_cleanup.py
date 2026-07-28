#!/usr/bin/env python3
"""Pipeline de cleanup — Wake the CRM.

Principe cardinal : RIEN n'est supprimé ni écrasé.
Chaque réparation vit dans une colonne neuve (*_parsed, *_format, *_clean, *_flag),
les colonnes d'origine restent intactes, et chaque règle écrit ses
compteurs + exemples dans cleanup_report.md (audit poste par poste).

Usage : python3 cleanup/run_cleanup.py   (depuis la racine du repo)
Sorties : data_clean/*.csv + cleanup_report.md
"""

import csv
import os
from datetime import datetime

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data_clean")
REPORT_PATH = os.path.join(ROOT, "cleanup_report.md")

with open(os.path.join(ROOT, "cleanup", "cleanup_config.yaml")) as f:
    CONFIG = yaml.safe_load(f)


def load(table):
    with open(os.path.join(ROOT, f"{table}.csv"), newline="") as f:
        return list(csv.DictReader(f))


def save(table, rows):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"{table}_clean.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ----------------------------------------------------------------
# Étape 1 — Les dates : 3 formats -> 1 (ISO), sans toucher l'original
# ----------------------------------------------------------------

def parse_date(raw):
    """Convertit une date du CRM en ISO. Retourne (iso, format).

    format ∈ {iso, mdy, dmy, empty, error} :
      - iso   : déjà au format 2022-12-13
      - mdy   : 05/19/24  -> année à 2 chiffres = MM/DD/YY (américain)
      - dmy   : 21/03/2022 -> année à 4 chiffres = DD/MM/YYYY (français)
    Règle du discriminant prouvée en amont : 0 contre-exemple sur ~90 000 dates.
    Une date illisible n'est JAMAIS devinée : elle sort en "error", vide.
    """
    if raw is None or not raw.strip():
        return "", "empty"
    s = raw.strip()
    if "-" in s:
        try:
            return datetime.strptime(s, "%Y-%m-%d").date().isoformat(), "iso"
        except ValueError:
            return "", "error"
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            year = parts[2]
            fmt = ("%m/%d/%y", "mdy") if len(year) == 2 else ("%d/%m/%Y", "dmy")
            try:
                return datetime.strptime(s, fmt[0]).date().isoformat(), fmt[1]
            except ValueError:
                return "", "error"
    return "", "error"


def step1_dates(tables, report):
    """Ajoute <col>_parsed (ISO) et <col>_format sur accounts et contacts."""
    lo, hi = CONFIG["dates"]["plausible_years"]
    report.append("## Étape 1 — Dates : 3 formats → ISO\n")
    report.append(
        "Règle : ISO tel quel · année à 2 chiffres = MM/DD/YY (américain) · "
        "année à 4 chiffres = DD/MM/YYYY (français). "
        "Aucune date devinée : illisible → vide + format `error`.\n"
    )

    for table, columns in CONFIG["dates"]["columns"].items():
        rows = tables[table]
        stats = {c: {"iso": 0, "mdy": 0, "dmy": 0, "empty": 0, "error": 0} for c in columns}
        examples = {c: [] for c in columns}
        out_of_range = {c: 0 for c in columns}

        for row in rows:
            for c in columns:
                iso, fmt = parse_date(row.get(c, ""))
                row[f"{c}_parsed"] = iso
                row[f"{c}_format"] = fmt
                stats[c][fmt] += 1
                if iso and not (lo <= int(iso[:4]) <= hi):
                    out_of_range[c] += 1
                if fmt in ("mdy", "dmy") and len(examples[c]) < 2:
                    examples[c].append(f"`{row[c]}` → `{iso}` ({fmt})")

        report.append(f"### {table}.csv ({len(rows)} lignes)\n")
        report.append("| Colonne | ISO | MM/DD/YY | DD/MM/YYYY | Vides | Erreurs | Hors bornes |")
        report.append("|---|---|---|---|---|---|---|")
        for c in columns:
            s = stats[c]
            report.append(
                f"| {c} | {s['iso']} | {s['mdy']} | {s['dmy']} | {s['empty']} | "
                f"{s['error']} | {out_of_range[c]} |"
            )
        report.append("")
        for c in columns:
            if examples[c]:
                report.append(f"Exemples {c} : " + " · ".join(examples[c]))
        report.append("")

        print(f"[étape 1] {table}: {len(rows)} lignes")
        for c in columns:
            s = stats[c]
            total_err = s["error"] + out_of_range[c]
            print(f"          {c}: iso={s['iso']} mdy={s['mdy']} dmy={s['dmy']} "
                  f"vides={s['empty']} erreurs={s['error']} hors_bornes={out_of_range[c]}"
                  + ("  ✔" if total_err == 0 else "  ⚠ A VERIFIER"))


# ----------------------------------------------------------------
# Étape 2 — Les pays : 30 graphies -> 8 codes ISO, via la table en config
# ----------------------------------------------------------------

def step2_countries(tables, report):
    """Ajoute country_clean (code ISO) sur accounts. Inconnu -> vide + compté."""
    mapping = CONFIG["countries"]["mapping"]
    canonical = CONFIG["countries"]["canonical"]
    rows = tables["accounts"]

    counts = {iso: 0 for iso in canonical}
    unmapped = {}
    variants_seen = set()

    for row in rows:
        raw = (row.get("country") or "").strip()
        key = raw.lower()
        iso = mapping.get(key, "")
        row["country_clean"] = iso
        if iso:
            counts[iso] += 1
            variants_seen.add(key)
        else:
            unmapped[raw] = unmapped.get(raw, 0) + 1

    report.append("## Étape 2 — Pays : 30 graphies → 8 codes ISO 3166\n")
    report.append(
        "Table de correspondance en config (cleanup_config.yaml). "
        "Une graphie absente de la table n'est jamais devinée : vide + listée ici.\n"
    )
    report.append("| Pays | Code | Fiches |")
    report.append("|---|---|---|")
    for iso, label in canonical.items():
        report.append(f"| {label} | {iso} | {counts[iso]} |")
    total_mapped = sum(counts.values())
    report.append("")
    report.append(f"Graphies distinctes reconnues : {len(variants_seen)} · "
                  f"fiches mappées : {total_mapped}/{len(rows)} · "
                  f"non mappées : {sum(unmapped.values())}"
                  + (f" ({unmapped})" if unmapped else ""))
    report.append("")

    print(f"[étape 2] accounts: {total_mapped}/{len(rows)} fiches mappées sur "
          f"{len(canonical)} pays, {len(variants_seen)} graphies reconnues, "
          f"non mappées: {sum(unmapped.values())}"
          + ("  ✔" if not unmapped else f"  ⚠ {unmapped}"))


# ----------------------------------------------------------------
# Étape 3 — Les domaines : www./casse -> domain_clean, racine -> domain_root
# ----------------------------------------------------------------

def step3_domains(tables, report):
    """Ajoute domain_clean, domain_root et has_domain sur accounts.

    - domain_clean : minuscules, sans les préfixes listés en config (www.)
    - domain_root  : partie avant l'extension (acme.com -> acme)
                     = clé n°1 de détection des doublons (étape 7)
    - has_domain   : "1"/"0" — les fiches sans domaine s'appuieront sur le NOM
    Aucun domaine n'est inventé. Extension inconnue -> listée dans le rapport.
    """
    prefixes = CONFIG["domains"]["strip_prefixes"]
    known_tlds = set(CONFIG["domains"]["known_tlds"])
    rows = tables["accounts"]

    n_www = n_empty = n_root_empty = 0
    tld_counts = {}
    unknown_tlds = {}
    examples = []

    for row in rows:
        raw = (row.get("domain") or "").strip()
        clean = raw.lower()
        for p in prefixes:
            if clean.startswith(p):
                clean = clean[len(p):]
                n_www += 1
                if len(examples) < 2:
                    examples.append(f"`{raw}` → `{clean}`")
                break
        row["domain_clean"] = clean
        if not clean:
            n_empty += 1
            row["domain_root"] = ""
            row["has_domain"] = "0"
            continue
        row["has_domain"] = "1"
        parts = clean.split(".")
        row["domain_root"] = parts[0]
        if not parts[0]:
            n_root_empty += 1
        tld = parts[-1] if len(parts) > 1 else ""
        tld_counts[tld] = tld_counts.get(tld, 0) + 1
        if tld not in known_tlds:
            unknown_tlds[tld] = unknown_tlds.get(tld, 0) + 1

    report.append("## Étape 3 — Domaines : nettoyage + racine (clé de dédup n°1)\n")
    report.append(
        "domain_clean = minuscules sans préfixe www. · domain_root = partie avant "
        "l'extension · has_domain = flag pour les fiches sans domaine "
        "(la fusion s'appuiera sur le nom pour elles). Aucun domaine inventé.\n"
    )
    report.append(f"- Préfixes www. retirés : **{n_www}** (attendu audit : 1 825)")
    report.append(f"- Fiches sans domaine : **{n_empty}** (attendu audit : 2 671) → has_domain=0")
    report.append(f"- Racines vides alors qu'un domaine existe : **{n_root_empty}** (attendu : 0)")
    report.append(f"- Extensions rencontrées : " +
                  ", ".join(f".{t} ({n})" for t, n in sorted(tld_counts.items())))
    report.append(f"- Extensions hors liste attendue : "
                  + (str(unknown_tlds) if unknown_tlds else "aucune"))
    if examples:
        report.append(f"- Exemples : " + " · ".join(examples))
    report.append("")

    print(f"[étape 3] accounts: www retirés={n_www} sans_domaine={n_empty} "
          f"racines_vides={n_root_empty} tlds={sorted(tld_counts)} "
          f"inconnues={unknown_tlds or 'aucune'}"
          + ("  ✔" if n_www == 1825 and n_empty == 2671 and n_root_empty == 0
             and not unknown_tlds else "  ⚠ A VERIFIER"))


def main():
    report = [
        "# Rapport d'audit du cleanup — Wake the CRM\n",
        f"Généré par `cleanup/run_cleanup.py` le {datetime.now().date().isoformat()} "
        f"(référence temporelle du dataset : {CONFIG['reference_date']}).\n",
        "Principe : rien n'est supprimé — réparations en colonnes neuves, originaux intacts.\n",
    ]

    tables = {"accounts": load("accounts"), "contacts": load("contacts")}

    step1_dates(tables, report)
    step2_countries(tables, report)
    step3_domains(tables, report)

    for table, rows in tables.items():
        save(table, rows)

    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(report) + "\n")
    print(f"\nRapport écrit : {REPORT_PATH}")


if __name__ == "__main__":
    main()
