"""
config_loader.py — Chargement des catalogues programme et des configs client
pour le générateur de dimensionnement Carbonio.

Les catalogues (catalogs/*.yaml) sont des données PROGRAMME : jamais
dupliquées dans une config client, jamais modifiées par le moteur.
"""
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CATALOGS_DIR = PROJECT_ROOT / "catalogs"
CLIENTS_DIR = PROJECT_ROOT / "config" / "clients"


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_catalogs() -> dict:
    """Charge les 5 catalogues programme."""
    return {
        "vm_catalog": load_yaml(CATALOGS_DIR / "vm_catalog.yaml"),
        "component_descriptions": load_yaml(CATALOGS_DIR / "component_descriptions.yaml"),
        "service_catalog": load_yaml(CATALOGS_DIR / "service_catalog.yaml"),
        "sizing_rules": load_yaml(CATALOGS_DIR / "sizing_rules.yaml"),
        "team_directory": load_yaml(CATALOGS_DIR / "team_directory.yaml"),
    }


def resolve_client_path(path_str: str) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def load_client_config(path_str: str) -> dict:
    p = resolve_client_path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"Config client introuvable : {p}")
    return load_yaml(p)


def save_client_config(path_str: str, config: dict) -> None:
    p = resolve_client_path(path_str)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def slugify(name: str) -> str:
    """Nom de fichier client à partir du nom (utilisé faute de --name).
    Les accents sont retirés pour garder des noms de dossier/fichier ASCII
    (cohérent avec les chemins relatifs LaTeX et les règles .gitignore)."""
    import unicodedata
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    keep = "".join(c if c.isalnum() else "_" for c in normalized.strip())
    while "__" in keep:
        keep = keep.replace("__", "_")
    return keep.strip("_").lower()
