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
(police Open Sans via `fontspec`), `latexmk`, et les paquets `babel`
(français), `tikz`, `adjustbox`, `longtable`, `colortbl`, `fancyhdr`,
`lastpage`, `amssymb` (cases à cocher de la page Confidentialité).
**`latexmk` est un paquet à part sur certaines distributions et n'est
pas toujours installé automatiquement par `texlive-latex-recommended`
— il est donc listé explicitement ci-dessous.**
Sur Debian/Ubuntu :

```bash
apt-get install texlive-xetex texlive-latex-recommended \
                 texlive-latex-extra texlive-lang-french \
                 texlive-pictures fonts-open-sans latexmk
```

### Dépannage : "latexmk n'est pas installé (ou pas dans le PATH)"

Ce message peut apparaître même si `latexmk` a été installé, si son
exécutable n'est pas dans un dossier listé par la variable `PATH`.
Étapes de diagnostic :

```bash
# 1. latexmk est-il trouvé par le shell actuel ?
which latexmk
# Si ça n'affiche rien, latexmk n'est pas dans le PATH de ce shell.

# 2. Le paquet est-il bien installé, et où ?
dpkg -l | grep latexmk          # doit afficher une ligne "ii  latexmk ..."
dpkg -L latexmk | grep bin      # chemin exact de l'exécutable (normalement /usr/bin/latexmk)

# 3. Si le paquet n'apparaît pas du tout à l'étape 2 :
sudo apt-get install latexmk

# 4. Si le paquet EST installé mais `which latexmk` reste vide : le
#    fichier n'est probablement pas dans un dossier standard (cas d'une
#    installation manuelle de TeX Live via install-tl plutôt que apt,
#    par exemple sous /usr/local/texlive/<année>/bin/x86_64-linux/).
#    Ajouter ce dossier au PATH dans ~/.bashrc (ou ~/.profile) :
echo 'export PATH="/usr/local/texlive/2025/bin/x86_64-linux:$PATH"' >> ~/.bashrc
source ~/.bashrc
# Puis ouvrir un NOUVEAU terminal (ou re-`source`) et retester `which latexmk`.
```

## Utilisation

```bash
# 1. Dimensionnement — nouvelle config, questionnaire interactif
python3 src/generate_sizing.py
# Affiche à la fin la commande exacte à copier-coller pour l'étape 2.

# Relecture/ajustement d'une config existante
python3 src/generate_sizing.py --client config/clients/univ_amboise.yaml

# 2. Génération du document de prérequis techniques (LaTeX + PDF)
python3 src/generate_pdf.py --client config/clients/univ_amboise.yaml --compile
# Demande "document complet ou partiel ?" — en partiel, propose d'ajouter
# les schémas d'architecture, la méthodologie de migration, la
# méthodologie projet et/ou le planning de migration au socle de base.
# --non-interactive : saute la question, génère le document complet
# (choix jamais écrit dans la config client : propre à chaque génération).
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
  preamble.tex.j2              # en-tête LaTeX (classe report, chapitres, couleurs, logos)
  prestataire.tex               # section "Intégrateur" STATIQUE (pas de Jinja, inséré tel quel)
  carbonio_solution.tex          # chapitre 3 STATIQUE (présentation générale Carbonio)
  partials/
    cover.tex.j2                 # page de garde (commercial/auteur résolus depuis team_directory)
    revisions.tex.j2              # historique des révisions (chapter*)
    intro_cadrage.tex.j2          # chapitre 1 : objet, rappel des besoins, confidentialité, périmètre
    parties_prenantes_client.tex.j2  # chapitre 2, section client (placeholders si non renseigné)
    zextras_contacts.tex.j2       # tableau de contacts Zextras (depuis team_directory.yaml)
    prerequis.tex.j2              # chapitre 4 : tableau des prérequis + ligne de totaux
    architecture.tex.j2           # schéma DMZ/LAN (via tikz_builder.py, sans flux)
  assets/logo_zextras_services.png

src/
  config_loader.py             # chargement catalogues + configs client
  sizing_engine.py              # cœur de calcul, aucune dépendance LaTeX
  generate_sizing.py            # CLI dimensionnement (interactif ou --client)
  latex_utils.py                 # échappement LaTeX + environnement Jinja2 (délimiteurs \BLOCK{}/\VAR{})
  tikz_builder.py                # génère le schéma TikZ (repris du Générateur de DAT)
  generate_pdf.py                # CLI génération du document (LaTeX + PDF)
```

## Structure du document généré

1. Page de garde
2. Historique des révisions
3. Sommaire
4. Chapitre 1 — Introduction et cadrage (objet, rappel des besoins exprimés, confidentialité,
   propriété intellectuelle, périmètre du document)
5. Chapitre 2 — Parties prenantes (client, intégrateur)
6. Chapitre 3 — Solution Zextras Carbonio (présentation générale)
7. Chapitre 4 — Prérequis techniques (tableau + schéma d'architecture)

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

- Contacts client (chapitre 2) : le schéma existe (`parties_prenantes.client`) mais n'est pas
  demandé en interactif — à compléter manuellement dans le YAML, sinon replis "[à préciser]" visibles.
- Prise en compte du niveau de service (Community/Advanced), du SLA, ou d'autres chapitres du DAT
  complet — ce document reste volontairement un récapitulatif de prérequis, pas un DAT.
