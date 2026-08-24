"""
latex_utils.py — Échappement LaTeX et environnement Jinja2 (délimiteurs
custom \\BLOCK{}/\\VAR{}, pour ne jamais entrer en collision avec la
syntaxe LaTeX qui utilise déjà massivement les accolades).

Mêmes conventions que le Générateur de DAT :
  - escape_latex() systématique sur toute donnée utilisateur
  - champs explicitement suffixés _raw (ou déjà du LaTeX généré, comme le
    schéma TikZ) : jamais échappés, insérés tels quels
"""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

REPLACEMENTS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape_latex(text) -> str:
    if text is None:
        return ""
    text = str(text)
    return "".join(REPLACEMENTS.get(c, c) for c in text)


def build_env(templates_dir: Path, partials_dir: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader([str(templates_dir), str(partials_dir)]),
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\#{",
        comment_end_string="}",
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["escape_latex"] = escape_latex
    return env
