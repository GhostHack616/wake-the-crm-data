#!/usr/bin/env python3
"""Pipeline de cleanup — Wake the CRM.

Principe cardinal : RIEN n'est supprimé ni écrasé.
Chaque réparation vit dans une colonne neuve (*_parsed, *_format, *_flag),
les colonnes d'origine restent intactes, et chaque règle écrit ses
compteurs + exemples dans cleanup_report.md (audit poste par poste).

Usage : python3 cleanup/run_cleanup.py   (depuis la racine du repo)
Sorties : data_clean/*.csv + cleanup_report.md
"""

import csv
import os
import sys
from datetime import datetime

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data_clean")
REPORT_PATH = os.path.join(ROOT, "cleanup_report.md")

with open(os.path.join(ROOT, "cleanup", "cleanup_config.yaml")) as f:
    CONFIG = yaml.safe_load(f)


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


def step1_dates(report):
    """Ajoute <col>_parsed (ISO) et <col>_format à accounts et contacts."""
    lo, hi = CONFIG["dates"]["plausible_years"]
    report.append("## Étape 1 — Dates : 3 formats → ISO\n")
    report.append(
        "Règle : ISO tel quel · année à 2 chiffres = MM/DD/YY (américain) · "
        "année à 4 chiffres = DD/MM/YYYY (français). "
        "Aucune date devinée : illisible → vide + format `error`.\n"
    )

    for table, columns in CONFIG["dates"]["columns"].items():
        src = os.path.join(ROOT, f"{table}.csv")
        dst = os.path.join(OUT_DIR, f"{table}_clean.csv")
        with open(src, newline="") as f:
            rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys())

        stats = {c: {"iso": 0, "mdy": 0, "dmy": 0, "empty": 0, "error": 0} for c in columns}
        examples = {c: [] for c in columns}
        out_of_range = {c: 0 for c in columns}

        for row in rows:
            for c in columns:
                iso, fmt = parse_date(row.get(c, ""))
                row[f"{c}_parsed"] = iso
                row[f"{c}_format"] = fmt
                stats[c][fmt] += 1
                if iso:
                    year = int(iso[:4])
                    if not (lo <= year <= hi):
                        out_of_range[c] += 1
                if fmt in ("mdy", "dmy") and len(examples[c]) < 2:
                    examples[c].append(f"`{row[c]}` → `{iso}` ({fmt})")

        for c in columns:
            fieldnames += [f"{c}_parsed", f"{c}_format"]

        os.makedirs(OUT_DIR, exist_ok=True)
        with open(dst, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        report.append(f"### {table}.csv → data_clean/{table}_clean.csv ({len(rows)} lignes)\n")
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

        print(f"[étape 1] {table}: {len(rows)} lignes, colonnes ajoutées: "
              + ", ".join(f"{c}_parsed/{c}_format" for c in columns))
        for c in columns:
            s = stats[c]
            total_err = s["error"] + out_of_range[c]
            print(f"          {c}: iso={s['iso']} mdy={s['mdy']} dmy={s['dmy']} "
                  f"vides={s['empty']} erreurs={s['error']} hors_bornes={out_of_range[c]}"
                  + ("  ✔" if total_err == 0 else "  ⚠ A VERIFIER"))


def main():
    report = [
        "# Rapport d'audit du cleanup — Wake the CRM\n",
        f"Généré par `cleanup/run_cleanup.py` le {datetime.now().date().isoformat()} "
        f"(référence temporelle du dataset : {CONFIG['reference_date']}).\n",
        "Principe : rien n'est supprimé — réparations en colonnes neuves, originaux intacts.\n",
    ]
    step1_dates(report)
    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(report) + "\n")
    print(f"\nRapport écrit : {REPORT_PATH}")


if __name__ == "__main__":
    main()
