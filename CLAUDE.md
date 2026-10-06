# CLAUDE.md — CarbonioSizingGenerator

Document de référence pour reprendre le projet en local : contexte, historique, architecture,
règles métier, pièges techniques déjà rencontrés et conventions de travail. À lire en entier avant
toute modification. État documenté : **v0.24.0** (dernier commit connu : `47d5638`).

Dépôt : https://github.com/JulienNicolas37/CarbonioSizingGenerator
Auteur : Julien (Zextras Services, Responsable de production, secteur Amboise/Tours).

---

## 1. Objectif du projet

Générer, à partir d'un fichier YAML client, le **document de prérequis / dimensionnement** d'une
infrastructure Zextras Carbonio, utilisé en **avant-vente**. Sortie : un PDF (LaTeX) au format
« DAT-like » (même esprit que le projet frère *CarbonioDATGenerator*, dont on reprend les
principes de cohérence).

Deux programmes, volontairement séparés :

1. `src/generate_sizing.py` — questionnaire interactif (ou `--non-interactive`) qui calcule le
   dimensionnement et écrit/complète le fichier YAML client (sections `nodes`, `qualification_nodes`,
   `infra_resolved`).
2. `src/generate_pdf.py` — lit le YAML client, construit le contexte, rend les templates Jinja2/LaTeX
   et compile le PDF (`--compile`). Pose la question « document complet ou partiel ? »
   (`--non-interactive` = complet).

Pipeline : YAML client → Python (contexte) → Jinja2 (délimiteurs `\BLOCK{}` / `\VAR{}`) → LaTeX →
`latexmk -xelatex` → PDF. Convention CLI : toujours `--client` (jamais `--config`).

## 2. Structure du dépôt

```
catalogs/            # catalogues PROGRAMME (jamais dupliqués dans les configs client)
  vm_catalog.yaml            # specs VM par composant (vcpu, ram, disques)
  qualification_catalog.yaml # specs réduites pour l'infra de qualification
  sizing_rules.yaml          # TOUTES les règles métier chiffrées (paliers HA, mailstores,
                             #   marges, backup, VMware, storage_categories, composants optionnels…)
  component_labels.yaml      # libellés d'affichage des composants
  carbonio_functions.yaml    # fonctions utilisateur ("Besoins fonctionnels")
  migration_raci.yaml        # tableau RACI de la méthodologie de migration
  migration_gantt.yaml       # planning type de migration (tâches du Gantt)
  gantt_config.yaml          # jours travaillés, ICS jours fériés, seuils de charge (défaut logiciel)
  jours_feries_fr.ics        # calendrier ICS exemple
  team_directory.yaml        # annuaire des intervenants Zextras
  service_catalog.yaml, component_descriptions.yaml
config/clients/      # client_exemple_petite.yaml, univ_amboise.yaml (+ logo),
                     # client_exemple_reference.yaml (TOUTES les options commentées)
src/                 # config_loader, sizing_engine, generate_sizing, generate_pdf,
                     # latex_utils, tikz_builder (schéma archi), gantt_engine, gantt_builder
templates/           # preamble.tex.j2, partials/*.tex.j2, prestataire.tex, carbonio_solution.tex (statiques)
build/               # PDF des 2 exemples suivis par git ; generation/ jamais suivi
```

Seuls 3 fichiers de `config/clients/` sont suivis par git (voir `.gitignore`) ; les configs clients
réelles ne doivent jamais être commitées.

## 3. Structure du document généré

1. Page de garde — 2. Historique des révisions — 3. Sommaire
- Ch.1 Introduction et cadrage — Ch.2 Parties prenantes (client + Zextras) — Ch.3 Solution Zextras Carbonio (statique)
- Ch.4 **Prérequis** : 4.1 Prestations commandées, 4.2 Récapitulatif des besoins, 4.3 Besoins fonctionnels,
  4.4 Dimensionnement (tableau paysage), 4.5 Schéma d'architecture
- Ch.5 Infrastructure de qualification (conditionnel)
- Ch.6 **Bilan des besoins** (tableau Production/Qualification/VMware snapshots/Total) + 6.1 Précisions techniques
- Ch.7 Méthodologie de migration (si migration incluse)
- Ch.8 Méthodologie de pilotage du projet (si MCO, migration ou destination ≠ On Premise)
- Ch.9 Planning de migration — Gantt + charge par ressource (si migration + dates renseignées), toujours en dernier

Mode « partiel » (`generate_pdf.py`) : socle de base + sélection parmi schémas d'architecture,
méthodologie migration, méthodologie projet, planning. Ce choix n'est **jamais** écrit dans le YAML.

## 4. Règles métier clés (source de vérité : `catalogs/sizing_rules.yaml`)

- **Paliers HA DMZ** : palier 0 (< 4000 comptes) 2 nœuds combinés ; paliers 1/2/3 éclatent
  proxy/mta_auth/mta_in/mta_out (palier 3 = ≥ 20000 comptes + IMAP direct).
- **Mode minimal** (remplace le palier 0 quand `comptes < 4000` **ET** `mailstore_count == 1`) :
  1 nœud DMZ combiné + 1 nœud services combiné **sans réplica LDAP** (mesh+directory_master+database)
  + 1 mailstore. Dès le 2ᵉ mailstore ou palier ≥ 1 : DMZ à 2 nœuds + 3 nœuds services (master/replica/database).
  Choix stratégique assumé : rassurer les petits clients on-premise venant d'un Zimbra mono-nœud, mailstore jamais en DMZ.
- **Mailstores** : volumétrie moyenne par mailstore arrondie au demi-To supérieur. Si HSM actif
  (avec ou sans Stockage Objet) : primaire = 200 Go × rétention/7, secondaire = reste. Le secondaire
  est routé « stockage objet » seulement si Stockage Objet actif, sinon « disque lent ».
- **Marge de capacité** `headroom_pct` = 30 % : `capacité = usage / (1 − 0,30)`, arrondie à la centaine
  de Go, appliquée au **primaire et au secondaire uniquement** (pas au backup).
- **Backup** : `1,3 × (primaire+secondaire)` calculé sur l'**usage brut**, sans marge. Rétention en
  jours (défaut 30) : chaque tranche complète de 30 j au-delà de la première ajoute 5 % de l'usage au
  multiplicateur (tranche entamée arrondie au-dessus). Disque **« Backup metadata »** fixe de 200 Go
  par mailstore (disque rapide, sans calcul ni marge).
- **Services applicatifs** : « Tâches » est un service *flottant* (`floating_services`) : il rejoint
  le groupe Chat ou Files/Édition collaborative actif, et n'a sa propre VM que si aucun n'est actif.
- **Optionnels (On Premise / SaaS dédié uniquement, jamais CarbonioCloud)** : VMware (ligne « VMware
  gestion des snapshots » = +15 % du disque rapide de la **production** dans le Bilan), pool VM
  technique (6 vCPU/16 Go/100 Go, production seule), pool PMG (nombre de nœuds = nombre de nœuds
  portant `mta_in`, comptés génériquement ; en DMZ, en coupure devant les MTA_IN).
- **Disque applicatif** : `disk_appli_gb` est optionnel dans le catalogue (repli à 0). Julien a
  rétabli 50 Go pour proxy/mta_* (commit manuel) — ne pas le re-supprimer.
- **Affichage** : DMZ avant LAN ; en DMZ, PMG en premier, visio en dernier
  (`_reorder_nodes_for_display`, affichage uniquement — l'ordre stocké dans le YAML n'est pas modifié).
- **Gantt** : jours travaillés + jours fériés ICS ; groupe répétable « bascule » dupliqué
  `nombre_bascules` fois (références `#1` / `#last` pour les tâches hors groupe) ; bascule 1 = fin des
  dépendances (ou date souhaitée si postérieure) avancée au 1ᵉʳ lundi/mardi/mercredi ; bascule 2 = +14 j ;
  suivantes = +7 j ; surcharge manuelle via `bascules_overrides`. Charge par ressource en % par jour,
  couleurs vert ≤ 80 / orange ≤ 100 / rouge > 100 (configurable). Les jalons n'ont ni durée ni charge.

## 5. Convention du fichier de config client

Clés racine : `revisions` (**toujours en premier**), `parties_prenantes` (`client`, `prestataire` avec
commercial/auteur/chef_projet en clair, jamais par id), `prestation` (migration_included,
destination_platform onpremise|carboniocloud|saasdedie, mco_contract), `gantt`, `services`, `infra`,
puis sections **calculées** (`nodes`, `qualification_nodes`, `infra_resolved`) — jamais éditées à la main.
Référence exhaustive commentée : `config/clients/client_exemple_reference.yaml` (à tenir à jour à
chaque nouveau champ). `--non-interactive` n'ajoute pas rétroactivement les nouveaux champs aux
anciennes configs (champ absent = valeur par défaut/False).

## 6. Historique des versions (résumé ; détail dans `CHANGELOG.md`)

- **0.1 → 0.3** : socle, génération LaTeX/PDF, structure DAT-like (chapitres, sommaire, parties prenantes).
- **0.4** : réorganisation du YAML (parties_prenantes.client/prestataire, chef de projet, infos en clair).
- **0.5** : Stockage Objet/HSM, backups, périmètre fonctionnel.
- **0.6** : infrastructure de qualification (minimal ou HA-mirror), bilan des besoins, catégories de
  stockage configurables, unités dans les en-têtes.
- **0.7** : section `prestation`, méthodologie de migration (RACI coloré, texte conditionnel par plateforme).
- **0.8** : méthodologie de pilotage du projet. **0.9** : Gantt (pgfgantt, charge par ressource) puis
  correctifs de mise en page. **0.10** : document complet/partiel.
- **0.11 → 0.14** : marge de capacité 30 %, nettoyage (suppression téléphone d'urgence, alias YAML,
  README, fichier de référence), HSM découplé du S3, disque Backup metadata.
- **0.15 → 0.17** : suppression puis rétablissement manuel du disque appli proxy/mta, mode minimal,
  « Tâches » flottant. **0.18** : plus de marge sur le backup.
- **0.19 → 0.21** : ligne VMware, pool VM technique, rétention backup par tranches.
- **0.22** : sous-chapitre « Précisions techniques ». **0.23(.1)** : pool PMG (+ correctif commit partiel).
  **0.24** : ordre d'affichage des nœuds DMZ.

## 7. Pièges techniques déjà rencontrés (ne pas les refaire)

- **LaTeX** : `%` est un commentaire → toujours `\%` (a cassé deux fois : texte migration, cellules de
  charge). Tout texte client passe par `escape_latex()` sauf les champs `_raw` (LaTeX déjà généré).
  Jamais bloquant sur donnée manquante : repli `[à préciser]` rouge.
- **Paysage** (`pdflscape`) : dans ce document, `\textwidth` et `\textheight` valent tous deux ~16,4 cm à
  l'intérieur de `landscape`. Gantt et tableaux de charge sont paginés (par groupes complets / blocs
  de jours) plutôt que redimensionnés. Un test isolé `\the\textwidth` a levé le doute.
- **pgfgantt** : `\gantttitlelist` ignore `title height` avec `\rotatebox` (le texte descend dans les
  tâches) → pas de rotation ; `\ganttlink` doit être **dans** l'environnement ; 2 passes LaTeX nécessaires.
- **YAML** : PyYAML génère des ancres `&id001` si des listes sont partagées → copier les listes
  (`list(...)`) et dumper avec `_NoAliasDumper`.
- **Détection de la prestation** : le nombre de nœuds PMG / `migration_factory_active` se déduit du contenu
  de `nodes`, pas d'un flag séparé.
- **Environnement de build** : besoin de `fonts-open-sans`, `texlive-lang-french`, `latexmk`, xelatex,
  `pdf2image`/poppler pour vérifier visuellement. Une session fraîche doit les réinstaller.

## 8. Conventions de travail avec Julien (IMPORTANT)

- **Validation avant génération** : pour tout nouveau programme ou toute nouvelle version, obtenir
  l'accord explicite de Julien avant de générer du code. En cas d'ambiguïté métier (seuils,
  portée, libellés), **poser la question avant d'implémenter** et restituer sa compréhension.
- **Patches** : ne jamais livrer un patch sans `git apply --check` sur un **clone frais et séparé** du
  vrai dépôt, au bon commit. Toujours re-cloner le dépôt réel en début de tâche : Julien fait des
  commits manuels entre deux patches (ex. `4b9e47b` RAM 12 Go, `ffedb97` libellé XFS) — les respecter,
  ne jamais les écraser.
- **Ne pas copier `cp -r src/. dest/`** vers un clone : ça écrase le `.git`.
- **Fichiers à contrôler avant overlay** : `catalogs/team_directory.yaml`, logos, `component_descriptions.yaml`
  (Julien les modifie lui-même).
- **Commit complet** : un patch de 8 fichiers n'a été committé qu'à moitié (v0.23.0, `KeyError: 'pmg'`).
  Vérifier `git status` après application — pas de `.rej`, rien en attente.
- **Livrables** : patch `carbonio-sizing-generator-vX.Y.Z.patch` + PDF d'exemple régénéré ; mettre à jour
  `CHANGELOG.md`, `VERSION`, `client_exemple_reference.yaml` et le README si pertinent ; vérifier la
  non-régression sur les 2 exemples (`client_exemple_petite`, `univ_amboise`) avec
  `--non-interactive`.
- **Formats** : documents bureautiques en LibreOffice (ODT/ODS/ODP), jamais Word/Excel/PowerPoint,
  sauf demande explicite. Les sources de texte fournies par Julien sont des `.odt` balisés
  (`<onpremise>`, `<migration>`, gras à préserver) — les coquilles de balises sont corrigées
  silencieusement après vérification de la cohérence avec lui.
- **Langue** : français pour l'interface, les commentaires et les échanges.

## 9. Idées évoquées, non traitées

- Flèches de flux visuelles « PMG → MTA_IN » dans le schéma d'architecture (aujourd'hui : simple
  regroupement par zone).
- Premier libellé du Gantt (« 02/02 ») légèrement rogné au bord gauche (cosmétique).
- Correction éventuelle de l'accord « seront formaté » dans « Précisions techniques » (édition manuelle de Julien, à laisser
  sauf demande).
