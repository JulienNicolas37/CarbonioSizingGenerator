# Générateur de dimensionnement Carbonio

Calcule le dimensionnement d'une infrastructure Zextras Carbonio à partir
de quelques informations de pré-vente (comptes, domaines, volumétrie,
stockage Objet, services demandés), selon les règles métier documentées
dans `catalogs/sizing_rules.yaml`.

**État actuel (v0.1 — premier socle)** : calcule et écrit la liste des
nœuds dans le YAML client (`nodes:` + `infra_resolved:`). La génération
LaTeX/PDF (schéma DMZ/LAN, document final) arrive dans une prochaine
version — voir CHANGELOG.md.

## Installation

```bash
pip install pyyaml questionary --break-system-packages
```

## Utilisation

```bash
# Nouvelle config, questionnaire interactif (crée config/clients/<nom>.yaml)
python3 src/generate_sizing.py

# Relecture/ajustement d'une config existante
python3 src/generate_sizing.py --client config/clients/univ_amboise.yaml

# Sans rétrospective interactive (CI, scripts) : respecte "auto" ou les
# valeurs explicites déjà présentes dans le fichier
python3 src/generate_sizing.py --client config/clients/univ_amboise.yaml --non-interactive
```

## Structure

```
catalogs/                    # données PROGRAMME, jamais dupliquées par client
  vm_catalog.yaml             # specs numériques par composant (vcpu/ram/disque)
  component_descriptions.yaml # descriptions textuelles (séparées du catalogue numérique)
  service_catalog.yaml        # service coché -> composant(s) Carbonio
  sizing_rules.yaml           # seuils, paliers HA, règles de calcul

config/clients/               # UN fichier YAML par client (gitignored sauf les 2 exemples)
  client_exemple_petite.yaml  # petite infra, palier 0, 1 mailstore
  univ_amboise.yaml           # grosse infra fictive, palier 3, 5 mailstores, tous services

src/
  config_loader.py            # chargement catalogues + configs client
  sizing_engine.py            # cœur de calcul, aucune dépendance LaTeX
  generate_sizing.py          # CLI (interactif ou --client)
```

## Deux exemples fournis

- `config/clients/client_exemple_petite.yaml` — 800 comptes, palier HA 0,
  1 mailstore, Chat+Tâches seulement.
- `config/clients/univ_amboise.yaml` — client fictif, 25000 comptes,
  palier HA 3, 5 mailstores, tous les services, usine de migration.

## Principes repris du Générateur de DAT (cohérence entre projets)

- Ids de composants strictement identiques (`mesh`, `directory_master`,
  `mailbox`, `proxy`, `mta_in`, `mta_auth`, `mta_out`, `files`, `docs`,
  `chat`, `videoconf`, `tasks`, `monitoring`...).
- Catalogues séparés de la config client, jamais dupliqués.
- Jamais de blocage sur donnée manquante — voir `sizing_rules.yaml` pour
  les valeurs de repli.
- Convention `--client` (pas `--config`) pour relire une config existante.
