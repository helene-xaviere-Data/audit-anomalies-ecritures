"""Chargement du FEC dans un DataFrame pandas prêt à analyser."""

from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parents[1]
FEC_PAR_DEFAUT = RACINE / "data" / "raw" / "999999999FEC20251231.txt"
COLONNES_DATES = ["EcritureDate", "PieceDate", "ValidDate", "DateLet"]


def charger_fec(chemin: str | Path = FEC_PAR_DEFAUT) -> pd.DataFrame:
    """Lit un FEC (tabulation, décimales à virgule, dates AAAAMMJJ) et convertit les types.

    Colonnes ajoutées :
        - Montant : Debit - Credit (positif = débit, négatif = crédit)
        - Classe  : premier chiffre du compte (6 = charges, 7 = produits, etc.)
    """
    fec = pd.read_csv(chemin, sep="\t", dtype=str, keep_default_na=False, encoding="utf-8")
    for col in ("Debit", "Credit"):
        fec[col] = fec[col].str.replace(",", ".", regex=False).astype(float)
    for col in COLONNES_DATES:
        fec[col] = pd.to_datetime(fec[col], format="%Y%m%d", errors="coerce")
    fec["Montant"] = (fec["Debit"] - fec["Credit"]).round(2)
    fec["Classe"] = fec["CompteNum"].str[0]
    return fec
