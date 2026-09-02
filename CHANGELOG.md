# Changelog

## 0.16.0 — Mode minimal (palier 0 remplacé)
- **Nouveau mode minimal** qui remplace le palier HA 0 : quand comptes < 4000 ET mailstore_count == 1
  (les DEUX conditions, sinon retour au comportement précédent), l'infrastructure de production
  devient 1 seul nœud DMZ combiné (proxy+mta_in+mta_auth+mta_out, au lieu de 2) et 1 seul nœud
  Services combiné SANS réplica LDAP (mesh+directory_master+database, au lieu des 3 nœuds
  habituels). Choix stratégique documenté dans `sizing_rules.yaml` : ne pas effrayer les petits
  clients on-premise migrant depuis une infra Zimbra mono-nœud, tout en gardant le mailstore hors
  DMZ (contrainte non négociable, jamais remise en cause par ce mode).
- **Bascule automatique dès le 2e mailstore** (même sous 4000 comptes) ou dès le palier HA 1+ (même
  avec 1 seul mailstore) : retour immédiat au DMZ à 2 nœuds et aux 3 nœuds Services avec réplica —
  évite le cas bancal d'un DMZ redondant avec un LDAP sans aucune tolérance de panne.
- Nouvelle règle `ha_scaling.minimal_mode` dans `sizing_rules.yaml` (activable/désactivable,
  `max_mailstore_count` configurable).
- Aucun effet sur la qualification, qui garde son propre mode minimal indépendant.
- Testé : petite infra (800 comptes, 1 mailstore) → mode minimal confirmé (schéma + tableau) ;
  bascule vérifiée à 2 mailstores (même sous 4000 comptes) et à 4500 comptes avec 1 seul mailstore
  (pas de mode minimal, DMZ éclaté + réplica conservés) ; non-régression sur Amboise (palier 3).

## 0.15.0 — Suppression du disque applicatif pour proxy/MTA
- **`disk_appli_gb` retiré du catalogue** pour `proxy`, `mta_in`, `mta_auth`, `mta_out`
  (`catalogs/vm_catalog.yaml` et `catalogs/qualification_catalog.yaml`, y compris `combined_dmz` du
  mode qualification minimal) — le disque OS seul suffit pour ces natures de nœud.
- `_sizing_from_catalog()` et `qual_sizing()` (`sizing_engine.py`) sécurisés pour ce champ désormais
  optionnel (repli à 0 Go, plutôt qu'une erreur si absent du catalogue).
- Vérifié sur l'exemple Amboise : les 8 nœuds proxy/mta_* affichent "0" en colonne Appli, disque OS
  (30 Go) inchangé, aucun autre chiffre du tableau affecté.

## 0.14.0 — Disque "Backup metadata"
- **Nouveau disque fixe "Backup metadata"** (200 Go par défaut, configurable via
  `sizing_rules.yaml` → `mailstore_scaling.disque_par_mailstore.backup_metadata_gb`) ajouté sur
  chaque mailstore dès que les backups sont activés — valeur FIXE, sans calcul ni marge de capacité,
  quelle que soit la taille réelle des backups (catalogue/index du logiciel de sauvegarde).
- Nouvelle colonne "Backup metadata (Go)" dans le tableau de dimensionnement, avec repli "—" si les
  backups ne sont pas activés.
- Routé dans la catégorie "Disque rapide" du Bilan des besoins (statique, toujours rapide quel que
  soit le contexte S3/lent du reste du dimensionnement).
- Vérifié sur l'exemple Amboise : +200 Go par mailstore (1000 Go de total sur 5 mailstores),
  disque rapide total passant de 6880 à 7880 Go, cohérent.

## 0.13.0 — HSM découplé du Stockage Objet
- **Le module HSM peut désormais être activé sans Stockage Objet** : le délestage des données
  froides peut cibler un simple disque lent local plutôt que du S3. Jusqu'ici le HSM n'avait de sens
  qu'avec du Stockage Objet actif — ce n'est plus une contrainte.
- **Question HSM toujours posée** juste après la question du Stockage Objet, quelle que soit la
  réponse donnée (valeur par défaut pré-cochée sur la réponse au Stockage Objet, sans l'imposer).
- **Calcul découplé** (`compute_mailstore_sizing`, `suggest_mailstore_count`) : le déclenchement du
  calcul primaire/secondaire et de la règle "volumétrie non dimensionnante" pour le nombre de
  mailstores reposent maintenant sur `hsm_active` seul, plus sur `stockage_objet ET hsm_active`.
- **Affichage dynamique** : en-tête de colonne "Secondaire (S3, Go)" ou "Secondaire (lent, Go)"
  selon le cas ; texte du récapitulatif des besoins adapté ("délestage vers un stockage secondaire
  lent/S3") ; routage dynamique du secondaire dans le Bilan des besoins (catégorie "Stockage Objet"
  seulement si réellement sur S3, sinon "Disque lent" — même mécanisme que pour le backup).
- Testé : cas HSM sans Stockage Objet (129500 Go routés en "Disque lent", "Stockage Objet" à "—") et
  non-régression du cas HSM+S3 existant (Amboise, chiffres et libellés inchangés).

## 0.12.0 — Nettoyage, doc et fichier de référence
- **Suppression du "téléphone d'urgence"** (chapitre Parties prenantes, section client) : hérité du
  Générateur de DAT, sans intérêt en avant-vente — retiré du template, de `generate_pdf.py`, de
  `generate_sizing.py` et des 2 exemples.
- **Ancres/alias YAML (`&id001`/`*id001`) éliminés** : ces artefacts apparaissaient quand plusieurs
  nœuds partageaient le même objet liste Python en mémoire (ex. les 2 VM d'un groupe HA, ou les nœuds
  de qualification en mode HA-mirror réutilisant directement les listes de `sizing_rules.yaml`) — pas
  une intention du fichier, juste un effet de bord de la sérialisation. Corrigé à la source
  (`sizing_engine.py` copie désormais chaque liste `components` par nœud) et en filet de sécurité
  côté sérialisation (`config_loader.py` désactive maintenant systématiquement les alias YAML).
- **README** : nouvelle section expliquant comment compiler un `.tex` en PDF sans repasser par
  `generate_pdf.py` (`latexmk` ou `xelatex` en 2 passes), et correction d'une documentation obsolète
  sur l'annuaire des intervenants (mentionnait encore `infra.commercial_id`/`infra.auteur_id`, un
  système de référence par id abandonné depuis la v0.4.0 au profit des infos recopiées en clair).
- **Nouveau fichier de référence `config/clients/client_exemple_reference.yaml`** : documente, avec
  un commentaire par champ, l'intégralité des options disponibles dans une config client — à
  consulter, pas à générer tel quel (pas de section `nodes`). Suivi par git comme les 2 autres
  exemples ; référencé dans le README.

## 0.11.0 — Marge de capacité sur le stockage mailstore
- **Nouvelle règle `headroom_pct`** (30 % par défaut) dans `sizing_rules.yaml`
  (`mailstore_scaling.disque_par_mailstore`) : la volumétrie communiquée par le client représente son
  USAGE réel, pas une capacité à provisionner telle quelle. Sans marge, le stockage serait déjà
  saturé à l'issue de la migration (plus de place pour la croissance quotidienne).
- Appliquée aux **3 supports** (disque primaire/block, secondaire/S3, backup) telle que 30 % de la
  capacité TOTALE provisionnée reste disponible : `capacité = usage / (1 - 0,30)`, arrondie à la
  centaine de Go la plus proche.
- Le multiplicateur de backup (1,3×) continue de s'appliquer sur l'usage réel (avant marge) — la
  marge de capacité est ensuite appliquée au résultat, pas de double marge cumulée.
- Vérifié sur l'exemple Amboise : 286/7714/10400 Go (usage brut) deviennent 400/11000/14900 Go
  (capacité avec marge) par mailstore.

## 0.10.1 — Tableaux de charge par ressource regroupés
- Les blocs de la table "Charge par ressource" s'empilent désormais sur la même page tant que la
  place le permet, au lieu d'un saut de page systématique entre chaque bloc de jours.
- Colonnes resserrées (0,52 cm au lieu de 0,75 cm) et police réduite (`\scriptsize`) pour tenir
  20 jours par bloc au lieu de 16, réduisant d'autant le nombre de blocs nécessaires.
- Sur l'exemple Amboise (38 jours travaillés) : 2 pages au lieu de 3 pour cette section.
- Correctif en cours de route : un premier essai à 24 jours/bloc empiétait légèrement sur l'élément
  décoratif de marge droite — ramené à 20 jours/bloc avec marge de sécurité.

## 0.10.0 — Document complet ou partiel
- **Nouvelle question lors de la génération du document final** (`generate_pdf.py`, pas
  `generate_sizing.py`) : "Document complet ou partiel ?". En partiel, propose d'ajouter au socle de
  base (Introduction, Parties prenantes, Solution Carbonio, Prérequis avec tableau de
  dimensionnement, Infrastructure de qualification avec tableau, Bilan des besoins) une sélection
  parmi 4 extras : les schémas d'architecture (production + qualification), la méthodologie de
  migration, la méthodologie projet, le planning de migration.
- Ce choix n'est **jamais écrit dans le fichier de config client** : c'est une décision propre à
  chaque génération, pas une propriété durable du projet — permet de produire un document complet
  pour usage interne et une version allégée pour le client à partir de la même config.
- **Nouveau flag `--non-interactive`** sur `generate_pdf.py` (miroir de celui de `generate_sizing.py`) :
  saute la question et génère le document complet, pour les usages scriptés/automatisés.
- Testé sur les 3 cas extrêmes : aucun extra (11 pages, socle nu), tous les extras (33 pages,
  identique au comportement précédent), et une sélection partielle (planning de migration seul).

## 0.9.2 — Vraie cause du chevauchement en-tête/tâches trouvée
- **Cause racine isolée** (test minimal reproductible) : `\gantttitlelist` de `pgfgantt` ignore
  purement et simplement le réglage `title height` dès que le libellé contient un `\rotatebox` — le
  texte pivoté descend directement dans la zone des tâches quelle que soit la hauteur de titre
  demandée, même très généreuse. Le texte NON pivoté, lui, reste parfaitement contenu.
- **Correctif** : abandon de la rotation à 90° pour les repères hebdomadaires. Format compact
  "JJ" seul pour chaque lundi, "JJ/MM" uniquement au changement de mois (pour garder un repère de
  mois sans réintroduire de rotation) — `title height` ramené à sa valeur normale (1).
- Confirmé par comparaison directe pivoté/non pivoté sur un cas isolé avant application au projet.

## 0.9.1 — Correctifs de mise en page du Gantt
- **Cause racine identifiée empiriquement** : dans ce document, l'espace utile disponible à l'intérieur
  de `\begin{landscape}` fait environ 16,4 cm à la fois en largeur ET en hauteur (`\textwidth` et
  `\textheight` valent la même chose dans ce contexte precis — pas un simple échange des deux comme
  on pourrait s'y attendre). Vérifié en imprimant `\the\textwidth`/`\the\textheight` à l'intérieur
  de l'environnement.
- **Gantt trop étroit** : la largeur des colonnes est maintenant calculée dynamiquement pour occuper
  la largeur utile réelle (~14,5 cm avec marge de sécurité), au lieu d'une largeur fixe minuscule.
- **Table de charge qui débordait** : largeur des colonnes et nombre de jours par page recalculés sur
  la base de la vraie largeur utile (16 jours par page à 0,75 cm, au lieu de 26 jours à 0,7 cm qui
  dépassait largement).
- **Premières tâches chevauchant les dates d'en-tête** : hauteur de titre du Gantt augmentée pour
  laisser assez de place aux dates pivotées à 90°, qui touchaient les barres de groupe juste en
  dessous.

## 0.9.0 — Planning de migration (Gantt)
- **Nouveau chapitre "Planning de migration"** (tout dernier chapitre du document, affiché uniquement
  si migration incluse ET les nouvelles questions de planning ont été renseignées) : diagramme
  `pgfgantt` avec flèches de dépendance et repères hebdomadaires (dates des lundis), suivi d'une
  page de charge par ressource et par jour.
- **Nouveau catalogue `catalogs/migration_gantt.yaml`** : planning type de migration (21 tâches),
  fourni par Julien et corrigé suite à échange (références `#1`/`#last` pour sortir du groupe
  répétable, durée par défaut sur une tâche non renseignée, jalons Kickoff/Recette avec durée/charge
  ignorées).
- **Nouveaux catalogues `catalogs/gantt_config.yaml`** (jours travaillés par défaut, chemin du
  calendrier de jours fériés, seuils de charge 80/100) et `catalogs/jours_feries_fr.ics` (exemple) —
  recopiés dans la config client à la génération, modifiables ensuite par projet.
- **Nouveau moteur `src/gantt_engine.py`** : calendrier de jours travaillés (jours fériés exclus),
  expansion du groupe répétable de bascule en `nombre_bascules` occurrences (référencement `#1` =
  première occurrence, `#last` = dernière), règle de calage des dates de bascule (1ère bascule = fin
  des dépendances ou date souhaitée si postérieure, avancée au premier lundi/mardi/mercredi ; 2e
  bascule = +14 jours ; suivantes = +7 jours ; surcharge manuelle par lot toujours prioritaire),
  calcul de la charge cumulée par ressource et par jour.
- **Nouveau constructeur `src/gantt_builder.py`** : génère le LaTeX `pgfgantt` (paginé automatiquement
  par groupes complets si la hauteur dépasse une page paysage) et la table de charge (paginée par
  blocs de jours si la largeur dépasse une page paysage) avec code couleur vert/orange/rouge.
- **4 nouvelles questions** (uniquement si migration incluse) : nombre de bascules, date souhaitée
  pour la première bascule (optionnelle), date de début estimée, date de fin estimée.
- **Avertissement** affiché en fin de questionnaire ET dans le document si la durée calculée du
  planning dépasse la date de fin estimée communiquée.
- Couleur des tâches : par défaut selon la condition (Toujours/Migration/Build), surchargeable par
  tâche via un code hexadécimal.
- Correctif : signe "%" non échappé dans les cellules de la table de charge (même piège LaTeX que
  précédemment rencontré) — corrigé.
- Correctif : dimensionnement du Gantt et de la table de charge — la hauteur/largeur utile d'une
  page en paysage correspond à l'ancienne largeur/hauteur de page (pas l'inverse), d'où la nécessité
  d'une pagination automatique plutôt qu'un simple redimensionnement de police.

## 0.8.0 — Méthodologie de pilotage du projet
- **Nouveau chapitre "Méthodologie de pilotage du projet"** (toujours en dernière position du
  document) : reprend le document fourni par Julien (Kick-off, suivi hebdomadaire, adaptation de la
  fréquence, pilotage par actions/jalons, accompagnement jusqu'à la mise en production), avec du
  contenu conditionné à la présence d'une migration (balises `<migration>`/`<!migration>` du document
  source, traduites en blocs Jinja — mêmes coquilles de balises repérées et corrigées que sur le
  chapitre précédent).
- **Visibilité du chapitre** : affiché si contrat de MCO, migration incluse, OU plateforme de
  destination non On Premise (CarbonioCloud/SaaS dédié assimilés à du SaaS) — HYPOTHÈSE à confirmer
  avec Julien sur la définition exacte de "SaaS" dans ce contexte.
- Gras du document source restauré (6 passages : "réunion de lancement (Kick-off)", "bascule
  unique", "point de suivi projet hebdomadaire", "six mois ou plus après le lancement du projet",
  "un même cadre de gouvernance...", phrase de conclusion sur le pilotage).
- Testé : chapitre absent quand aucune des 3 conditions n'est vraie (migration=non, MCO=non,
  plateforme=onpremise).

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
