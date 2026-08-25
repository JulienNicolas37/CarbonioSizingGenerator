#!/usr/bin/env python3
"""
generate_pdf.py — Génère le document de récapitulatif (prérequis
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

from config_loader import load_client_config, load_yaml, CATALOGS_DIR, slugify
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


def lookup_person(team_directory: dict, person_id) -> dict:
    if person_id is None:
        return {"nom": "[à préciser]", "role": ""}
    entry = team_directory.get(person_id) or team_directory.get(str(person_id))
    if not entry:
        return {"nom": f"[id {person_id} inconnu dans team_directory.yaml]", "role": ""}
    return {"nom": entry["nom"], "role": entry.get("role", "")}


def build_context(client_config: dict, catalogs: dict) -> dict:
    team_directory = catalogs["team_directory"]
    component_labels = catalogs["component_labels"]

    client = client_config["client"]
    commercial = lookup_person(team_directory, client_config.get("infra", {}).get("commercial_id"))
    auteur = lookup_person(team_directory, client_config.get("infra", {}).get("auteur_id"))

    raw_revisions = client_config.get("revisions") or [
        {"version": "1.0", "date": "[à préciser]", "auteur_id": None, "commentaire": "Version générée automatiquement"}
    ]
    revisions = []
    for rev in raw_revisions:
        rev_auteur = lookup_person(team_directory, rev.get("auteur_id"))
        revisions.append({
            "version": escape_latex(rev.get("version", "")),
            "date": escape_latex(rev.get("date", "")),
            "auteur_nom": escape_latex(rev_auteur["nom"]),
            "commentaire": escape_latex(rev.get("commentaire", "")),
        })

    nodes = []
    totals = {"vcpu": 0, "ram_gb": 0, "disk_os_gb": 0, "disk_appli_gb": 0, "disk_store_gb": 0}
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

    return {
        "client": {
            "name": escape_latex(client["name"]),
            "classification": escape_latex(client.get("classification", "Public/Client")),
            "logo_file": client.get("logo_file"),
        },
        "integrator": DEFAULT_INTEGRATOR,
        "commercial": {"nom": escape_latex(commercial["nom"]), "role": escape_latex(commercial["role"])},
        "auteur": {"nom": escape_latex(auteur["nom"]), "role": escape_latex(auteur["role"])},
        "revisions": revisions,
        "nodes": nodes,
        "totals": totals,
        "diagram_tikz_raw": diagram_tikz_raw,   # LaTeX déjà généré : jamais échappé
    }


def render_document(ctx: dict) -> str:
    env = build_env(TEMPLATES_DIR, PARTIALS_DIR)
    preamble = env.get_template("preamble.tex.j2").render(**ctx)
    cover = env.get_template("cover.tex.j2").render(**ctx)
    revisions = env.get_template("revisions.tex.j2").render(**ctx)
    prestataire = (TEMPLATES_DIR / "prestataire.tex").read_text(encoding="utf-8")  # statique, jamais rendu
    prerequis = env.get_template("prerequis.tex.j2").render(**ctx)
    architecture = env.get_template("architecture.tex.j2").render(**ctx)

    return (
        preamble
        + "\n\n\\begin{document}\n\n"
        + cover + "\n\n"
        + revisions + "\n\n"
        + prestataire + "\n\n"
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
        "team_directory": load_yaml(CATALOGS_DIR / "team_directory.yaml"),
        "component_labels": load_yaml(CATALOGS_DIR / "component_labels.yaml"),
    }

    if "nodes" not in client_config:
        print("Erreur : cette config client ne contient pas de 'nodes:'.")
        print("Lancez d'abord generate_sizing.py --client ... pour calculer le dimensionnement.")
        sys.exit(1)

    ctx = build_context(client_config, catalogs)

    client_dir = BUILD_DIR / slugify(client_config["client"]["name"])
    generation_dir = client_dir / "generation"
    generation_dir.mkdir(parents=True, exist_ok=True)

    # Logos copiés dans generation/ (chemins relatifs depuis le .tex,
    # même convention que le Générateur de DAT).
    shutil.copy(TEMPLATES_DIR / "assets" / "logo_zextras_services.png", generation_dir / "integrator_logo.png")
    ctx["integrator"]["logo_file"] = "integrator_logo.png"
    if client_config["client"].get("logo"):
        client_logo_src = Path(args.client).resolve().parent / client_config["client"]["logo"]
        if client_logo_src.exists():
            shutil.copy(client_logo_src, generation_dir / "client_logo.png")
            ctx["client"]["logo_file"] = "client_logo.png"

    tex_filename = f"Prerequis_{slugify(client_config['client']['name'])}.tex"
    tex_path = generation_dir / tex_filename
    tex_path.write_text(render_document(ctx), encoding="utf-8")
    print(f"Fichier LaTeX écrit : {tex_path}")

    if args.compile:
        if shutil.which("latexmk") is None:
            print("Erreur : 'latexmk' n'est pas installé (ou pas dans le PATH).")
            print("Installation (Debian/Ubuntu) :")
            print("  apt-get install texlive-xetex texlive-latex-recommended \\")
            print("                   texlive-latex-extra texlive-lang-french \\")
            print("                   texlive-pictures fonts-open-sans")
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
