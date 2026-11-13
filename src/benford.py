"""
Loi de Benford appliquée aux montants comptables.

Dans de nombreuses données financières « naturelles », le premier chiffre significatif
n'est pas uniforme : environ 30,1 % des montants commencent par 1, mais seulement 4,6 % par 9.
La probabilité que le premier chiffre (ou les deux premiers) vaille d est log10(1 + 1/d).

Références : Nigrini, *Benford's Law: Applications for Forensic Accounting, Auditing,
and Fraud Detection* (2012), pour les seuils de conformité MAD et le test z.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

# Seuils de conformité de Nigrini sur l'écart absolu moyen (MAD)
SEUILS_MAD = {
    1: [(0.006, "Conformité forte"), (0.012, "Conformité acceptable"),
        (0.015, "Conformité marginale"), (np.inf, "Non-conformité")],
    2: [(0.0012, "Conformité forte"), (0.0018, "Conformité acceptable"),
        (0.0022, "Conformité marginale"), (np.inf, "Non-conformité")],
}


def premiers_chiffres(montants, n: int = 1) -> pd.Series:
    """Les n premiers chiffres de chaque montant (montants d'au moins 10 €)."""
    m = pd.Series(montants, dtype=float).abs()
    m = m[m >= 10]
    return m.astype("int64").astype(str).str[:n].astype(int)


def distribution_benford(n: int = 1) -> pd.Series:
    """Probabilités théoriques de Benford pour le premier (n=1) ou les deux premiers chiffres (n=2)."""
    chiffres = np.arange(10 ** (n - 1), 10 ** n)
    return pd.Series(np.log10(1 + 1 / chiffres), index=chiffres, name="attendu")


def conformite(mad: float, n: int = 1) -> str:
    return next(libelle for seuil, libelle in SEUILS_MAD[n] if mad <= seuil)


@dataclass
class ResultatBenford:
    effectif: int
    mad: float
    conformite: str
    chi2: float
    p_value: float
    tableau: pd.DataFrame

    def resume(self) -> pd.Series:
        return pd.Series({
            "Montants analysés": f"{self.effectif:,}".replace(",", " "),
            "MAD (écart absolu moyen)": f"{self.mad:.4f}",
            "Verdict (seuils de Nigrini)": self.conformite,
            "Khi-deux": f"{self.chi2:,.1f}".replace(",", " "),
            "p-value": f"{self.p_value:.3g}",
        })


def test_benford(montants, n: int = 1) -> ResultatBenford:
    """Compare la distribution observée à Benford : MAD, khi-deux et test z par chiffre."""
    chiffres = premiers_chiffres(montants, n)
    total = len(chiffres)
    attendu = distribution_benford(n)
    effectifs = chiffres.value_counts().reindex(attendu.index, fill_value=0)
    observe = effectifs / total
    ecart = observe - attendu

    # Test z de Nigrini (avec correction de continuité) : |z| > 1,96 = écart significatif à 5 %
    z = ((ecart.abs() - 1 / (2 * total)) / np.sqrt(attendu * (1 - attendu) / total)).clip(lower=0)
    chi2, p_value = stats.chisquare(effectifs, attendu * total)

    tableau = pd.DataFrame({"effectif": effectifs, "observé": observe, "attendu": attendu,
                            "écart": ecart, "z": z})
    tableau.index.name = "chiffre" if n == 1 else "deux premiers chiffres"
    mad = float(ecart.abs().mean())
    return ResultatBenford(total, mad, conformite(mad, n), float(chi2), float(p_value), tableau)


def benford_par_groupe(donnees: pd.DataFrame, groupe: str, montant: str, effectif_min: int = 10) -> pd.DataFrame:
    """Test du premier chiffre pour chaque groupe (fournisseur, compte, journal…) d'au moins `effectif_min` montants."""
    lignes = []
    for nom, sous_ensemble in donnees.groupby(groupe):
        chiffres = premiers_chiffres(sous_ensemble[montant])
        if len(chiffres) < effectif_min:
            continue
        r = test_benford(sous_ensemble[montant])
        dominant = r.tableau["observé"].idxmax()
        lignes.append({groupe: nom, "montants": r.effectif, "MAD": r.mad, "p-value": r.p_value,
                       "chiffre dominant": dominant,
                       "part du chiffre dominant": r.tableau.loc[dominant, "observé"],
                       "attendu pour ce chiffre": r.tableau.loc[dominant, "attendu"]})
    return pd.DataFrame(lignes).set_index(groupe).sort_values("p-value")


def part_montants_ronds(montants: pd.Series) -> pd.Series:
    """Part des montants sans centimes et part des multiples de 100 € (montants >= 10 €)."""
    m = montants[montants >= 10]
    sans_centimes = (m.round(2) % 1 == 0)
    multiples_100 = (m.round(2) % 100 == 0)
    return pd.Series({"montants": len(m), "sans centimes": sans_centimes.mean(),
                      "multiples de 100 €": multiples_100.mean()})
