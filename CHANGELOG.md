# Changelog

## 0.3.2 — Clarification latexmk
- README et message d'erreur de `generate_pdf.py` : pointent maintenant explicitement vers
  `sudo apt-get install latexmk` comme correctif le plus probable (paquet parfois absent même
  quand texlive-latex-recommended est installé, selon la distribution)

## 0.3.1 — Correctifs et confort d'usage
- `generate_sizing.py` : retrait de la question sur le chemin du logo client — ce champ reste dans le
  schéma (`client.logo`) mais se renseigne manuellement dans le YAML par la personne qui finalise le
  document, pas lors du questionnaire de dimensionnement
- `generate_sizing.py` : affiche en fin d'exécution la commande `generate_pdf.py --client ... --compile`
  prête à copier-coller, avec le bon chemin vers la config générée
- `README.md` : section "Dépannage" pour le cas "latexmk n'est pas installé (ou pas dans le PATH)"
  alors que le paquet est bien installé (le plus souvent : TeX Live installé manuellement via
  install-tl, binaires hors des dossiers standards du PATH) ; ajout de `amssymb` à la liste des
  dépendances système documentées et de `latexmk` explicitement à la commande d'installation apt

## 0.3.0 — Structure DAT-like (chapitres, sommaire, parties prenantes)
- Passage de la classe LaTeX `article` à `report` : chapitres numérotés, sommaire (`\tableofcontents`),
  pied de page actif seulement à partir du chapitre 1 (comme le Générateur de DAT)
- Nouveau chapitre 1 "Introduction et cadrage" : Objet du document, **Rappel des besoins exprimés**
  (domaines/comptes/volumétrie/stockage Objet/services — restitue les réponses au questionnaire),
  Confidentialité (4 niveaux avec cases à cocher : Public/Client/Restreint/Confidentiel, remplace
  l'ancienne valeur unique "Public/Client"), Propriété intellectuelle, Périmètre du document
  (liste dérivée automatiquement des composants réellement présents, via component_descriptions.yaml)
- Nouveau chapitre 2 "Parties prenantes" : section Client (description/site web/adresse multi-ligne/
  téléphone/contacts — champs prévus dans le schéma mais PAS demandés en interactif, replis
  "[à préciser]" visibles sinon) et section Intégrateur (Zextras Services, contenu enrichi, adresse
  multi-ligne, tableau de contacts = tout `team_directory.yaml`)
- Nouveau chapitre 3 "Solution Zextras Carbonio" : présentation générale reprise du DAT (version
  légère, sans tableaux Version déployée/Licence, non pertinents en phase de dimensionnement)
- Chapitre 4 : Prérequis techniques + schéma (contenu existant, renuméroté)
- `client.logo` : chemin vers le logo client posé sur la page de garde (testé avec un vrai fichier
  sur l'exemple Université d'Amboise)
- `revisions:` déplacé en première clé des fichiers de config client (mise à jour la plus fréquente
  = la plus facile à retrouver), y compris en le réordonnant automatiquement à chaque sauvegarde
- Correctif : ajout du package `amssymb` manquant (nécessaire pour les cases à cocher $\square$/$\boxtimes$)
- Exemple Université d'Amboise enrichi : contacts et adresse repris du Générateur de DAT (cohérence
  entre les deux projets), logo client placeholder ajouté

## 0.2.1 — Correctifs
- `generate_pdf.py` : message d'erreur clair (installation à faire) si `latexmk` est absent du PATH,
  au lieu d'un traceback Python brut
- `generate_sizing.py` (mode interactif) : ajout des questions manquantes "Commercial en charge" et
  "Qui génère ce document ?" (sélection dans `team_directory.yaml`), plus génération automatique de
  la première entrée de `revisions:` (date du jour, version 1.0) — jusqu'ici ces champs restaient à
  `[à préciser]` sur les configs générées en interactif
- `config_loader.load_catalogs()` inclut désormais `team_directory.yaml`

## 0.2.0 — Génération LaTeX/PDF
- Nouveau catalogue `team_directory.yaml` : annuaire des intervenants Zextras, référencés par id numérique
  (commercial en charge, auteur du document, auteur de chaque révision) — jamais retapés en clair
- Nouveau catalogue `component_labels.yaml` : libellés d'affichage courts pour le tableau et le schéma
- `templates/preamble.tex.j2`, `templates/partials/cover.tex.j2`, `revisions.tex.j2` : repris du style du
  Générateur de DAT (police Open Sans, couleurs, logos en-tête/pied de page, page de garde)
- `templates/prestataire.tex` : infos Zextras Services statiques (pas de Jinja2, \input tel quel)
- `templates/partials/prerequis.tex.j2` : tableau des prérequis techniques avec ligne de totaux
  (vCPU/RAM/disque OS/disque Appli/disque Store cumulés)
- `templates/partials/architecture.tex.j2` + `src/tikz_builder.py` (vendoré du Générateur de DAT) :
  schéma DMZ/LAN en grille par famille de rôle, sans flux (volontairement plus simple qu'un DAT complet)
- `src/latex_utils.py` : échappement LaTeX + environnement Jinja2 (délimiteurs \BLOCK{}/\VAR{})
- `src/generate_pdf.py` : nouveau point d'entrée, lit une config client déjà dimensionnée
  (`nodes:` présent) et produit le .tex + PDF via xelatex/latexmk
- Correctif : `slugify()` normalise les accents (ASCII) pour des noms de dossier/fichier cohérents
  avec les exceptions .gitignore
- Correctif : double échappement LaTeX sur les ids de nœuds dans le schéma d'architecture
- 2 PDF d'exemple générés et vérifiés visuellement (page de garde, tableau, schéma dense à 20 nœuds)

## 0.1.0 — Premier socle
- Catalogues programme : vm_catalog, component_descriptions, service_catalog, sizing_rules
- Moteur de calcul (sizing_engine.py) : palier HA proxy/MTA à 4 niveaux (0/4000/10000/20000+IMAP),
  scaling mailstores (5000 comptes / 5 To, ignoré si stockage Objet), regroupement Application01/02,
  usine de migration optionnelle
- CLI (generate_sizing.py) : mode interactif (questionary) et mode --client, rétrospective finale
  avec ajustement du nombre de mailstores et du palier HA
- 2 configs d'exemple : petite infra et Université d'Amboise (grosse infra fictive)
- .gitignore protégeant les configs clients réelles et les dossiers de génération

À venir :
- Éventuel enrichissement du "Rappel des besoins exprimés" / "Périmètre" selon retours d'usage
