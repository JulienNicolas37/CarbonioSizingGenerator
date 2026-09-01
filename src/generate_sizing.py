#!/usr/bin/env python3
"""
generate_sizing.py — Point d'entrée du générateur de dimensionnement Carbonio.

Calcule et écrit la liste des nœuds (nodes) dans le YAML client. La
génération LaTeX/PDF se fait ensuite via generate_pdf.py (la commande
exacte est affichée en fin d'exécution).

Usage :
    python3 generate_sizing.py --client config/clients/univ_amboise.yaml
    python3 generate_sizing.py                     # mode interactif, crée une nouvelle config
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_catalogs, load_client_config, save_client_config, slugify, get_client, load_yaml, CATALOGS_DIR, CLIENTS_DIR
from sizing_engine import build_nodes, suggest_ha_tier, suggest_mailstore_count, needs_imap_question

# Étiquette de fonction affichée dans le document pour chaque rôle projet
# (voir generate_pdf.py, table des contacts Zextras).
PROJECT_ROLE_LABELS = {
    "commercial": "Commercial en charge",
    "auteur": "Rédacteur du document",
    "chef_projet": "Chef de projet",
}


def print_review(client_config: dict, result: dict) -> None:
    client = get_client(client_config)
    infra = result["infra_resolved"]
    print("\n=== Rétrospective — récapitulatif du dimensionnement ===")
    print(f"Client            : {client.get('name')}")
    print(f"Comptes           : {client.get('comptes')}")
    print(f"Palier HA retenu  : {infra['ha_tier']} "
          f"(suggestion : {infra['ha_tier_suggestion']} — {infra['ha_tier_reason']})")
    print(f"Mailstores retenu : {infra['mailstore_count']} "
          f"(suggestion : {infra['mailstore_count_suggestion']} — {infra['mailstore_reason']})")
    print(f"Nombre total de nœuds (production) : {len(result['nodes'])}")
    for node in result["nodes"]:
        label = node.get("label", "")
        print(f"  - {node['id']:<20} [{node['zone']}] {node['components']} {label}")
    if result["qualification_nodes"]:
        print(f"\nNombre de nœuds (qualification) : {len(result['qualification_nodes'])}")
        for node in result["qualification_nodes"]:
            print(f"  - {node['id']:<20} [{node['zone']}] {node['components']}")
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
    domaines = int(questionary.text("Nombre de domaines :", default="1").ask())
    comptes = int(questionary.text("Nombre de comptes :").ask())
    volumetrie_to = float(questionary.text("Volumétrie totale (To) :", default="0").ask())
    stockage_objet = questionary.confirm("Stockage Objet activé ?", default=False).ask()

    hsm_active = False
    retention_days = None
    if stockage_objet:
        hsm_active = questionary.confirm(
            "Activer le module HSM (stockage secondaire S3) ?", default=True
        ).ask()
        if hsm_active:
            retention_days = int(questionary.text(
                "Rétention en jours à prévoir sur le stockage primaire :", default="7"
            ).ask())

    backups = questionary.confirm("Mettre en place des backups ?", default=True).ask()
    backup_sur_s3 = False
    if backups and stockage_objet:
        backup_sur_s3 = questionary.confirm(
            "Le backup sera-t-il également sur S3 ?", default=False
        ).ask()

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

    # --- Infrastructure de qualification (optionnelle) ---
    qualification_active = questionary.confirm(
        "Faut-il prévoir une infrastructure de qualification ?", default=False
    ).ask()
    qualification_ha_mirror = False
    if qualification_active:
        # Aperçu du palier HA suggéré à ce stade (le choix définitif n'est
        # confirmé qu'à la rétrospective) : la question de mirroring HA
        # n'a de sens que si la production a effectivement de la HA.
        ha_preview = suggest_ha_tier(comptes, imap, catalogs["sizing_rules"])
        if ha_preview.level > 0:
            qualification_ha_mirror = questionary.confirm(
                "Faut-il prévoir les mêmes fonctions HA (proxy, MTA, etc.) "
                "que la production sur la qualification ?", default=False
            ).ask()

    # --- Prestation commandée (migration, plateforme de destination, MCO) ---
    # Toujours posées (même sans migration), car "plateforme de destination"
    # a vocation à être réutilisée au-delà du seul chapitre migration.
    migration_included = questionary.confirm(
        "La migration est-elle incluse dans la prestation ?", default=False
    ).ask()
    destination_platform_choices = [
        questionary.Choice(title="CarbonioCloud", value="carboniocloud"),
        questionary.Choice(title="On Premise", value="onpremise"),
        questionary.Choice(title="SaaS dédié", value="saasdedie"),
    ]
    destination_platform = questionary.select(
        "Quelle est la plateforme de destination ?", choices=destination_platform_choices
    ).ask()
    mco_contract = questionary.confirm(
        "Un contrat de MCO est-il prévu à la suite de la migration ?", default=False
    ).ask()

    # --- Planning de migration (Gantt) — uniquement si migration incluse ---
    nombre_bascules = None
    date_premiere_bascule_souhaitee = None
    date_debut_estimee = None
    date_fin_estimee = None
    if migration_included:
        nombre_bascules = int(questionary.text(
            "Combien de bascules (lots de migration) sont prévues ?", default="1"
        ).ask())
        date_premiere_bascule_souhaitee = questionary.text(
            "Date souhaitée pour la première bascule (JJ/MM/AAAA, laisser vide pour un calcul automatique) :",
            default=""
        ).ask() or None
        date_debut_estimee = questionary.text(
            "Date de début estimée du projet (JJ/MM/AAAA) :"
        ).ask()
        date_fin_estimee = questionary.text(
            "Date de fin estimée du projet (JJ/MM/AAAA) :"
        ).ask()

    # --- Parties prenantes côté prestataire (Zextras) ---
    # On sélectionne dans l'annuaire (catalogs/team_directory.yaml) pour
    # éviter les fautes de frappe, mais l'enregistrement COMPLET (nom,
    # rôle, email, téléphone) est recopié tel quel dans la config client :
    # pas de simple id de référence, pour que le fichier reste
    # auto-suffisant et facile à maintenir sans devoir croiser un autre
    # fichier.
    team_directory = catalogs["team_directory"]
    team_choices = [
        questionary.Choice(title=f"{entry['nom']} ({entry.get('role', '')})", value=person_id)
        for person_id, entry in team_directory.items()
    ]
    commercial_id = questionary.select("Commercial en charge :", choices=team_choices).ask()
    auteur_id = questionary.select("Qui rédige ce document ?", choices=team_choices).ask()
    chef_projet_id = questionary.select("Qui est le chef de projet ?", choices=team_choices).ask()

    def inline_person(person_id):
        entry = team_directory[person_id]
        return {
            "nom": entry["nom"],
            "role": entry.get("role", ""),
            "email": entry.get("email", ""),
            "telephone": entry.get("telephone", ""),
        }

    commercial = inline_person(commercial_id)
    auteur = inline_person(auteur_id)
    chef_projet = inline_person(chef_projet_id)

    # L'historique des révisions est placé en PREMIÈRE clé du fichier —
    # c'est la partie qu'on doit mettre à jour le plus souvent (nouvelle
    # version du document), donc la plus simple à retrouver en tête de
    # fichier.
    client_config = {
        "revisions": [{
            "version": "1.0",
            "date": date.today().strftime("%d/%m/%Y"),
            "auteur": auteur["nom"],
            "commentaire": "Première version",
        }],
        # Chapitre "Parties prenantes" : TOUTES les informations relatives
        # au client (identité, dimensionnement, contacts) sont ici — un
        # seul endroit, pas de section "client" séparée par ailleurs.
        "parties_prenantes": {
            "client": {
                "name": name,
                "classification": classification,
                "logo": None,  # chemin relatif à ce fichier vers un logo client — à ajouter manuellement si besoin
                "domaines": domaines,
                "comptes": comptes,
                "volumetrie_to": volumetrie_to,
                "stockage_objet": stockage_objet,
                # Contacts client : structure prévue mais PAS demandée en
                # interactif (à compléter manuellement, voir README). Tant
                # que ces champs sont vides, le document affiche des
                # repères "[à préciser]" plutôt que de bloquer.
                "description": None,
                "site_web": None,
                "adresse": [],
                "contacts": [],
            },
            "prestataire": {
                "commercial": commercial,
                "auteur": auteur,
                "chef_projet": chef_projet,
            },
        },
        "services": {
            "chat": chat,
            "tache": tache,
            "files": files,
            "edition_collaborative": edition_collaborative,
            "visio": visio,
        },
        # Ce qui a été VENDU / commandé, distinct des décisions techniques
        # d'infra ci-dessous (cf. remarque : "pourquoi tu as mis ça dans
        # infra ?!" — cette fois ces informations vivent bien à part).
        "prestation": {
            "migration_included": migration_included,
            "destination_platform": destination_platform,
            "mco_contract": mco_contract,
        },
        # Config Gantt : recopiée du défaut logiciel (catalogs/gantt_config.yaml)
        # dans le fichier client, pour rester modifiable projet par projet
        # sans toucher au défaut global (même principe que team_directory).
        "gantt": {
            "jours_travailles": dict(catalogs["gantt_config"]["jours_travailles"]),
            "jours_feries_ics": catalogs["gantt_config"]["jours_feries_ics"],
            "seuils_charge": dict(catalogs["gantt_config"]["seuils_charge"]),
            "date_debut_estimee": date_debut_estimee,
            "date_fin_estimee": date_fin_estimee,
            "nombre_bascules": nombre_bascules,
            "date_premiere_bascule_souhaitee": date_premiere_bascule_souhaitee,
            "bascules_overrides": [],  # jamais en questionnaire, ajouté à la main
        },
        "infra": {
            "imap": imap,
            "migration_factory": migration_factory,
            "ha_tier": "auto",
            "mailstore_count": "auto",
            "hsm_active": hsm_active,
            "retention_days": retention_days,
            "backups": backups,
            "backup_sur_s3": backup_sur_s3,
            "qualification_active": qualification_active,
            "qualification_ha_mirror": qualification_ha_mirror,
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
    client = get_client(client_config)
    imap = infra.get("imap", True)
    ha_suggestion = suggest_ha_tier(client["comptes"], imap, catalogs["sizing_rules"])
    ha_level_override = interactive_ha_choice(ha_suggestion.level, ha_suggestion.reason)

    mailstore_suggestion = suggest_mailstore_count(
        client["comptes"], client.get("volumetrie_to", 0),
        client.get("stockage_objet", False), infra.get("hsm_active", False),
        catalogs["sizing_rules"],
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
        output_path = str(CLIENTS_DIR / f"{slugify(get_client(client_config)['name'])}.yaml")

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
    client_config["qualification_nodes"] = result["qualification_nodes"]
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

    # Avertissement si le planning de migration calculé dépasse la date de
    # fin estimée communiquée pour le projet.
    prestation = client_config.get("prestation", {})
    gantt_cfg = client_config.get("gantt", {})
    if prestation.get("migration_included") and gantt_cfg.get("date_debut_estimee") and gantt_cfg.get("date_fin_estimee"):
        from gantt_engine import WorkCalendar, compute_schedule, parse_ics_dates, parse_date_fr, format_date_fr
        raw_tasks = load_yaml(CATALOGS_DIR / "migration_gantt.yaml")
        holidays = parse_ics_dates(str(Path(gantt_cfg["jours_feries_ics"])))
        cal = WorkCalendar(gantt_cfg["jours_travailles"], holidays)
        date_debut = parse_date_fr(gantt_cfg["date_debut_estimee"])
        date_fin_souhaitee = parse_date_fr(gantt_cfg["date_fin_estimee"])
        date_premiere_bascule = parse_date_fr(gantt_cfg.get("date_premiere_bascule_souhaitee"))
        sched = compute_schedule(
            raw_tasks, cal, date_debut, gantt_cfg["nombre_bascules"],
            date_premiere_bascule, gantt_cfg.get("bascules_overrides", []),
        )
        if date_debut and date_fin_souhaitee and sched["date_fin_projet"] > date_fin_souhaitee:
            print(f"\n⚠ AVERTISSEMENT : le planning de migration calculé se termine le "
                  f"{format_date_fr(sched['date_fin_projet'])}, après la date de fin estimée "
                  f"communiquée ({format_date_fr(date_fin_souhaitee)}). Un réajustement du "
                  f"calendrier global est à prévoir avec le client.")

    generate_pdf_script = Path(__file__).resolve().parent / "generate_pdf.py"
    try:
        generate_pdf_rel = os.path.relpath(generate_pdf_script, Path.cwd())
        output_rel = os.path.relpath(output_path, Path.cwd())
    except ValueError:
        generate_pdf_rel, output_rel = str(generate_pdf_script), str(output_path)
    print("\nPour générer le document LaTeX/PDF :")
    print(f"  python3 {generate_pdf_rel} --client {output_rel} --compile")


if __name__ == "__main__":
    main()
