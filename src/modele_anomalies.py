"""
Détection d'anomalies non supervisée (Isolation Forest) sur les écritures comptables.

Principe : chaque écriture est décrite par des variables génériques (montant, calendrier,
délai de validation, rareté du schéma comptable, comportement du tiers…). L'Isolation Forest
isole les écritures « qui ne ressemblent pas aux autres », sans connaître les fraudes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score

import tests_audit as ta

DESCRIPTION_VARIABLES = {
    "log_montant": "Montant de l'écriture (échelle logarithmique)",
    "ecart_montant_schema": "Écart du montant par rapport aux écritures du même type",
    "montant_rond": "Montant multiple de 100 € sans centimes",
    "jour_non_ouvre": "Date un week-end ou un jour férié",
    "jours_avant_cloture": "Nombre de jours avant le 31/12",
    "delai_validation": "Jours entre la date et la validation",
    "rarete_schema": "Rareté de la combinaison de comptes",
    "desequilibre": "Écart débit - crédit (log)",
    "nb_meme_piece": "Écritures portant le même tiers et la même pièce",
    "anciennete_tiers": "Jours depuis la première écriture du tiers",
    "dispersion_montants_tiers": "Variabilité des montants du tiers",
    "delai_reglement_tiers": "Délai médian de règlement du tiers",
    "journal_OD": "Journal des opérations diverses",
    "journal_BQ": "Journal de banque",
    "journal_AC": "Journal des achats",
    "journal_VE": "Journal des ventes",
}


def construire_variables(fec: pd.DataFrame) -> pd.DataFrame:
    """Tableau « une ligne par écriture » avec les variables du modèle (hors à-nouveaux)."""
    fec = fec[fec["JournalCode"] != "AN"]
    ecr = ta.tableau_ecritures(fec)
    v = pd.DataFrame(index=ecr.index)

    v["log_montant"] = np.log10(ecr["montant"].clip(lower=1))
    groupe = v.groupby(ecr["schema"])["log_montant"]
    v["ecart_montant_schema"] = ((v["log_montant"] - groupe.transform("mean"))
                                 / groupe.transform("std").fillna(0).replace(0, 1)).abs()
    v["montant_rond"] = ((ecr["montant"] % 100 == 0) & (ecr["montant"] >= 100)).astype(int)

    date = ecr["EcritureDate"]
    v["jour_non_ouvre"] = ((date.dt.day_of_week >= 5) | date.isin(ta.FERIES)).astype(int)
    v["jours_avant_cloture"] = (ta.FIN_EXERCICE - date).dt.days
    v["delai_validation"] = ecr["delai_validation"]

    v["rarete_schema"] = -np.log10(ecr["schema"].map(ecr["schema"].value_counts()) / len(ecr))
    v["desequilibre"] = np.log10(1 + ecr["solde"].abs())
    v["nb_meme_piece"] = ecr.groupby(["tiers", "PieceRef"])["montant"].transform("size").where(ecr["tiers"] != "", 1)

    # Comportement du tiers (client ou fournisseur)
    a_tiers = ecr["tiers"] != ""
    premiere = ecr[a_tiers].groupby("tiers")["EcritureDate"].transform("min")
    v["anciennete_tiers"] = (date - premiere).dt.days.reindex(ecr.index).fillna(365)
    v["dispersion_montants_tiers"] = (v.loc[a_tiers, "log_montant"].groupby(ecr.loc[a_tiers, "tiers"])
                                      .transform("std").reindex(ecr.index).fillna(0.5))
    lettrees = fec[(fec["EcritureLet"] != "") & (fec["Credit"] + fec["Debit"] > 0)
                   & fec["JournalCode"].isin(["VE", "AC"]) & (fec["CompAuxNum"] != "")]
    delais = (lettrees["DateLet"] - lettrees["EcritureDate"]).dt.days.groupby(lettrees["CompAuxNum"]).median()
    v["delai_reglement_tiers"] = ecr["tiers"].map(delais).fillna(delais.median())

    for journal in ["OD", "BQ", "AC", "VE"]:
        v[f"journal_{journal}"] = (ecr["JournalCode"] == journal).astype(int)

    return v[list(DESCRIPTION_VARIABLES)].astype(float), ecr


def entrainer(variables: pd.DataFrame, graine: int = 42) -> tuple[IsolationForest, pd.Series]:
    """Entraîne l'Isolation Forest et renvoie le score d'anomalie (plus il est élevé, plus c'est suspect)."""
    modele = IsolationForest(n_estimators=500, max_samples=256, random_state=graine)
    modele.fit(variables)
    score = pd.Series(-modele.score_samples(variables), index=variables.index, name="score_anomalie")
    return modele, score


def courbe_rappel(score: pd.Series, est_anomalie: pd.Series, tailles=(25, 50, 91, 100, 200, 300, 500)) -> pd.DataFrame:
    """Précision et rappel parmi les k écritures les plus suspectes."""
    ordre = score.sort_values(ascending=False).index
    lignes = []
    for k in tailles:
        top = est_anomalie.loc[ordre[:k]]
        lignes.append({"k (écritures examinées)": k, "anomalies trouvées": int(top.sum()),
                       "précision": top.mean(), "rappel": top.sum() / est_anomalie.sum()})
    return pd.DataFrame(lignes).set_index("k (écritures examinées)")


def precision_moyenne(score: pd.Series, est_anomalie: pd.Series) -> float:
    """Average precision (aire sous la courbe précision-rappel). Un tirage au hasard vaut le taux d'anomalies."""
    return float(average_precision_score(est_anomalie, score))


def expliquer(variables: pd.DataFrame, ecriture: str, seuil: float = 0.02) -> list[str]:
    """Variables pour lesquelles l'écriture fait partie des 2 % les plus extrêmes."""
    rangs = variables.rank(pct=True)
    raisons = []
    for col in variables.columns:
        valeur = variables.loc[ecriture, col]
        if variables[col].nunique() <= 2:
            if valeur == 1 and variables[col].mean() < seuil * 5:
                raisons.append(DESCRIPTION_VARIABLES[col])
            continue
        r = rangs.loc[ecriture, col]
        if r >= 1 - seuil or r <= seuil:
            sens = "très élevé" if r >= 1 - seuil else "très faible"
            raisons.append(f"{DESCRIPTION_VARIABLES[col]} : {sens}")
    return raisons
