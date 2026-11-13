"""
Exporte les données du projet sous forme de modèle en étoile pour Power BI.

Usage (depuis le dossier du projet, après avoir exécuté les notebooks 02 et 04) :
    python src/export_powerbi.py

Sorties dans powerbi/donnees/ (CSV, séparateur « ; », décimales à virgule, UTF-8) :
    Faits_Lignes, Ecritures, Alertes, Comptes, Tiers, Journaux, Calendrier,
    Benford_Distribution, Benford_Fournisseurs
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
import benford as bf  # noqa: E402
import modele_anomalies as ma  # noqa: E402
import tests_audit as ta  # noqa: E402
from chargement import charger_fec  # noqa: E402

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "powerbi" / "donnees"

LIBELLES_CLASSES = {
    "1": "1 - Capitaux", "2": "2 - Immobilisations", "3": "3 - Stocks", "4": "4 - Tiers",
    "5": "5 - Trésorerie", "6": "6 - Charges", "7": "7 - Produits",
}
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def ecrire(df: pd.DataFrame, nom: str) -> None:
    df.to_csv(SORTIE / f"{nom}.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig",
              date_format="%Y-%m-%d")
    print(f"  {nom:22s} {len(df):>6} lignes")


def main() -> None:
    SORTIE.mkdir(parents=True, exist_ok=True)
    fec = charger_fec()

    # --- Écritures : tests d'audit + score du modèle ------------------------------------
    resultats = ta.appliquer_tests(fec)
    variables, _ = ma.construire_variables(fec)
    _, score = ma.entrainer(variables)
    ecr_ml = ta.tableau_ecritures(fec[fec["JournalCode"] != "AN"])
    recurrentes = (ecr_ml.groupby(["tiers", "montant"])["montant"].transform("size") >= 6) & (ecr_ml["tiers"] != "")
    score[recurrentes] = score.min()

    ecritures = resultats.reset_index()[[
        "EcritureNum", "JournalCode", "EcritureDate", "ValidDate", "PieceRef", "EcritureLib",
        "tiers", "montant", "solde", "delai_validation", "nb_alertes"]]
    ecritures.columns = ["EcritureNum", "JournalCode", "Date", "DateValidation", "PieceRef", "Libelle",
                         "TiersCode", "Montant", "EcartDebitCredit", "DelaiValidationJours", "NbAlertes"]
    # Clé non vide pour la relation Ecritures -> Tiers dans Power BI
    ecritures["TiersCode"] = ecritures["TiersCode"].replace("", "AUCUN")
    for col in ("Montant", "EcartDebitCredit"):
        ecritures[col] = ecritures[col].round(2) + 0.0  # + 0.0 évite les « -0 »
    ecritures["ScoreAnomalie"] = ecritures["EcritureNum"].map(score).fillna(score.min()).round(4)
    ecritures["PercentileScore"] = ecritures["ScoreAnomalie"].rank(pct=True).round(4)
    ecritures["RangScore"] = ecritures["ScoreAnomalie"].rank(ascending=False, method="first").astype(int)
    ecritures["Recurrente"] = ecritures["EcritureNum"].map(recurrentes).fillna(False)

    top5 = ecritures["PercentileScore"] >= 0.95
    ecritures["NiveauRisque"] = np.select(
        [(ecritures["NbAlertes"] >= 2) | ((ecritures["NbAlertes"] >= 1) & top5),
         (ecritures["NbAlertes"] == 1) | top5],
        ["1 - Élevé", "2 - Moyen"], default="3 - Faible")
    ecritures["Raisons"] = [
        " · ".join(ma.expliquer(variables, e)[:3]) if (e in variables.index and t) else ""
        for e, t in zip(ecritures["EcritureNum"], top5)]

    noms_tests = {nom: lib for nom, (_, lib) in ta.TESTS.items()}
    ecritures["TestsDeclenches"] = resultats[list(noms_tests)].apply(
        lambda l: ", ".join(noms_tests[n] for n in l.index[l]), axis=1).values

    anomalies = pd.read_csv(RACINE / "data" / "raw" / "anomalies_injectees.csv")
    types = anomalies.set_index("EcritureNum")["type_anomalie"]
    ecritures["AnomalieInjectee"] = ecritures["EcritureNum"].isin(types.index)
    ecritures["TypeAnomalieInjectee"] = ecritures["EcritureNum"].map(types).fillna("(aucune)")

    # --- Alertes : une ligne par test déclenché (table de pont) ---------------------------
    alertes = (resultats[list(noms_tests)].reset_index()
               .melt(id_vars="EcritureNum", var_name="CodeTest", value_name="Declenche"))
    alertes = alertes[alertes["Declenche"]].drop(columns="Declenche")
    alertes["Test"] = alertes["CodeTest"].map(noms_tests)

    # --- Faits : lignes du FEC -------------------------------------------------------------
    faits = fec[["EcritureNum", "CompteNum", "CompAuxNum", "Debit", "Credit", "Montant",
                 "EcritureLet", "DateLet"]].copy()
    faits[["Debit", "Credit", "Montant"]] = faits[["Debit", "Credit", "Montant"]].round(2) + 0.0
    faits.insert(0, "LigneId", np.arange(1, len(faits) + 1))
    faits = faits.rename(columns={"CompAuxNum": "TiersCode", "EcritureLet": "Lettrage", "DateLet": "DateLettrage"})

    # --- Dimensions --------------------------------------------------------------------------
    comptes = fec[["CompteNum", "CompteLib"]].drop_duplicates().sort_values("CompteNum")
    comptes["Racine2"] = comptes["CompteNum"].str[:2]
    comptes["Classe"] = comptes["CompteNum"].str[0].map(LIBELLES_CLASSES)

    tiers = fec.loc[fec["CompAuxNum"] != "", ["CompAuxNum", "CompAuxLib"]].drop_duplicates()
    tiers.columns = ["TiersCode", "Tiers"]
    tiers["TypeTiers"] = np.where(tiers["TiersCode"].str.startswith("C"), "Client", "Fournisseur")
    tiers = pd.concat([tiers, pd.DataFrame([{"TiersCode": "AUCUN", "Tiers": "(sans tiers)", "TypeTiers": "(sans tiers)"}])])

    journaux = fec[["JournalCode", "JournalLib"]].drop_duplicates()

    dates = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    calendrier = pd.DataFrame({"Date": dates})
    calendrier["Annee"] = dates.year
    calendrier["Trimestre"] = "T" + dates.quarter.astype(str)
    calendrier["MoisNum"] = dates.month
    calendrier["Mois"] = [MOIS[m - 1] for m in dates.month]
    calendrier["JourSemaineNum"] = dates.day_of_week + 1
    calendrier["JourSemaine"] = [JOURS[d] for d in dates.day_of_week]
    calendrier["JourOuvre"] = (dates.day_of_week < 5) & ~dates.isin(ta.FERIES)
    calendrier["JoursAvantCloture"] = (ta.FIN_EXERCICE - dates).days

    # --- Benford ---------------------------------------------------------------------------
    hors_an = fec[fec["JournalCode"] != "AN"]
    distributions = []
    r = bf.test_benford(hors_an["Debit"] + hors_an["Credit"])
    distributions.append(r.tableau.reset_index().assign(Segment="Tout le FEC", Effectif=r.effectif))
    ecr_tiers = ta.tableau_ecritures(hors_an)["tiers_lib"]
    achats_ht = hors_an[(hors_an["JournalCode"] == "AC") & hors_an["CompteNum"].str.startswith("6")
                        & (hors_an["Debit"] > 0)]
    achats_ht = achats_ht.assign(fournisseur=achats_ht["EcritureNum"].map(ecr_tiers))
    par_fournisseur = bf.benford_par_groupe(achats_ht, "fournisseur", "Debit", effectif_min=10)
    for nom in par_fournisseur.index:
        r = bf.test_benford(achats_ht.loc[achats_ht["fournisseur"] == nom, "Debit"])
        distributions.append(r.tableau.reset_index().assign(Segment=f"Fournisseur : {nom}", Effectif=r.effectif))
    benford = pd.concat(distributions)
    benford.columns = ["Chiffre", "NbMontants", "PartObservee", "PartAttendue", "Ecart", "Z", "Segment", "EffectifSegment"]
    benford = benford[["Segment", "Chiffre", "NbMontants", "EffectifSegment", "PartObservee", "PartAttendue", "Ecart", "Z"]]

    benford_f = par_fournisseur.reset_index()
    benford_f.columns = ["Fournisseur", "NbFactures", "MAD", "PValue", "ChiffreDominant",
                         "PartChiffreDominant", "AttenduChiffreDominant"]
    benford_f["Alerte"] = np.where(benford_f["PValue"] < 0.001, "Écart fort", "Conforme ou écart faible")

    print(f"Export vers {SORTIE.relative_to(RACINE)} :")
    ecrire(faits, "Faits_Lignes")
    ecrire(ecritures, "Ecritures")
    ecrire(alertes, "Alertes")
    ecrire(comptes, "Comptes")
    ecrire(tiers, "Tiers")
    ecrire(journaux, "Journaux")
    ecrire(calendrier, "Calendrier")
    ecrire(benford.round(6), "Benford_Distribution")
    ecrire(benford_f.round(6), "Benford_Fournisseurs")


if __name__ == "__main__":
    main()
