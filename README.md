# Générateur de dimensionnement Carbonio

Calcule le dimensionnement d'une infrastructure Zextras Carbonio à partir
de quelques informations de pré-vente (comptes, domaines, volumétrie,
stockage Objet, services demandés), selon les règles métier documentées
dans `catalogs/sizing_rules.yaml`, puis génère un document de prérequis
techniques (LaTeX/PDF) avec tableau de dimensionnement et schéma
d'architecture DMZ/LAN.

## Installation

```bash
pip install pyyaml questionary jinja2 --break-system-packages
```

Dépendances système : une distribution LaTeX (TeX Live) avec `xelatex`
(police Open Sans via `fontspec`), et les paquets `babel` (français),
`tikz`, `adjustbox`, `longtable`, `colortbl`, `fancyhdr`, `lastpage`.
Sur Debian/Ubuntu :

```bash
apt-get install texlive-xetex texlive-latex-recommended \
                 texlive-latex-extra texlive-lang-french \
                 texlive-pictures fonts-open-sans
```

## Utilisation

```bash
# 1. Dimensionnement — nouvelle config, questionnaire interactif
python3 src/generate_sizing.py

# Relecture/ajustement d'une config existante
python3 src/generate_sizing.py --client config/clients/univ_amboise.yaml

# 2. Génération du document de prérequis techniques (LaTeX + PDF)
python3 src/generate_pdf.py --client config/clients/univ_amboise.yaml --compile
```

Sortie dans `build/<nom_client_slugifié>/` : le PDF final à la racine
(suivi par git uniquement pour les 2 exemples), les fichiers
intermédiaires (.tex, logos, résidus LaTeX) dans `generation/` (jamais
suivi par git, même pour les exemples).

## Structure

```
catalogs/                    # données PROGRAMME, jamais dupliquées par client
  vm_catalog.yaml             # specs numériques par composant (vcpu/ram/disque)
  component_descriptions.yaml # descriptions textuelles (séparées du catalogue numérique)
  component_labels.yaml       # libellés d'affichage courts (tableau + schéma)
  service_catalog.yaml        # service coché -> composant(s) Carbonio
  sizing_rules.yaml           # seuils, paliers HA, règles de calcul
  team_directory.yaml         # annuaire des intervenants Zextras (id numérique -> nom/rôle/contact)

config/clients/               # UN fichier YAML par client (gitignored sauf les 2 exemples)
  client_exemple_petite.yaml  # petite infra, palier 0, 1 mailstore
  univ_amboise.yaml           # grosse infra fictive, palier 3, 5 mailstores, tous services

templates/
  preamble.tex.j2              # en-tête LaTeX (police, couleurs, logos) — repris du DAT generator
  prestataire.tex               # infos Zextras Services STATIQUES (pas de Jinja, \input tel quel)
  partials/
    cover.tex.j2                 # page de garde (commercial/auteur résolus depuis team_directory)
    revisions.tex.j2             # historique des révisions
    prerequis.tex.j2             # tableau des prérequis + ligne de totaux
    architecture.tex.j2          # schéma DMZ/LAN (via tikz_builder.py, sans flux)
  assets/logo_zextras_services.png

src/
  config_loader.py            # chargement catalogues + configs client
  sizing_engine.py             # cœur de calcul, aucune dépendance LaTeX
  generate_sizing.py           # CLI dimensionnement (interactif ou --client)
  latex_utils.py                # échappement LaTeX + environnement Jinja2 (délimiteurs \BLOCK{}/\VAR{})
  tikz_builder.py               # génère le schéma TikZ (repris du Générateur de DAT)
  generate_pdf.py               # CLI génération du document (LaTeX + PDF)
```

## Deux exemples fournis

- `config/clients/client_exemple_petite.yaml` — 800 comptes, palier HA 0,
  1 mailstore, Chat+Tâches seulement (7 nœuds).
- `config/clients/univ_amboise.yaml` — client fictif, 25000 comptes,
  palier HA 3, 5 mailstores, tous les services, usine de migration
  (20 nœuds).

## Annuaire des intervenants (`catalogs/team_directory.yaml`)

Le commercial en charge et l'auteur du document sont référencés par id
numérique depuis la config client (`infra.commercial_id`,
`infra.auteur_id`, et `revisions[].auteur_id`) — jamais retapés à la
main. Ajouter un intervenant = ajouter une entrée numérotée dans ce
fichier.

## Principes repris du Générateur de DAT (cohérence entre projets)

- Ids de composants strictement identiques (`mesh`, `directory_master`,
  `mailbox`, `proxy`, `mta_in`, `mta_auth`, `mta_out`, `files`, `docs`,
  `chat`, `videoconf`, `tasks`, `monitoring`...).
- Catalogues séparés de la config client, jamais dupliqués.
- Jamais de blocage sur donnée manquante — voir `sizing_rules.yaml` pour
  les valeurs de repli.
- Convention `--client` (pas `--config`) pour relire une config existante.
- Même préambule LaTeX (police Open Sans, couleurs, logos en-tête/pied
  de page), même style de page de garde et d'historique des révisions.
- `tikz_builder.py` vendoré tel quel (appelé avec `flows=[]` pour un
  schéma volontairement plus simple qu'un DAT complet — zones/nœuds
  seulement, sans flux).

## Ce qui manque volontairement pour l'instant

- Logo client (le champ `client.logo` existe dans le schéma mais n'a pas
  encore été testé avec un vrai fichier).
- Prise en compte du niveau de service (Community/Advanced), du SLA, ou
  d'autres chapitres du DAT complet — ce document reste volontairement un
  récapitulatif de prérequis, pas un DAT.
