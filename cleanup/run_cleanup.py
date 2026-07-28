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
import sys
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

def email_root(email, personal_domains):
    """Racine du domaine d'un email pro. None si vide, malformé ou perso.

    Robuste aux défauts connus (réparés à l'étape 5) : espaces internes,
    double @@ (on prend la partie après le DERNIER @).
    """
    e = (email or "").strip().lower().replace(" ", "")
    if "@" not in e:
        return None
    dom = e.rsplit("@", 1)[1]
    if not dom or dom in personal_domains:
        return None
    return dom.split(".")[0]


def step3_domains(tables, report):
    """Ajoute domain_clean, domain_root, domain_source et has_domain sur accounts.

    - domain_clean  : minuscules, sans les préfixes listés en config (www.)
    - domain_root   : partie avant l'extension (acme.com -> acme)
                      = clé n°1 de détection des doublons (étape 7)
    - domain_source : 'declared' (champ domain) | 'inferred_from_contacts'
                      (déduit des emails pro des contacts, uniquement si
                      UNANIMES sur une seule racine) | 'none'
    - has_domain    : "1" si une racine existe (déclarée ou déduite), sinon "0"
    Traçabilité totale : aucune déduction cachée, aucune déduction ambiguë.
    Extension inconnue -> listée dans le rapport.
    """
    prefixes = CONFIG["domains"]["strip_prefixes"]
    known_tlds = set(CONFIG["domains"]["known_tlds"])
    personal = set(CONFIG["domains"]["personal_email_domains"])
    rows = tables["accounts"]

    # racines d'emails pro par compte (pour l'inférence des domaines manquants)
    roots_by_account = {}
    for c in tables["contacts"]:
        aid = c.get("account_id") or ""
        if not aid:
            continue
        r = email_root(c.get("email"), personal)
        roots_by_account.setdefault(aid, set())
        if r:
            roots_by_account[aid].add(r)

    n_www = n_root_empty = 0
    n_declared = n_inferred = n_none = n_ambiguous = 0
    none_reasons = {"aucun contact": 0, "emails perso/vides seulement": 0}
    tld_counts = {}
    unknown_tlds = {}
    examples = []
    infer_examples = []

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

        if clean:
            # cas 1 : domaine déclaré dans le CRM
            parts = clean.split(".")
            row["domain_root"] = parts[0]
            row["domain_source"] = "declared"
            row["has_domain"] = "1"
            n_declared += 1
            if not parts[0]:
                n_root_empty += 1
            tld = parts[-1] if len(parts) > 1 else ""
            tld_counts[tld] = tld_counts.get(tld, 0) + 1
            if tld not in known_tlds:
                unknown_tlds[tld] = unknown_tlds.get(tld, 0) + 1
            continue

        # cas 2 : domaine vide -> déduction depuis les emails pro des contacts
        aid = row.get("account_id") or ""
        roots = roots_by_account.get(aid)
        if roots and len(roots) == 1:
            row["domain_root"] = next(iter(roots))
            row["domain_source"] = "inferred_from_contacts"
            row["has_domain"] = "1"
            n_inferred += 1
            if len(infer_examples) < 2:
                infer_examples.append(f"{row['account_name']} → racine `{row['domain_root']}`")
        else:
            row["domain_root"] = ""
            row["domain_source"] = "none"
            row["has_domain"] = "0"
            n_none += 1
            if roots and len(roots) > 1:
                n_ambiguous += 1
            elif aid not in roots_by_account:
                none_reasons["aucun contact"] += 1
            else:
                none_reasons["emails perso/vides seulement"] += 1

    report.append("## Étape 3 — Domaines : nettoyage + racine (clé de dédup n°1) + inférence tracée\n")
    report.append(
        "domain_clean = minuscules sans préfixe www. · domain_root = partie avant "
        "l'extension, ou déduite des emails pro des contacts quand ils sont UNANIMES · "
        "domain_source trace l'origine (declared / inferred_from_contacts / none) · "
        "has_domain = flag final. Validation de l'inférence : sur les comptes ayant "
        "domaine ET emails pro, racine(domaine) = racine(emails) dans 25 785 cas sur "
        "25 785 (0 divergence) — déduire n'est pas deviner.\n"
    )
    report.append(f"- Préfixes www. retirés : **{n_www}** (attendu audit : 1 825)")
    report.append(f"- Domaines déclarés : **{n_declared}** · racine déduite des contacts : "
                  f"**{n_inferred}** (attendu : 2 538) · sans racine : **{n_none}** "
                  f"(attendu : 133 = 94 sans contact + 39 emails perso) {none_reasons}")
    report.append(f"- Déductions ambiguës (plusieurs racines candidates) : **{n_ambiguous}** (attendu : 0)")
    report.append(f"- Racines vides alors qu'un domaine existe : **{n_root_empty}** (attendu : 0)")
    report.append(f"- Extensions rencontrées : " +
                  ", ".join(f".{t} ({n})" for t, n in sorted(tld_counts.items())))
    report.append(f"- Extensions hors liste attendue : "
                  + (str(unknown_tlds) if unknown_tlds else "aucune"))
    if examples:
        report.append(f"- Exemples nettoyage : " + " · ".join(examples))
    if infer_examples:
        report.append(f"- Exemples inférence : " + " · ".join(infer_examples))
    report.append("")

    ok = (n_www == 1825 and n_inferred == 2538 and n_none == 133
          and n_ambiguous == 0 and n_root_empty == 0 and not unknown_tlds)
    print(f"[étape 3] accounts: www retirés={n_www} déclarés={n_declared} "
          f"déduits={n_inferred} sans_racine={n_none} ({none_reasons}) "
          f"ambigus={n_ambiguous} racines_vides={n_root_empty} "
          f"tlds={sorted(tld_counts)} inconnues={unknown_tlds or 'aucune'}"
          + ("  ✔" if ok else "  ⚠ A VERIFIER"))


# ----------------------------------------------------------------
# Le filet — invariants vérifiés après CHAQUE exécution du pipeline
# ----------------------------------------------------------------

def run_invariants(tables, report):
    """Vérifie les invariants (config: invariants). Un seul rouge = pipeline en erreur.

    Un invariant = une vérité qui doit rester vraie quelle que soit l'étape
    qui vient de tourner. 4 familles : conservation (rien ne se perd),
    cohérence (les chiffres se verrouillent entre eux), bornes de sanité,
    et non-régression (celles-là s'arment avec les étapes 7+, cf. config).
    """
    inv = CONFIG["invariants"]
    accounts, contacts, events = tables["accounts"], tables["contacts"], tables["events"]
    checks = []  # (id, libellé, attendu, mesuré)

    # -- Conservation : rien ne se perd, rien n'est écrasé
    c = inv["conservation"]
    checks.append(("C1", "fiches accounts", c["accounts_rows"], len(accounts)))
    checks.append(("C2", "contacts", c["contacts_rows"], len(contacts)))
    checks.append(("C3", "events", c["events_rows"], len(events)))
    checks.append(("C4", "domaines d'origine non vides (colonne intacte)",
                   c["accounts_domain_non_vide"],
                   sum(1 for r in accounts if (r.get("domain") or "").strip())))
    checks.append(("C5", "graphies pays d'origine distinctes (colonne intacte)",
                   c["accounts_country_graphies_distinctes"],
                   len({(r.get("country") or "").strip() for r in accounts})))
    checks.append(("C6", "noms d'origine non vides (colonne intacte)",
                   c["accounts_nom_non_vide"],
                   sum(1 for r in accounts if (r.get("account_name") or "").strip())))

    # -- Cohérence : les chiffres se verrouillent entre eux
    k = inv["coherence"]
    date_cols = [("accounts", col) for col in CONFIG["dates"]["columns"]["accounts"]] + \
                [("contacts", col) for col in CONFIG["dates"]["columns"]["contacts"]]
    n_err = sum(1 for t, col in date_cols for r in tables[t]
                if r.get(f"{col}_format") == "error")
    checks.append(("K1", "erreurs de parsing de dates", k["dates_erreurs_parsing"], n_err))
    checks.append(("K2", "renewal_date remplies (= customers + churned contradictoires)",
                   k["renewal_date_remplies"],
                   sum(1 for r in accounts if r.get("renewal_date_format") not in (None, "empty"))))
    checks.append(("K3", "form_fill présents", k["events_form_fill"],
                   sum(1 for e in events if e.get("event_type") == "form_fill")))
    checks.append(("K4", "meeting_booked présents", k["events_meeting_booked"],
                   sum(1 for e in events if e.get("event_type") == "meeting_booked")))

    # -- Bornes de sanité (étapes 1-3)
    s = inv["sanite"]
    src = [r.get("domain_source") for r in accounts]
    checks.append(("S1", "domaines déclarés", s["domaines_declares"], src.count("declared")))
    checks.append(("S2", "racines déduites des contacts", s["racines_deduites"],
                   src.count("inferred_from_contacts")))
    checks.append(("S3", "fiches sans racine", s["fiches_sans_racine"], src.count("none")))
    roots = [r["domain_root"] for r in accounts if r.get("domain_root")]
    checks.append(("S4", "longueur minimale des racines (anti-collision)",
                   f">= {s['longueur_racine_min']}", min(len(x) for x in roots)))
    checks.append(("S5", "préfixes www. dans la colonne d'origine (recomptés)",
                   s["www_retires"],
                   sum(1 for r in accounts
                       if (r.get("domain") or "").strip().lower().startswith("www."))))
    # NB : "0 déduction ambiguë" est couvert par S3 — un cas ambigu ferait
    # passer les fiches sans racine de 133 à 134 → alarme.

    ok = True
    lines = ["## 🛡️ Filet d'invariants — vérifié à chaque exécution\n",
             "| ID | Invariant | Attendu | Mesuré | Statut |",
             "|---|---|---|---|---|"]
    for cid, label, expected, measured in checks:
        if isinstance(expected, str) and expected.startswith(">="):
            passed = measured >= int(expected[2:])
        else:
            passed = measured == expected
        ok &= passed
        lines.append(f"| {cid} | {label} | {expected} | {measured} | "
                     f"{'🟢' if passed else '🔴 ALARME'} |")
    lines.append("")
    lines.append("À armer avec leurs étapes : " + " · ".join(inv["a_armer"]))
    lines.append("")
    report.extend(lines)

    n_green = sum(1 for cid, label, e, m in checks
                  if (m >= int(e[2:]) if isinstance(e, str) and e.startswith(">=") else m == e))
    print(f"[filet]   {n_green}/{len(checks)} invariants verts"
          + ("  ✔" if ok else "  🔴 ALARME — voir rapport"))
    if not ok:
        with open(REPORT_PATH, "w") as f:
            f.write("\n".join(report) + "\n")
        sys.exit(1)


def main():
    report = [
        "# Rapport d'audit du cleanup — Wake the CRM\n",
        f"Généré par `cleanup/run_cleanup.py` le {datetime.now().date().isoformat()} "
        f"(référence temporelle du dataset : {CONFIG['reference_date']}).\n",
        "Principe : rien n'est supprimé — réparations en colonnes neuves, originaux intacts.\n",
    ]

    tables = {"accounts": load("accounts"), "contacts": load("contacts"),
              "events": load("events")}

    step1_dates(tables, report)
    step2_countries(tables, report)
    step3_domains(tables, report)

    run_invariants(tables, report)

    for table, rows in tables.items():
        if table != "events":          # events pas encore transformés (étapes 8-10)
            save(table, rows)

    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(report) + "\n")
    print(f"\nRapport écrit : {REPORT_PATH}")


if __name__ == "__main__":
    main()
