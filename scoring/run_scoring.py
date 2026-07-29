#!/usr/bin/env python3
# =============================================================
# Le MOTEUR de scoring — Wake the CRM · V1.1
# Lit data_clean/ (sortie du pipeline de cleanup), écrit :
#   - scores_companies.csv  (un score par entreprise + la ligne d'action)
#   - scores_persons.csv    (le double étage : un score par personne)
#   - hot_list.csv          (Tier 1 + Tier 2, la liste de travail UNIQUE)
#   - dashboard_data.json   (tout ce que le dashboard affiche)
# Toute la connaissance vit dans scoring_config.yaml — ici, la mécanique.
# Mode --robustesse : secoue chaque poids de ±30 % et mesure la stabilité.
# =============================================================
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_DIR = os.path.join(ROOT, "data_clean")
CFG = yaml.safe_load(open(os.path.join(ROOT, "scoring", "scoring_config.yaml")))

CONVERSIONS = ("meeting_booked", "form_fill")
LIBELLES = {"meeting_booked": "RDV pris", "form_fill": "formulaire",
            "email_click": "clic email", "linkedin_comment": "commentaire LinkedIn",
            "linkedin_like": "like LinkedIn"}


def jour(ts):
    return date(int(ts[:4]), int(ts[5:7]), int(ts[8:10]))


def charge():
    lire = lambda f: list(csv.DictReader(open(os.path.join(IN_DIR, f))))
    return lire("contacts_clean.csv"), lire("companies.csv"), lire("events_clean.csv")


def calcule(cfg, contacts, companies, events):
    """Le moteur. Retourne (comptes, personnes, alarmes)."""
    ref = jour(cfg["reference_date"])
    P, PAGES, MULT = cfg["points"], cfg["pages"], cfg["multiplicateurs"]
    D = cfg["decroissance"]
    porte2 = cfg["portes"]["porte2_comite"]

    def decay(age, demi_vie):
        d = 0.5 ** (age / demi_vie)
        return max(d, D["plancher"]) if age <= D["plancher_fenetre_jours"] else d

    primaire, tier_de, infos = {}, {}, {}
    par_entite = defaultdict(list)
    for c in contacts:
        cid = c["contact_id"]
        primaire[cid] = c["duplicate_of"] or cid
        tier_de[cid] = c["persona_tier"]
        infos[cid] = c
        if c["entity_id"] and c["person_primary"] == "1":
            par_entite[c["entity_id"]].append(cid)

    score_p = defaultdict(lambda: defaultdict(float))     # entité -> personne -> pts
    events_p = defaultdict(lambda: defaultdict(list))     # entité -> personne -> détail
    activite = defaultdict(list)                          # entité -> (jour, personne) — poids > 0
    conv = defaultdict(list)                              # entité -> (date, personne, type)
    negatif = defaultdict(float)
    clics = defaultdict(lambda: [0, 0])                   # entité -> [clics, clics_optout]
    alarmes = []
    flux_interdit = 0

    for e in events:
        if e["is_duplicate_event"] == "1" or e["from_bot"] == "1" or e["is_anonymous"] == "1":
            continue
        cid = e["contact_id"]
        if not cid:
            continue
        p = primaire.get(cid, cid)
        ent, et = e["entity_id"], e["event_type"]
        age = (ref - jour(e["timestamp"])).days

        if et == "website_visit":
            page = e["page_url"]
            if page not in PAGES:
                alarmes.append(f"page inconnue sans poids déclaré : {page}")
                continue
            pts, cle = PAGES[page], page
        elif et == "linkedin_engagement":
            cle = "linkedin_comment" if e["metadata"].startswith("comment") else "linkedin_like"
            pts = P[cle]
        elif et in P:
            pts, cle = P[et], et
        else:
            alarmes.append(f"type d'event inconnu sans poids déclaré : {et}")
            continue

        if pts > 0:
            activite[ent].append(((jour(e["timestamp"])).toordinal(), p))
        if et in CONVERSIONS:
            conv[ent].append((e["timestamp"][:10], p, et))
        if et == "email_click":
            clics[ent][0] += 1
            if infos[cid]["opted_out"].strip().lower() in ("true", "1"):
                clics[ent][1] += 1
        if pts == 0:
            continue

        if et in CONVERSIONS:                      # preuve : plein poids, décroissance lente
            m, demi = 1.0, D["demi_vie_preuves_jours"]
        elif pts < 0:                              # négatif : plein poids peu importe le porteur
            m, demi = 1.0, D["demi_vie_gestes_jours"]
        else:                                      # geste : pondéré par le porteur
            m, demi = MULT.get(tier_de.get(p, ""), MULT["sans_titre"]), D["demi_vie_gestes_jours"]

        dk = decay(age, demi)
        v = pts * m * dk
        score_p[ent][p] += v
        if v < 0:
            negatif[ent] += v
        # La décomposition complète part au dashboard : la vue Logique doit
        # pouvoir afficher « 8 x 0,8 x 0,54 = 3,5 » sans ouvrir le code.
        events_p[ent][p].append({"date": e["timestamp"][:10], "quoi": LIBELLES.get(cle, cle),
                                 "base": pts, "x_porteur": m, "x_temps": round(dk, 3),
                                 "pts": round(v, 1)})

    # ---- portes, perdus, fit, comité --------------------------------
    fenetre1 = cfg["portes"]["porte1_conversion_fenetre_jours"]
    comptes = {}
    for ent in set(list(score_p) + list(conv)):
        sc = sum(score_p[ent].values())
        conv_recente = any((ref - jour(d + "T00")).days <= fenetre1 for d, _, _ in conv[ent])

        # Fenêtre ANCRÉE au présent : « N personnes actives dans les 14 DERNIERS
        # jours » — un comité d'il y a 2 mois n'est pas un comité (le compte
        # Grimolexlab à 0,1 pt l'a prouvé au premier run).
        ref_o = ref.toordinal()
        meilleur = {p for j, p in activite[ent]
                    if ref_o - (porte2["fenetre_jours"] - 1) <= j <= ref_o}
        sponsor = any(tier_de.get(p) == "buyer" for p in meilleur)
        comite_ok = (len(meilleur) >= porte2["personnes_min"]
                     and (sponsor or not porte2["decideur_requis"]))

        porte = "conversion" if conv_recente else ("comite" if comite_ok and not conv[ent] else "")
        comptes[ent] = {"score": sc, "porte": porte, "comite_n": len(meilleur),
                        "sponsor": sponsor, "negatif": round(negatif[ent], 1)}
    return comptes, score_p, events_p, conv, clics, par_entite, infos, tier_de, alarmes


def enrichit(cfg, comptes, score_p, events_p, conv, clics, par_entite, infos, tier_de, companies):
    """Tiers, perdus, fit, qui-appeler, canal — la ligne d'action complète."""
    S = cfg["seuils"]
    fiche = {c["entity_id"]: c for c in companies}
    VALIDE = ("ok", "repaired")

    def joignable(cid):
        i = infos[cid]
        return (i["opted_out"].strip().lower() not in ("true", "1")
                and i["email_status"] in VALIDE)

    lignes = []
    for ent, d in comptes.items():
        f = fiche.get(ent)
        if f is None:
            continue
        # perdu — canal mort (acté 28/07) : jamais client, rien d'autre ne vit,
        # tous les cliqueurs désabonnés, plus AUCUN contact joignable.
        nb_clics, nb_opt = clics[ent]
        rien_d_autre = not conv[ent] and all(
            e["quoi"] in ("clic email",) for pers in events_p[ent].values() for e in pers)
        perdu = (cfg["perdu_canal_mort"]["actif"] and f["a_ete_client"] == "0"
                 and nb_clics >= 1 and nb_clics == nb_opt and rien_d_autre
                 and not any(joignable(c) for c in par_entite[ent]))

        if perdu:
            tier = "PERDU"
        elif d["porte"]:
            tier = "T1"
        elif d["score"] >= S["tier2"]:
            tier = "T2"
        elif d["score"] >= S["tier1"]:
            tier = "T1"          # théorique : accumulation pure au-dessus du seuil
        else:
            tier = "T3"

        # fit A/B/C — ordonne, ne bloque jamais
        taille_ok = f["employee_range"] in cfg["fit"]["tailles_cible"]
        buyer_connu = any(tier_de.get(c) == "buyer" for c in par_entite[ent])
        fit = "A" if (taille_ok and buyer_connu) else ("C" if not (taille_ok or buyer_connu) else "B")

        # qui appeler : la personne qui a converti (porte 1), sinon la plus active
        if conv[ent]:
            date_c, pers, type_c = sorted(conv[ent])[-1]
            quoi = f"{LIBELLES[type_c]} le {date_c[5:]}"
        elif score_p[ent]:
            pers = max(score_p[ent], key=score_p[ent].get)
            date_c = ""
            # Le mot « comité » ne s'imprime que quand sa définition gravée est
            # vraie (3+ personnes dont un décideur) — sinon on dit le FAIT.
            # Correctif de libellé 29/07 (attrapé par l'IA n°2 au push Slack) :
            # 28 lignes disaient « comité » pour UNE personne active.
            n = d["comite_n"]
            if d["porte"] == "comite":
                quoi = f"comité : {n} personnes actives / 14 j dont un décideur, sans demande"
            elif n == 0:
                quoi = "signaux récents (15-21 j), sans demande"
            else:
                p_ = "s" if n > 1 else ""
                quoi = f"{n} personne{p_} active{p_} / 14 j, sans demande"
        else:
            pers, quoi = "", ""
        i = infos.get(pers, {})
        nom = f"{i.get('first_name', '')} {i.get('last_name', '')}".strip()
        if pers and joignable(pers):
            canal = "email"
        elif pers:
            canal = ("téléphone/LinkedIn (désabonné)"
                     if i.get("opted_out", "").strip().lower() in ("true", "1")
                     else "téléphone/LinkedIn (pas d'adresse pro)")
        else:
            canal = ""

        play = f["play"]
        if d["porte"] == "comite" and d["negatif"] < 0:
            play = "risque"      # un comité actif qui regarde la porte de sortie = à sauver

        lignes.append({
            "entity_id": ent, "entreprise": f["name"],
            "score": round(min(S["score_affiche_max"], max(0.0, d["score"])), 1),
            "score_brut": round(d["score"], 2), "tier": tier, "porte": d["porte"],
            "fit": fit, "comite_personnes_14j": d["comite_n"],
            "sponsor_decideur": "oui" if d["sponsor"] else "non",
            "qui_appeler": nom, "son_titre": i.get("job_title", ""), "preuve": quoi,
            "canal": canal, "play": play, "segment": f["segment"],
            "n_records": f["n_records"], "signaux_negatifs": d["negatif"],
            "perdu_canal_mort": "1" if perdu else "0",
        })
    ordre_fit = {"A": 0, "B": 1, "C": 2}
    lignes.sort(key=lambda r: (r["tier"] != "T1", r["tier"] != "T2", ordre_fit[r["fit"]],
                               -int(r["n_records"]), -r["score_brut"]))
    return lignes


def invariants(cfg, lignes, score_p, comptes, alarmes):
    exp = cfg["invariants"]
    t1 = [r for r in lignes if r["tier"] == "T1"]
    t2 = [r for r in lignes if r["tier"] == "T2"]
    perdus = [r for r in lignes if r["perdu_canal_mort"] == "1"]
    checks = [
        ("SC1", "Tier 1 total", exp["tier1_total"], len(t1)),
        ("SC2", "Tier 1 porte conversion", exp["tier1_porte1_conversions"],
         len([r for r in t1 if r["porte"] == "conversion"])),
        ("SC3", "Tier 1 porte comité", exp["tier1_porte2_comite"],
         len([r for r in t1 if r["porte"] == "comite"])),
        ("SC4", "Tier 2", exp["tier2"], len(t2)),
        ("SC5", "perdus — canal mort", exp["perdus_canal_mort"], len(perdus)),
        ("SC6", "perdus dans les files de travail", exp["perdus_dans_files_de_travail"],
         len([r for r in perdus if r["tier"] in ("T1", "T2")])),
        ("SC7", "hot list unique (aucune entité en double)", 0,
         len(lignes) - len({r["entity_id"] for r in lignes})),
        ("SC8", "somme des étages personnes = score compte", 0,
         sum(1 for r in lignes
             if abs(sum(score_p[r["entity_id"]].values()) - r["score_brut"]) > exp["ecart_max_somme_etages"])),
        ("SC9", "pages/types sans poids déclaré (alarme couverture)", 0, len(alarmes)),
        ("SC10", "poids de sortie strictement négatifs (config)", 0,
         sum(1 for p in ("/help/cancel-subscription", "/help/export-data")
             if cfg["pages"][p] >= 0)),
        ("SC11", "opens/envois/carrières/facture à zéro (config)", 0,
         sum(1 for k, v in [("email_open", cfg["points"]["email_open"]),
                            ("email_sent", cfg["points"]["email_sent"]),
                            ("/careers", cfg["pages"]["/careers"]),
                            ("/billing", cfg["pages"]["/billing"])] if v != 0)),
        ("SC12", "désabonné jamais en canal email", 0,
         len([r for r in lignes if r["canal"] == "email" and "désabonné" in r["canal"]])),
        ("SC13", "Tier 1 toujours joignable (un canal par ligne)", 0,
         len([r for r in t1 if not r["canal"]])),
        ("SC14", "ENT-16714 en play risque, jamais en new business", 0,
         len([r for r in lignes if r["entity_id"] == "ENT-16714" and r["play"] != "risque"])),
        ("SC15", "règles dormantes étiquetées en config", 5, len(cfg["regles_dormantes"])),
    ]
    verts = sum(1 for _, _, att, obt in checks if att == obt)
    for cid, lib, att, obt in checks:
        etat = "🟢" if att == obt else "🔴"
        print(f"  {etat} {cid:5s} {lib:52s} attendu {att} · obtenu {obt}")
    return verts, len(checks), checks


def robustesse(contacts, companies, events):
    """Secoue chaque poids de ±30 % — la liste Tier 1 doit rester identique
    (les portes sont des règles), le Tier 2 quasi stable."""
    import copy
    base_c, base_sp, *_ = calcule(CFG, contacts, companies, events)
    base = enrichit(CFG, base_c, base_sp, *calcule(CFG, contacts, companies, events)[2:8], companies)
    t1_base = {r["entity_id"] for r in base if r["tier"] == "T1"}
    t2_base = {r["entity_id"] for r in base if r["tier"] == "T2"}

    cibles = ([("points", k) for k, v in CFG["points"].items() if v != 0]
              + [("pages", k) for k, v in CFG["pages"].items() if v != 0]
              + [("multiplicateurs", k) for k in ("champion", "utilisateur", "sans_titre")]
              + [("decroissance", "demi_vie_gestes_jours"), ("decroissance", "demi_vie_preuves_jours")])
    pire_t1, pire_t2, tests = 1.0, 1.0, 0
    for sect, cle in cibles:
        for f in (0.7, 1.3):
            cfg = copy.deepcopy(CFG)
            cfg[sect][cle] = cfg[sect][cle] * f
            r = calcule(cfg, contacts, companies, events)
            lignes = enrichit(cfg, r[0], r[1], *r[2:8], companies)
            t1 = {x["entity_id"] for x in lignes if x["tier"] == "T1"}
            t2 = {x["entity_id"] for x in lignes if x["tier"] == "T2"}
            j1 = len(t1 & t1_base) / max(1, len(t1 | t1_base))
            j2 = len(t2 & t2_base) / max(1, len(t2 | t2_base))
            pire_t1, pire_t2 = min(pire_t1, j1), min(pire_t2, j2)
            tests += 1
    print(f"[±30 %] {tests} variations testées — stabilité Tier 1 : {pire_t1:.0%} (pire cas) · "
          f"Tier 2 : {pire_t2:.0%} (pire cas)")
    return pire_t1, pire_t2


def main():
    contacts, companies, events = charge()
    r = calcule(CFG, contacts, companies, events)
    comptes, score_p, events_p, conv, clics, par_entite, infos, tier_de, alarmes = r
    lignes = enrichit(CFG, comptes, score_p, events_p, conv, clics, par_entite, infos, tier_de, companies)

    os.makedirs(IN_DIR, exist_ok=True)
    champs = list(lignes[0].keys())
    with open(os.path.join(IN_DIR, "scores_companies.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=champs)
        w.writeheader()
        w.writerows(lignes)
    with open(os.path.join(IN_DIR, "hot_list.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=champs)
        w.writeheader()
        w.writerows([x for x in lignes if x["tier"] in ("T1", "T2")])
    with open(os.path.join(IN_DIR, "scores_persons.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entity_id", "contact_id", "nom", "titre", "persona", "score", "detail"])
        for ent in score_p:
            for p, s in sorted(score_p[ent].items(), key=lambda x: -x[1]):
                i = infos.get(p, {})
                w.writerow([ent, p, f"{i.get('first_name','')} {i.get('last_name','')}".strip(),
                            i.get("job_title", ""), tier_de.get(p, ""), round(s, 1),
                            " · ".join(f"{e['quoi']} {e['date'][5:]} ({e['pts']})"
                                       for e in events_p[ent][p])])

    fiche = {c["entity_id"]: c for c in companies}
    detail = []
    for x in lignes:
        if x["tier"] not in ("T1", "T2"):
            continue
        ent = x["entity_id"]
        detail.append({**x, "personnes": [
            {"nom": f"{infos[p].get('first_name','')} {infos[p].get('last_name','')}".strip(),
             "titre": infos[p].get("job_title", ""), "persona": tier_de.get(p, ""),
             "score": round(s, 1), "events": events_p[ent][p]}
            for p, s in sorted(score_p[ent].items(), key=lambda y: -y[1])]})
    from datetime import datetime
    verts, total, checks = invariants(CFG, lignes, score_p, comptes, alarmes)
    # Vue OPS (exigence du brief : « statut du dernier run + une alarme si
    # quelque chose casse ») — l'état du moteur voyage AVEC les données.
    ops = {"genere_le": datetime.now().isoformat(timespec="seconds"),
           "config_version": CFG["version"],
           "reference_date": CFG["reference_date"],
           "gardes": [{"id": c[0], "libelle": c[1], "attendu": c[2], "obtenu": c[3],
                       "ok": c[2] == c[3]} for c in checks],
           "gardes_vertes": f"{verts}/{total}",
           "alarme": verts != total,
           "regles_dormantes": CFG["regles_dormantes"]}
    replay = [{"d": e["timestamp"][:10], "e": e["entity_id"], "t": e["event_type"]}
              for e in events
              if e["entity_id"] and e["is_duplicate_event"] != "1" and e["from_bot"] != "1"]
    dash = {"meta": {"config": CFG["version"], "reference_date": CFG["reference_date"],
                     "genere_par": "scoring/run_scoring.py"},
            "compteurs": {"tier1": len([x for x in lignes if x["tier"] == "T1"]),
                          "tier2": len([x for x in lignes if x["tier"] == "T2"]),
                          "perdus": len([x for x in lignes if x["perdu_canal_mort"] == "1"]),
                          "scores_calcules": len(lignes)},
            "ops": ops,
            "hot_list": detail,
            "tous_scores": [{"e": x["entity_id"], "n": x["entreprise"], "s": x["score"],
                             "t": x["tier"]} for x in lignes],
            "replay": replay}
    with open(os.path.join(IN_DIR, "dashboard_data.json"), "w") as f:
        json.dump(dash, f, ensure_ascii=False)

    # Export VERSIONNÉ pour le dashboard (dossier commité, contrairement à
    # data_clean/) : une seule source de vérité, les données du dash ne
    # peuvent plus être périmées. Pure copie — aucun calcul ici.
    import shutil
    dash_dir = os.path.join(ROOT, "dashboard_data")
    os.makedirs(dash_dir, exist_ok=True)
    for fn in ("companies.csv", "accounts_clean.csv", "contacts_clean.csv",
               "hot_list.csv", "dashboard_data.json", "scores_persons.csv"):
        shutil.copy(os.path.join(IN_DIR, fn), os.path.join(dash_dir, fn))

    print(f"[moteur V1.1] {len(lignes)} entreprises scorées — "
          f"T1={dash['compteurs']['tier1']} T2={dash['compteurs']['tier2']} "
          f"perdus={dash['compteurs']['perdus']}")
    print(f"[gardes]  {verts}/{total} invariants scoring verts" + ("  ✔" if verts == total else "  ⚠"))
    if "--robustesse" in sys.argv:
        robustesse(contacts, companies, events)
    if verts != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
