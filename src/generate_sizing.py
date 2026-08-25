#!/usr/bin/env python3
"""
generate_sizing.py — Point d'entrée du générateur de dimensionnement Carbonio.

Version actuelle (premier socle) : calcule et écrit la liste des nœuds
(nodes) dans le YAML client. La génération LaTeX/PDF arrive dans une
prochaine version (voir CHANGELOG.md) — conformément à la consigne de
toujours valider avant de générer une nouvelle version du programme.

Usage :
    python3 generate_sizing.py --client config/clients/univ_amboise.yaml
    python3 generate_sizing.py                     # mode interactif, crée une nouvelle config
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_catalogs, load_client_config, save_client_config, slugify, CLIENTS_DIR
from sizing_engine import build_nodes, suggest_ha_tier, suggest_mailstore_count, needs_imap_question


def print_review(client_config: dict, result: dict) -> None:
    infra = result["infra_resolved"]
    print("\n=== Rétrospective — récapitulatif du dimensionnement ===")
    print(f"Client            : {client_config['client']['name']}")
    print(f"Comptes           : {client_config['client']['comptes']}")
    print(f"Palier HA retenu  : {infra['ha_tier']} "
          f"(suggestion : {infra['ha_tier_suggestion']} — {infra['ha_tier_reason']})")
    print(f"Mailstores retenu : {infra['mailstore_count']} "
          f"(suggestion : {infra['mailstore_count_suggestion']} — {infra['mailstore_reason']})")
    print(f"Nombre total de nœuds : {len(result['nodes'])}")
    for node in result["nodes"]:
        label = node.get("label", "")
        print(f"  - {node['id']:<20} [{node['zone']}] {node['components']} {label}")
    print()


def interactive_ha_choice(suggestion_level: int, reason: str) -> int:
    print(f"\nPalier de répartition de charge suggéré : {suggestion_level} ({reason})")
    answer = input(f"Appliquer ce palier ? [Entrée = oui / entrer un autre palier 0-3] : ").strip()
    if answer == "":
        return suggestion_level
    return int(answer)


def interactive_mailstore_choice(suggestion_count: int, reason: str) -> int:
    print(f"\nNombre de mailstores suggéré : {suggestion_count} ({reason})")
    answer = input("Ajuster ce nombre ? [Entrée = garder la suggestion / entrer un nombre] : ").strip()
    if answer == "":
        return suggestion_count
    return int(answer)


def run_interactive(catalogs: dict) -> dict:
    try:
        import questionary
    except ImportError:
        print("Le module 'questionary' n'est pas installé.")
        print("Installation : pip install questionary --break-system-packages")
        sys.exit(1)

    print("=== Nouveau dimensionnement Carbonio ===\n")

    name = questionary.text("Nom du client :").ask()
    classification = questionary.select(
        "Classification du document :",
        choices=["Public", "Client", "Restreint", "Confidentiel"],
        default="Client",
    ).ask()
    logo = questionary.text(
        "Chemin vers le logo client (optionnel, chemin relatif à ce fichier de config, laisser vide si aucun) :",
        default="",
    ).ask()
    domaines = int(questionary.text("Nombre de domaines :", default="1").ask())
    comptes = int(questionary.text("Nombre de comptes :").ask())
    volumetrie_to = float(questionary.text("Volumétrie totale (To) :", default="0").ask())
    stockage_objet = questionary.confirm("Stockage Objet activé ?", default=False).ask()

    print("\nServices à activer (email/calendrier/contacts sont toujours inclus) :")
    chat = questionary.confirm("Chat ?", default=False).ask()
    tache = questionary.confirm("Tâches ?", default=False).ask()
    files = questionary.confirm("Files ?", default=False).ask()
    edition_collaborative = questionary.confirm("Édition collaborative ?", default=False).ask()
    visio = questionary.confirm("Visioconférence ?", default=False).ask()

    migration_factory = questionary.confirm(
        "Y a-t-il une usine de migration sur l'infrastructure client ?", default=False
    ).ask()

    imap = True
    if needs_imap_question(comptes, catalogs["sizing_rules"]):
        imap = questionary.confirm(
            "L'accès IMAP direct est-il proposé aux utilisateurs ?", default=True
        ).ask()

    team_directory = catalogs["team_directory"]
    team_choices = [
        questionary.Choice(title=f"{entry['nom']} ({entry.get('role', '')})", value=person_id)
        for person_id, entry in team_directory.items()
    ]
    commercial_id = questionary.select("Commercial en charge :", choices=team_choices).ask()
    auteur_id = questionary.select("Qui génère ce document ?", choices=team_choices).ask()

    # L'historique des révisions est placé en PREMIÈRE clé du fichier —
    # c'est la partie qu'on doit mettre à jour le plus souvent (nouvelle
    # version du document), donc la plus simple à retrouver en tête de
    # fichier.
    client_config = {
        "revisions": [{
            "version": "1.0",
            "date": date.today().strftime("%d/%m/%Y"),
            "auteur_id": auteur_id,
            "commentaire": "Première version",
        }],
        "client": {
            "name": name,
            "classification": classification,
            "logo": logo or None,
            "domaines": domaines,
            "comptes": comptes,
            "volumetrie_to": volumetrie_to,
            "stockage_objet": stockage_objet,
        },
        "services": {
            "chat": chat,
            "tache": tache,
            "files": files,
            "edition_collaborative": edition_collaborative,
            "visio": visio,
        },
        "infra": {
            "imap": imap,
            "migration_factory": migration_factory,
            "ha_tier": "auto",
            "mailstore_count": "auto",
            "commercial_id": commercial_id,
            "auteur_id": auteur_id,
        },
        # Chapitre "Parties prenantes" côté client : structure prévue mais
        # PAS demandée en interactif (à compléter manuellement plus tard,
        # voir README). Tant que ces champs sont vides, le document affiche
        # des repères "[à préciser]" plutôt que de bloquer.
        "parties_prenantes": {
            "client": {
                "description": None,
                "site_web": None,
                "adresse": [],
                "telephone_urgence": None,
                "contacts": [],
            },
        },
    }
    return client_config


def resolve_overrides(client_config: dict, catalogs: dict, non_interactive: bool):
    """Applique la logique 'suggestion + choix utilisateur' pour le palier
    HA et le nombre de mailstores (sauf en mode non-interactif : 'auto'
    reste 'auto', un entier explicite dans la config est respecté tel quel)."""
    infra = client_config.get("infra", {})
    ha_override = infra.get("ha_tier", "auto")
    mailstore_override = infra.get("mailstore_count", "auto")

    if non_interactive:
        ha_level_override = None if ha_override == "auto" else int(ha_override)
        mailstore_count_override = None if mailstore_override == "auto" else int(mailstore_override)
        return ha_level_override, mailstore_count_override

    # Mode interactif : on présente toujours la suggestion, même si la
    # config avait déjà une valeur explicite.
    client = client_config["client"]
    imap = infra.get("imap", True)
    ha_suggestion = suggest_ha_tier(client["comptes"], imap, catalogs["sizing_rules"])
    ha_level_override = interactive_ha_choice(ha_suggestion.level, ha_suggestion.reason)

    mailstore_suggestion = suggest_mailstore_count(
        client["comptes"], client.get("volumetrie_to", 0),
        client.get("stockage_objet", False), catalogs["sizing_rules"],
    )
    mailstore_count_override = interactive_mailstore_choice(
        mailstore_suggestion.count, mailstore_suggestion.reason
    )
    return ha_level_override, mailstore_count_override


def main():
    parser = argparse.ArgumentParser(description="Générateur de dimensionnement Carbonio")
    parser.add_argument("--client", help="Chemin vers une config client existante (YAML)")
    parser.add_argument("--non-interactive", action="store_true",
                         help="N'affiche pas la rétrospective, applique 'auto' ou les valeurs de la config telles quelles")
    args = parser.parse_args()

    catalogs = load_catalogs()

    if args.client:
        client_config = load_client_config(args.client)
        output_path = args.client
    else:
        client_config = run_interactive(catalogs)
        output_path = str(CLIENTS_DIR / f"{slugify(client_config['client']['name'])}.yaml")

    ha_level_override, mailstore_count_override = resolve_overrides(
        client_config, catalogs, args.non_interactive
    )

    result = build_nodes(
        client_config, catalogs,
        ha_level_override=ha_level_override,
        mailstore_count_override=mailstore_count_override,
    )

    if not args.non_interactive:
        print_review(client_config, result)

    client_config["nodes"] = result["nodes"]
    client_config["infra_resolved"] = result["infra_resolved"]
    # Fige les choix retenus, pour qu'une relecture ultérieure du fichier
    # (--client) sans repasser par la rétrospective reproduise le même résultat.
    client_config["infra"]["ha_tier"] = result["infra_resolved"]["ha_tier"]
    client_config["infra"]["mailstore_count"] = result["infra_resolved"]["mailstore_count"]

    # "revisions" toujours en première clé du fichier (mise à jour la plus
    # fréquente = doit être la plus facile à retrouver), quel que soit
    # l'ordre d'origine du fichier relu en --client.
    if "revisions" in client_config:
        client_config = {"revisions": client_config.pop("revisions"), **client_config}

    save_client_config(output_path, client_config)
    print(f"Config client écrite : {output_path}")
    print("(Génération LaTeX/PDF : à venir dans une prochaine version)")


if __name__ == "__main__":
    main()
