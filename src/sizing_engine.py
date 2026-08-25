"""
sizing_engine.py — Moteur de calcul du dimensionnement Carbonio.

Aucune dépendance LaTeX : entièrement testable en isolation. Prend une
config client + les catalogues programme, et produit :
  - des suggestions (palier HA proxy/MTA, nombre de mailstores)
  - la liste finale des nœuds une fois les choix de l'utilisateur
    appliqués (palier HA retenu, nombre de mailstores retenu, tous deux
    ajustables — voir sizing_rules.yaml, sections ha_scaling.selection et
    mailstore_scaling.selection)

Rien ne bloque jamais sur une donnée manquante : les valeurs par défaut
documentées dans sizing_rules.yaml s'appliquent (principe repris du
Générateur de DAT).
"""
from dataclasses import dataclass
from typing import Optional
import math

# Mapping service coché (config client, clé "services") -> id composant du
# vm_catalog. Tenu ici plutôt que dans catalogs/ car c'est un mapping de
# CODE (comment le moteur interprète la config), distinct de
# service_catalog.yaml qui documente la même correspondance pour un
# lecteur humain / le futur DAT.
SERVICE_TO_COMPONENT = {
    "chat": "chat",
    "tache": "tasks",
    "files": "files",
    "edition_collaborative": "docs",
}

SERVICES_PATTERN = [
    ("services01", ["mesh", "directory_master"]),
    ("services02", ["mesh", "directory_replica"]),
    ("services03", ["mesh", "database"]),
]


@dataclass
class HaSuggestion:
    level: int
    groups: list
    reason: str


@dataclass
class MailstoreSuggestion:
    count: int
    reason: str


def suggest_ha_tier(comptes: int, imap: bool, sizing_rules: dict) -> HaSuggestion:
    """
    Retient le palier le plus élevé dont min_accounts <= comptes et dont
    les conditions 'requires' (le cas échéant) sont satisfaites. Retombe
    sur le palier qualifiant précédent sinon (ex. IMAP non activé mais
    plus de 20000 comptes -> reste au palier 2).
    """
    tiers = sizing_rules["ha_scaling"]["tiers"]
    chosen = tiers[0]
    for tier in tiers:
        if comptes < tier["min_accounts"]:
            continue
        requires = tier.get("requires", [])
        if "imap" in requires and not imap:
            continue
        chosen = tier
    reason = f"{comptes} comptes"
    if "imap" in chosen.get("requires", []):
        reason += ", IMAP direct activé"
    return HaSuggestion(level=chosen["level"], groups=chosen["groups"], reason=reason)


def suggest_mailstore_count(comptes: int, volumetrie_to: float, stockage_objet: bool,
                             hsm_active: bool, sizing_rules: dict) -> MailstoreSuggestion:
    rules = sizing_rules["mailstore_scaling"]
    by_accounts = math.ceil(comptes / rules["max_accounts_per_mailstore"]) if comptes > 0 else 1

    # La volumétrie n'est ignorée pour le NOMBRE de mailstores que si les
    # données sont effectivement déportées (Stockage Objet ET module HSM
    # actif) — sans HSM, tout reste sur le stockage primaire.
    if stockage_objet and hsm_active and rules.get("object_storage_ignores_volumetry", False):
        count = max(1, by_accounts)
        reason = f"{comptes} comptes (stockage Objet + HSM actifs : volumétrie non dimensionnante)"
    else:
        by_volume = (math.ceil(volumetrie_to / rules["max_block_data_to_per_mailstore"])
                     if volumetrie_to > 0 else 1)
        count = max(1, by_accounts, by_volume)
        reason = f"{comptes} comptes / {volumetrie_to} To en stockage block"

    return MailstoreSuggestion(count=count, reason=reason)


def needs_imap_question(comptes: int, sizing_rules: dict) -> bool:
    threshold = sizing_rules["ha_scaling"]["conditional_questions"]["imap"]["ask_when_accounts_gte"]
    return comptes >= threshold


def application_groups(services: dict, sizing_rules: dict) -> list:
    """Groupes Application (01/02...) à créer, selon les services cochés."""
    groups = sizing_rules["application_grouping"]
    result = []
    for group_id, group_def in groups.items():
        active_services = [s for s in group_def["services"] if services.get(s, False)]
        if active_services:
            components = [SERVICE_TO_COMPONENT[s] for s in active_services]
            result.append({"group": group_id, "components": components, "label": group_def["label"]})
    return result


def standalone_nodes_needed(services: dict, sizing_rules: dict) -> list:
    """Nœuds dédiés (ex. visio) à créer si le service correspondant est coché."""
    result = []
    for node_id, node_def in sizing_rules["standalone_nodes"].items():
        if services.get(node_id, False):
            result.append({"id": node_id, "components": node_def["components"], "zone": node_def["zone"]})
    return result


def _sizing_from_catalog(vm_catalog: dict, component_id: str) -> dict:
    specs = vm_catalog[component_id]
    sizing = {
        "vcpu": specs["vcpu"],
        "ram_gb": specs["ram_gb"],
        "disk_os_gb": specs["disk_os_gb"],
        "disk_appli_gb": specs["disk_appli_gb"],
    }
    if "disk_store_gb" in specs:
        sizing["disk_store_gb"] = specs["disk_store_gb"]
    return sizing


def compute_mailstore_sizing(vm_catalog: dict, sizing_rules: dict, mailstore_count: int,
                              volumetrie_to: float, stockage_objet: bool, hsm_active: bool,
                              retention_days: Optional[int], backups: bool) -> dict:
    """
    Dimensionnement disque d'un mailstore (identique pour tous les
    mailstores du client — volumétrie moyenne, pas de répartition
    différenciée) :
      - volumétrie moyenne par mailstore = volumétrie totale / nombre de
        mailstores, arrondie au demi-To supérieur ;
      - si Stockage Objet + HSM actifs : stockage primaire dimensionné
        pour la rétention demandée (200 Go pour 7 jours, mis à l'échelle
        linéairement — voir hypothèse documentée dans sizing_rules.yaml),
        le reste de la volumétrie moyenne part en secondaire (S3) ;
      - sinon : tout reste en primaire (= volumétrie moyenne) ;
      - si backups activés : 1,3x la taille cumulée primaire + secondaire.
    """
    base = vm_catalog["mailbox"]
    rules = sizing_rules["mailstore_scaling"]["disque_par_mailstore"]

    avg_to = volumetrie_to / mailstore_count if mailstore_count else volumetrie_to
    avg_to_rounded = math.ceil(avg_to * 2) / 2  # arrondi au demi-To supérieur
    avg_gb = avg_to_rounded * 1000

    secondary_gb = 0
    if stockage_objet and hsm_active:
        retention = retention_days or rules["hsm_reference_retention_days"]
        primary_gb = round(
            rules["hsm_primary_gb_reference"] * retention / rules["hsm_reference_retention_days"]
        )
        secondary_gb = max(0, round(avg_gb - primary_gb))
    else:
        primary_gb = round(avg_gb)

    sizing = {
        "vcpu": base["vcpu"],
        "ram_gb": base["ram_gb"],
        "disk_os_gb": base["disk_os_gb"],
        "disk_appli_gb": base["disk_appli_gb"],
        "disk_store_gb": primary_gb,
    }
    if secondary_gb:
        sizing["disk_secondaire_gb"] = secondary_gb
    if backups:
        sizing["disk_backup_gb"] = round(rules["backup_multiplier"] * (primary_gb + secondary_gb))

    return sizing


def build_nodes(client_config: dict, catalogs: dict,
                 ha_level_override: Optional[int] = None,
                 mailstore_count_override: Optional[int] = None) -> dict:
    """
    Assemble la liste finale des nœuds à partir de la config client et des
    choix retenus (palier HA, nombre de mailstores — auto ou forcés par
    l'utilisateur lors de la rétrospective).

    Retourne {"nodes": [...], "infra_resolved": {...}} — à injecter dans
    le YAML client sous les clés correspondantes.
    """
    sizing_rules = catalogs["sizing_rules"]
    vm_catalog = catalogs["vm_catalog"]

    client = client_config.get("parties_prenantes", {}).get("client", {})
    comptes = client.get("comptes", 0)
    volumetrie_to = client.get("volumetrie_to", 0)
    stockage_objet = client.get("stockage_objet", False)
    services = client_config.get("services", {})
    infra_in = client_config.get("infra", {})
    imap = infra_in.get("imap", True)
    hsm_active = infra_in.get("hsm_active", False)
    retention_days = infra_in.get("retention_days")
    backups = infra_in.get("backups", False)

    nodes = []
    node_counters = {}

    def add_group(base_id: str, zone: str, components: list, count: int):
        for _ in range(count):
            node_counters[base_id] = node_counters.get(base_id, 0) + 1
            idx = node_counters[base_id]
            node_id = f"{base_id}{idx:02d}" if count > 1 else base_id
            nodes.append({
                "id": node_id,
                "zone": zone,
                "components": components,
                "sizing": _sizing_from_catalog(vm_catalog, components[0]),
            })

    # --- Palier HA proxy/MTA ---
    ha_suggestion = suggest_ha_tier(comptes, imap, sizing_rules)
    ha_level = ha_level_override if ha_level_override is not None else ha_suggestion.level
    tier = next(t for t in sizing_rules["ha_scaling"]["tiers"] if t["level"] == ha_level)
    for group in tier["groups"]:
        base_id = group.get("id_prefix") or "_".join(group["components"])
        add_group(base_id, group["zone"], group["components"], group["count"])

    # --- Services (mesh + directory_master/replica + database) ---
    for node_id, components in SERVICES_PATTERN:
        nodes.append({
            "id": node_id,
            "zone": "LAN",
            "components": components,
            "sizing": _sizing_from_catalog(vm_catalog, components[-1]),
        })

    # --- Mailstores ---
    mailstore_suggestion = suggest_mailstore_count(comptes, volumetrie_to, stockage_objet, hsm_active, sizing_rules)
    mailstore_count = (mailstore_count_override if mailstore_count_override is not None
                       else mailstore_suggestion.count)
    mailstore_sizing = compute_mailstore_sizing(
        vm_catalog, sizing_rules, mailstore_count, volumetrie_to,
        stockage_objet, hsm_active, retention_days, backups,
    )
    for i in range(mailstore_count):
        nodes.append({
            "id": f"mailstore{i + 1:02d}",
            "zone": "LAN",
            "components": ["mailbox"],
            "sizing": dict(mailstore_sizing),
        })

    # --- Application01 / Application02 ---
    for i, app in enumerate(application_groups(services, sizing_rules), start=1):
        nodes.append({
            "id": f"application{i:02d}",
            "zone": "LAN",
            "components": app["components"],
            "label": app["label"],
            "sizing": _sizing_from_catalog(vm_catalog, app["components"][0]),
        })

    # --- Nœuds dédiés (visio) ---
    for node in standalone_nodes_needed(services, sizing_rules):
        nodes.append({
            "id": node["id"],
            "zone": node["zone"],
            "components": node["components"],
            "sizing": _sizing_from_catalog(vm_catalog, node["components"][0]),
        })

    # --- Usine de migration (optionnelle) ---
    if infra_in.get("migration_factory", False):
        rules = sizing_rules["optional_components"]["migration_factory"]
        nodes.append({
            "id": "migration_factory",
            "zone": rules["zone"],
            "components": ["migration_factory"],
            "temporary": True,
            "sizing": _sizing_from_catalog(vm_catalog, "migration_factory"),
        })

    return {
        "nodes": nodes,
        "infra_resolved": {
            "ha_tier": ha_level,
            "ha_tier_suggestion": ha_suggestion.level,
            "ha_tier_reason": ha_suggestion.reason,
            "mailstore_count": mailstore_count,
            "mailstore_count_suggestion": mailstore_suggestion.count,
            "mailstore_reason": mailstore_suggestion.reason,
        },
    }
