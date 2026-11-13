# 🔍 Détection d'anomalies dans les écritures comptables

> Projet de data analyse appliquée à l'**audit financier** : analyser un Fichier des Écritures Comptables (FEC) pour repérer les écritures à risque (erreurs, fraudes, contournement des contrôles).

🚧 *Projet en cours de construction*

## 🎯 Objectif

En audit, on ne peut pas contrôler les milliers d'écritures d'une entreprise une par une. Ce projet montre comment la data permet de :

- tester **100 % des écritures** au lieu d'un échantillon ;
- appliquer automatiquement les **tests d'audit classiques** (journal entry testing) ;
- repérer les montants suspects grâce à la **loi de Benford** ;
- attribuer un **score de risque** à chaque écriture grâce au machine learning.

## 🗺️ Étapes du projet

- [ ] 1. Génération d'un FEC réaliste (données simulées, avec anomalies cachées)
- [ ] 2. Exploration des données (volumes, comptes, saisonnalité)
- [ ] 3. Tests d'audit : week-ends, montants ronds, doublons, déséquilibres, écritures de clôture
- [ ] 4. Loi de Benford
- [ ] 5. Score de risque par machine learning (Isolation Forest)
- [ ] 6. Restitution : application interactive et/ou rapport Power BI

## 🛠️ Outils

Python · pandas · NumPy · Matplotlib · scikit-learn · Jupyter

## 📁 Structure

```
audit-anomalies-ecritures/
├── data/
│   ├── raw/          # données brutes (FEC)
│   └── processed/    # données nettoyées / enrichies
├── notebooks/        # analyses pas à pas
├── src/              # scripts Python réutilisables
├── reports/figures/  # graphiques exportés
└── requirements.txt  # bibliothèques nécessaires
```

## ▶️ Lancer le projet

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 👤 Auteur

**Hélène Xavière** · [GitHub](https://github.com/helene-xaviere-Data)
