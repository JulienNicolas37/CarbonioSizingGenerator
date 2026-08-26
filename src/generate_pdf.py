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


def categorize_storage(totals: dict, backup_sur_s3: bool, storage_rules: dict) -> dict:
    """Regroupe les colonnes disque détaillées (chapitre "Prérequis
    techniques") en catégories de synthèse pour le "Bilan des besoins".
    La composition de chaque catégorie vient de sizing_rules.yaml
    (storage_categories) — modifiable sans toucher au code."""
    backup_field = storage_rules.get("backup_field", "disk_backup_gb")
    backup_category = (storage_rules.get("backup_category_if_s3") if backup_sur_s3
                        else storage_rules.get("backup_category_if_not_s3"))
    result = {}
    for cat_name, cat_def in storage_rules.get("categories", {}).items():
        total = sum(totals.get(f, 0) for f in cat_def.get("fields", []))
        if cat_name == backup_category:
            total += totals.get(backup_field, 0)
        result[cat_name] = total
    return result


def build_context(client_config: dict, catalogs: dict) -> dict:
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
    storage_rules = catalogs["sizing_rules"]["storage_categories"]
    storage_categories = {
        "production": categorize_storage(totals, backup_sur_s3, storage_rules),
        "qualification": categorize_storage(qualif_totals, False, storage_rules),  # jamais de backup en qualif
        "bilan": categorize_storage(bilan_totals, backup_sur_s3, storage_rules),
    }

    infra_resolved = client_config.get("infra_resolved", {})
    qualification = {
        "active": qualification_active,
        "mode": infra_resolved.get("qualification_mode") or "minimal",
    }

    # --- Récapitulatif des besoins exprimés (chapitre "Prérequis techniques") ---
    active_services = [SERVICE_DISPLAY_LABELS[s] for s, v in client_config.get("services", {}).items()
                        if v and s in SERVICE_DISPLAY_LABELS]
    services_display = "Messagerie, agenda et contacts (toujours inclus)"
    if active_services:
        services_display += ", " + ", ".join(active_services)
    infra_raw = client_config.get("infra", {})
    besoins = {
        "domaines": client_raw.get("domaines", "[à préciser]"),
        "comptes": client_raw.get("comptes", "[à préciser]"),
        "volumetrie_to": client_raw.get("volumetrie_to", "[à préciser]"),
        "stockage_objet": "Oui" if client_raw.get("stockage_objet") else "Non",
        "services_display": escape_latex(services_display),
        "hsm_active": infra_raw.get("hsm_active", False),
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
    # gardant que celles pertinentes pour ce client (toujours incluses, ou
    # conditionnées par un service coché).
    services_cfg = client_config.get("services", {})
    perimetre_items = []
    for func in catalogs["carbonio_functions"].values():
        if func.get("always") or services_cfg.get(func.get("service_key"), False):
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
        "telephone_urgence": value_or_placeholder(client_raw.get("telephone_urgence"), "Téléphone d'urgence à préciser"),
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
    architecture = env.get_template("architecture.tex.j2").render(**ctx)
    qualification = (env.get_template("qualification.tex.j2").render(**ctx)
                      if ctx["qualification"]["active"] else "")
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
        + "\\end{document}\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Génère le document de prérequis techniques (LaTeX/PDF)")
    parser.add_argument("--client", required=True, help="Chemin vers la config client (déjà dimensionnée)")
    parser.add_argument("--compile", action="store_true", help="Compile le PDF via latexmk (sinon : .tex seul)")
    args = parser.parse_args()

    client_config = load_client_config(args.client)
    catalogs = {
        "component_labels": load_yaml(CATALOGS_DIR / "component_labels.yaml"),
        "component_descriptions": load_yaml(CATALOGS_DIR / "component_descriptions.yaml"),
        "carbonio_functions": load_yaml(CATALOGS_DIR / "carbonio_functions.yaml"),
        "sizing_rules": load_yaml(CATALOGS_DIR / "sizing_rules.yaml"),
    }

    if "nodes" not in client_config:
        print("Erreur : cette config client ne contient pas de 'nodes:'.")
        print("Lancez d'abord generate_sizing.py --client ... pour calculer le dimensionnement.")
        sys.exit(1)

    ctx = build_context(client_config, catalogs)

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
