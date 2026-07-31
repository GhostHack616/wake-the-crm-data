#!/usr/bin/env python3
# =============================================================
# Le FILET — Wake the CRM · proto 2b (V0)
# L'intégration continue, mais pour le CRM : des règles métier en
# une ligne de config, trois réactions — compter, sonner, bloquer.
# Lit data_clean/ (les sorties de la machine), écrit filet/filet_report.md.
# Une règle "bloquer" violée => exit 1 : la sortie ne part pas.
# Mode --demo-panne : injecte 2 violations en mémoire (rien n'est
# écrit sur disque) pour montrer le blocage en live pendant la démo.
# =============================================================
import csv
import os
import sys
from datetime import datetime

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# dashboard_data/ est le canonique : c'est ce que l'écran consomme.
# (data_clean/ garde des copies d'étape qui peuvent retarder d'un run.)
IN_DIR = os.path.join(ROOT, "dashboard_data")
CFG = yaml.safe_load(open(os.path.join(ROOT, "filet", "filet_rules.yaml")))
# Le NOW du dataset vit dans la config du scoring — jamais la date système.
REF_DATE = yaml.safe_load(open(os.path.join(ROOT, "scoring", "scoring_config.yaml")))["reference_date"]

ICONES = {"compter": "🧮", "sonner": "🔔", "bloquer": "⛔"}


def charge():
    lire = lambda f: list(csv.DictReader(open(os.path.join(IN_DIR, f))))
    d = {
        "contacts": lire("contacts_clean.csv"),
        "companies": lire("companies.csv"),
        "hot": lire("hot_list.csv"),
        "scores_persons": lire("scores_persons.csv"),
        "scores_companies": lire("scores_companies.csv"),
    }
    d["contact_par_id"] = {c["contact_id"]: c for c in d["contacts"]}
    d["company_par_id"] = {c["entity_id"]: c for c in d["companies"]}
    # La hot list nomme la personne ; scores_persons fait le pont vers son contact_id.
    d["pont_hot"] = {(p["entity_id"], p["nom"]): p["contact_id"] for p in d["scores_persons"]}
    return d


def contact_hot(d, h):
    return d["contact_par_id"].get(d["pont_hot"].get((h["entity_id"], h["qui_appeler"])))


def saboter(d):
    # Deux pannes réalistes, en mémoire seulement : (1) un désabonnement
    # arrivé APRÈS la construction de la hot list — le cas exact que le
    # filet existe pour attraper ; (2) une contradiction churned/deal
    # qui sort de la file de review sans arbitrage.
    for h in d["hot"]:
        c = contact_hot(d, h)
        if h["canal"] == "email" and c:
            c["opted_out"] = "true"
            break
    for comp in d["companies"]:
        if comp["lifecycle_consolidated"] == "churned" and comp["deal_en_cours"] == "1":
            comp["review_churned_vs_opportunity"] = "0"
            break
    # (3) le bug Sylvasolfinance du 31/07, rejoué tel quel : un ex-client
    # sans facturation rebasculé « à sauver » par un signal de départ.
    comp_par_id = {c["entity_id"]: c for c in d["companies"]}
    for s in d["scores_companies"]:
        c = comp_par_id.get(s["entity_id"])
        if (s["liste"] == "reconquete" and c and c["a_ete_client"] == "1"
                and not c["arr_actif"]):
            s["liste"] = "retention"
            break


def f1_desabonne_jamais_emaille(d, _):
    v = []
    for h in d["hot"]:
        c = contact_hot(d, h)
        if h["canal"] == "email" and c and c["opted_out"] == "true":
            v.append(f"{h['entreprise']} : envoi email recommandé vers {h['qui_appeler']} — désabonné(e)")
    return v, f"{len(d['hot'])} lignes de hot list vérifiées"


def f2_churne_sans_deal_sauvage(d, _):
    v = []
    for c in d["companies"]:
        if (c["lifecycle_consolidated"] == "churned" and c["deal_en_cours"] == "1"
                and c["review_churned_vs_opportunity"] != "1"):
            v.append(f"{c['name']} : churné avec un deal ouvert, hors file de review")
    n = sum(1 for c in d["companies"] if c["lifecycle_consolidated"] == "churned" and c["deal_en_cours"] == "1")
    return v, f"{n} contradictions churned/deal, toutes doivent être arbitrées ou en review"


def f3_bot_jamais_score(d, _):
    bots = {c["contact_id"] for c in d["contacts"] if c["is_bot"] == "1"}
    v = [f"{p['nom']} ({p['contact_id']}) : bot présent dans les scores"
         for p in d["scores_persons"] if p["contact_id"] in bots]
    return v, f"{len(bots)} bot(s) connus, {len(d['scores_persons'])} personnes scorées"


def f4_adresse_morte(d, _):
    v = []
    for h in d["hot"]:
        c = contact_hot(d, h)
        if h["canal"] == "email" and c and c["email_status"] != "ok":
            v.append(f"{h['entreprise']} : canal email vers {h['qui_appeler']} mais adresse « {c['email_status']} »")
    return v, "canal email ⇒ adresse au statut ok"


def f5_ex_client_hors_acquisition(d, _):
    v = []
    for h in d["hot"]:
        comp = d["company_par_id"].get(h["entity_id"])
        if h["liste"] == "acquisition" and comp and comp["a_ete_client"] == "1":
            v.append(f"{h['entreprise']} : ex-client rangé en acquisition au lieu de reconquête")
    return v, "un passé client change le message — jamais le pitch d'un inconnu"


def f6_orphelins(d, regle):
    n = sum(1 for c in d["contacts"] if c["is_orphan"] == "1")
    pct = 100.0 * n / len(d["contacts"])
    seuil = float(regle.get("seuil_pct", 1.0))
    v = [f"{n} orphelins ({pct:.2f} % des contacts) — seuil {seuil} % dépassé"] if pct > seuil else []
    return v, f"{n} orphelins ({pct:.2f} % — seuil {seuil} %)"


def f7_on_ne_sauve_pas_un_parti(d, _):
    # L'exception assumée du correctif moteur : un « parti » qui porte un
    # renouvellement FUTUR reste en rétention (le perdre coûte de l'argent).
    comp_par_id = {c["entity_id"]: c for c in d["companies"]}
    v, n_exceptions = [], 0
    for s in d["scores_companies"]:
        c = comp_par_id.get(s["entity_id"])
        if not (s["liste"] == "retention" and c and c["a_ete_client"] == "1"
                and not c["arr_actif"]):
            continue
        if c["renewal_date"] and c["renewal_date"] >= REF_DATE:
            n_exceptions += 1
        else:
            v.append(f"{s['entreprise']} : « à sauver » alors qu'il ne paie plus rien — sa place est en reconquête")
    return v, f"{n_exceptions} exceptions assumées (renouvellement futur au contrat)"


CHECKS = {"F1": f1_desabonne_jamais_emaille, "F2": f2_churne_sans_deal_sauvage,
          "F3": f3_bot_jamais_score, "F4": f4_adresse_morte,
          "F5": f5_ex_client_hors_acquisition, "F6": f6_orphelins,
          "F7": f7_on_ne_sauve_pas_un_parti}


def main():
    demo = "--demo-panne" in sys.argv
    d = charge()
    if demo:
        saboter(d)

    lignes, bloque, sonne = [], [], []
    for regle in CFG["regles"]:
        reaction = regle["reaction"]
        viols, mesure = CHECKS[regle["id"]](d, regle)
        # Une règle "compter" dont le seuil déborde monte d'un cran : elle sonne.
        if viols and reaction == "compter":
            reaction = "sonner"
        statut = "✅" if not viols else ICONES[reaction]
        if viols and reaction == "bloquer":
            bloque.append(regle)
        if viols and reaction == "sonner":
            sonne.append(regle)
        lignes.append((regle, reaction, statut, viols, mesure))

    titre_mode = " · MODE DÉMO-PANNE (violations injectées en mémoire)" if demo else ""
    out = [f"# Rapport du Filet — {CFG['version']}{titre_mode}",
           f"*généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}*", "",
           "| # | La règle | Réaction | Statut | Mesure |", "|---|---|---|---|---|"]
    for regle, reaction, statut, viols, mesure in lignes:
        out.append(f"| {regle['id']} | {regle['regle']} | {reaction} | {statut} | {mesure} |")
    for regle, reaction, statut, viols, mesure in lignes:
        if viols:
            out += ["", f"## {ICONES[reaction]} {regle['id']} — {len(viols)} violation(s)"]
            out += [f"- {x}" for x in viols[:20]]

    verdict = ("⛔ FILET ROUGE : la sortie ne part pas." if bloque
               else "🔔 Filet orange : le run passe, des alertes sonnent." if sonne
               else "✅ Filet vert : rien à signaler — normal juste après un nettoyage. Sa valeur, c'est demain.")
    out += ["", f"**{verdict}**", ""]

    if not demo:
        open(os.path.join(ROOT, "filet", "filet_report.md"), "w").write("\n".join(out))
    print("\n".join(out))
    sys.exit(1 if bloque else 0)


if __name__ == "__main__":
    main()
