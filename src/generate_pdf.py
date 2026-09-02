#!/usr/bin/env python3
"""
generate_pdf.py — Génère le document de prérequis techniques (page de
garde, historique des révisions, sommaire, introduction et cadrage,
parties prenantes, présentation de la solution Carbonio, prérequis
techniques + schéma d'architecture) au format LaTeX/PDF, à partir d'une
config client déjà dimensionnée (contenant nodes:, voir generate_sizing.py).

Usage :
    python3 generate_pdf.py --client config/clients/univ_amboise.yaml --compile
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import load_client_config, load_yaml, CATALOGS_DIR, slugify, get_client
from latex_utils import build_env, escape_latex
from tikz_builder import build_tikz
from gantt_engine import WorkCalendar, compute_schedule, parse_ics_dates, parse_date_fr, format_date_fr, compute_resource_load
from gantt_builder import build_pgfgantt, build_charge_table

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = PROJECT_ROOT / "templates"
PARTIALS_DIR = TEMPLATES_DIR / "partials"
BUILD_DIR = PROJECT_ROOT / "build"

ZONES = [
    {"id": "DMZ", "label": "Zone Publique (DMZ)", "short_label": "Publique (DMZ)", "max_cols": 2},
    {"id": "LAN", "label": "Zone Privée (LAN)", "short_label": "Privée (LAN)", "max_cols": 3},
]

DEFAULT_INTEGRATOR = {
    "name": "Zextras Services",
    "website": "https://www.zextras-services.fr",
    "logo_file": "assets/logo_zextras_services.png",
}

# 4 niveaux de classification, mêmes libellés que le Générateur de DAT.
CLASSIFICATION_LEVELS = [
    ("Public", "Le contenu de ce document et de ses annexes peut être diffusé librement sans restriction."),
    ("Client", "Le contenu de ce document et de ses annexes est strictement confidentiel et ne peut être diffusé en dehors des intervenants directs."),
    ("Restreint", "Le contenu de ce document et de ses annexes est strictement confidentiel et est réservé uniquement aux collaborateurs de ZEXTRAS SERVICES."),
    ("Confidentiel", "Le contenu de ce document et de ses annexes est strictement confidentiel et est réservé uniquement aux collaborateurs de ZEXTRAS SERVICES identifiés ci-dessous."),
]

# Libellés d'affichage des services cochés (config client, clé "services"),
# pour le récapitulatif des besoins exprimés — email/calendrier/contacts
# sont toujours inclus et affichés à part.
SERVICE_DISPLAY_LABELS = {
    "chat": "Chat",
    "tache": "Tâches",
    "files": "Files",
    "edition_collaborative": "Édition collaborative",
    "visio": "Visioconférence",
}

# Libellés d'affichage de la plateforme de destination (config client,
# infra.destination_platform) — mêmes valeurs internes que les balises du
# document de méthodologie de migration (onpremise/carboniocloud/saasdedie).
DESTINATION_PLATFORM_LABELS = {
    "carboniocloud": "CarbonioCloud",
    "onpremise": "On Premise",
    "saasdedie": "SaaS dédié",
}

RACI_LETTER_COLORS = {"R": "raciR", "A": "raciA", "C": "raciC", "I": "raciI"}


def format_raci(code: str) -> str:
    """Transforme un code RACI type "R / A" en LaTeX brut avec chaque
    lettre en gras et colorée (R jaune, A rouge, C bleu, I vert). Jamais
    échappé ensuite : c'est déjà du LaTeX généré."""
    if not code:
        return "---"
    parts = [p.strip() for p in code.split("/")]
    formatted = []
    for p in parts:
        color = RACI_LETTER_COLORS.get(p)
        if color:
            formatted.append(r"\textbf{\color{" + color + "}" + p + "}")
        else:
            formatted.append(escape_latex(p))
    return " / ".join(formatted)


def value_or_placeholder(value, label: str) -> str:
    """Repli visible (jamais bloquant) : \\placeholder{...} en LaTeX brut
    si la donnée est absente, sinon la valeur échappée."""
    if value in (None, "", [], {}):
        return r"\placeholder{" + escape_latex(label) + "}"
    return escape_latex(value)


def _process_nodes(raw_nodes: list, component_labels: dict) -> tuple:
    """Transforme une liste de nœuds bruts (config client) en (nodes
    affichables, totals, composants vus) — factorisé pour être réutilisé
    identiquement pour la production ET la qualification."""
    nodes = []
    totals = {"vcpu": 0, "ram_gb": 0, "disk_os_gb": 0, "disk_appli_gb": 0,
              "disk_store_gb": 0, "disk_secondaire_gb": 0, "disk_backup_gb": 0}
    components_seen = []
    for n in raw_nodes:
        sizing = n.get("sizing", {})
        components_display = ", ".join(component_labels.get(c, c) for c in n.get("components", []))
        nodes.append({
            "id": escape_latex(n["id"]),
            "zone": escape_latex(n["zone"]),
            "components": n["components"],
            "components_display": escape_latex(components_display),
            "components_display_diagram": components_display,
            "sizing": sizing,
        })
        for c in n.get("components", []):
            if c not in components_seen:
                components_seen.append(c)
        for key in totals:
            totals[key] += sizing.get(key, 0)
    return nodes, totals, components_seen


def _diagram_for(raw_nodes: list, component_labels: dict) -> str:
    diagram_nodes = [
        {
            "id": n["id"],
            "zone": n["zone"],
            "components_display_diagram": ", ".join(component_labels.get(c, c) for c in n.get("components", [])),
        }
        for n in raw_nodes
    ]
    return build_tikz(zones=ZONES, nodes=diagram_nodes, flows=[], network_equipment=[], legend_entries=[])


def categorize_storage(totals: dict, backup_sur_s3: bool, secondaire_is_s3: bool, storage_rules: dict) -> dict:
    """Regroupe les colonnes disque détaillées (chapitre "Prérequis
    techniques") en catégories de synthèse pour le "Bilan des besoins".
    La composition de chaque catégorie vient de sizing_rules.yaml
    (storage_categories) — modifiable sans toucher au code. Le backup et
    le secondaire (délestage HSM) sont routés dynamiquement : le
    secondaire va en stockage Objet seulement si le Stockage Objet est
    réellement actif, sinon (HSM sans Stockage Objet -> délestage vers
    un disque lent local) il va en disque lent."""
    backup_field = storage_rules.get("backup_field", "disk_backup_gb")
    backup_category = (storage_rules.get("backup_category_if_s3") if backup_sur_s3
                        else storage_rules.get("backup_category_if_not_s3"))
    secondaire_field = storage_rules.get("secondaire_field", "disk_secondaire_gb")
    secondaire_category = (storage_rules.get("secondaire_category_if_s3") if secondaire_is_s3
                            else storage_rules.get("secondaire_category_if_not_s3"))
    result = {}
    for cat_name, cat_def in storage_rules.get("categories", {}).items():
        total = sum(totals.get(f, 0) for f in cat_def.get("fields", []))
        if cat_name == backup_category:
            total += totals.get(backup_field, 0)
        if cat_name == secondaire_category:
            total += totals.get(secondaire_field, 0)
        result[cat_name] = total
    return result


def build_context(client_config: dict, catalogs: dict, document_scope: dict) -> dict:
    component_labels = catalogs["component_labels"]

    client_raw = get_client(client_config)
    prestataire_raw = client_config.get("parties_prenantes", {}).get("prestataire", {})
    commercial_raw = prestataire_raw.get("commercial", {})
    auteur_raw = prestataire_raw.get("auteur", {})
    chef_projet_raw = prestataire_raw.get("chef_projet", {})

    raw_revisions = client_config.get("revisions") or [
        {"version": "1.0", "date": "[à préciser]", "auteur": None, "commentaire": "Version générée automatiquement"}
    ]
    revisions = [
        {
            "version": escape_latex(rev.get("version", "")),
            "date": escape_latex(rev.get("date", "")),
            "auteur_nom": value_or_placeholder(rev.get("auteur"), "Auteur à préciser"),
            "commentaire": escape_latex(rev.get("commentaire", "")),
        }
        for rev in raw_revisions
    ]

    nodes, totals, all_components_seen = _process_nodes(client_config.get("nodes", []), component_labels)
    diagram_tikz_raw = _diagram_for(client_config.get("nodes", []), component_labels)

    qualif_raw_nodes = client_config.get("qualification_nodes", [])
    qualification_active = bool(qualif_raw_nodes)
    qualif_nodes, qualif_totals, _ = _process_nodes(qualif_raw_nodes, component_labels)
    diagram_tikz_raw_qualif = _diagram_for(qualif_raw_nodes, component_labels) if qualification_active else ""

    bilan_totals = {key: totals[key] + qualif_totals[key] for key in totals}

    backup_sur_s3 = client_config.get("infra", {}).get("backup_sur_s3", False)
    secondaire_is_s3_flag = bool(client_raw.get("stockage_objet")) and bool(client_config.get("infra", {}).get("hsm_active"))
    storage_rules = catalogs["sizing_rules"]["storage_categories"]
    storage_categories = {
        "production": categorize_storage(totals, backup_sur_s3, secondaire_is_s3_flag, storage_rules),
        "qualification": categorize_storage(qualif_totals, False, False, storage_rules),  # jamais de backup/secondaire en qualif
        "bilan": categorize_storage(bilan_totals, backup_sur_s3, secondaire_is_s3_flag, storage_rules),
    }

    infra_resolved = client_config.get("infra_resolved", {})
    qualification = {
        "active": qualification_active,
        "mode": infra_resolved.get("qualification_mode") or "minimal",
    }

    # --- Prestation commandée (migration, plateforme de destination, MCO) ---
    prestation_raw = client_config.get("prestation", {})
    destination_platform_raw = prestation_raw.get("destination_platform", "onpremise")
    prestation = {
        "migration_included": prestation_raw.get("migration_included", False),
        "destination_platform": destination_platform_raw,
        "destination_platform_display": escape_latex(
            DESTINATION_PLATFORM_LABELS.get(destination_platform_raw, destination_platform_raw)
        ),
        "mco_contract": prestation_raw.get("mco_contract", False),
    }
    migration = {
        "included": prestation["migration_included"],
        "destination_platform": destination_platform_raw,
        "is_onpremise": destination_platform_raw == "onpremise",
        "is_carboniocloud": destination_platform_raw == "carboniocloud",
        "is_saasdedie": destination_platform_raw == "saasdedie",
        "mco": prestation["mco_contract"],
    }

    # Chapitre "Méthodologie de pilotage du projet" : affiché si contrat de
    # MCO, migration incluse, OU plateforme non On Premise (CarbonioCloud/
    # SaaS dédié assimilés à une forme de SaaS) — HYPOTHÈSE à confirmer.
    is_saas_like = destination_platform_raw in ("carboniocloud", "saasdedie")
    pilotage_active = prestation["mco_contract"] or prestation["migration_included"] or is_saas_like

    # Tableau RACI de la migration : n'inclut une ligne taguée que si elle
    # correspond à la plateforme de destination retenue ; les lignes non
    # taguées s'affichent toujours. Lettres RACI mises en forme (couleurs)
    # une fois pour toutes ici (LaTeX déjà généré, jamais échappé ensuite).
    migration_raci = []
    if prestation["migration_included"]:
        for row in catalogs.get("migration_raci", []):
            tag = row.get("tag")
            if tag and tag != destination_platform_raw:
                continue
            migration_raci.append({
                "phase": escape_latex(row.get("phase", "")),
                "activite": escape_latex(row.get("activite", "")),
                "client_raci": format_raci(row.get("client", "")),
                "zextras_raci": format_raci(row.get("zextras", "")),
            })

    # --- Récapitulatif des besoins exprimés (chapitre "Prérequis techniques") ---
    active_services = [SERVICE_DISPLAY_LABELS[s] for s, v in client_config.get("services", {}).items()
                        if v and s in SERVICE_DISPLAY_LABELS]
    services_display = "Messagerie, agenda et contacts (toujours inclus)"
    if active_services:
        services_display += ", " + ", ".join(active_services)
    infra_raw = client_config.get("infra", {})
    stockage_objet_actif = bool(client_raw.get("stockage_objet"))
    hsm_active = infra_raw.get("hsm_active", False)
    # Le module HSM délie les données froides du stockage primaire, que
    # la cible soit du S3 (si Stockage Objet actif) ou un simple disque
    # lent local (sinon) — décidé ici, une fois pour tout le document.
    secondaire_is_s3 = hsm_active and stockage_objet_actif
    secondaire_label = "S3" if secondaire_is_s3 else "lent"
    besoins = {
        "domaines": client_raw.get("domaines", "[à préciser]"),
        "comptes": client_raw.get("comptes", "[à préciser]"),
        "volumetrie_to": client_raw.get("volumetrie_to", "[à préciser]"),
        "stockage_objet": "Oui" if stockage_objet_actif else "Non",
        "services_display": escape_latex(services_display),
        "hsm_active": hsm_active,
        "secondaire_is_s3": secondaire_is_s3,
        "secondaire_label": secondaire_label,
        "retention_days": infra_raw.get("retention_days"),
        "backups": infra_raw.get("backups", False),
        "backup_sur_s3": infra_raw.get("backup_sur_s3", False),
    }

    # --- Confidentialité (chapitre 1) ---
    classification_actuelle = client_raw.get("classification", "Client")
    classification_niveaux = [
        {
            "case": r"$\boxtimes$" if label == classification_actuelle else r"$\square$",
            "label": escape_latex(label),
            "description": escape_latex(description),
        }
        for label, description in CLASSIFICATION_LEVELS
    ]

    # --- Besoins fonctionnels (chapitre "Prérequis techniques") : liste des
    # FONCTIONS utilisateur activées (pas des composants d'infra) — reprend
    # catalogs/carbonio_functions.yaml, dans l'ordre du fichier, en ne
    # gardant que celles pertinentes pour ce client (toujours incluses,
    # conditionnées par un service coché, ou par un booléen d'infra —
    # ex. "sauvegarde" conditionnée par infra.backups).
    services_cfg = client_config.get("services", {})
    infra_cfg = client_config.get("infra", {})
    perimetre_items = []
    for func in catalogs["carbonio_functions"].values():
        applicable = (
            func.get("always")
            or services_cfg.get(func.get("service_key"), False)
            or infra_cfg.get(func.get("infra_key"), False)
        )
        if applicable:
            perimetre_items.append(
                escape_latex(func["label"]) + r" --- " + escape_latex(func["description"].strip())
            )

    # --- Parties prenantes : côté client (chapitre 2) ---
    adresse_lines = client_raw.get("adresse") or []
    adresse_display = r"\\".join(escape_latex(line) for line in adresse_lines) if adresse_lines else None
    contacts = [
        {
            "nom": escape_latex(c.get("nom", "")),
            "role": escape_latex(c.get("role", "")),
            "email": escape_latex(c.get("email", "")),
            "telephone": escape_latex(c.get("telephone", "")),
        }
        for c in client_raw.get("contacts", [])
    ]
    client = {
        "name": escape_latex(client_raw.get("name", "[à préciser]")),
        "classification": escape_latex(classification_actuelle),
        "logo_file": None,  # résolu dans main() une fois le logo copié dans generation/
        "description": value_or_placeholder(client_raw.get("description"), "Description du client à compléter"),
        "site_web": value_or_placeholder(client_raw.get("site_web"), "Site web à préciser"),
        "adresse": adresse_display or r"\placeholder{Adresse à préciser}",
        "contacts": contacts,
    }

    # --- Parties prenantes : côté prestataire (chapitre 2) ---
    # Les informations de commercial/auteur/chef de projet sont désormais
    # recopiées EN CLAIR dans la config client (voir generate_sizing.py) —
    # plus de référence par id à résoudre ici.
    def escaped_person(raw: dict) -> dict:
        return {
            "nom": escape_latex(raw.get("nom", "[à préciser]")),
            "role": escape_latex(raw.get("role", "")),
        }

    commercial = escaped_person(commercial_raw)
    auteur = escaped_person(auteur_raw)

    # Table des contacts Zextras : dédupliquée (une même personne ne doit
    # apparaître qu'une fois même si elle cumule plusieurs fonctions sur
    # le projet), et n'affiche QUE son titre (pas de fonction projet /
    # "Rédacteur du document" etc., sur demande).
    zextras_contacts = []
    seen_emails = set()
    for person_raw in (commercial_raw, auteur_raw, chef_projet_raw):
        nom = person_raw.get("nom")
        if not nom:
            continue
        dedup_key = person_raw.get("email") or nom
        if dedup_key in seen_emails:
            continue
        seen_emails.add(dedup_key)
        zextras_contacts.append({
            "nom": escape_latex(nom),
            "role": escape_latex(person_raw.get("role", "")),
            "email": escape_latex(person_raw.get("email", "")),
            "telephone": escape_latex(person_raw.get("telephone", "")),
        })

    # --- Planning de migration (Gantt) ---
    gantt_cfg = client_config.get("gantt", {})
    gantt_ctx = {"active": False}
    if prestation["migration_included"] and gantt_cfg.get("date_debut_estimee") and gantt_cfg.get("nombre_bascules"):
        raw_tasks = catalogs["migration_gantt"]
        ics_path = gantt_cfg.get("jours_feries_ics")
        if ics_path and not Path(ics_path).is_absolute():
            ics_path = str(PROJECT_ROOT / ics_path)
        holidays = parse_ics_dates(ics_path)
        cal = WorkCalendar(gantt_cfg.get("jours_travailles", {}), holidays)
        date_debut = parse_date_fr(gantt_cfg["date_debut_estimee"])
        date_fin_estimee = parse_date_fr(gantt_cfg.get("date_fin_estimee"))
        date_premiere_bascule = parse_date_fr(gantt_cfg.get("date_premiere_bascule_souhaitee"))
        sched = compute_schedule(
            raw_tasks, cal, date_debut, gantt_cfg["nombre_bascules"],
            date_premiere_bascule, gantt_cfg.get("bascules_overrides", []),
        )
        resources = sorted({t.get(f"ressource_{i}") for t in sched["tasks"].values() for i in (1, 2) if t.get(f"ressource_{i}")})
        load = compute_resource_load(sched["tasks"], cal, resources)
        diagram_pages = build_pgfgantt(sched["tasks"], cal, date_debut, sched["date_fin_projet"])
        charge_tables = build_charge_table(load, cal, date_debut, sched["date_fin_projet"], gantt_cfg.get("seuils_charge", {}))
        warning = bool(date_fin_estimee and sched["date_fin_projet"] > date_fin_estimee)
        gantt_ctx = {
            "active": True,
            "date_debut_estimee_display": escape_latex(format_date_fr(date_debut)),
            "date_fin_estimee_display": escape_latex(format_date_fr(date_fin_estimee)) if date_fin_estimee else "",
            "date_fin_calculee_display": escape_latex(format_date_fr(sched["date_fin_projet"])),
            "warning": warning,
            "diagram_pages": diagram_pages,
            "charge_tables": charge_tables,
        }

    return {
        "client": client,
        "integrator": DEFAULT_INTEGRATOR,
        "commercial": commercial,
        "auteur": auteur,
        "revisions": revisions,
        "nodes": nodes,
        "totals": totals,
        "diagram_tikz_raw": diagram_tikz_raw,   # LaTeX déjà généré : jamais échappé
        "besoins": besoins,
        "classification_niveaux": classification_niveaux,
        "perimetre_items": perimetre_items,
        "zextras_contacts": zextras_contacts,
        "qualification": qualification,
        "qualif_nodes": qualif_nodes,
        "qualif_totals": qualif_totals,
        "diagram_tikz_raw_qualif": diagram_tikz_raw_qualif,
        "bilan_totals": bilan_totals,
        "storage_categories": storage_categories,
        "prestation": prestation,
        "migration": migration,
        "migration_raci": migration_raci,
        "pilotage_active": pilotage_active,
        "gantt": gantt_ctx,
        "document_scope": document_scope,
    }


def render_document(ctx: dict) -> str:
    env = build_env(TEMPLATES_DIR, PARTIALS_DIR)
    preamble = env.get_template("preamble.tex.j2").render(**ctx)
    cover = env.get_template("cover.tex.j2").render(**ctx)
    revisions = env.get_template("revisions.tex.j2").render(**ctx)
    intro_cadrage = env.get_template("intro_cadrage.tex.j2").render(**ctx)
    parties_prenantes_client = env.get_template("parties_prenantes_client.tex.j2").render(**ctx)
    prestataire = (TEMPLATES_DIR / "prestataire.tex").read_text(encoding="utf-8")  # statique, jamais rendu
    zextras_contacts = env.get_template("zextras_contacts.tex.j2").render(**ctx)
    carbonio_solution = (TEMPLATES_DIR / "carbonio_solution.tex").read_text(encoding="utf-8")  # statique
    prerequis = env.get_template("prerequis.tex.j2").render(**ctx)
    architecture = (env.get_template("architecture.tex.j2").render(**ctx)
                    if ctx["document_scope"]["schemas_architecture"] else "")
    qualification = (env.get_template("qualification.tex.j2").render(**ctx)
                      if ctx["qualification"]["active"] else "")
    migration_methodology = (env.get_template("migration_methodology.tex.j2").render(**ctx)
                              if ctx["migration"]["included"] and ctx["document_scope"]["methodologie_migration"] else "")
    methodologie_pilotage = (env.get_template("methodologie_pilotage.tex.j2").render(**ctx)
                              if ctx["pilotage_active"] and ctx["document_scope"]["methodologie_projet"] else "")
    gantt_migration = (env.get_template("gantt_migration.tex.j2").render(**ctx)
                        if ctx["gantt"]["active"] and ctx["document_scope"]["planning_migration"] else "")
    bilan_ressources = env.get_template("bilan_ressources.tex.j2").render(**ctx)

    # Pied de page (nom prestataire + pagination) activé seulement à partir
    # du chapitre 1 : rien sur la page de garde, l'historique des révisions
    # et le sommaire (même convention que le Générateur de DAT).
    footer_activation = (
        r"\renewcommand{\footrulewidth}{0.4pt}" + "\n"
        + r"\fancyfoot[L]{\small\color{graytxt}" + ctx["integrator"]["name"]
        + r" --- " + ctx["integrator"]["website"] + "}\n"
        + r"\fancyfoot[R]{\small\color{graytxt}Page \thepage/\pageref{LastPage}}"
    )

    return (
        preamble
        + "\n\n\\begin{document}\n\n"
        + cover + "\n\n\\clearpage\n\n"
        + revisions + "\n\n\\clearpage\n\n"
        + r"\tableofcontents" + "\n\n\\clearpage\n\n"
        + footer_activation + "\n\n"
        + intro_cadrage + "\n\n"
        + parties_prenantes_client + "\n\n"
        + prestataire + "\n\n"
        + zextras_contacts + "\n\n"
        + carbonio_solution + "\n\n"
        + prerequis + "\n\n"
        + architecture + "\n\n"
        + qualification + "\n\n"
        + bilan_ressources + "\n\n"
        + migration_methodology + "\n\n"
        + methodologie_pilotage + "\n\n"
        + gantt_migration + "\n\n"
        + "\\end{document}\n"
    )


DOCUMENT_SCOPE_EXTRAS = [
    ("schemas_architecture", "Les schémas d'architecture"),
    ("methodologie_migration", "La méthodologie de migration"),
    ("methodologie_projet", "La méthodologie projet"),
    ("planning_migration", "Le planning de migration"),
]


def ask_document_scope(non_interactive: bool) -> dict:
    """Document complet (tout ce qui s'applique au projet) ou partiel
    (uniquement le socle de base, plus les sections cochées parmi les 4
    extras). Ce choix n'est jamais écrit dans la config client : c'est
    une décision propre à CETTE génération, pas une propriété durable du
    projet — le même fichier peut ainsi servir à produire un document
    complet pour usage interne ET une version partielle pour le client."""
    if non_interactive:
        return {key: True for key, _ in DOCUMENT_SCOPE_EXTRAS}

    import questionary
    scope_choice = questionary.select(
        "Document complet ou partiel ?", choices=["Complet", "Partiel"]
    ).ask()
    if scope_choice == "Complet":
        return {key: True for key, _ in DOCUMENT_SCOPE_EXTRAS}

    selected = questionary.checkbox(
        "Au-delà du socle de base, quelles sections ajouter ?",
        choices=[questionary.Choice(title=label, value=key) for key, label in DOCUMENT_SCOPE_EXTRAS],
    ).ask() or []
    return {key: (key in selected) for key, _ in DOCUMENT_SCOPE_EXTRAS}


def main():
    parser = argparse.ArgumentParser(description="Génère le document de prérequis techniques (LaTeX/PDF)")
    parser.add_argument("--client", required=True, help="Chemin vers la config client (déjà dimensionnée)")
    parser.add_argument("--compile", action="store_true", help="Compile le PDF via latexmk (sinon : .tex seul)")
    parser.add_argument("--non-interactive", action="store_true",
                         help="Ne pose pas la question document complet/partiel : génère le document complet")
    args = parser.parse_args()

    client_config = load_client_config(args.client)
    catalogs = {
        "component_labels": load_yaml(CATALOGS_DIR / "component_labels.yaml"),
        "component_descriptions": load_yaml(CATALOGS_DIR / "component_descriptions.yaml"),
        "carbonio_functions": load_yaml(CATALOGS_DIR / "carbonio_functions.yaml"),
        "sizing_rules": load_yaml(CATALOGS_DIR / "sizing_rules.yaml"),
        "migration_raci": load_yaml(CATALOGS_DIR / "migration_raci.yaml"),
        "migration_gantt": load_yaml(CATALOGS_DIR / "migration_gantt.yaml"),
    }

    if "nodes" not in client_config:
        print("Erreur : cette config client ne contient pas de 'nodes:'.")
        print("Lancez d'abord generate_sizing.py --client ... pour calculer le dimensionnement.")
        sys.exit(1)

    document_scope = ask_document_scope(args.non_interactive)

    ctx = build_context(client_config, catalogs, document_scope)

    client_name = get_client(client_config).get("name", "client")
    client_dir = BUILD_DIR / slugify(client_name)
    generation_dir = client_dir / "generation"
    generation_dir.mkdir(parents=True, exist_ok=True)

    # Logos copiés dans generation/ (chemins relatifs depuis le .tex,
    # même convention que le Générateur de DAT).
    shutil.copy(TEMPLATES_DIR / "assets" / "logo_zextras_services.png", generation_dir / "integrator_logo.png")
    ctx["integrator"]["logo_file"] = "integrator_logo.png"
    client_logo = get_client(client_config).get("logo")
    if client_logo:
        client_logo_src = Path(args.client).resolve().parent / client_logo
        if client_logo_src.exists():
            shutil.copy(client_logo_src, generation_dir / "client_logo.png")
            ctx["client"]["logo_file"] = "client_logo.png"
        else:
            print(f"Avertissement : logo client introuvable ({client_logo_src}), page de garde sans logo.")

    tex_filename = f"Prerequis_{slugify(client_name)}.tex"
    tex_path = generation_dir / tex_filename
    tex_path.write_text(render_document(ctx), encoding="utf-8")
    print(f"Fichier LaTeX écrit : {tex_path}")

    if args.compile:
        if shutil.which("latexmk") is None:
            print("Erreur : 'latexmk' n'est pas installé (ou pas dans le PATH).")
            print("Sur Debian/Ubuntu, ce paquet n'est pas toujours installé automatiquement")
            print("avec texlive-latex-recommended — installez-le explicitement :")
            print("  sudo apt-get install latexmk")
            print("Si le problème persiste après installation, vérifiez avec : which latexmk")
            print(f"Le fichier .tex a bien été généré : {tex_path}")
            print("Vous pouvez le compiler manuellement une fois latexmk installé.")
            sys.exit(1)
        result = subprocess.run(
            ["latexmk", "-xelatex", "-interaction=nonstopmode", tex_filename],
            cwd=generation_dir, capture_output=True, text=True,
        )
        if result.returncode != 0:
            print("Erreur de compilation LaTeX :")
            print(result.stdout[-4000:])
            print(result.stderr[-2000:])
            sys.exit(1)
        pdf_name = tex_filename.replace(".tex", ".pdf")
        shutil.copy(generation_dir / pdf_name, client_dir / pdf_name)
        print(f"PDF généré : {client_dir / pdf_name}")


if __name__ == "__main__":
    main()
