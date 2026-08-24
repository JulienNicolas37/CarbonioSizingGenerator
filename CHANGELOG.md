# Changelog

## 0.1.0 — Premier socle
- Catalogues programme : vm_catalog, component_descriptions, service_catalog, sizing_rules
- Moteur de calcul (sizing_engine.py) : palier HA proxy/MTA à 4 niveaux (0/4000/10000/20000+IMAP),
  scaling mailstores (5000 comptes / 5 To, ignoré si stockage Objet), regroupement Application01/02,
  usine de migration optionnelle
- CLI (generate_sizing.py) : mode interactif (questionary) et mode --client, rétrospective finale
  avec ajustement du nombre de mailstores et du palier HA
- 2 configs d'exemple : petite infra et Université d'Amboise (grosse infra fictive)
- .gitignore protégeant les configs clients réelles et les dossiers de génération

À venir (voir discussion en cours) :
- Templates LaTeX (préambule, cover, chapitres) repris du style du Générateur de DAT
- tikz_builder.py pour le schéma DMZ/LAN
- Compilation PDF via xelatex/latexmk
