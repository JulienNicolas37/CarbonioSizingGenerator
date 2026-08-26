# Changelog

## 0.7.1 — Ajustements post-migration
- **Ordre des chapitres** : "Bilan des besoins" passe avant "Méthodologie de migration" (était
  l'inverse).
- **Titre + tableau "Dimensionnement de l'infrastructure" sur la même page** : le titre de section et
  le texte d'introduction sont désormais à l'intérieur du bloc `landscape`, donc sur la même page
  physique que le tableau (au prix de pivoter avec lui à 90° — techniquement impossible de mélanger
  portrait et paysage sur une seule page PDF).
- **"Besoins fonctionnels"** : nouvelle entrée "Sauvegarde des données" (conditionnée par
  `infra.backups`, pas par un service) qui présente le backup comme une fonctionnalité client,
  au-delà de l'aspect technique — nouveau support `infra_key` dans `carbonio_functions.yaml` en plus
  de `service_key`/`always`.
- **Gras restauré** dans le chapitre "Méthodologie de migration" : ~20 passages en gras du document
  source (mis en évidence de points clés : recommandations, seuils, responsabilités) avaient été
  perdus lors de la retranscription — repérés précisément via les styles de caractères du fichier
  ODT source et réintégrés en `\textbf{}`.

## 0.7.0 — Méthodologie de migration
- **Nouvelle section `prestation`** (au niveau racine, distincte de `infra`) : `migration_included`,
  `destination_platform` (carboniocloud/onpremise/saasdedie), `mco_contract` — 3 nouvelles questions
  toujours posées en interactif.
- **Chapitre "Prérequis" renommé** (ex "Prérequis techniques"), nouvelle première sous-section
  "Prestations commandées" qui rappelle migration/plateforme/MCO.
- **Nouveau chapitre "Méthodologie de migration"** (positionné entre "Infrastructure de
  qualification" et "Bilan des besoins"), affiché uniquement si `migration_included` — reprend le
  document fourni par Julien (7 sections, synthèse des responsabilités, RACI), avec du contenu
  conditionné à la plateforme de destination (balises `<onpremise>`/`<carboniocloud>`/`<saasdedie>`
  du document source, traduites en blocs Jinja) et au contrat de MCO (`<mco>`).
- **3 coquilles corrigées** dans le document source (balises fermantes sans ouverture, ou balise
  ouvrante jamais fermée) — lecture validée avec Julien avant application.
- **SaaS dédié** n'affiche que le contenu explicitement tagué `<saasdedie>` (pas d'héritage du
  contenu `<onpremise>` — choix validé explicitement, génère quelques sections plus courtes que le
  cas On Premise, par exemple pas de sous-section "Intégration du provisionnement au SI").
- **Nouveau catalogue `catalogs/migration_raci.yaml`** : tableau RACI (41 lignes) en données
  structurées, avec balises de plateforme optionnelles par ligne.
- **Tableau RACI coloré** : chaque lettre en gras et en couleur (R jaune/or, A rouge, C bleu, I vert)
  — nouvelle fonction `format_raci()` et 4 couleurs `raciR`/`raciA`/`raciC`/`raciI` dans le préambule.
- Correctif : signes "%" non échappés dans le texte source (interprétés comme des commentaires
  LaTeX, coupant le texte) — corrigés en `\%`.

## 0.6.4 — Unités déplacées dans les en-têtes de tableau
- Tableaux "Dimensionnement de l'infrastructure" (production et qualification) et "Bilan des
  besoins" : les unités ("Go") et mentions "(S3)" sont désormais uniquement dans l'en-tête de
  colonne (ex. "RAM (Go)", "Secondaire (S3, Go)", "Backup (S3, Go)") — les cellules n'affichent plus
  que la valeur numérique brute, plus lisible sur des tableaux déjà denses.

## 0.6.3 — Correctif en-tête colonne Backup
- Tableau "Dimensionnement de l'infrastructure" : l'en-tête de la colonne "Backup" affiche désormais
  "(S3)" quand `infra.backup_sur_s3` est actif, comme c'est déjà le cas pour "Secondaire (S3)" —
  jusqu'ici seule chaque cellule portait la mention, pas l'en-tête.

## 0.6.2 — Catégorisation du stockage rendue modulable
- La composition des catégories "disque rapide"/"disque lent"/"stockage Objet" (chapitre Bilan des
  besoins) n'est plus codée en dur dans `generate_pdf.py` : elle vient désormais de
  `sizing_rules.yaml` (nouvelle section `storage_categories`). Modifiable sans toucher au code —
  ex. réaffecter quel champ de disque appartient à quelle catégorie, ou changer la règle de
  rattachement du backup selon `infra.backup_sur_s3`.

## 0.6.1 — Lisibilité et catégorisation du stockage
- Colonne "Backup" du tableau des prérequis : ajout du libellé "(S3)" quand le backup est sur
  stockage Objet (`infra.backup_sur_s3`), comme c'était déjà le cas pour "Secondaire (S3)"
- Tableau "Dimensionnement de l'infrastructure" (production) : saut de page avant le tableau, et
  page entière en orientation paysage (`pdflscape`) pour une meilleure lisibilité sur les nombreuses
  colonnes
- Chapitre "Bilan des besoins" : le stockage est désormais regroupé en 3 catégories de synthèse
  (disque rapide = OS + Appli, disque lent = Store + Backup si pas sur S3, stockage Objet S3 =
  Secondaire HSM + Backup si sur S3), plus lisible qu'un détail colonne par colonne à ce niveau de
  synthèse. Nouvelle fonction `categorize_storage()` dans `generate_pdf.py`.

## 0.6.0 — Infrastructure de qualification, bilan des besoins
- **2 nouvelles questions** : "Faut-il prévoir une infrastructure de qualification ?", puis (si oui,
  et seulement si la production a un palier HA > 0) "Faut-il prévoir les mêmes fonctions HA (proxy,
  MTA, etc.) que la production sur la qualification ?"
- **Nouveau catalogue `qualification_catalog.yaml`** : specs par défaut volontairement petites
  (2 vCPU / 4-8 Go RAM / disques réduits), granulaires (mode HA-mirror) et combinées (mode minimal).
- **Mode minimal (par défaut)** : 1 VM combinant tous les rôles DMZ (proxy+mta_in+mta_auth+mta_out),
  1 VM combinant mesh+directory_master+database, 1 VM mailstore — 3 VM au total.
- **Mode HA-mirror** : reprend exactement la structure du palier HA retenu en production (mêmes
  groupes DMZ, même répartition des 3 VM Services), à taille qualification. Retombe automatiquement
  sur le mode minimal si la production n'a pas de HA, même si le mode HA-mirror a été demandé — le
  mode réellement appliqué est tracé dans `infra_resolved.qualification_mode`.
- **Nouveau chapitre 5 "Infrastructure de qualification"** (uniquement si demandée) : dimensionnement
  + schéma DMZ/LAN, même structure que le chapitre Prérequis techniques.
- **Nouveau chapitre 6 "Bilan des besoins"** : tableau de synthèse Production / Qualification (si
  active) / Total général, toutes ressources confondues (vCPU/RAM/disques/secondaire S3/backup).
- **Réorganisation** : la section "Périmètre du document" est déplacée du chapitre 1 (Introduction et
  cadrage) vers le chapitre 4 (Prérequis techniques), juste après le récapitulatif des besoins
  exprimés, et renommée "Besoins fonctionnels".
- Factorisation du traitement des nœuds (`_process_nodes`, `_diagram_for`) dans `generate_pdf.py`,
  réutilisée à l'identique pour la production et la qualification.

## 0.5.0 — Stockage Objet/HSM, backups, périmètre fonctionnel
- **Nouvelles questions (dans l'ordre)** : après "Stockage Objet activé ?" -> "Activer le module HSM
  (stockage secondaire S3) ?" (si Stockage Objet), puis si HSM actif "Rétention en jours sur le
  stockage primaire ?" (défaut 7) ; puis "Mettre en place des backups ?" (juste après la question S3),
  et si backups + Stockage Objet -> "Le backup sera-t-il également sur S3 ?"
- **Nouveau calcul de dimensionnement disque par mailstore** :
  - Volumétrie moyenne par mailstore = volumétrie totale / nombre de mailstores, arrondie au
    demi-To supérieur (remplace l'ancienne valeur fixe de 5000 Go issue du catalogue).
  - Si Stockage Objet + HSM actifs : stockage primaire dimensionné pour la rétention demandée
    (HYPOTHÈSE : 200 Go pour 7 jours de référence, mis à l'échelle linéairement — voir
    `sizing_rules.yaml`), le reste de la volumétrie moyenne part en secondaire (S3).
  - Si backups activés : 1,3x la taille cumulée primaire + secondaire.
  - Le seuil qui ignore la volumétrie pour le NOMBRE de mailstores ne s'applique plus sur
    Stockage Objet seul, mais sur Stockage Objet ET HSM actifs (sans HSM, tout reste sur le
    stockage primaire, donc la volumétrie redevient dimensionnante pour le nombre de mailstores).
  - Tableau des prérequis : 2 nouvelles colonnes ("Secondaire (S3)", "Backup"), toujours affichées
    avec repli "---" si non applicable ; police réduite (\small) pour absorber les 10 colonnes.
- **Périmètre du document** entièrement revu : remplace la liste technique de composants
  d'infrastructure par la liste des FONCTIONS utilisateur activées (Messagerie, Agenda, Contacts,
  Chat, Tâches, Fichiers, Édition collaborative, Visioconférence), reprise et condensée du chapitre
  "Services rendus aux utilisateurs" du Générateur de DAT — nouveau catalogue
  `catalogs/carbonio_functions.yaml`.
- **Table des contacts Zextras** : dédupliquée (une même personne n'apparaît plus qu'une fois même
  si elle cumule plusieurs fonctions projet), n'affiche plus que son titre (plus de "Commercial en
  charge —"/"Rédacteur du document —" etc.) ; police réduite et colonne e-mail élargie pour éviter
  le débordement (ex. avec des e-mails plus longs comme celui de Maxime Sautière ou William
  Santaliestra). Même traitement appliqué à la table des contacts client, par cohérence.
- "Récapitulatif des besoins exprimés" mentionne désormais HSM/rétention/backups quand pertinent.

## 0.4.0 — Réorganisation du fichier de configuration
- **Fusion des sections "client"** : toutes les informations relatives au client (identité,
  dimensionnement, parties prenantes) vivent maintenant sous une seule clé
  `parties_prenantes.client`. Il n'y a plus de section `client:` séparée au niveau racine.
- **Nouvelle section `parties_prenantes.prestataire`** : commercial, auteur (rédacteur) et
  **chef de projet** (nouveau rôle, nouvelle question en interactif) — déplacés hors de `infra:`,
  qui ne contient plus que des décisions techniques (ha_tier, mailstore_count, imap, migration_factory).
- **Contacts Zextras recopiés en clair** : `commercial`/`auteur`/`chef_projet` contiennent
  désormais nom/rôle/email/téléphone directement dans le YAML (recopiés depuis
  `team_directory.yaml` au moment de la génération), et non plus une simple référence par id —
  le fichier de config reste auto-suffisant, plus besoin de croiser team_directory.yaml pour
  comprendre qui est qui. `revisions[].auteur` est également un nom en clair, plus un id.
- **Table des contacts Zextras (chapitre Parties prenantes)** : n'affiche plus tout
  `team_directory.yaml`, mais uniquement les 3 personnes du projet (commercial/rédacteur/chef de
  projet), avec le rôle affiché comme "Fonction projet --- Titre" (ex. "Chef de projet ---
  Directeur technique").
- **"Récapitulatif des besoins exprimés"** déplacé du chapitre 1 (Introduction et cadrage) vers le
  chapitre 4 (Prérequis techniques), où il a plus de sens. Le chapitre 4 est maintenant structuré en
  2 sous-sections : "Récapitulatif des besoins exprimés" et "Dimensionnement de l'infrastructure"
  (le tableau, avant directement au niveau du chapitre, est maintenant sa propre sous-section).
- `config_loader.get_client()` : nouvel accesseur centralisant le chemin `parties_prenantes.client`,
  utilisé par sizing_engine.py, generate_sizing.py et generate_pdf.py.

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
