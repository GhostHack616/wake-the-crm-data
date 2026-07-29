#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tables.json — depuis dashboard_data/ VERSIONNE. Colonnes completes, chaque ajout a cote de son origine."""
import csv, json, os
SRC="/tmp/claude-0/-home-user-RomainPro/b68d9eed-9ab6-5ca4-b9df-696bc9953de5/scratchpad/run17/dashboard_data/"
RAW="/tmp/claude-0/-home-user-RomainPro/b68d9eed-9ab6-5ca4-b9df-696bc9953de5/scratchpad/run17/"
OUT="/tmp/claude-0/-home-user-RomainPro/b68d9eed-9ab6-5ca4-b9df-696bc9953de5/wtc/tables/"

ACC=["account_id","account_name","name_norm","dup_marker","entity_id","is_master","merged_into",
     "domain","domain_clean","domain_root","domain_source","has_domain",
     "country","country_clean","industry","employee_range","lifecycle_stage","owner","arr_eur",
     "created_date","created_date_parsed","created_date_format",
     "last_activity_date","last_activity_date_parsed","last_activity_date_format","last_activity_flag",
     "renewal_date","renewal_date_parsed","renewal_date_format"]
CTC=["contact_id","account_id","entity_id","entity_source","is_orphan",
     "first_name","last_name","job_title","title_from_copy","persona_tier",
     "email","email_clean","email_status","email_domain_root",
     "email_is_duplicate","email_duplicate_count","email_multi_entity",
     "opted_out","is_bot","person_primary","duplicate_of",
     "created_date","created_date_parsed","created_date_format","created_date_flag"]

def load(f, order=None):
    rows=list(csv.DictReader(open(SRC+f, encoding="utf-8")))
    src=list(rows[0].keys())
    if order:
        assert sorted(order)==sorted(src), "colonnes manquantes/en trop pour %s : %s" % (f, set(src)^set(order))
    c=order or src
    return {"cols":c, "rows":[[ (r.get(k) or "") for k in c ] for r in rows]}

T={"companies":load("companies.csv"), "accounts":load("accounts_clean.csv",ACC),
   "contacts":load("contacts_clean.csv",CTC), "hot_list":load("hot_list.csv")}
os.makedirs(OUT,exist_ok=True)
for k,v in T.items():
    json.dump(v, open(OUT+k+".json","w",encoding="utf-8"), ensure_ascii=False, separators=(",",":"))

# ---- controle : les colonnes d'origine sont bien celles des CSV de Gab, et les comptes collent au rapport
ORIG={"accounts": next(csv.reader(open(RAW+"accounts.csv",encoding="utf-8"))),
      "contacts": next(csv.reader(open(RAW+"contacts.csv",encoding="utf-8")))}
rep=open(RAW+"cleanup_report.md",encoding="utf-8").read()
print("%-11s %7s %5s %8s %7s  %s" % ("table","lignes","cols","origine","ajoutees","rapport"))
for k,v in T.items():
    og=ORIG.get(k)
    if og:
        assert set(og)<=set(v["cols"]), "colonne d'origine perdue dans %s" % k
        add=[c for c in v["cols"] if c not in og]
        att="| `%s_clean.csv` | %d | **%d**" % (k[:-1] if k=="accounts" else k[:-1], len(og), len(add))
        ok = ("| %d | **%d** :" % (len(og),len(add))) in rep
        print("%-11s %7d %5d %8d %8d  %s" % (k,len(v["rows"]),len(v["cols"]),len(og),len(add),
              "OK — le rapport annonce %d/%d" % (len(og),len(add)) if ok else "!! DESACCORD avec le rapport"))
    else:
        ok = ("**%d** colonnes" % len(v["cols"])) in rep if k=="companies" else True
        print("%-11s %7d %5d %8s %8s  %s" % (k,len(v["rows"]),len(v["cols"]),"—","toutes",
              "OK — rapport : 32 colonnes" if (k=="companies" and ok) else "table produite"))
    print("            fichier : %.2f Mo" % (os.path.getsize(OUT+k+".json")/1e6))
