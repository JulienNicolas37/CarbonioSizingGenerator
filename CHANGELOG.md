# Changelog

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
- Logo client (champ prévu, pas encore testé avec un vrai fichier)
- Éventuel chapitre "Solution Zextras Carbonio" (édition/version produit) si besoin exprimé
