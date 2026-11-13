"""
Tests d'audit sur les écritures comptables (« journal entry testing »).

Chaque test prend le FEC (une ligne par mouvement) et le tableau des écritures
(une ligne par écriture) et renvoie une série booléenne : True = écriture signalée.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DEBUT_EXERCICE = pd.Timestamp("2025-01-01")
FIN_EXERCICE = pd.Timestamp("2025-12-31")
SEUIL_APPROBATION = 5_000.0

FERIES = pd.to_datetime([
    "2025-01-01", "2025-04-21", "2025-05-01", "2025-05-08", "2025-05-29", "2025-06-09",
    "2025-07-14", "2025-08-15", "2025-11-01", "2025-11-11", "2025-12-25",
])


# ---------------------------------------------------------------------------
# Préparation : passer d'une ligne par mouvement à une ligne par écriture
# ---------------------------------------------------------------------------
def tableau_ecritures(fec: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par écriture, avec les informations utiles aux tests."""
    ecr = fec.groupby("EcritureNum").agg(
        JournalCode=("JournalCode", "first"),
        EcritureDate=("EcritureDate", "first"),
        ValidDate=("ValidDate", "first"),
        PieceRef=("PieceRef", "first"),
        EcritureLib=("EcritureLib", "first"),
        montant=("Debit", "sum"),
        solde=("Montant", "sum"),
        nb_lignes=("CompteNum", "size"),
    )
    lignes_tiers = fec[fec["CompAuxNum"] != ""].groupby("EcritureNum")
    ecr["tiers"] = lignes_tiers["CompAuxNum"].first().reindex(ecr.index).fillna("")
    ecr["tiers_lib"] = lignes_tiers["CompAuxLib"].first().reindex(ecr.index).fillna("")

    # Schéma comptable : la combinaison des comptes et de leur sens (D = débit, C = crédit)
    sens = np.where(fec["Debit"] > 0, "D", "C")
    cles = fec["CompteNum"] + sens
    ecr["schema"] = cles.groupby(fec["EcritureNum"]).agg(lambda s: " ".join(sorted(set(s))))

    ecr["solde"] = ecr["solde"].round(2)
    ecr["delai_validation"] = (ecr["ValidDate"] - ecr["EcritureDate"]).dt.days
    return ecr


# ---------------------------------------------------------------------------
# Les tests
# ---------------------------------------------------------------------------
def test_desequilibre(fec, ecr):
    """Total des débits différent du total des crédits."""
    return ecr["solde"].abs() > 0


def test_jour_non_ouvre(fec, ecr):
    """Écriture datée d'un samedi, d'un dimanche ou d'un jour férié (hors à-nouveaux)."""
    date = ecr["EcritureDate"]
    non_ouvre = (date.dt.day_of_week >= 5) | date.isin(FERIES)
    return non_ouvre & (ecr["JournalCode"] != "AN")


def test_montant_rond(fec, ecr, minimum=1_000, multiple=500):
    """Montant total d'au moins 1 000 €, multiple exact de 500 €."""
    return (ecr["montant"] >= minimum) & (ecr["montant"] % multiple == 0) & (ecr["JournalCode"] != "AN")


def test_doublon(fec, ecr):
    """Facture fournisseur dont le couple (fournisseur, n° de pièce) a déjà été comptabilisé."""
    achats = ecr[ecr["JournalCode"] == "AC"].sort_values("EcritureDate", kind="stable")
    doublons = achats.duplicated(subset=["tiers", "PieceRef"], keep="first")
    return doublons.reindex(ecr.index, fill_value=False)


def test_fin_exercice(fec, ecr, jours=5, quantile=0.95):
    """Écriture importante (au-dessus du 95e percentile de son journal) dans les 5 derniers jours."""
    seuil = ecr.groupby("JournalCode")["montant"].transform(lambda s: s.quantile(quantile))
    fin = ecr["EcritureDate"] > FIN_EXERCICE - pd.Timedelta(days=jours)
    return fin & (ecr["montant"] > seuil) & ecr["JournalCode"].isin(["VE", "AC", "OD"])


def test_validation_tardive(fec, ecr, jours=10):
    """Écriture validée plus de 10 jours après sa date comptable."""
    return ecr["delai_validation"] > jours


def test_sous_seuil(fec, ecr, seuil=SEUIL_APPROBATION, marge=0.10, min_factures=3):
    """Fournisseur ayant au moins 3 factures dont le HT est juste sous le seuil d'approbation (90-100 %)."""
    charges = fec[(fec["JournalCode"] == "AC") & fec["CompteNum"].str.startswith("6") & (fec["Debit"] > 0)]
    ht = charges.groupby("EcritureNum")["Debit"].sum()
    zone = ht[(ht >= seuil * (1 - marge)) & (ht < seuil)]
    tiers = ecr.loc[zone.index, "tiers"]
    nb_par_tiers = tiers.map(tiers.value_counts())
    suspectes = nb_par_tiers[nb_par_tiers >= min_factures].index
    return pd.Series(ecr.index.isin(suspectes), index=ecr.index)


def test_schema_rare(fec, ecr, max_occurrences=9):
    """Combinaison de comptes utilisée moins de 10 fois dans l'année (hors à-nouveaux)."""
    frequence = ecr["schema"].map(ecr["schema"].value_counts())
    return (frequence <= max_occurrences) & (ecr["JournalCode"] != "AN")


TESTS = {
    "desequilibre": (test_desequilibre, "Écriture déséquilibrée"),
    "jour_non_ouvre": (test_jour_non_ouvre, "Saisie un week-end ou un jour férié"),
    "montant_rond": (test_montant_rond, "Montant rond (multiple de 500 €)"),
    "doublon": (test_doublon, "Facture fournisseur en double"),
    "fin_exercice": (test_fin_exercice, "Écriture importante en fin d'exercice"),
    "validation_tardive": (test_validation_tardive, "Validation plus de 10 jours après la date"),
    "sous_seuil": (test_sous_seuil, "Factures répétées juste sous le seuil d'approbation"),
    "schema_rare": (test_schema_rare, "Combinaison de comptes inhabituelle"),
}


def appliquer_tests(fec: pd.DataFrame) -> pd.DataFrame:
    """Applique tous les tests. Renvoie le tableau des écritures avec une colonne par test."""
    ecr = tableau_ecritures(fec)
    for nom, (fonction, _) in TESTS.items():
        ecr[nom] = fonction(fec, ecr).astype(bool)
    ecr["nb_alertes"] = ecr[list(TESTS)].sum(axis=1)
    return ecr


# ---------------------------------------------------------------------------
# Évaluation par rapport aux anomalies injectées
# ---------------------------------------------------------------------------
def evaluer(ecr: pd.DataFrame, anomalies: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Compare les alertes à la vérité terrain.

    - precision : parmi les écritures signalées, part de vraies anomalies
    - rappel    : parmi les vraies anomalies, part retrouvée
    """
    est_anomalie = ecr.index.isin(anomalies["EcritureNum"])
    type_anomalie = anomalies.set_index("EcritureNum")["type_anomalie"].reindex(ecr.index)

    lignes = []
    for nom, (_, libelle) in TESTS.items():
        signale = ecr[nom]
        vrais = int((signale & est_anomalie).sum())
        lignes.append({"test": nom, "description": libelle, "signalées": int(signale.sum()),
                       "vraies anomalies": vrais, "fausses alertes": int(signale.sum()) - vrais,
                       "précision": vrais / signale.sum() if signale.sum() else np.nan})
    par_test = pd.DataFrame(lignes).set_index("test")

    au_moins_une = ecr["nb_alertes"] > 0
    par_type = (pd.DataFrame({"type": type_anomalie[est_anomalie], "retrouvée": au_moins_une[est_anomalie]})
                .groupby("type")["retrouvée"].agg(anomalies="size", retrouvées="sum"))
    par_type["rappel"] = par_type["retrouvées"] / par_type["anomalies"]

    matrice = (ecr.loc[est_anomalie, list(TESTS)]
               .groupby(type_anomalie[est_anomalie]).sum()
               .rename_axis("type d'anomalie"))

    vrais = int((au_moins_une & est_anomalie).sum())
    global_ = pd.Series({
        "Écritures testées": len(ecr),
        "Écritures signalées (≥ 1 test)": int(au_moins_une.sum()),
        "Anomalies cachées": int(est_anomalie.sum()),
        "Anomalies retrouvées": vrais,
        "Rappel": vrais / est_anomalie.sum(),
        "Précision": vrais / au_moins_une.sum(),
    })
    return {"par_test": par_test, "par_type": par_type, "matrice": matrice, "global": global_}
