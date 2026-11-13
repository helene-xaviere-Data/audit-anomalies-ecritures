# 📊 Guide : construire le rapport Power BI « Audit des écritures »

Ce guide décrit pas à pas le rapport de restitution du projet. Toutes les données sont prêtes dans [`donnees/`](donnees/). Elles sont produites par `python src/export_powerbi.py`.

**Résultat attendu :** un rapport de 5 pages, enregistré sous `powerbi/AuditAnomalies.pbix`.

| Page | Pour qui ? | Message |
|---|---|---|
| 1. Vue d'ensemble | Associé, directeur financier | L'activité et le périmètre testé, en un coup d'œil |
| 2. Alertes d'audit | Auditeur | Quelles écritures examiner en priorité, et pourquoi |
| 3. Loi de Benford | Auditeur | Les montants « non naturels » et le fournisseur suspect |
| 4. Fiche écriture | Auditeur (exploration) | Le détail d'une écriture, accessible par extraction (drill-through) |
| 5. Méthodologie | Recruteur, relecteur | Efficacité mesurée des règles et du modèle |

⏱️ Durée estimée : 2 à 3 heures.

---

## Étape 1 : Importer les données

1. Ouvrir **Power BI Desktop**, puis faire **Accueil > Obtenir les données > Texte/CSV**.
2. Importer les 9 fichiers de `powerbi/donnees/` un par un : `Faits_Lignes`, `Ecritures`, `Alertes`, `Comptes`, `Tiers`, `Journaux`, `Calendrier`, `Benford_Distribution`, `Benford_Fournisseurs`.
3. Pour chaque fichier, cliquer sur **Transformer les données** (pas « Charger ») et vérifier dans Power Query :
   - **Origine du fichier : 65001 (Unicode UTF-8)** et **Délimiteur : point-virgule** ;
   - les colonnes de montants (`Montant`, `Debit`, `Credit`, `ScoreAnomalie`…) sont en **Nombre décimal** ;
   - les colonnes `Date`, `DateValidation` et `DateLettrage` sont en **Date** ;
   - `CompteNum`, `TiersCode` et `Chiffre` sont en **Texte**, pour garder les zéros et éviter les sommes absurdes. `Chiffre` peut rester en nombre entier si vous préférez le tri numérique.

> 💡 **Si les montants apparaissent comme du texte ou sont multipliés par 100**, votre Power BI est en paramètres régionaux anglais. Clic droit sur la colonne, puis **Modifier le type > Utilisation des paramètres régionaux… > Nombre décimal / Français (France)**.

4. **Fermer et appliquer.**

## Étape 2 : Le modèle en étoile

Dans la **vue Modèle**, créer ou vérifier les relations suivantes :

| De (côté *plusieurs*) | Vers (côté *un*) | Direction du filtre |
|---|---|---|
| `Faits_Lignes[EcritureNum]` | `Ecritures[EcritureNum]` | Unique |
| `Faits_Lignes[CompteNum]` | `Comptes[CompteNum]` | Unique |
| `Ecritures[Date]` | `Calendrier[Date]` | Unique |
| `Ecritures[JournalCode]` | `Journaux[JournalCode]` | Unique |
| `Ecritures[TiersCode]` | `Tiers[TiersCode]` | Unique |
| `Alertes[EcritureNum]` | `Ecritures[EcritureNum]` | **Les deux** ⚠️ |

- Supprimer toute relation créée automatiquement entre `Faits_Lignes[TiersCode]` et `Tiers` : le tiers est porté par `Ecritures`, ce qui évite une ambiguïté.
- La relation **bidirectionnelle** sur `Alertes` permet qu'un segment « Test » filtre les écritures.
- `Benford_Distribution` et `Benford_Fournisseurs` restent **sans relation** : ce sont des tables d'analyse autonomes.
- Marquer `Calendrier` comme **table de dates** (clic droit > Marquer comme table de dates > colonne `Date`).
- Trier `Calendrier[Mois]` par `MoisNum` et `Calendrier[JourSemaine]` par `JourSemaineNum` (Outils de colonne > Trier par colonne).

📸 **Faire une capture de la vue Modèle** : elle illustrera le README (`reports/figures/powerbi_modele.png`).

## Étape 3 : Le thème et les mesures

1. **Affichage > Thèmes > Parcourir les thèmes**, puis choisir [`theme_audit.json`](theme_audit.json).
2. **Accueil > Entrer des données**, nommer la table **`Mesures`**, puis **Charger**.
3. Créer les mesures du fichier [`mesures.dax`](mesures.dax) dans cette table (**Modélisation > Nouvelle mesure**, puis copier-coller). Appliquer les formats indiqués en commentaire.
4. Supprimer la colonne vide de la table `Mesures` : elle devient une table de mesures, avec une icône de calculatrice.

## Étape 4 : Les pages

### Page 1 : Vue d'ensemble
- **Titre** : « Audit des écritures 2025 : Atelier Lumière SAS ».
- **5 cartes** : `Nb écritures`, `Chiffre d'affaires HT`, `Taux de résultat`, `Écritures signalées`, `% écritures signalées`.
- **Graphique en courbes** : `Calendrier[Mois]` × `Chiffre d'affaires HT` (saisonnalité, pic de décembre).
- **Histogramme groupé** : `Journaux[JournalLib]` × `Nb écritures`.
- **Histogramme** : `Calendrier[JourSemaine]` × `Nb écritures`, avec une mise en forme conditionnelle en rouge pour samedi et dimanche (les écritures du week-end ressortent).
- **Segments** : `Journaux[JournalLib]`, `Calendrier[Trimestre]`.

### Page 2 : Alertes d'audit *(la page la plus importante)*
- **Cartes** : `Écritures signalées`, `Montant signalé`, `Écritures risque élevé`, `Nb alertes`.
- **Graphique à barres** : `Alertes[Test]` × `Nb écritures`, trié par valeur décroissante.
- **Matrice** : lignes `Alertes[Test]`, colonnes `Journaux[JournalCode]`, valeurs `Nb écritures`, avec une mise en forme conditionnelle de type « échelle de couleurs ».
- **Tableau des écritures à examiner** : `EcritureNum`, `Date`, `Libelle`, `Tiers[Tiers]`, `Montant`, `NbAlertes`, `ScoreAnomalie`, `TestsDeclenches`, `Raisons`.
  - Filtre du visuel : `NiveauRisque` = « 1 - Élevé » ou « 2 - Moyen ».
  - Tri : `NbAlertes`, puis `ScoreAnomalie`, par ordre décroissant.
  - Mise en forme conditionnelle : barres de données sur `ScoreAnomalie`, et fond rouge si `NbAlertes` ≥ 2.
- **Segments** : `Ecritures[NiveauRisque]`, `Alertes[Test]`, `Tiers[TypeTiers]`.

### Page 3 : Loi de Benford
- **Graphique combiné** (histogramme + courbe) : axe `Benford_Distribution[Chiffre]`, colonnes `Part observée`, ligne `Part attendue (Benford)`.
- **Segment** (sélection unique, liste déroulante) : `Benford_Distribution[Segment]`, avec « Tout le FEC » par défaut.
- **Carte** : `MAD du segment`.
- **Tableau** `Benford_Fournisseurs` : `Fournisseur`, `NbFactures`, `ChiffreDominant`, `PartChiffreDominant`, `PValue`, `Alerte`, trié par `PValue` croissante, avec la ligne en rouge quand `Alerte` = « Écart fort ».
- **Zone de texte** pour l'interprétation : « Conseil Stratégie Plus : 100 % des factures commencent par 4 (juste sous le seuil de 5 000 € HT). SCI Les Tilleuls : écart attendu, car c'est un loyer fixe. »

> 🎯 La démonstration clé : sélectionner « Tout le FEC » (conforme), puis « Fournisseur : Conseil Stratégie Plus » (une seule barre sur le 4).

### Page 4 : Fiche écriture (extraction)
- Dans le volet **Champs d'extraction**, ajouter `Ecritures[EcritureNum]`.
- **Carte multiligne** : `EcritureNum`, `Date`, `DateValidation`, `DelaiValidationJours`, `PieceRef`, `Libelle`, `Tiers[Tiers]`, `NiveauRisque`, `ScoreAnomalie`.
- **Tableau** des lignes : `Comptes[CompteNum]`, `Comptes[CompteLib]`, `Faits_Lignes[Debit]`, `Faits_Lignes[Credit]`, `Faits_Lignes[Lettrage]`.
- **Zones de texte** dynamiques : `TestsDeclenches` et `Raisons`.
- Sur la page 2 : clic droit sur une écriture du tableau, puis **Extraire > Fiche écriture**.

### Page 5 : Méthodologie et performance
- **Cartes** : `Anomalies injectées`, `Rappel des règles`, `Précision des règles`, `Rappel du modèle (top 200)`.
- **Matrice** : lignes `Ecritures[TypeAnomalieInjectee]` (filtrer pour exclure « (aucune) »), valeurs `Anomalies injectées`, `Anomalies détectées par les règles`, `Anomalies dans le top 200 du modèle`.
- **Zone de texte** expliquant la démarche : données simulées, 81 anomalies cachées utilisées **uniquement pour l'évaluation**, règles contre modèle non supervisé, limites (lien vers les notebooks GitHub).

## Étape 5 : Finitions
- Même en-tête sur chaque page : titre, sous-titre « Données simulées : projet de portfolio », logo ou icône.
- **Navigateur de pages** (Insérer > Boutons > Navigateur > Navigateur de pages) en haut de chaque page.
- Vérifier que les nombres sont au format français (espace pour les milliers, € pour les montants).
- **Enregistrer** sous `powerbi/AuditAnomalies.pbix`.

## Étape 6 : Captures pour GitHub
Exporter chaque page en image, avec l'outil Capture d'écran de Windows (`Win + Maj + S`) ou via **Fichier > Exporter > PDF**. Enregistrer les fichiers dans `reports/figures/` sous les noms :

- `powerbi_1_vue_ensemble.png`
- `powerbi_2_alertes.png`
- `powerbi_3_benford.png`
- `powerbi_4_fiche_ecriture.png`
- `powerbi_5_methodologie.png`
- `powerbi_modele.png`

Il suffit ensuite de prévenir Claude : il les intégrera au README et publiera le tout sur GitHub.
