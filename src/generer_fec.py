"""
Génère un Fichier des Écritures Comptables (FEC) simulé pour une PME fictive,
avec des anomalies cachées volontairement pour tester des contrôles d'audit.

Entreprise fictive : « Atelier Lumière SAS », distributeur de luminaires.
Exercice : du 01/01/2025 au 31/12/2025.

Usage (depuis le dossier du projet) :
    python src/generer_fec.py

Sorties dans data/raw/ :
    - 999999999FEC20251231.txt : le FEC au format officiel (séparateur tabulation)
    - anomalies_injectees.csv  : la « vérité terrain », c'est-à-dire la liste des
      anomalies cachées. Un auditeur ne l'a pas en réalité : elle sert uniquement
      à mesurer si nos tests retrouvent bien les anomalies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import product
from pathlib import Path

import sys

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paramètres généraux
# ---------------------------------------------------------------------------
SEED = 42  # graine aléatoire : on obtient toujours les mêmes données
EXERCICE_DEBUT = date(2025, 1, 1)
EXERCICE_FIN = date(2025, 12, 31)
TAUX_TVA = 0.20
SEUIL_APPROBATION = 5_000.0  # au-delà, une facture fournisseur doit être approuvée

RACINE = Path(__file__).resolve().parents[1]
DOSSIER_SORTIE = RACINE / "data" / "raw"
FICHIER_FEC = DOSSIER_SORTIE / "999999999FEC20251231.txt"
FICHIER_ANOMALIES = DOSSIER_SORTIE / "anomalies_injectees.csv"

rng = np.random.default_rng(SEED)

JOURNAUX = {
    "AN": "A nouveaux",
    "VE": "Journal des ventes",
    "AC": "Journal des achats",
    "BQ": "Banque",
    "PA": "Paie",
    "OD": "Opérations diverses",
}

PLAN_COMPTABLE = {
    "101000": "Capital",
    "110000": "Report à nouveau",
    "164000": "Emprunts auprès des établissements de crédit",
    "218300": "Matériel de bureau et informatique",
    "281830": "Amortissements du matériel de bureau",
    "370000": "Stocks de marchandises",
    "401000": "Fournisseurs",
    "411000": "Clients",
    "421000": "Personnel - rémunérations dues",
    "431000": "Sécurité sociale",
    "445660": "TVA déductible sur autres biens et services",
    "445710": "TVA collectée",
    "512000": "Banque",
    "606100": "Fournitures non stockables",
    "607000": "Achats de marchandises",
    "613200": "Locations immobilières",
    "622600": "Honoraires",
    "625100": "Voyages et déplacements",
    "626000": "Frais postaux et de télécommunications",
    "627000": "Services bancaires",
    "641000": "Rémunérations du personnel",
    "645000": "Charges de sécurité sociale",
    "681120": "Dotations aux amortissements",
    "707000": "Ventes de marchandises",
}

# ---------------------------------------------------------------------------
# Calendrier : jours ouvrés 2025 (hors week-ends et jours fériés)
# ---------------------------------------------------------------------------
FERIES = {
    date(2025, 1, 1), date(2025, 4, 21), date(2025, 5, 1), date(2025, 5, 8),
    date(2025, 5, 29), date(2025, 6, 9), date(2025, 7, 14), date(2025, 8, 15),
    date(2025, 11, 1), date(2025, 11, 11), date(2025, 12, 25), date(2026, 1, 1),
}


def est_ouvre(d: date) -> bool:
    return d.weekday() < 5 and d not in FERIES


def prochain_jour_ouvre(d: date) -> date:
    while not est_ouvre(d):
        d += timedelta(days=1)
    return d


JOURS_OUVRES = [
    EXERCICE_DEBUT + timedelta(days=i)
    for i in range((EXERCICE_FIN - EXERCICE_DEBUT).days + 1)
    if est_ouvre(EXERCICE_DEBUT + timedelta(days=i))
]


def jour_ouvre_aleatoire(mois: int | None = None, debut: date | None = None, fin: date | None = None) -> date:
    candidats = [
        d for d in JOURS_OUVRES
        if (mois is None or d.month == mois)
        and (debut is None or d >= debut)
        and (fin is None or d <= fin)
    ]
    return candidats[rng.integers(len(candidats))]


def dernier_jour_ouvre(mois: int) -> date:
    return max(d for d in JOURS_OUVRES if d.month == mois)


def montant_aleatoire(mediane: float, dispersion: float, mini: float, maxi: float) -> float:
    """Montant tiré d'une loi log-normale (la forme typique des montants comptables)."""
    return round(float(np.clip(rng.lognormal(np.log(mediane), dispersion), mini, maxi)), 2)


# ---------------------------------------------------------------------------
# Structures : une écriture = plusieurs lignes dont le total débit = total crédit
# ---------------------------------------------------------------------------
@dataclass
class Ecriture:
    journal: str
    date: date
    piece_ref: str
    libelle: str
    lignes: list[dict]
    piece_date: date | None = None
    valid_date: date | None = None
    anomalie: str | None = None
    anomalie_desc: str | None = None
    ordre: int = field(default=0)


def ligne(compte: str, debit: float = 0.0, credit: float = 0.0, tiers: tuple | None = None,
          lettrage: tuple | None = None) -> dict:
    """tiers = (code, nom) ; lettrage = (identifiant du rapprochement, date)."""
    return {"compte": compte, "debit": round(debit, 2), "credit": round(credit, 2),
            "tiers": tiers, "lettrage": lettrage}


ecritures: list[Ecriture] = []
compteur_lettrage = iter(range(1, 1_000_000))


def ajouter(e: Ecriture) -> Ecriture:
    e.ordre = len(ecritures)
    ecritures.append(e)
    return e


# ---------------------------------------------------------------------------
# Tiers : clients et fournisseurs fictifs
# ---------------------------------------------------------------------------
PREFIXES = ["Boutique", "Hôtel", "Restaurant", "Café", "Maison", "Galerie", "Agence", "Studio"]
NOMS = ["Horizon", "Saint-Michel", "des Arts", "Belle Époque", "du Port", "Opale", "Riviera",
        "Montmartre", "Vauban", "Bellevue", "Croix-Rousse", "Confluence", "Garonne", "Chartrons"]
combinaisons = [f"{p} {n}" for p, n in product(PREFIXES, NOMS)]
noms_clients = rng.choice(combinaisons, size=40, replace=False)
CLIENTS = [(f"C{i:04d}", str(nom)) for i, nom in enumerate(noms_clients, start=1)]
# Quelques gros clients concentrent l'essentiel du chiffre d'affaires
poids_clients = 1 / np.arange(1, len(CLIENTS) + 1) ** 0.8
poids_clients /= poids_clients.sum()

PREFIXES_F = ["Distribution", "Grossiste", "Import", "Manufacture", "Fabrique", "Comptoir"]
NOMS_F = ["Lumen", "Éclat", "Verre & Laiton", "Atlas", "Nordlicht", "Céramique du Sud", "Métal Design"]
noms_fournisseurs = rng.choice([f"{p} {n}" for p, n in product(PREFIXES_F, NOMS_F)], size=18, replace=False)
FOURNISSEURS_MARCHANDISES = [(f"F{i:04d}", str(n)) for i, n in enumerate(noms_fournisseurs, start=1)]

F_BUREAU = [("F0019", "Bureau Plus Fournitures"), ("F0020", "Papeterie Centrale")]
F_TELECOM = ("F0021", "TéléCom Pro Services")
F_BAILLEUR = ("F0022", "SCI Les Tilleuls")
F_COMPTABLE = ("F0023", "Cabinet Expertise Comptable Martin")
F_VOYAGES = [("F0024", "Voyages Affaires Express"), ("F0025", "Hôtels Étape Business")]
F_FICTIF = ("F0099", "Conseil Stratégie Plus")  # fournisseur fictif (anomalie)


# ---------------------------------------------------------------------------
# Fonctions de création des opérations courantes
# ---------------------------------------------------------------------------
def creer_achat(fournisseur: tuple, compte_charge: str, d: date, ht: float, ref: str | None = None,
                delai: int | None = None, payer: bool = True) -> tuple[Ecriture, Ecriture | None]:
    """Facture fournisseur (journal AC) puis, si elle est payée dans l'exercice, son règlement (BQ)."""
    ref = ref or f"{fournisseur[0]}-{rng.integers(10_000, 99_999)}"
    tva = round(ht * TAUX_TVA, 2)
    ttc = round(ht + tva, 2)
    if delai is None:
        delai = int(rng.choice([30, 45, 60]) + rng.normal(0, 5))
    date_paiement = prochain_jour_ouvre(d + timedelta(days=max(delai, 0)))
    payee = payer and date_paiement <= EXERCICE_FIN and rng.random() > 0.02
    lettrage = (next(compteur_lettrage), date_paiement) if payee else None

    facture = ajouter(Ecriture(
        "AC", d, ref, f"Facture {ref} {fournisseur[1]}",
        [ligne(compte_charge, debit=ht), ligne("445660", debit=tva),
         ligne("401000", credit=ttc, tiers=fournisseur, lettrage=lettrage)],
        piece_date=d - timedelta(days=int(rng.integers(0, 6))),
    ))
    reglement = None
    if payee:
        reglement = ajouter(Ecriture(
            "BQ", date_paiement, f"VIR-{ref}", f"Règlement {fournisseur[1]} {ref}",
            [ligne("401000", debit=ttc, tiers=fournisseur, lettrage=lettrage), ligne("512000", credit=ttc)],
        ))
    return facture, reglement


def creer_ventes() -> None:
    """Factures clients (VE) et encaissements (BQ), avec une saisonnalité marquée en fin d'année."""
    poids_mois = np.array([7, 7, 8, 8, 8, 8, 8, 5, 8, 9, 11, 13], dtype=float)
    poids_mois /= poids_mois.sum()
    ventes = []
    for _ in range(2_400):
        mois = int(rng.choice(np.arange(1, 13), p=poids_mois))
        ventes.append({
            "date": jour_ouvre_aleatoire(mois),
            "client": CLIENTS[rng.choice(len(CLIENTS), p=poids_clients)],
            "ht": montant_aleatoire(750, 1.1, 15, 40_000),
            "fictive": False,
        })
    # ANOMALIE : ventes fictives passées dans les tout derniers jours de l'exercice
    for _ in range(10):
        ventes.append({
            "date": rng.choice([date(2025, 12, 29), date(2025, 12, 30), date(2025, 12, 31)]),
            "client": CLIENTS[rng.integers(0, 10)],
            "ht": float(round(rng.uniform(8_000, 25_000), -2)),
            "fictive": True,
        })

    ventes.sort(key=lambda v: v["date"])
    for numero, v in enumerate(ventes, start=1):
        num_facture = f"FA2025-{numero:05d}"
        client, ht = v["client"], v["ht"]
        tva = round(ht * TAUX_TVA, 2)
        ttc = round(ht + tva, 2)
        delai = int(rng.choice([30, 45, 60]) + rng.normal(0, 7))
        date_paiement = prochain_jour_ouvre(v["date"] + timedelta(days=max(delai, 0)))
        payee = not v["fictive"] and date_paiement <= EXERCICE_FIN and rng.random() > 0.04
        lettrage = (next(compteur_lettrage), date_paiement) if payee else None

        facture = ajouter(Ecriture(
            "VE", v["date"], num_facture, f"Facture {num_facture} {client[1]}",
            [ligne("411000", debit=ttc, tiers=client, lettrage=lettrage),
             ligne("707000", credit=ht), ligne("445710", credit=tva)],
        ))
        if v["fictive"]:
            facture.libelle = f"Facture {num_facture} prestation complémentaire {client[1]}"
            facture.valid_date = date(2026, 1, int(rng.integers(12, 28)))
            facture.anomalie = "vente_fictive_cloture"
            facture.anomalie_desc = ("Vente importante saisie en fin d'exercice, jamais encaissée "
                                     "et validée après la clôture")
        if payee:
            ajouter(Ecriture(
                "BQ", date_paiement, f"REM-{num_facture}", f"Encaissement {client[1]} {num_facture}",
                [ligne("512000", debit=ttc), ligne("411000", credit=ttc, tiers=client, lettrage=lettrage)],
            ))


def creer_achats() -> list[tuple]:
    """Achats de marchandises et frais généraux. Renvoie les achats de marchandises (pour les doublons)."""
    achats_marchandises = []
    for _ in range(900):
        f = FOURNISSEURS_MARCHANDISES[rng.integers(len(FOURNISSEURS_MARCHANDISES))]
        d = jour_ouvre_aleatoire()
        ht = montant_aleatoire(1_300, 1.0, 20, 30_000)
        facture, reglement = creer_achat(f, "607000", d, ht)
        achats_marchandises.append((f, d, ht, facture.piece_ref, facture))
    for _ in range(150):
        creer_achat(F_BUREAU[rng.integers(2)], "606100", jour_ouvre_aleatoire(),
                    montant_aleatoire(150, 0.8, 10, 2_500))
    for _ in range(100):
        creer_achat(F_VOYAGES[rng.integers(2)], "625100", jour_ouvre_aleatoire(),
                    montant_aleatoire(250, 0.7, 30, 3_000))
    for mois in range(1, 13):
        premier = min(d for d in JOURS_OUVRES if d.month == mois)
        creer_achat(F_BAILLEUR, "613200", premier, 3_500.00, ref=f"LOYER-2025-{mois:02d}", delai=5)
        creer_achat(F_TELECOM, "626000", jour_ouvre_aleatoire(mois),
                    round(rng.uniform(160, 210), 2), ref=f"TEL-2025-{mois:02d}")
    for mois in (3, 6, 9, 12):
        creer_achat(F_COMPTABLE, "622600", dernier_jour_ouvre(mois), 2_400.00,
                    ref=f"HON-2025-T{mois // 3}", delai=15)
    return achats_marchandises


def creer_paie() -> None:
    """Paie mensuelle de 18 salariés : charges, net à payer, cotisations sociales."""
    salaires_bruts = rng.uniform(1_900, 3_800, size=18).round(-1)
    for mois in range(1, 13):
        brut = float(salaires_bruts.sum()) * (2 if mois == 12 else 1)  # 13e mois en décembre
        cotis_salariales = round(brut * 0.22, 2)
        net = round(brut - cotis_salariales, 2)
        cotis_patronales = round(brut * 0.42, 2)
        d = dernier_jour_ouvre(mois)
        ajouter(Ecriture("PA", d, f"PAIE-2025-{mois:02d}", f"Paie {mois:02d}/2025", [
            ligne("641000", debit=brut), ligne("421000", credit=net), ligne("431000", credit=cotis_salariales),
            ligne("645000", debit=cotis_patronales), ligne("431000", credit=cotis_patronales),
        ]))
        ajouter(Ecriture("BQ", d, f"VIR-SAL-2025-{mois:02d}", f"Virement salaires {mois:02d}/2025",
                         [ligne("421000", debit=net), ligne("512000", credit=net)]))
        if mois < 12:  # les cotisations de décembre sont payées en janvier 2026
            d_urssaf = prochain_jour_ouvre(date(2025, mois + 1, 15))
            total = round(cotis_salariales + cotis_patronales, 2)
            ajouter(Ecriture("BQ", d_urssaf, f"URSSAF-2025-{mois:02d}", f"Cotisations sociales {mois:02d}/2025",
                             [ligne("431000", debit=total), ligne("512000", credit=total)]))


def creer_declarations_tva() -> None:
    """Chaque mois, la TVA collectée moins la TVA déductible est reversée à l'État (le 20 du mois suivant)."""
    for mois in range(1, 12):  # la TVA de décembre est payée en janvier 2026
        collectee = deductible = 0.0
        for e in ecritures:
            if e.date.month == mois and e.journal in ("VE", "AC"):
                for l in e.lignes:
                    if l["compte"] == "445710":
                        collectee += l["credit"] - l["debit"]
                    elif l["compte"] == "445660":
                        deductible += l["debit"] - l["credit"]
        collectee, deductible = round(collectee, 2), round(deductible, 2)
        a_payer = round(collectee - deductible, 2)
        if a_payer <= 0:
            continue
        ajouter(Ecriture("BQ", prochain_jour_ouvre(date(2025, mois + 1, 20)), f"TVA-2025-{mois:02d}",
                         f"Paiement TVA {mois:02d}/2025",
                         [ligne("445710", debit=collectee), ligne("445660", credit=deductible),
                          ligne("512000", credit=a_payer)]))


def creer_operations_diverses() -> None:
    """À-nouveaux, frais bancaires, remboursement d'emprunt, amortissements."""
    ajouter(Ecriture("AN", EXERCICE_DEBUT, "AN-2025", "Reprise des soldes au 01/01/2025", [
        ligne("218300", debit=60_000), ligne("370000", debit=45_000), ligne("512000", debit=350_000),
        ligne("281830", credit=24_000), ligne("101000", credit=50_000),
        ligne("164000", credit=70_000), ligne("110000", credit=311_000),
    ]))
    for mois in range(1, 13):
        d = dernier_jour_ouvre(mois)
        frais = round(rng.uniform(35, 60), 2)
        ajouter(Ecriture("BQ", d, f"FRAIS-2025-{mois:02d}", f"Frais bancaires {mois:02d}/2025",
                         [ligne("627000", debit=frais), ligne("512000", credit=frais)]))
        echeance = prochain_jour_ouvre(date(2025, mois, 5))
        ajouter(Ecriture("BQ", echeance, f"PRET-2025-{mois:02d}", f"Échéance emprunt {mois:02d}/2025",
                         [ligne("164000", debit=1_200), ligne("512000", credit=1_200)]))
    ajouter(Ecriture("OD", EXERCICE_FIN, "AMORT-2025", "Dotation aux amortissements 2025",
                     [ligne("681120", debit=12_000), ligne("281830", credit=12_000)],
                     valid_date=date(2026, 1, 15)))


# ---------------------------------------------------------------------------
# Anomalies injectées (ce que l'audit doit retrouver)
# ---------------------------------------------------------------------------
def marquer(e: Ecriture, type_anomalie: str, description: str) -> None:
    e.anomalie, e.anomalie_desc = type_anomalie, description


def injecter_anomalies(achats_marchandises: list[tuple]) -> None:
    # 1. Doublons : la même facture fournisseur saisie (et payée) deux fois
    indices = rng.choice(len(achats_marchandises), size=12, replace=False)
    for i in indices:
        f, d, ht, ref, _ = achats_marchandises[i]
        d_doublon = prochain_jour_ouvre(d + timedelta(days=int(rng.integers(1, 12))))
        if d_doublon > EXERCICE_FIN:
            continue
        doublon, _ = creer_achat(f, "607000", d_doublon, ht, ref=ref)
        marquer(doublon, "doublon", f"Facture {ref} déjà comptabilisée le {d:%d/%m/%Y}")

    # 2. Fractionnement sous le seuil d'approbation, par un fournisseur fictif
    dates = sorted(jour_ouvre_aleatoire(debut=date(2025, 6, 2), fin=date(2025, 11, 28)) for _ in range(9))
    dates += list(rng.choice(dates, size=5, replace=False))
    for d in dates:
        ht = round(float(rng.uniform(4_750, 4_990)), 2)
        facture, _ = creer_achat(F_FICTIF, "622600", d, ht, delai=int(rng.integers(3, 8)), payer=True)
        marquer(facture, "fractionnement_seuil",
                f"Facture juste sous le seuil d'approbation de {SEUIL_APPROBATION:,.0f} € "
                "d'un nouveau fournisseur payé très rapidement")

    # 3. Montants ronds sans pièce justificative, payés directement en OD
    for _ in range(12):
        d = jour_ouvre_aleatoire()
        montant = float(rng.choice([1_000, 1_500, 2_000, 2_500, 3_000, 5_000, 7_500, 10_000, 15_000]))
        compte = str(rng.choice(["622600", "625100", "606100"]))
        libelle = str(rng.choice(["Régularisation", "Divers", "Ajustement", "Frais divers"]))
        e = ajouter(Ecriture("OD", d, f"OD-{rng.integers(1000, 9999)}", libelle,
                             [ligne(compte, debit=montant), ligne("512000", credit=montant)]))
        marquer(e, "montant_rond", "Montant rond, libellé vague, sortie de banque passée en OD")

    # 4. Écritures déséquilibrées (inversion de chiffres lors de la saisie)
    for _ in range(4):
        d = jour_ouvre_aleatoire()
        debit = float(rng.integers(1_000, 9_999))
        chiffres = list(f"{int(debit)}")
        chiffres[1], chiffres[2] = chiffres[2], chiffres[1]
        credit = float("".join(chiffres))
        if credit == debit:
            credit += 9
        e = ajouter(Ecriture("OD", d, f"OD-{rng.integers(1000, 9999)}", "Reclassement de charges",
                             [ligne("606100", debit=debit), ligne("607000", credit=credit)]))
        marquer(e, "desequilibre", f"Débit {debit:.2f} ≠ crédit {credit:.2f} (chiffres inversés)")

    # 5. Avoirs antidatés : validés plusieurs mois après la date d'écriture
    for _ in range(8):
        d = jour_ouvre_aleatoire(debut=date(2025, 3, 1), fin=date(2025, 9, 30))
        f = FOURNISSEURS_MARCHANDISES[rng.integers(len(FOURNISSEURS_MARCHANDISES))]
        ht = montant_aleatoire(2_500, 0.5, 500, 9_000)
        tva = round(ht * TAUX_TVA, 2)
        ref = f"AV-{f[0]}-{rng.integers(100, 999)}"
        e = ajouter(Ecriture("AC", d, ref, f"Avoir commercial {f[1]}",
                             [ligne("401000", debit=round(ht + tva, 2), tiers=f),
                              ligne("607000", credit=ht), ligne("445660", credit=tva)],
                             valid_date=d + timedelta(days=int(rng.integers(90, 200)))))
        marquer(e, "validation_tardive", "Avoir réduisant les charges, validé plus de 3 mois après sa date")

    # 6. Contreparties inhabituelles : salaires payés hors du journal de paie
    for _ in range(6):
        d = jour_ouvre_aleatoire()
        montant = montant_aleatoire(1_500, 0.4, 400, 5_000)
        libelle = str(rng.choice(["Avance sur salaire", "Prime exceptionnelle"]))
        e = ajouter(Ecriture("BQ", d, f"VIR-{rng.integers(10000, 99999)}", libelle,
                             [ligne("641000", debit=montant), ligne("512000", credit=montant)]))
        marquer(e, "contrepartie_inhabituelle", "Rémunération payée directement par la banque, hors paie")

    # 7. Saisies le week-end : écritures courantes déplacées un samedi ou un dimanche
    candidates = [e for e in ecritures if e.journal in ("VE", "AC") and e.anomalie is None]
    for i in rng.choice(len(candidates), size=15, replace=False):
        e = candidates[i]
        nouvelle_date = e.date + timedelta(days=5 - e.date.weekday() + int(rng.integers(0, 2)))
        if nouvelle_date > EXERCICE_FIN:
            continue
        e.date = nouvelle_date
        marquer(e, "saisie_weekend", f"Écriture datée d'un {['samedi', 'dimanche'][nouvelle_date.weekday() - 5]}")


# ---------------------------------------------------------------------------
# Mise au format FEC et export
# ---------------------------------------------------------------------------
def code_lettrage(n: int) -> str:
    """0 -> AAA, 1 -> AAB, ... (codes de rapprochement factures / règlements)."""
    lettres = ""
    for _ in range(3):
        n, reste = divmod(n, 26)
        lettres = chr(65 + reste) + lettres
    return lettres


def fmt_date(d: date | None) -> str:
    return d.strftime("%Y%m%d") if d else ""


def fmt_montant(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def exporter() -> pd.DataFrame:
    ordre_journaux = list(JOURNAUX)
    ecritures.sort(key=lambda e: (ordre_journaux.index(e.journal), e.date, e.ordre))

    # Codes de lettrage : numérotés par tiers, dans l'ordre des règlements
    rapprochements = {}
    for e in ecritures:
        for l in e.lignes:
            if l["lettrage"] and l["tiers"]:
                rapprochements.setdefault(l["tiers"][0], {}).setdefault(l["lettrage"][0], None)
    codes = {}
    for tiers, ids in rapprochements.items():
        for n, id_ in enumerate(ids):
            codes[id_] = code_lettrage(n)

    lignes_fec, anomalies = [], []
    compteurs = {j: 0 for j in JOURNAUX}
    for e in ecritures:
        compteurs[e.journal] += 1
        num = f"{e.journal}{compteurs[e.journal]:06d}"
        valid = e.valid_date or (e.date + timedelta(days=int(rng.integers(0, 6))))
        for l in e.lignes:
            tiers = l["tiers"] or ("", "")
            lett = l["lettrage"]
            lignes_fec.append({
                "JournalCode": e.journal,
                "JournalLib": JOURNAUX[e.journal],
                "EcritureNum": num,
                "EcritureDate": fmt_date(e.date),
                "CompteNum": l["compte"],
                "CompteLib": PLAN_COMPTABLE[l["compte"]],
                "CompAuxNum": tiers[0],
                "CompAuxLib": tiers[1],
                "PieceRef": e.piece_ref,
                "PieceDate": fmt_date(e.piece_date or e.date),
                "EcritureLib": e.libelle,
                "Debit": fmt_montant(l["debit"]),
                "Credit": fmt_montant(l["credit"]),
                "EcritureLet": codes.get(lett[0], "") if lett else "",
                "DateLet": fmt_date(lett[1]) if lett else "",
                "ValidDate": fmt_date(valid),
                "Montantdevise": "",
                "Idevise": "",
            })
        if e.anomalie:
            anomalies.append({"EcritureNum": num, "JournalCode": e.journal, "EcritureDate": e.date.isoformat(),
                              "PieceRef": e.piece_ref, "type_anomalie": e.anomalie,
                              "description": e.anomalie_desc})

    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    fec = pd.DataFrame(lignes_fec)
    fec.to_csv(FICHIER_FEC, sep="\t", index=False, encoding="utf-8")
    pd.DataFrame(anomalies).to_csv(FICHIER_ANOMALIES, index=False, encoding="utf-8")
    return fec


def resume(fec: pd.DataFrame) -> None:
    debit = fec["Debit"].str.replace(",", ".").astype(float)
    credit = fec["Credit"].str.replace(",", ".").astype(float)
    anomalies = pd.read_csv(FICHIER_ANOMALIES)
    print(f"FEC généré : {FICHIER_FEC.relative_to(RACINE)}")
    print(f"  {len(fec):_} lignes / {fec['EcritureNum'].nunique():_} écritures".replace("_", " "))
    print(f"  Total débit  : {debit.sum():,.2f} €".replace(",", " "))
    print(f"  Total crédit : {credit.sum():,.2f} €".replace(",", " "))
    print("  Écritures par journal :", fec.groupby("JournalCode")["EcritureNum"].nunique().to_dict())
    print(f"\nAnomalies cachées : {len(anomalies)} écritures ({FICHIER_ANOMALIES.relative_to(RACINE)})")
    print(anomalies["type_anomalie"].value_counts().to_string())


if __name__ == "__main__":
    creer_operations_diverses()
    creer_ventes()
    achats = creer_achats()
    creer_paie()
    creer_declarations_tva()
    injecter_anomalies(achats)
    sys.stdout.reconfigure(encoding="utf-8")  # accents corrects dans la console Windows
    resume(exporter())
