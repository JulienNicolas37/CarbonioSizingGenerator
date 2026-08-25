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

# Étiquette de fonction projet affichée dans la table des contacts Zextras
# (chapitre Parties prenantes), distincte du rôle/titre de la personne.
PROJECT_ROLE_LABELS = {
    "commercial": "Commercial en charge",
    "auteur": "Rédacteur du document",
    "chef_projet": "Chef de projet",
}


def value_or_placeholder(value, label: str) -> str:
    """Repli visible (jamais bloquant) : \\placeholder{...} en LaTeX brut
    si la donnée est absente, sinon la valeur échappée."""
    if value in (None, "", [], {}):
        return r"\placeholder{" + escape_latex(label) + "}"
    return escape_latex(value)


def build_context(client_config: dict, catalogs: dict) -> dict:
    component_labels = catalogs["component_labels"]
    component_descriptions = catalogs["component_descriptions"]

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

    nodes = []
    totals = {"vcpu": 0, "ram_gb": 0, "disk_os_gb": 0, "disk_appli_gb": 0, "disk_store_gb": 0}
    all_components_seen = []
    for n in client_config.get("nodes", []):
        sizing = n.get("sizing", {})
        components_display = ", ".join(
            component_labels.get(c, c) for c in n.get("components", [])
        )
        nodes.append({
            "id": escape_latex(n["id"]),
            "zone": escape_latex(n["zone"]),
            "components": n["components"],   # ids bruts, pour le diagramme
            "components_display": escape_latex(components_display),
            "components_display_diagram": components_display,  # utilisé tel quel par tikz_builder (police \scriptsize)
            "sizing": sizing,
        })
        for c in n.get("components", []):
            if c not in all_components_seen:
                all_components_seen.append(c)
        totals["vcpu"] += sizing.get("vcpu", 0)
        totals["ram_gb"] += sizing.get("ram_gb", 0)
        totals["disk_os_gb"] += sizing.get("disk_os_gb", 0)
        totals["disk_appli_gb"] += sizing.get("disk_appli_gb", 0)
        totals["disk_store_gb"] += sizing.get("disk_store_gb", 0)

    # tikz_builder échappe lui-même les ids/labels : on lui passe les valeurs
    # BRUTES (pas celles déjà échappées pour le tableau LaTeX), sinon double
    # échappement (ex. "proxy\_mta01" affiché tel quel).
    diagram_nodes = [
        {
            "id": n["id"],
            "zone": n["zone"],
            "components_display_diagram": ", ".join(component_labels.get(c, c) for c in n.get("components", [])),
        }
        for n in client_config.get("nodes", [])
    ]
    diagram_tikz_raw = build_tikz(
        zones=ZONES, nodes=diagram_nodes, flows=[], network_equipment=[], legend_entries=[],
    )

    # --- Récapitulatif des besoins exprimés (chapitre "Prérequis techniques") ---
    active_services = [SERVICE_DISPLAY_LABELS[s] for s, v in client_config.get("services", {}).items()
                        if v and s in SERVICE_DISPLAY_LABELS]
    services_display = "Messagerie, agenda et contacts (toujours inclus)"
    if active_services:
        services_display += ", " + ", ".join(active_services)
    besoins = {
        "domaines": client_raw.get("domaines", "[à préciser]"),
        "comptes": client_raw.get("comptes", "[à préciser]"),
        "volumetrie_to": client_raw.get("volumetrie_to", "[à préciser]"),
        "stockage_objet": "Oui" if client_raw.get("stockage_objet") else "Non",
        "services_display": escape_latex(services_display),
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

    # --- Périmètre du document (chapitre 1) : dérivé des composants
    # réellement présents dans les nœuds, dans l'ordre du catalogue
    # component_descriptions.yaml (ordre stable, pas l'ordre d'apparition).
    perimetre_items = [
        escape_latex(component_descriptions[comp_id])
        for comp_id in component_descriptions
        if comp_id in all_components_seen
    ]

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

    zextras_contacts = []
    for key, person_raw in (("commercial", commercial_raw), ("auteur", auteur_raw), ("chef_projet", chef_projet_raw)):
        if not person_raw.get("nom"):
            continue
        fonction = PROJECT_ROLE_LABELS[key]
        role_titre = person_raw.get("role", "")
        role_display = f"{fonction} --- {role_titre}" if role_titre else fonction
        zextras_contacts.append({
            "nom": escape_latex(person_raw["nom"]),
            "role": escape_latex(role_display),
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
