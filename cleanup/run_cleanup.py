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
    name = "companies.csv" if table == "companies" else f"{table}_clean.csv"
    with open(os.path.join(OUT_DIR, name), "w", newline="") as f:
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
    report.append(f"Graphies reconnues : {len(variants_seen)} canoniques (30 brutes avant minuscules/trim, invariant C5) · "
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
# Étape 4 — Les noms : normalisation (clé de dédup n°2) + marqueurs de doublon
# ----------------------------------------------------------------

import re


def step4_names(tables, report):
    """Ajoute name_norm et dup_marker sur accounts.

    - name_norm   : minuscules -> retrait des marqueurs de doublon
                    -> retrait itératif des mentions juridiques finales
                    -> retrait de tout ce qui n'est pas lettre/chiffre.
                    = clé n°2 de la fusion (couvre les fiches sans racine).
    - dup_marker  : 'old' | 'import' | '2' | '' — une fiche marquée ne sera
                    JAMAIS choisie comme fiche maîtresse à la fusion.
    Auto-validation massive : name_norm doit être identique à domain_root
    sur 100 % des fiches à domaine déclaré (audit : 27 329/27 329).
    """
    suffixes = sorted(CONFIG["names"]["legal_suffixes"], key=len, reverse=True)
    suffix_re = re.compile(
        r"\s+(" + "|".join(re.escape(s) for s in suffixes) + r")\s*$", re.I)
    rows = tables["accounts"]

    markers = {"old": 0, "import": 0, "2": 0}
    n_empty = 0
    concord_decl = total_decl = 0
    concord_inf = total_inf = 0
    mismatch_examples = []

    for row in rows:
        s = (row.get("account_name") or "").strip().lower()
        marker = ""
        if re.search(r"\(old\)\s*$", s):
            marker = "old"
            s = re.sub(r"\s*\(old\)\s*$", "", s)
        elif re.search(r"-\s*import\s*$", s):
            marker = "import"
            s = re.sub(r"\s*-\s*import\s*$", "", s)
        elif re.search(r"\s2\s*$", s):
            marker = "2"
            s = re.sub(r"\s+2\s*$", "", s)
        if marker:
            markers[marker] += 1
        while True:
            s2 = suffix_re.sub("", s)
            if s2 == s:
                break
            s = s2
        norm = re.sub(r"[^a-z0-9]", "", s)
        row["name_norm"] = norm
        row["dup_marker"] = marker
        if not norm:
            n_empty += 1

        src = row.get("domain_source")
        if src == "declared":
            total_decl += 1
            if norm == row["domain_root"]:
                concord_decl += 1
            elif len(mismatch_examples) < 5:
                mismatch_examples.append(
                    f"{row['account_id']} `{row['account_name']}` → `{norm}` ≠ `{row['domain_root']}`")
        elif src == "inferred_from_contacts":
            total_inf += 1
            if norm == row["domain_root"]:
                concord_inf += 1

    n_distinct = len({r["name_norm"] for r in rows})
    n_markers = sum(markers.values())

    report.append("## Étape 4 — Noms : normalisation (clé de dédup n°2) + marqueurs\n")
    report.append(
        "name_norm = minuscules, sans marqueurs de doublon ni mentions juridiques "
        "(liste en config), sans ponctuation. dup_marker mémorise l'étiquette "
        "trouvée — une fiche marquée ne sera jamais fiche maîtresse.\n"
    )
    report.append(f"- Marqueurs détectés : **{n_markers}** (attendu audit : 234) — "
                  f"(old) {markers['old']}, - import {markers['import']}, ' 2' {markers['2']}")
    report.append(f"- Noms vides après normalisation : **{n_empty}** (attendu : 0)")
    report.append(f"- **Concordance nom↔racine (domaines déclarés) : {concord_decl}/{total_decl}** "
                  f"(attendu : 27 329/27 329 — c'est LE test de validation du geste)")
    report.append(f"- Concordance nom↔racine (racines déduites des emails) : "
                  f"{concord_inf}/{total_inf} (contrôle indépendant bonus)")
    report.append(f"- Noms normalisés distincts : **{n_distinct}** "
                  f"(borne de sanité : 19 000 - 22 000 = future taille de la table entreprises)")
    if mismatch_examples:
        report.append("- ⚠ Discordances : " + " · ".join(mismatch_examples))
    report.append("")

    ok = (n_markers == 234 and n_empty == 0 and concord_decl == total_decl == 27329
          and 19000 <= n_distinct <= 22000)
    print(f"[étape 4] accounts: marqueurs={n_markers} ({markers}) vides={n_empty} "
          f"concordance_déclarés={concord_decl}/{total_decl} "
          f"concordance_déduits={concord_inf}/{total_inf} distincts={n_distinct}"
          + ("  ✔" if ok else "  ⚠ A VERIFIER"))


# ----------------------------------------------------------------
# Étape 5 — Les emails : réparation mécanique + statut + doublons de personnes
# ----------------------------------------------------------------

EMAIL_VALID_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")


def step5_emails(tables, report):
    """Ajoute email_clean, email_status, email_domain_root,
    email_is_duplicate et email_duplicate_count sur contacts.

    - email_clean  : espaces internes retirés, '@@' -> '@', minuscules.
                     Réparation MÉCANIQUE uniquement — rien d'inventé.
    - email_status : ok | repaired | missing | personal
    - email_domain_root : racine du domaine (témoin fusion/rattachement),
                     vide si missing/personal
    - email_is_duplicate / email_duplicate_count : la même adresse portée
      par plusieurs contacts = la même PERSONNE en plusieurs fiches.
      Flag posé ici pour interdire le double-comptage du buying committee.
    """
    personal = set(CONFIG["domains"]["personal_email_domains"])
    watchlist = set(CONFIG["emails"]["freemail_watchlist"])
    rows = tables["contacts"]

    n_missing = n_personal = n_repaired_at = n_repaired_space = n_ok = 0
    n_invalid_after = 0
    watch_hits = {}
    examples = []

    for row in rows:
        raw = (row.get("email") or "").strip()
        if not raw:
            row["email_clean"] = ""
            row["email_status"] = "missing"
            row["email_domain_root"] = ""
            n_missing += 1
            continue
        had_space = " " in raw
        had_at = "@@" in raw
        clean = re.sub(r"@+", "@", raw.lower().replace(" ", ""))
        row["email_clean"] = clean
        domain = clean.rsplit("@", 1)[1] if "@" in clean else ""
        if domain in personal:
            row["email_status"] = "personal"
            row["email_domain_root"] = ""
            n_personal += 1
        elif had_space or had_at:
            row["email_status"] = "repaired"
            row["email_domain_root"] = domain.split(".")[0]
            if had_at:
                n_repaired_at += 1
            else:
                n_repaired_space += 1
            if len(examples) < 2:
                examples.append(f"`{raw}` → `{clean}`")
        else:
            row["email_status"] = "ok"
            row["email_domain_root"] = domain.split(".")[0]
            n_ok += 1
        if not EMAIL_VALID_RE.match(clean):
            n_invalid_after += 1
        if domain in watchlist and domain not in personal:
            watch_hits[domain] = watch_hits.get(domain, 0) + 1

    # doublons de personnes : même adresse réparée, portée par >= 2 contacts
    counts = {}
    for row in rows:
        if row["email_clean"]:
            counts[row["email_clean"]] = counts.get(row["email_clean"], 0) + 1
    n_dup_addr = sum(1 for n in counts.values() if n >= 2)
    n_carriers = 0
    for row in rows:
        n = counts.get(row["email_clean"], 0)
        dup = bool(row["email_clean"]) and n >= 2
        row["email_is_duplicate"] = "1" if dup else "0"
        row["email_duplicate_count"] = str(n) if dup else ""
        if dup:
            n_carriers += 1

    n_repaired = n_repaired_at + n_repaired_space
    report.append("## Étape 5 — Emails : réparation mécanique + statut + doublons de personnes\n")
    report.append(
        "email_clean = espaces retirés, @@ → @ (rien d'inventé) · email_status = "
        "ok/repaired/missing/personal · doublons d'adresse flagués (même adresse = "
        "même personne, interdit de la compter deux fois dans un buying committee).\n"
    )
    report.append(f"- Réparées : **{n_repaired}** (attendu : 1 544 = 769 `@@` + 775 espaces) — "
                  f"@@ : {n_repaired_at}, espaces : {n_repaired_space}")
    report.append(f"- **Encore invalides au regex après réparation : {n_invalid_after}** (attendu : 0 — LE contrôle qui prouve)")
    report.append(f"- Sans adresse : **{n_missing}** (attendu : 3 065) · Perso (gmail) : **{n_personal}** (attendu : 2 359) · OK : {n_ok}")
    report.append(f"- Adresses partagées par ≥2 contacts : **{n_dup_addr}** (attendu : 783) · porteurs flagués : **{n_carriers}** (attendu : 1 940, dont 1 157 copies excédentaires)")
    report.append(f"- Freemails hors config détectés : " + (str(watch_hits) if watch_hits else "aucun (gmail reste le seul domaine perso)"))
    if examples:
        report.append(f"- Exemples : " + " · ".join(examples))
    report.append("")
    report.append("> 📌 Honnêteté (mesuré) : cette étape n'améliore la joignabilité d'AUCUN compte chaud "
                  "(0 des 25 signaux forts avait un email cassé ; 1 est sans adresse, 2 en gmail). "
                  "C'est du nettoyage de fond, pas de la récupération de rappel — ça change le canal, pas le score.\n")

    ok = (n_repaired == 1544 and n_repaired_at == 769 and n_repaired_space == 775
          and n_invalid_after == 0 and n_missing == 3065 and n_personal == 2359
          and n_dup_addr == 783 and n_carriers == 1940 and not watch_hits)
    print(f"[étape 5] contacts: réparées={n_repaired} (@@={n_repaired_at} espaces={n_repaired_space}) "
          f"invalides_après={n_invalid_after} sans_adresse={n_missing} perso={n_personal} "
          f"adresses_partagées={n_dup_addr} porteurs={n_carriers} "
          f"freemails_inconnus={watch_hits or 'aucun'}"
          + ("  ✔" if ok else "  ⚠ A VERIFIER"))


# ----------------------------------------------------------------
# Étape 6 — Dates impossibles & cohérence : neutraliser + tracer, jamais corriger
# ----------------------------------------------------------------

def step6_date_sanity(tables, report):
    """Neutralise les dates impossibles (parsée vidée) et pose les flags.

    - contacts.created_date_flag : future | emails_avant_creation |
      visites_avant_creation | '' (cf. config, étape 6)
    - accounts.last_activity_flag : future | ''
    Les events ne sont JAMAIS touchés ni déclassés — seule la fiabilité
    de la DATE est jugée. La récence du scoring vient des events.
    """
    ref = CONFIG["reference_date"]

    # premières dates d'events par contact, séparées email vs visite/linkedin
    first_email = {}
    first_other = {}
    for e in tables["events"]:
        cid = e.get("contact_id") or ""
        if not cid:
            continue
        d = e["timestamp"][:10]
        if e["event_type"] in ("email_sent", "email_open", "email_click"):
            if cid not in first_email or d < first_email[cid]:
                first_email[cid] = d
        else:
            if cid not in first_other or d < first_other[cid]:
                first_other[cid] = d

    n_future = n_mail = n_visit = 0
    for row in tables["contacts"]:
        row["created_date_flag"] = ""
        parsed = row.get("created_date_parsed") or ""
        if not parsed:
            continue
        if parsed > ref:
            row["created_date_flag"] = "future"
            row["created_date_parsed"] = ""      # neutralisée, l'originale reste
            n_future += 1
            continue
        cid = row["contact_id"]
        if first_email.get(cid, "9999") < parsed:
            row["created_date_flag"] = "emails_avant_creation"
            n_mail += 1
        elif first_other.get(cid, "9999") < parsed:
            row["created_date_flag"] = "visites_avant_creation"
            n_visit += 1

    n_la_future = 0
    for row in tables["accounts"]:
        row["last_activity_flag"] = ""
        parsed = row.get("last_activity_date_parsed") or ""
        if parsed and parsed > ref:
            row["last_activity_flag"] = "future"
            row["last_activity_date_parsed"] = ""
            n_la_future += 1

    report.append("## Étape 6 — Dates impossibles & cohérence\n")
    report.append(
        "Une date fausse n'entre jamais dans un calcul : neutralisée (parsée vidée) "
        "+ flag. Jamais 'corrigée' (vraie valeur inconnaissable), originale conservée. "
        "Les events ne sont jamais touchés — seule la fiabilité de la date est jugée.\n"
    )
    report.append(f"- Contacts créés dans le futur : **{n_future}** (attendu : 6 321) → date neutralisée + flag")
    report.append(f"- Contacts ayant REÇU des emails avant leur création (impossible → date corrompue) : "
                  f"**{n_mail}** (attendu : 414)")
    report.append(f"- Contacts avec seulement visites/linkedin avant création (attribution rétroactive "
                  f"possible, bénéfice du doute) : **{n_visit}** (attendu : 20)")
    report.append(f"- Comptes avec dernière activité future : **{n_la_future}** (attendu : 3) → neutralisée + flag")
    report.append("")

    ok = (n_future == 6321 and n_mail == 414 and n_visit == 20 and n_la_future == 3)
    print(f"[étape 6] futures={n_future} emails_avant={n_mail} visites_avant={n_visit} "
          f"last_activity_futures={n_la_future}"
          + ("  ✔" if ok else "  ⚠ A VERIFIER"))


# ----------------------------------------------------------------
# Étape 7 — LA FUSION : 30 000 fiches -> 20 519 entreprises
# ----------------------------------------------------------------

def step7_fusion(tables, report):
    """Construit la table companies et pose entity_id / merged_into sur accounts.

    Clé d'entité = name_norm (== domain_root à 100 %, partitions identiques
    prouvées par deux clés indépendantes). Élection marqueur-exclu d'abord.
    Consolidation par les règles actées (cf. config, étape 7).
    Rien n'est supprimé : chaque doublon garde merged_into -> rollback.
    """
    from collections import Counter, defaultdict

    cascade = CONFIG["fusion"]["cascade_statuts"]
    rank = {s: i for i, s in enumerate(cascade)}
    accounts = tables["accounts"]

    groups = defaultdict(list)
    for r in accounts:
        groups[r["name_norm"]].append(r)

    def elect(members):
        return min(members, key=lambda r: (
            1 if r["dup_marker"] else 0,             # marqueur exclu d'abord
            rank[r["lifecycle_stage"]],              # statut le plus avancé
            0 if r["arr_eur"] else 1,                # ARR rempli
            r["created_date_parsed"] or "9999",      # la plus ancienne
            r["account_id"]))                        # déterminisme

    def pick_arr(members):
        """La fiche qui porte le contrat : customer d'abord, puis churned ;
        à statut égal, la renewal la plus tardive. ARR et renewal ensemble."""
        for stage in ("customer", "churned"):
            cands = [m for m in members if m["lifecycle_stage"] == stage and m["arr_eur"]]
            if cands:
                return max(cands, key=lambda m: (m["renewal_date_parsed"] or "", m["account_id"]))
        return None

    companies = []
    stats = Counter()
    for i, key in enumerate(sorted(groups), 1):
        members = groups[key]
        master = elect(members)
        entity_id = f"ENT-{i:05d}"
        stages = {m["lifecycle_stage"] for m in members}
        consolidated = min(stages, key=lambda s: rank[s])   # le plus avancé du GROUPE

        arr_fiche = pick_arr(members)
        arr_values = {m["arr_eur"] for m in members if m["arr_eur"]}
        countries = Counter(m["country_clean"] for m in members)
        top_country, top_n = countries.most_common(1)[0]
        if list(countries.values()).count(top_n) > 1:       # égalité -> maîtresse
            top_country = master["country_clean"]
        owners = {m["owner"].strip() for m in members if (m["owner"] or "").strip()}
        domains = Counter(m["domain_clean"] for m in members if m["domain_clean"])
        las = [m["last_activity_date_parsed"] for m in members if m["last_activity_date_parsed"]]
        crs = [m["created_date_parsed"] for m in members if m["created_date_parsed"]]

        flags = {
            "country_conflict": len(countries) > 1,
            "arr_conflict": len(arr_values) > 1,
            "owner_conflict": len(owners) > 1,
            "lifecycle_conflict": len(stages) > 1,
            "review_churned_vs_opportunity": consolidated == "churned" and "opportunity" in stages,
            "owner_a_router": not owners,
        }
        for f, v in flags.items():
            if v:
                stats[f] += 1
        if master["dup_marker"]:
            stats["marked_elected"] += 1

        def first_non_empty(field):
            v = (master.get(field) or "").strip()
            if v:
                return v
            for m in members:
                if (m.get(field) or "").strip():
                    return m[field].strip()
            return ""

        # Commercial : même règle de récupération que l'ARR — si la fiche élue
        # n'en a pas, on hérite d'une jumelle (choisie par la cascade d'élection,
        # déterministe). owner_source_account trace la provenance.
        if (master["owner"] or "").strip():
            owner_fiche = master
        else:
            owner_cands = [m for m in members if (m["owner"] or "").strip()]
            owner_fiche = min(owner_cands, key=lambda r: (
                1 if r["dup_marker"] else 0,
                rank[r["lifecycle_stage"]],
                0 if r["arr_eur"] else 1,
                r["created_date_parsed"] or "9999",
                r["account_id"])) if owner_cands else None
            if owner_fiche is not None:
                stats["owner_herite"] += 1

        companies.append({
            "entity_id": entity_id,
            "name": master["account_name"],
            "name_norm": key,
            "master_id": master["account_id"],
            "n_records": str(len(members)),
            "account_ids": "|".join(m["account_id"] for m in members),
            "domain": domains.most_common(1)[0][0] if domains else "",
            "domain_root": next((m["domain_root"] for m in members if m["domain_root"]), ""),
            "country": top_country,
            "industry": first_non_empty("industry"),
            "employee_range": first_non_empty("employee_range"),
            "lifecycle_consolidated": consolidated,
            "a_ete_client": "1" if stages & {"customer", "churned"} else "0",
            "deal_en_cours": "1" if "opportunity" in stages else "0",
            "arr_eur": arr_fiche["arr_eur"] if arr_fiche else "",
            # Piège n°11 (ARR fantôme) : l'agrégat comptable est séparé —
            # arr_actif (clients) / arr_ex_client (churned, dimensionne le win-back).
            # SUM(arr_eur) brut mélangerait 21,9 % d'ARR d'ex-clients.
            "arr_actif": arr_fiche["arr_eur"] if arr_fiche and consolidated == "customer" else "",
            "arr_ex_client": arr_fiche["arr_eur"] if arr_fiche and consolidated == "churned" else "",
            "renewal_date": arr_fiche["renewal_date_parsed"] if arr_fiche else "",
            "arr_source_account": arr_fiche["account_id"] if arr_fiche else "",
            "owner": owner_fiche["owner"].strip() if owner_fiche else "",
            "owner_source_account": owner_fiche["account_id"] if owner_fiche else "",
            "created_date_min": min(crs) if crs else "",
            "last_activity_max": max(las) if las else "",
            **{f: ("1" if v else "0") for f, v in flags.items()},
        })

        for m in members:
            m["entity_id"] = entity_id
            m["is_master"] = "1" if m is master else "0"
            m["merged_into"] = "" if m is master else master["account_id"]

    tables["companies"] = companies

    # comptabilité ARR à l'euro près
    total = sum(int(r["arr_eur"]) for r in accounts if r["arr_eur"])
    kept = sum(int(c["arr_eur"]) for c in companies if c["arr_eur"])
    arr_sources = {c["arr_source_account"] for c in companies if c["arr_source_account"]}
    discarded = sum(int(r["arr_eur"]) for r in accounts
                    if r["arr_eur"] and r["account_id"] not in arr_sources)
    sizes = Counter(len(v) for v in groups.values())

    report.append("## Étape 7 — LA FUSION : 30 000 fiches → entreprises\n")
    report.append(
        "Clé = name_norm (partitions identiques prouvées par 2 clés indépendantes). "
        "Élection marqueur-exclu → cascade de statuts → ARR rempli → ancienneté. "
        "Statut consolidé = le plus avancé du GROUPE. ARR+renewal ensemble "
        "(customer puis churned, renewal la plus tardive). Dernière activité = MAX, "
        "création = MIN. Conflits → flags, jamais tranchés en silence. "
        "Commercial : si la fiche élue n'en a pas, hérité d'une jumelle "
        "(cascade d'élection, provenance tracée dans owner_source_account). "
        "Rien n'est supprimé : merged_into sur chaque doublon.\n"
    )
    report.append(f"- **Entités : {len(companies)}** (attendu : 20 519) — tailles : "
                  + ", ".join(f"{n} fiches × {sizes[n]}" for n in sorted(sizes)))
    report.append(f"- Fiches étiquetées élues maîtresses : **{stats['marked_elected']}** (attendu : 0)")
    report.append(f"- Comptabilité ARR : total fiches **{total:,} €** = conservé **{kept:,} €** "
                  f"+ écarté (doublons) **{discarded:,} €** — écart : "
                  f"**{total - kept - discarded} €** (attendu : 0)")
    report.append(f"- Conflits flagués : pays **{stats['country_conflict']}** (attendu 5 947) · "
                  f"ARR **{stats['arr_conflict']}** (251) · owner **{stats['owner_conflict']}** (5 067) · "
                  f"lifecycle **{stats['lifecycle_conflict']}** (6 858)")
    report.append(f"- Arbitrages churned-vs-opportunity : **{stats['review_churned_vs_opportunity']}** (attendu : 80)")
    report.append(f"- Commerciaux hérités d'une fiche jumelle : **{stats['owner_herite']}** (attendu : 1 407)")
    report.append(f"- Entités sans commercial (à router) : **{stats['owner_a_router']}** (attendu : 2 729)")
    report.append("")

    ok = (len(companies) == 20519 and stats["marked_elected"] == 0
          and total - kept - discarded == 0
          and stats["country_conflict"] == 5947 and stats["arr_conflict"] == 251
          and stats["owner_conflict"] == 5067 and stats["lifecycle_conflict"] == 6858
          and stats["review_churned_vs_opportunity"] == 80
          and stats["owner_herite"] == 1407 and stats["owner_a_router"] == 2729)
    print(f"[étape 7] entités={len(companies)} marquées_élues={stats['marked_elected']} "
          f"ARR: {total}={kept}+{discarded} (écart {total-kept-discarded}) "
          f"conflits: pays={stats['country_conflict']} arr={stats['arr_conflict']} "
          f"owner={stats['owner_conflict']} lifecycle={stats['lifecycle_conflict']} "
          f"arbitrages_churned_opp={stats['review_churned_vs_opportunity']} "
          f"owner_herites={stats['owner_herite']} sans_owner={stats['owner_a_router']}"
          + ("  ✔" if ok else "  ⚠ A VERIFIER"))


# ----------------------------------------------------------------
# Étape 8 — Le ré-attachement : contacts et events rejoignent leurs entités
# ----------------------------------------------------------------

def persona_tier(title, personas):
    if title in personas["_buyers_flat"]:
        return "buyer"
    if title in personas["champions"]:
        return "champion"
    if title in personas["utilisateurs"]:
        return "utilisateur"
    if title in personas["bruit"]:
        return "bruit"
    return "sans_titre" if not title else "NON_CLASSE"


def step8_reattach(tables, report):
    """entity_id sur contacts et events, orphelins rattachés par email,
    dédup des personnes au sein d'une entité, tier persona stampé.

    - entity_source : 'account' | 'inferred_from_email' | '' (vrai inconnu)
    - is_orphan     : "1" uniquement pour les vrais inconnus (liste comptes à créer)
    - person_primary / duplicate_of : même email dans la même entité = même
      personne — une fiche principale, les copies tracées. Rien de supprimé.
    - email_multi_entity : même email présent sur >= 2 entités (jamais fusionné)
    - events : entity_id + is_anonymous + reparented (compte non-maître)
    """
    from collections import defaultdict

    personas = dict(CONFIG["personas"])
    personas["_buyers_flat"] = {t for ts in CONFIG["personas"]["buyers"].values() for t in ts}
    accounts = tables["accounts"]
    contacts = tables["contacts"]
    events = tables["events"]

    entity_of_account = {a["account_id"]: a["entity_id"] for a in accounts}
    master_accounts = {a["account_id"] for a in accounts if a["is_master"] == "1"}
    entity_by_root = {c["name_norm"]: c["entity_id"] for c in tables["companies"]}

    n_by_account = n_by_email = n_unknown = 0
    to_create = []
    for c in contacts:
        title = (c.get("job_title") or "").strip()
        c["persona_tier"] = persona_tier(title, personas)
        aid = (c.get("account_id") or "").strip()
        if aid:
            c["entity_id"] = entity_of_account[aid]
            c["entity_source"] = "account"
            c["is_orphan"] = "0"
            n_by_account += 1
        elif c.get("email_domain_root") and c["email_domain_root"] in entity_by_root:
            c["entity_id"] = entity_by_root[c["email_domain_root"]]
            c["entity_source"] = "inferred_from_email"
            c["is_orphan"] = "0"
            n_by_email += 1
        else:
            c["entity_id"] = ""
            c["entity_source"] = ""
            c["is_orphan"] = "1"
            n_unknown += 1
            to_create.append(c)

    # dédup des personnes : même email dans la même entité = même personne
    couples = defaultdict(list)
    for c in contacts:
        if c["entity_id"] and c.get("email_clean"):
            couples[(c["entity_id"], c["email_clean"])].append(c)
    entities_of_email = defaultdict(set)
    for c in contacts:
        if c["entity_id"] and c.get("email_clean"):
            entities_of_email[c["email_clean"]].add(c["entity_id"])

    n_dup_couples = n_copies = 0
    for members in couples.values():
        members.sort(key=lambda c: c["contact_id"])
        for i, c in enumerate(members):
            c["person_primary"] = "1" if i == 0 else "0"
            c["duplicate_of"] = "" if i == 0 else members[0]["contact_id"]
        if len(members) > 1:
            n_dup_couples += 1
            n_copies += len(members) - 1

    # Correctif 28/07 (audit croisé) — clé SECONDAIRE (entité, prénom+nom) :
    # une fiche sans email est invisible à la clé (entité, email). Périmètre
    # conservateur : paires non liées dont EXACTEMENT une fiche a un email —
    # la primaire est la fiche avec email. Le groupe à entité vide (2 fiches
    # sans email ni compte) est hors périmètre : une entité vide n'est pas
    # une entité.
    by_name = defaultdict(list)
    for c in contacts:
        fn = (c.get("first_name") or "").strip().lower()
        ln = (c.get("last_name") or "").strip().lower()
        if c["entity_id"] and (fn or ln) and not c.get("duplicate_of"):
            by_name[(c["entity_id"], fn, ln)].append(c)
    n_name_couples = 0
    for members in by_name.values():
        if len(members) != 2:
            continue
        avec = [c for c in members if (c.get("email_clean") or "").strip()]
        if len(avec) != 1:
            continue
        prim = avec[0]
        copie = members[0] if members[1] is prim else members[1]
        copie["person_primary"] = "0"
        copie["duplicate_of"] = prim["contact_id"]
        n_name_couples += 1

    # Correctif 28/07 (audit croisé) — une fiche principale sans titre hérite
    # du titre de sa copie (même règle que les vides de la fusion : ARR, owner),
    # persona recalculé, provenance tracée title_from_copy.
    by_id = {c["contact_id"]: c for c in contacts}
    n_titres_herites = 0
    for c in sorted(contacts, key=lambda x: x["contact_id"]):
        dup = c.get("duplicate_of")
        if not dup:
            continue
        prim = by_id[dup]
        if not (prim.get("job_title") or "").strip() and (c.get("job_title") or "").strip():
            prim["job_title"] = c["job_title"].strip()
            prim["persona_tier"] = persona_tier(prim["job_title"], personas)
            prim["title_from_copy"] = "1"
            n_titres_herites += 1

    for c in contacts:
        c.setdefault("person_primary", "1" if not c["is_orphan"] == "1" else "")
        c.setdefault("duplicate_of", "")
        c.setdefault("title_from_copy", "0")
        c["email_multi_entity"] = ("1" if c.get("email_clean")
                                   and len(entities_of_email.get(c["email_clean"], set())) >= 2
                                   else "0")

    n_ev_attached = n_ev_anon = n_ev_reparented = 0
    for e in events:
        aid = (e.get("account_id") or "").strip()
        if aid:
            e["entity_id"] = entity_of_account[aid]
            e["is_anonymous"] = "0"
            e["reparented"] = "0" if aid in master_accounts else "1"
            n_ev_attached += 1
            n_ev_reparented += e["reparented"] == "1"
        else:
            e["entity_id"] = ""
            e["is_anonymous"] = "1"
            e["reparented"] = "0"
            n_ev_anon += 1

    n_con_reparented = sum(1 for c in contacts
                           if (c.get("account_id") or "").strip()
                           and c["account_id"] not in master_accounts)
    to_create_ids = {t["contact_id"] for t in to_create}
    unknown_with_events = sum(1 for e in events
                              if e.get("contact_id") in to_create_ids)

    # la liste "comptes à créer" : livrable à part entière
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "accounts_to_create.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["contact_id", "email", "email_domain_root", "job_title", "persona_tier"])
        for c in to_create:
            w.writerow([c["contact_id"], c.get("email_clean") or c.get("email") or "",
                        c.get("email_domain_root") or "", c.get("job_title") or "",
                        c["persona_tier"]])

    report.append("## Étape 8 — Ré-attachement : contacts et events rejoignent leurs entités\n")
    report.append(
        "entity_id partout · orphelins rattachés par le domaine de leur email quand il "
        "désigne UNE entité (tracé inferred_from_email, même geste que l'étape 3) · "
        "vrais inconnus → liste 'comptes à créer' · dédup des personnes (même email dans "
        "la même entité = une personne : primaire + copies tracées) · rien de supprimé.\n"
    )
    report.append(f"- Contacts rattachés : **{n_by_account}** par leur compte + **{n_by_email}** "
                  f"par leur email (attendu : 547) = {n_by_account + n_by_email}")
    report.append(f"- Vrais inconnus : **{n_unknown}** (attendu : 53) → `accounts_to_create.csv` "
                  f"— dont events portés : {unknown_with_events} (attendu : 0)")
    report.append(f"- Events : **{n_ev_attached}** rattachés + **{n_ev_anon}** anonymes conservés "
                  f"= {n_ev_attached + n_ev_anon}")
    report.append(f"- Re-parentés (fiche non-maîtresse → entité) : **{n_ev_reparented}** events "
                  f"(32,1 % des rattachables) · **{n_con_reparented}** contacts")
    report.append(f"- Dédup personnes : **{n_dup_couples}** couples (entité, email) + "
                  f"**{n_name_couples}** couples (entité, nom — fiches sans email) = "
                  f"{n_copies + n_name_couples} copies flaguées `duplicate_of` (attendu : 99 + 6 = 105)")
    report.append(f"- Titres hérités d'une copie (persona recalculé) : **{n_titres_herites}** "
                  f"(attendu : 11, dont 1 CHRO)")
    report.append("")

    exp = CONFIG["invariants"]["reattachement"]
    ok = (n_by_email == exp["orphelins_rattaches_email"]
          and n_unknown == exp["vrais_inconnus"]
          and unknown_with_events == exp["inconnus_avec_events"]
          and n_ev_attached == exp["events_avec_entite"]
          and n_ev_anon == exp["events_anonymes"]
          and n_ev_reparented == exp["events_reparentes"]
          and n_con_reparented == exp["contacts_reparentes"]
          and n_dup_couples == exp["couples_dedup_personnes"]
          and n_copies + n_name_couples == exp["copies_flaguees"]
          and n_name_couples == exp["couples_dedup_nom"]
          and n_titres_herites == exp["titres_herites"])
    print(f"[étape 8] contacts: compte={n_by_account} email={n_by_email} inconnus={n_unknown} "
          f"(events des inconnus={unknown_with_events}) | events: rattachés={n_ev_attached} "
          f"anonymes={n_ev_anon} reparentés={n_ev_reparented} | contacts reparentés={n_con_reparented} "
          f"| dédup: {n_dup_couples} couples email + {n_name_couples} couples nom, "
          f"{n_copies + n_name_couples} copies | titres hérités: {n_titres_herites}"
          + ("  ✔" if ok else "  ⚠ A VERIFIER"))


# ----------------------------------------------------------------
# Étape 9 — Dédup des events : flag des répétitions strictes, anonymes intouchés
# ----------------------------------------------------------------

def step9_dedup_events(tables, report):
    """Flague is_duplicate_event sur les répétitions STRICTES
    (contact, type, campagne, page, jour) — première occurrence conservée.
    Les events anonymes ne sont jamais touchés (visiteurs différents).
    """
    from collections import defaultdict
    events = tables["events"]

    groups = defaultdict(list)
    for e in events:
        e["is_duplicate_event"] = "0"
        if e.get("contact_id"):
            groups[(e["contact_id"], e["event_type"], e.get("campaign") or "",
                    e.get("page_url") or "", e["timestamp"][:10])].append(e)

    n_flagged = n_groups = n_conv = 0
    for members in groups.values():
        if len(members) > 1:
            n_groups += 1
            members.sort(key=lambda e: e["timestamp"])
            for e in members[1:]:
                e["is_duplicate_event"] = "1"
                n_flagged += 1
                if e["event_type"] in ("form_fill", "meeting_booked"):
                    n_conv += 1
    n_anon_flagged = sum(1 for e in events
                         if not e.get("contact_id") and e["is_duplicate_event"] == "1")

    report.append("## Étape 9 — Dédup des events (flags, jamais de suppression)\n")
    report.append(
        "Clé stricte (contact, type, campagne, PAGE, jour) — la page protège le "
        "pattern /pricing puis /demo. Anonymes intouchés (l'appliquer supprimerait "
        "2 872 lignes à tort — mesuré). Première occurrence conservée.\n"
    )
    report.append(f"- Lignes flaguées : **{n_flagged}** (attendu : 1 988) dans **{n_groups}** groupes (attendu : 1 860)")
    report.append(f"- Conversions touchées : **{n_conv}** (attendu : 0) · anonymes flagués : **{n_anon_flagged}** (attendu : 0)")
    report.append("")

    exp = CONFIG["invariants"]["dedup_events"]
    ok = (n_flagged == exp["lignes_flaguees"] and n_groups == exp["groupes"]
          and n_conv == exp["conversions_flaguees"] and n_anon_flagged == exp["anonymes_flagues"])
    print(f"[étape 9] flagués={n_flagged} groupes={n_groups} conversions={n_conv} "
          f"anonymes={n_anon_flagged}" + ("  ✔" if ok else "  ⚠ A VERIFIER"))


# ----------------------------------------------------------------
# Étape 10 — Le bot : détection au chronomètre, sur le FLUX BRUT
# ----------------------------------------------------------------

def step10_bot(tables, report):
    """Flague is_bot (contact) et from_bot (events) par la CADENCE.

    Détection sur le flux BRUT (doublons inclus) : la dédup efface le motif
    mécanique. Définition verrouillée : délai open -> dernier envoi antérieur
    de la même campagne ; bot = médiane <= seuil config sur >= N emails.
    """
    from collections import defaultdict
    from datetime import datetime
    from statistics import median

    cfg = CONFIG["bot_detection"]
    events = tables["events"]
    contacts = tables["contacts"]
    parse = lambda e: datetime.strptime(e["timestamp"], "%Y-%m-%dT%H:%M:%S")

    sends = defaultdict(list)     # (contact, campagne) -> timestamps triés
    opens = defaultdict(list)     # contact -> [(campagne, ts)]
    n_sends = defaultdict(int)
    for e in events:
        cid = e.get("contact_id")
        if not cid:
            continue
        if e["event_type"] == "email_sent":
            sends[(cid, e.get("campaign") or "")].append(parse(e))
            n_sends[cid] += 1
        elif e["event_type"] == "email_open":
            opens[cid].append((e.get("campaign") or "", parse(e)))
    for v in sends.values():
        v.sort()

    bots = set()
    medians = {}
    for cid, os_ in opens.items():
        if n_sends[cid] < cfg["min_emails_recus"]:
            continue
        delays = []
        for camp, t in os_:
            prior = [s for s in sends.get((cid, camp), []) if s <= t]
            if prior:
                delays.append((t - prior[-1]).total_seconds())
        if delays:
            medians[cid] = median(delays)
            if medians[cid] <= cfg["mediane_max_s"]:
                bots.add(cid)

    for c in contacts:
        c["is_bot"] = "1" if c["contact_id"] in bots else "0"
    n_from_bot = 0
    for e in events:
        e["from_bot"] = "1" if e.get("contact_id") in bots else "0"
        n_from_bot += e["from_bot"] == "1"
    temoins_flagues = [t for t in cfg["temoins_humains"] if t in bots]

    report.append("## Étape 10 — Le bot : détection au chronomètre, sur le flux brut\n")
    report.append(
        "Définition verrouillée : délai open → dernier envoi antérieur (même campagne), "
        "bot = médiane ≤ 60 s sur ≥ 5 emails. Sur le flux BRUT — la dédup efface le "
        "motif mécanique (3+3 par envoi → 1+1). Flag, jamais suppression : le bot est "
        "une information sur le compte, pas un déchet.\n"
    )
    det = ", ".join(f"{cid} (médiane {medians[cid]:.0f} s)" for cid in sorted(bots))
    report.append(f"- Bots détectés : **{len(bots)}** — {det or 'aucun'} (attendu : 1, CON-077194 à 4 s)")
    report.append(f"- Events flagués from_bot : **{n_from_bot}** (attendu : 420)")
    report.append(f"- Témoins humains flagués à tort : **{len(temoins_flagues)}** (attendu : 0) — "
                  + " · ".join(f"{t} : médiane {medians.get(t, 0):.0f} s = {medians.get(t, 0)/3600:.1f} h"
                               for t in cfg["temoins_humains"]))
    report.append("")

    exp = CONFIG["invariants"]["bot"]
    ok = (len(bots) == exp["bots_detectes"] and bots == {"CON-077194"}
          and n_from_bot == exp["events_from_bot"]
          and len(temoins_flagues) == exp["temoins_humains_flagues"])
    print(f"[étape 10] bots={sorted(bots)} from_bot={n_from_bot} "
          f"témoins_flagués={temoins_flagues or 0} "
          f"(CON-077195: {medians.get('CON-077195', 0)/3600:.1f} h)"
          + ("  ✔" if ok else "  ⚠ A VERIFIER"))


# ----------------------------------------------------------------
# Étape 11 — La segmentation : 11 états factuels, partition complète
# ----------------------------------------------------------------

def step11_segment(tables, report):
    """Colonnes segment, play et segment_evidence sur companies.

    Règles factuelles en ordre strict (première qui matche gagne).
    Engagement sur le flux NET (doublons + bot exclus), jamais les opens.
    MORT/DORMANT : last_activity_max en DERNIER RECOURS (champ déclaré,
    disqualifié du scoring), assumé et flagué segment_evidence.
    """
    from collections import defaultdict
    from datetime import datetime, timedelta

    cfg = CONFIG["segmentation"]
    STRONG = set(cfg["engagement_fort"])
    INTENT_PAGES = set(cfg["pages_intent"])
    NOW = CONFIG["reference_date"]
    year_ago = (datetime.strptime(NOW, "%Y-%m-%d")
                - timedelta(days=cfg["seuil_mort_jours"])).date().isoformat()

    has_events = defaultdict(int)
    strong = defaultdict(int)
    intent = defaultdict(int)
    for e in tables["events"]:
        ent = e.get("entity_id")
        if not ent:
            continue
        has_events[ent] += 1
        if e["is_duplicate_event"] == "0" and e["from_bot"] == "0":
            t = e["event_type"]
            if t in STRONG:
                strong[ent] += 1
            if t in ("form_fill", "meeting_booked") or \
               (t == "website_visit" and e.get("page_url") in INTENT_PAGES):
                intent[ent] += 1

    counts = defaultdict(int)
    for c in tables["companies"]:
        ent, lc = c["entity_id"], c["lifecycle_consolidated"]
        ren, la = c["renewal_date"], c["last_activity_max"]
        s, f, ev = intent[ent] > 0, strong[ent] > 0, has_events[ent] > 0
        evidence = "events"
        if lc == "customer":
            seg = "CLIENT_ACTIF" if ren >= NOW else "CLIENT_RENEWAL_ECHUE"
        elif lc == "churned":
            if ren and ren > NOW:
                seg = "CHURN_CONTRADICTOIRE"
            elif f:
                seg = "EX_CLIENT_REACTIF"
            else:
                seg = "EX_CLIENT"
        elif s:
            seg = "PROSPECT_CHAUD"           # intent attribué — lost inclus
        elif lc in ("lead", "prospect", "opportunity") and f:
            seg = "PROSPECT_TIEDE"
        elif lc == "lost" and f:
            seg = "LOST_REACTIF"
        elif ev:
            seg = "TOUCHE_EMAIL_SEULEMENT"
        elif not la or la < year_ago:
            seg = "MORT"
        else:
            seg = "DORMANT"
            evidence = "declared_field"      # le champ disqualifié décide — assumé
        c["segment"] = seg
        c["play"] = cfg["play"][seg]
        c["segment_evidence"] = evidence
        counts[seg] += 1

    exp = CONFIG["invariants"]["segmentation"]
    report.append("## Étape 11 — Segmentation : 11 états factuels → 9 plays\n")
    report.append(
        "Règles en ordre strict sur les FAITS (statut consolidé, renewal, engagement "
        "NET). MORT/DORMANT : champ déclaré en dernier recours, hors scoring, flagué. "
        "Décision architecturale : la hot list finale est UNIQUE, tous segments, avec "
        "le play — 3 des 25 entités les plus chaudes vivent hors des segments prospects.\n"
    )
    report.append("| Segment | Entités | Play |")
    report.append("|---|---|---|")
    for seg in cfg["play"]:
        report.append(f"| {seg} | {counts[seg]} | {cfg['play'][seg]} |")
    report.append("")

    ok = all(counts[k] == v for k, v in exp.items() if k != "evidence_declared_field") \
        and sum(counts.values()) == len(tables["companies"])
    print(f"[étape 11] " + " ".join(f"{k}={counts[k]}" for k in cfg["play"])
          + f" total={sum(counts.values())}" + ("  ✔" if ok else "  ⚠ A VERIFIER"))


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
    checks.append(("K5", "concordance nom normalisé ↔ racine de domaine (déclarés)",
                   k["concordance_nom_racine_declares"],
                   sum(1 for r in accounts if r.get("domain_source") == "declared"
                       and r.get("name_norm") == r.get("domain_root"))))

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
    checks.append(("S6", "fiches marquées (old)/- import/' 2'", s["noms_marques"],
                   sum(1 for r in accounts if r.get("dup_marker"))))
    n_distinct_names = len({r.get("name_norm") for r in accounts})
    checks.append(("S7", "noms normalisés distincts (future table entreprises)",
                   f"{s['noms_distincts_min']}-{s['noms_distincts_max']}", n_distinct_names))
    checks.append(("S8", "emails réparés", s["emails_repares"],
                   sum(1 for r in contacts if r.get("email_status") == "repaired")))
    checks.append(("S9", "emails invalides après réparation",
                   s["emails_invalides_apres_reparation"],
                   sum(1 for r in contacts if r.get("email_clean")
                       and not EMAIL_VALID_RE.match(r["email_clean"]))))
    email_counts = {}
    for r in contacts:
        e = r.get("email_clean")
        if e:
            email_counts[e] = email_counts.get(e, 0) + 1
    checks.append(("S10", "adresses email partagées (doublons de personnes)",
                   s["adresses_email_partagees"],
                   sum(1 for n in email_counts.values() if n >= 2)))
    checks.append(("S11", "contacts créés dans le futur (neutralisés + flag)",
                   s["contacts_dates_futures"],
                   sum(1 for r in contacts if r.get("created_date_flag") == "future")))
    checks.append(("S12", "contacts avec emails reçus avant création (date corrompue)",
                   s["contacts_emails_avant_creation"],
                   sum(1 for r in contacts if r.get("created_date_flag") == "emails_avant_creation")))
    checks.append(("S13", "contacts en attribution rétroactive possible",
                   s["contacts_visites_avant_creation"],
                   sum(1 for r in contacts if r.get("created_date_flag") == "visites_avant_creation")))
    checks.append(("S14", "comptes à dernière activité future (neutralisés + flag)",
                   s["accounts_last_activity_future"],
                   sum(1 for r in accounts if r.get("last_activity_flag") == "future")))
    # S16 — l'équilibre clé↔marqueurs (dépendance rendue visible et testable) :
    # noms distincts SANS retrait des marqueurs − marqueurs détectés = entités.
    # Protège la propriété "zéro fusion transitive" contre une regex modifiée.
    suffixes16 = sorted(CONFIG["names"]["legal_suffixes"], key=len, reverse=True)
    sre16 = re.compile(r"\s+(" + "|".join(re.escape(x) for x in suffixes16) + r")\s*$", re.I)
    def norm_marker_included(name):
        t = (name or "").lower().strip()
        while True:
            t2 = sre16.sub("", t)
            if t2 == t:
                break
            t = t2
        return re.sub(r"[^a-z0-9]", "", t)
    n_with_marker = len({norm_marker_included(r["account_name"]) for r in accounts})
    n_markers16 = sum(1 for r in accounts if r.get("dup_marker"))
    n_entities16 = len({r.get("name_norm") for r in accounts})
    expected16 = s["noms_distincts_marqueurs_inclus"]
    balance_ok = (n_with_marker == expected16
                  and n_with_marker - n_markers16 == n_entities16)
    checks.append(("S16", "équilibre clé↔marqueurs : noms (marqueurs inclus) − marqueurs = entités",
                   f"{expected16} − 234 = 20519",
                   f"{n_with_marker} − {n_markers16} = {n_with_marker - n_markers16}"
                   if balance_ok else
                   f"CASSÉ : {n_with_marker} − {n_markers16} ≠ {n_entities16}"))

    ref = CONFIG["reference_date"]
    checks.append(("S15", "dates parsées encore au futur après neutralisation",
                   s["dates_parsees_futures_restantes"],
                   sum(1 for r in contacts if (r.get("created_date_parsed") or "") > ref)
                   + sum(1 for r in accounts
                         if (r.get("created_date_parsed") or "") > ref
                         or (r.get("last_activity_date_parsed") or "") > ref)))

    # -- Fusion (étape 7) : les gros calibres
    f = inv["fusion"]
    companies = tables.get("companies", [])
    checks.append(("F1", "entités (exact, triple-prouvé)", f["entites"], len(companies)))
    checks.append(("F2", "taille max d'un groupe de doublons", f["taille_groupe_max"],
                   max((int(c["n_records"]) for c in companies), default=0)))
    checks.append(("F3", "fiches étiquetées élues maîtresses (absolu)",
                   f["fiches_marquees_elues"],
                   sum(1 for r in accounts if r.get("is_master") == "1" and r.get("dup_marker"))))
    checks.append(("F4", "fiches rattachées à exactement une entité", len(accounts),
                   sum(1 for r in accounts if r.get("entity_id"))))
    arr_total = sum(int(r["arr_eur"]) for r in accounts if r.get("arr_eur"))
    arr_kept = sum(int(c["arr_eur"]) for c in companies if c.get("arr_eur"))
    arr_sources = {c["arr_source_account"] for c in companies if c.get("arr_source_account")}
    arr_discarded = sum(int(r["arr_eur"]) for r in accounts
                        if r.get("arr_eur") and r["account_id"] not in arr_sources)
    checks.append(("F5", "conservation ARR totale (fiches)", f["arr_total_fiches"], arr_total))
    checks.append(("F6", "comptabilité ARR : total − conservé − écarté", 0,
                   arr_total - arr_kept - arr_discarded))
    checks.append(("F7", "conflits de pays flagués", f["conflits_pays"],
                   sum(1 for c in companies if c.get("country_conflict") == "1")))
    checks.append(("F8", "conflits d'ARR flagués", f["conflits_arr"],
                   sum(1 for c in companies if c.get("arr_conflict") == "1")))
    checks.append(("F9", "conflits de commercial flagués", f["conflits_owner"],
                   sum(1 for c in companies if c.get("owner_conflict") == "1")))
    checks.append(("F10", "conflits de statut flagués", f["conflits_lifecycle"],
                   sum(1 for c in companies if c.get("lifecycle_conflict") == "1")))
    checks.append(("F11", "arbitrages churned-vs-opportunity", f["arbitrages_churned_opportunity"],
                   sum(1 for c in companies if c.get("review_churned_vs_opportunity") == "1")))
    # F12 (invariant n°28) — corroboration : toute fusion déclenchée par un
    # marqueur doit avoir une 2e preuve indépendante (racine partagée)
    by_entity = {}
    for r in accounts:
        by_entity.setdefault(r.get("entity_id"), []).append(r)
    c_decl = c_inf = c_none = 0
    for r in accounts:
        if not r.get("dup_marker"):
            continue
        others = [m for m in by_entity[r["entity_id"]] if m is not r]
        share = [m for m in others if r["domain_root"] and m["domain_root"] == r["domain_root"]]
        if not share:
            c_none += 1
        elif r["domain_source"] == "declared" and any(m["domain_source"] == "declared" for m in share):
            c_decl += 1
        else:
            c_inf += 1
    checks.append(("F12", "corroboration des fusions par marqueur (racine déclarée)",
                   f["corroboration_racine_declaree"], c_decl))
    checks.append(("F13", "corroboration des fusions par marqueur (racine déduite)",
                   f["corroboration_racine_deduite"], c_inf))
    checks.append(("F14", "fusions reposant sur le SEUL marqueur",
                   f["fusions_marqueur_seul"], c_none))
    # F15-F17 (invariant n°42) — piège n°11 : la séparation comptable de l'ARR
    # est VERROUILLÉE, pas seulement documentée.
    sum_actif = sum(int(c["arr_actif"]) for c in companies if c.get("arr_actif"))
    sum_ex = sum(int(c["arr_ex_client"]) for c in companies if c.get("arr_ex_client"))
    checks.append(("F15", "ARR actif (customers uniquement)", f["arr_actif"], sum_actif))
    checks.append(("F16", "ARR ex-client (churned, pool win-back)", f["arr_ex_client"], sum_ex))
    checks.append(("F17", "ARR actif + ex-client = ARR conservé", arr_kept, sum_actif + sum_ex))
    # F18-F20 (correctif owner 28/07) — héritage du commercial depuis les jumelles :
    # le compte hérité est verrouillé, le reste-vide aussi, et la symétrie
    # owner vide ⟺ flag à-router est à double sens (aucun cas orphelin des deux côtés).
    checks.append(("F18", "commerciaux hérités d'une jumelle", f["owner_herites"],
                   sum(1 for c in companies
                       if c.get("owner") and c.get("owner_source_account")
                       and c["owner_source_account"] != c["master_id"])))
    checks.append(("F19", "entités sans commercial après héritage", f["owner_sans"],
                   sum(1 for c in companies if not (c.get("owner") or "").strip())))
    checks.append(("F20", "owner vide ⟺ à router (double sens)", 0,
                   sum(1 for c in companies
                       if bool((c.get("owner") or "").strip()) == (c.get("owner_a_router") == "1"))))

    # -- Personas (paramètre de scoring) : partition complète, double sens
    p = inv["personas"]
    tiers = {}
    for r in contacts:
        tiers[r.get("persona_tier", "")] = tiers.get(r.get("persona_tier", ""), 0) + 1
    checks.append(("P1", "buyers (périmètre produit)", p["buyers"], tiers.get("buyer", 0)))
    checks.append(("P2", "champions", p["champions"], tiers.get("champion", 0)))
    checks.append(("P3", "utilisateurs", p["utilisateurs"], tiers.get("utilisateur", 0)))
    checks.append(("P4", "bruit (×0 sur signaux faibles, jamais sur conversions)",
                   p["bruit"], tiers.get("bruit", 0)))
    checks.append(("P5", "sans titre", p["sans_titre"], tiers.get("sans_titre", 0)))
    census_titles = {(r.get("job_title") or "").strip() for r in contacts} - {""}
    mapping_titles = ({t for ts in CONFIG["personas"]["buyers"].values() for t in ts}
                      | set(CONFIG["personas"]["champions"])
                      | set(CONFIG["personas"]["utilisateurs"])
                      | set(CONFIG["personas"]["bruit"]))
    checks.append(("P6", "libellés fantômes dans le mapping (double sens, aller)",
                   p["libelles_fantomes"], len(mapping_titles - census_titles)))
    checks.append(("P7", "titres du recensement non classés (double sens, retour)",
                   p["titres_non_classes"],
                   len(census_titles - mapping_titles) + tiers.get("NON_CLASSE", 0)))

    # -- Ré-attachement (étape 8)
    r8 = inv["reattachement"]
    checks.append(("R1", "contacts avec entité", r8["contacts_avec_entite"],
                   sum(1 for r in contacts if r.get("entity_id"))))
    checks.append(("R2", "orphelins rattachés par email (tracés)",
                   r8["orphelins_rattaches_email"],
                   sum(1 for r in contacts if r.get("entity_source") == "inferred_from_email")))
    checks.append(("R3", "vrais inconnus (liste comptes à créer)", r8["vrais_inconnus"],
                   sum(1 for r in contacts if r.get("is_orphan") == "1")))
    unknown_ids = {r["contact_id"] for r in contacts if r.get("is_orphan") == "1"}
    checks.append(("R4", "events portés par un vrai inconnu", r8["inconnus_avec_events"],
                   sum(1 for e in events if e.get("contact_id") in unknown_ids)))
    checks.append(("R5", "events avec entité", r8["events_avec_entite"],
                   sum(1 for e in events if e.get("entity_id"))))
    checks.append(("R6", "events anonymes conservés", r8["events_anonymes"],
                   sum(1 for e in events if e.get("is_anonymous") == "1")))
    checks.append(("R7", "events re-parentés (32,1 % des rattachables)",
                   r8["events_reparentes"],
                   sum(1 for e in events if e.get("reparented") == "1")))
    masters8 = {a["account_id"] for a in accounts if a["is_master"] == "1"}
    checks.append(("R8", "contacts re-parentés", r8["contacts_reparentes"],
                   sum(1 for r in contacts if (r.get("account_id") or "").strip()
                       and r["account_id"] not in masters8)))
    checks.append(("R9", "copies de personnes flaguées (duplicate_of)",
                   r8["copies_flaguees"],
                   sum(1 for r in contacts if r.get("duplicate_of"))))
    checks.append(("R10", "emails présents sur >= 2 entités (flag, jamais fusionnés)",
                   r8["emails_multi_entites"],
                   len({r["email_clean"] for r in contacts if r.get("email_multi_entity") == "1"})))
    # R12-R14 (correctif 28/07, audit croisé) — la clé (entité, email) est
    # aveugle aux fiches sans email : clé secondaire (entité, nom) + héritage
    # des titres depuis les copies, chacun sous son invariant.
    checks.append(("R12", "couples de personnes par la clé nom (fiches sans email)",
                   r8["couples_dedup_nom"],
                   sum(1 for r in contacts if r.get("duplicate_of")
                       and not (r.get("email_clean") or "").strip())))
    restants = 0
    _seen = {}
    for r in contacts:
        fn = (r.get("first_name") or "").strip().lower()
        ln = (r.get("last_name") or "").strip().lower()
        if r.get("entity_id") and (fn or ln) and not r.get("duplicate_of"):
            _seen.setdefault((r["entity_id"], fn, ln), []).append(r)
    for g in _seen.values():
        if len(g) == 2 and sum(1 for r in g if (r.get("email_clean") or "").strip()) == 1:
            restants += 1
    checks.append(("R13", "faux doublons NOM restants (l'angle mort de R11, refermé)",
                   r8["faux_clusters_nom_restants"], restants))
    checks.append(("R14", "titres hérités d'une copie (title_from_copy tracé)",
                   r8["titres_herites"],
                   sum(1 for r in contacts if r.get("title_from_copy") == "1")))
    # E1 (acté 28/07) — la file d'enrichissement : trou de données ≠ refus
    en = inv["enrichissement"]
    checks.append(("E1", "contacts à enrichir (adresse pro absente/perso, primaires, bot exclu)",
                   en["contacts_a_enrichir"],
                   sum(1 for r in contacts
                       if r.get("person_primary") == "1" and r.get("is_bot") != "1"
                       and r.get("email_status") in ("missing", "personal"))))
    # -- Segmentation (étape 11) : partition complète + cohérences croisées
    g = inv["segmentation"]
    seg_counts = {}
    for c in companies:
        seg_counts[c.get("segment", "")] = seg_counts.get(c.get("segment", ""), 0) + 1
    for i, (seg, expected_n) in enumerate(
            ((k, v) for k, v in g.items() if k != "evidence_declared_field"), 1):
        checks.append((f"G{i}", f"segment {seg}", expected_n, seg_counts.get(seg, 0)))
    checks.append(("G12", "partition complète (somme des segments)", len(companies),
                   sum(seg_counts.values())))
    checks.append(("G13", "cohérence : CLIENT_ACTIF + RENEWAL_ECHUE = entités customer",
                   sum(1 for c in companies if c["lifecycle_consolidated"] == "customer"),
                   seg_counts.get("CLIENT_ACTIF", 0) + seg_counts.get("CLIENT_RENEWAL_ECHUE", 0)))
    checks.append(("G14", "cohérence : segments churned = entités churned",
                   sum(1 for c in companies if c["lifecycle_consolidated"] == "churned"),
                   seg_counts.get("CHURN_CONTRADICTOIRE", 0) + seg_counts.get("EX_CLIENT_REACTIF", 0)
                   + seg_counts.get("EX_CLIENT", 0)))
    checks.append(("G15", "DORMANT sur champ déclaré = tous flagués segment_evidence",
                   g["evidence_declared_field"],
                   sum(1 for c in companies if c.get("segment_evidence") == "declared_field")))

    # -- ARR écarté (étape 12) : la décomposition sous invariant
    a12 = inv["arr_ecarte"]
    from collections import defaultdict as _dd
    by_ent12 = _dd(list)
    for a in accounts:
        by_ent12[a["entity_id"]].append(a)
    comp12 = {c["entity_id"]: c for c in companies}
    dec12 = _dd(int)
    for ent, members in by_ent12.items():
        src = comp12[ent]["arr_source_account"]
        src_f = next((m for m in members if m["account_id"] == src), None)
        for m in members:
            if not m["arr_eur"] or m["account_id"] == src:
                continue
            if src_f and m["lifecycle_stage"] == "customer" and src_f["lifecycle_stage"] == "customer":
                k = ("customer_doublons_meme_montant" if m["arr_eur"] == src_f["arr_eur"]
                     else "conflits_bi_customer")
            elif m["lifecycle_stage"] == "churned":
                k = ("churned_sous_customer"
                     if src_f and src_f["lifecycle_stage"] == "customer" else "churned_doublons")
            else:
                k = "autre"
            dec12[k] += int(m["arr_eur"])
    for i, (k, v) in enumerate(a12.items(), 1):
        checks.append((f"A{i}", f"ARR écarté — {k}", v, dec12.get(k, 0)))
    checks.append(("A5", "ARR écarté — la décomposition ferme sur le total",
                   arr_discarded, sum(dec12.values())))

    # -- Dédup events (étape 9) + Bot (étape 10)
    d9 = inv["dedup_events"]
    checks.append(("D1", "events flagués doublons (jamais supprimés)",
                   d9["lignes_flaguees"],
                   sum(1 for e in events if e.get("is_duplicate_event") == "1")))
    checks.append(("D2", "conversions flaguées doublons", d9["conversions_flaguees"],
                   sum(1 for e in events if e.get("is_duplicate_event") == "1"
                       and e["event_type"] in ("form_fill", "meeting_booked"))))
    checks.append(("D3", "events anonymes flagués doublons", d9["anonymes_flagues"],
                   sum(1 for e in events if not e.get("contact_id")
                       and e.get("is_duplicate_event") == "1")))
    b10 = inv["bot"]
    checks.append(("B1", "bots détectés (CON-077194, et lui seul)", b10["bots_detectes"],
                   sum(1 for r in contacts if r.get("is_bot") == "1")))
    checks.append(("B2", "events from_bot", b10["events_from_bot"],
                   sum(1 for e in events if e.get("from_bot") == "1")))
    checks.append(("B3", "témoins humains flagués bot (non-régression)",
                   b10["temoins_humains_flagues"],
                   sum(1 for r in contacts if r.get("is_bot") == "1"
                       and r["contact_id"] in CONFIG["bot_detection"]["temoins_humains"])))

    # anti-faux-cluster : dans une entité, deux "personnes distinctes" ne
    # partagent jamais un email
    primary_pairs = {}
    n_faux = 0
    for r in contacts:
        if r.get("person_primary") == "1" and r.get("entity_id") and r.get("email_clean"):
            k = (r["entity_id"], r["email_clean"])
            if k in primary_pairs:
                n_faux += 1
            primary_pairs[k] = True
    checks.append(("R11", "faux clusters restants (2 primaires, même email, même entité)",
                   r8["faux_clusters_restants"], n_faux))

    def check_passes(expected, measured):
        if isinstance(expected, str) and expected.startswith(">="):
            return measured >= int(expected[2:])
        if isinstance(expected, str) and "-" in expected:
            lo, hi = expected.split("-")
            return int(lo) <= measured <= int(hi)
        return measured == expected

    results = [(cid, label, e, m, check_passes(e, m)) for cid, label, e, m in checks]
    ok = all(p for *_, p in results)
    lines = ["## 🛡️ Filet d'invariants — vérifié à chaque exécution\n",
             "| ID | Invariant | Attendu | Mesuré | Statut |",
             "|---|---|---|---|---|"]
    for cid, label, expected, measured, passed in results:
        lines.append(f"| {cid} | {label} | {expected} | {measured} | "
                     f"{'🟢' if passed else '🔴 ALARME'} |")
    lines.append("")
    lines.append("Armées par le scoring V1.1 — chaque promesse cite sa garde, "
                 "vérifiée verte dans la traçabilité ci-dessous : "
                 + " · ".join(inv["armees_par_scoring"]))
    lines.append("")
    report.extend(lines)

    n_green = sum(1 for *_, p in results if p)
    print(f"[filet]   {n_green}/{len(results)} invariants verts"
          + ("  ✔" if ok else "  🔴 ALARME — voir rapport"))
    if not ok:
        with open(REPORT_PATH, "w") as f:
            f.write("\n".join(report) + "\n")
        sys.exit(1)


def step12_final_report(tables, report):
    """Consolide le rapport en livrable : résumé exécutif en tête +
    décomposition de l'ARR écarté (sous invariant) + livrables."""
    from collections import defaultdict

    accounts, companies = tables["accounts"], tables["companies"]
    comp_by_id = {c["entity_id"]: c for c in companies}
    by_entity = defaultdict(list)
    for a in accounts:
        by_entity[a["entity_id"]].append(a)

    # décomposition de l'ARR écarté, par raison
    dec = defaultdict(lambda: [0, 0])
    for ent, members in by_entity.items():
        src = comp_by_id[ent]["arr_source_account"]
        src_f = next((m for m in members if m["account_id"] == src), None)
        for m in members:
            if not m["arr_eur"] or m["account_id"] == src:
                continue
            amt = int(m["arr_eur"])
            if src_f and m["lifecycle_stage"] == "customer" and src_f["lifecycle_stage"] == "customer":
                key = ("customer_doublons_meme_montant" if m["arr_eur"] == src_f["arr_eur"]
                       else "conflits_bi_customer")
            elif m["lifecycle_stage"] == "churned":
                key = ("churned_sous_customer"
                       if src_f and src_f["lifecycle_stage"] == "customer" else "churned_doublons")
            else:
                key = "autre"
            dec[key][0] += 1
            dec[key][1] += amt

    segs = defaultdict(int)
    for c in companies:
        segs[c["segment"]] += 1
    arr_actif = sum(int(c["arr_actif"]) for c in companies if c["arr_actif"])
    arr_ex = sum(int(c["arr_ex_client"]) for c in companies if c["arr_ex_client"])

    # Livrable « contacts à enrichir » (acté 28/07) : adresse pro absente ou
    # perso. Un trou de données se répare (enrichissement automatisé), un
    # refus (opt-out) se respecte — les deux ne se mélangent jamais.
    # Fiches principales uniquement, bot exclu. 912 de ces contacts ont un
    # historique email : l'adresse a EXISTÉ, le CRM l'a perdue.
    contacts = tables["contacts"]
    ev_par_contact = defaultdict(lambda: {"n": 0, "mail": 0, "li": 0})
    for e in tables["events"]:
        cid = e.get("contact_id")
        if not cid or e["is_duplicate_event"] == "1" or e["from_bot"] == "1":
            continue
        d = ev_par_contact[cid]
        d["n"] += 1
        if e["event_type"] in ("email_sent", "email_open", "email_click"):
            d["mail"] += 1
        if e["event_type"] == "linkedin_engagement":
            d["li"] += 1
    a_enrichir = [c for c in contacts
                  if c.get("person_primary") == "1" and c.get("is_bot") != "1"
                  and c.get("email_status") in ("missing", "personal")]
    with open(os.path.join(OUT_DIR, "contacts_a_enrichir.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["contact_id", "entity_id", "entreprise", "job_title", "persona_tier",
                    "raison", "adresse_a_existe", "linkedin_vu", "nb_events_net"])
        for c in a_enrichir:
            d = ev_par_contact.get(c["contact_id"], {"n": 0, "mail": 0, "li": 0})
            w.writerow([c["contact_id"], c.get("entity_id") or "",
                        comp_by_id.get(c.get("entity_id"), {}).get("name", ""),
                        c.get("job_title") or "", c.get("persona_tier") or "",
                        "sans_adresse" if c["email_status"] == "missing" else "adresse_perso",
                        "1" if d["mail"] else "0", "1" if d["li"] else "0", d["n"]])
    n_enrichir = len(a_enrichir)

    resume = [
        "## 📋 Résumé exécutif — l'état du CRM après cleanup\n",
        "| Avant | Après |",
        "|---|---|",
        f"| 30 000 fiches comptes (1/3 de doublons) | **{len(companies)} entreprises réelles** "
        "(fusion prouvée par 2 clés indépendantes, rollback intégral) |",
        "| 3 formats de dates, 30 graphies de pays, 2 671 domaines vides | 0 erreur de parsing, "
        "8 pays ISO, 133 fiches sans racine (95 % récupérées) |",
        "| ARR invérifiable (69,7 M€ bruts, 21,9 % fantôme) | **ARR actif "
        f"{arr_actif:,} €** ({segs['CLIENT_ACTIF'] + segs['CLIENT_RENEWAL_ECHUE']} clients) · "
        f"ex-client {arr_ex:,} € (win-back) · écarté doublons 3 025 000 €, décomposé ci-dessous |",
        f"| 77 199 contacts, doublons de personnes invisibles | 77 146 rattachés, 105 doublons flagués "
        "(99 par email + 6 par nom), 53 comptes à créer, 4 tiers persona produit |",
        f"| 94 838 events en vrac | 90 838 rattachés aux entités, 1 988 doublons flagués, "
        "1 bot isolé (420 events), 4 000 anonymes tracés |",
        "",
        f"**Segments** : {segs['PROSPECT_CHAUD']} prospects chauds · {segs['PROSPECT_TIEDE']} tièdes · "
        f"{segs['CLIENT_ACTIF']} clients actifs · {segs['CLIENT_RENEWAL_ECHUE']} renewals échues · "
        f"{segs['CHURN_CONTRADICTOIRE']} churns contradictoires · {segs['EX_CLIENT_REACTIF']} ex-clients "
        f"réactifs · {segs['LOST_REACTIF']} lost réactifs · {segs['MORT'] + segs['DORMANT']} muets.",
        "",
        "**Décomposition de l'ARR écarté (3 025 000 €, à l'euro près, sous invariant)** :",
        "| Raison | Fiches | Montant |",
        "|---|---|---|",
    ]
    for k, label in [("conflits_bi_customer", "Conflits bi-customer (2 montants, règle contrat le plus tardif) — 89 groupes"),
                     ("churned_sous_customer", "Churned écartés (le customer prime)"),
                     ("churned_doublons", "Churned doublons"),
                     ("customer_doublons_meme_montant", "Customer doublons, même montant")]:
        resume.append(f"| {label} | {dec[k][0]} | {dec[k][1]:,} € |")
    resume += [
        "",
        "NB : la règle « contrat le plus tardif » ne maximise pas l'ARR affiché "
        "(616 000 € de moins qu'une règle « max ») — elle suit le contrat en cours.",
        "",
        # Section GÉNÉRÉE à chaque run (leçon 28/07 : maintenue à la main,
        # elle s'est périmée trois fois — désormais elle lit les fichiers)
        "**Les modifications, fichier par fichier** (généré depuis les fichiers, "
        "jamais maintenu à la main) :",
        "| Fichier | Colonnes d'origine (intactes) | Colonnes ajoutées |",
        "|---|---|---|",
    ]
    for t in ("accounts", "contacts", "events"):
        with open(os.path.join(ROOT, f"{t}.csv"), newline="") as f:
            orig = next(csv.reader(f))
        clean_cols = list(tables[t][0].keys())
        added = [k for k in clean_cols if k not in orig]
        resume.append(f"| `{t}_clean.csv` | {len(orig)} | **{len(added)}** : "
                      + ", ".join(f"`{k}`" for k in added) + " |")
    resume.append(f"| `companies.csv` | — (table née de la fusion) | "
                  f"**{len(list(companies[0].keys()))}** colonnes |")
    resume += [
        "",
        "Principe : l'original n'est jamais modifié — chaque transformation vit "
        "dans une colonne neuve, avec sa trace.",
        "",
        "**Livrables** : `companies.csv` (20 519 entreprises, segments, plays, flags) · "
        "`accounts_clean.csv` / `contacts_clean.csv` / `events_clean.csv` · "
        "`accounts_to_create.csv` (53) · "
        f"`contacts_a_enrichir.csv` ({n_enrichir} — adresse pro absente ou perso : un trou "
        "de données se répare par enrichissement, un refus opt-out se respecte ; 912 ont un "
        "historique email, l'adresse a existé) · `cleanup_config.yaml` (toutes les règles) · "
        "ce rapport (auto-généré à chaque exécution).",
        "",
        "---",
        "",
    ]
    report[3:3] = resume
    print(f"[étape 12] résumé exécutif consolidé — ARR écarté décomposé : "
          + " + ".join(f"{v[1]:,}" for v in dec.values()) + " = 3 025 000 €")


def render_traceability(report):
    """La table règle actée → invariant garant. Née de l'erreur 'règle ARR
    actée mais jamais implémentée' : une ligne sans invariant = un trou
    VISIBLE, au lieu d'être découvert par hasard. Régénérée à chaque run.

    Correctif 29/07 (revue croisée) : la table a produit l'erreur INVERSE —
    10 règles implémentées encore affichées « à venir ». Depuis : les
    invariants SCx appartiennent au run de SCORING, et une ligne SCx n'est
    verte que si sa garde est VERTE dans dashboard_data.json au moment de la
    génération. Un statut ne se déclare pas dans un yaml, il se constate."""
    import json
    rows = CONFIG["tracabilite"]
    gardes, version_scoring = {}, ""
    dj = os.path.join(ROOT, "dashboard_data", "dashboard_data.json")
    if os.path.exists(dj):
        with open(dj) as f:
            ops = json.load(f)["ops"]
        gardes = {g["id"]: g["ok"] for g in ops["gardes"]}
        version_scoring = ops["config_version"]

    def statut_de(inv):
        if not inv:
            return "🔴 à armer avec son étape"
        sc = [i.strip() for i in inv.split(",") if i.strip().startswith("SC")]
        if not sc:
            return "🟢 garantie"           # invariant du cleanup, mesuré dans CE run
        if not gardes:
            return "🔴 run de scoring introuvable — lancer run_scoring.py"
        absentes = [i for i in sc if i not in gardes]
        rouges = [i for i in sc if gardes.get(i) is False]
        if absentes:
            return "🔴 garde absente du run de scoring : " + ", ".join(absentes)
        if rouges:
            return "🔴 garde ROUGE au run de scoring : " + ", ".join(rouges)
        return f"🟢 garantie (garde verte, scoring {version_scoring})"

    report.append("## 🧭 Traçabilité — chaque règle actée a-t-elle son contrôle automatique ?\n")
    report.append("| Règle actée | Implémentée où | Invariant garant | Statut |")
    report.append("|---|---|---|---|")
    n_ok = 0
    for r in rows:
        statut = statut_de(r["invariants"])
        n_ok += statut.startswith("🟢")
        report.append(f"| {r['regle']} | {r['ou']} | {r['invariants'] or '—'} | {statut} |")
    report.append("")
    print(f"[traça]   {n_ok}/{len(rows)} règles actées sous contrôle automatique vérifié, "
          f"{len(rows) - n_ok} non garanties (visibles dans le rapport)")


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
    step4_names(tables, report)
    step5_emails(tables, report)
    step6_date_sanity(tables, report)
    step7_fusion(tables, report)
    step8_reattach(tables, report)
    step9_dedup_events(tables, report)
    step10_bot(tables, report)
    step11_segment(tables, report)

    run_invariants(tables, report)
    step12_final_report(tables, report)
    render_traceability(report)

    for table, rows in tables.items():
        save(table, rows)

    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(report) + "\n")
    print(f"\nRapport écrit : {REPORT_PATH}")


if __name__ == "__main__":
    main()
