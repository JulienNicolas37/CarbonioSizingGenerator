"""
Construit dynamiquement un schéma TikZ (zones DMZ/LAN + nœuds) à partir
des zones/nœuds calculés par sizing_engine.py.

Repris tel quel du Générateur de DAT (même style visuel, mêmes couleurs).
Dans ce générateur de dimensionnement, appelé avec flows=[] et
network_equipment=[]/legend_entries=[] : uniquement les boîtes de zone et
les nœuds en grille, sans flux ni équipements réseau (schéma volontairement
plus simple qu'un DAT complet).
"""
import re

BOX_W = 3.6
GAP_X = 1.2
ROW_GAP = 2.9
EXT_GAP = 3.1
EQUIP_W = 2.4
EQUIP_GAP_X = 1.0
EQUIP_ROW_GAP = 2.6


def escape_latex(text):
    """Échappe les caractères spéciaux LaTeX dans une chaîne de données brutes
    (hostnames, IP, id de nœuds...). Ne PAS utiliser sur du texte déjà écrit
    en LaTeX (ex. champ `label` fourni tel quel par l'utilisateur).

    Insère aussi des points de césure autorisés (\\allowbreak) après chaque
    point et tiret : les hostnames/FQDN (ex. "mailstore01.exemple.local")
    n'ont sinon aucun point de rupture naturel et débordent des colonnes de
    tableau étroites."""
    if text is None:
        return ""
    text = str(text)
    replacements = {
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
    escaped = "".join(replacements.get(c, c) for c in text)
    escaped = escaped.replace(".", ".\\allowbreak{}").replace("-", "-\\allowbreak{}")
    return escaped


def safe_id(node_id):
    """Identifiant TikZ valide dérivé de l'id de nœud (alphanumérique only)."""
    return "nd_" + re.sub(r"[^A-Za-z0-9]", "_", str(node_id))


def _node_content(node):
    if node.get("label"):
        # Contenu fourni tel quel par la configuration (peut contenir du LaTeX,
        # ex. "\\\\" pour un saut de ligne) : on ne l'échappe pas.
        return node["label"]
    parts = [r"\textbf{" + escape_latex(node["id"]) + "}"]
    comps = node.get("components_display_diagram", node.get("components_display"))
    if comps:
        parts.append(r"{\scriptsize " + escape_latex(comps) + "}")
    if node.get("hostname"):
        parts.append(r"{\scriptsize " + escape_latex(node["hostname"]) + "}")
    return r"\\".join(parts)


def build_tikz(zones, nodes, flows, network_equipment=None, legend_entries=None):
    """
    zones, nodes, flows : voir le fichier de configuration client.
    network_equipment    : liste optionnelle de {id, label, type} (type in
                            internet/router/firewall/switch), dessinée en
                            chaîne horizontale au-dessus de toutes les zones.
    legend_entries        : liste optionnelle de (color_name, label) pour la
                            légende des catégories de flux effectivement
                            utilisées par ce client.

    Chaque zone peut contenir plus de nœuds qu'une seule rangée n'en
    accueille confortablement (ex. 5+ nœuds dans une unique zone LAN) : ils
    sont alors répartis en grille (plusieurs rangées) à l'intérieur de la
    même zone, alignés en colonnes. Le nombre de colonnes est contrôlé par
    l'attribut optionnel `max_cols` de la zone (3 par défaut).
    """
    network_equipment = network_equipment or []
    legend_entries = legend_entries or []

    nodes_by_zone = {}
    for n in nodes:
        nodes_by_zone.setdefault(n["zone"], []).append(n)

    positions = {}

    def place_row(row_nodes, y, box_w=BOX_W, gap_x=GAP_X):
        n = len(row_nodes)
        if n == 0:
            return
        total_w = n * box_w + (n - 1) * gap_x
        x0 = -total_w / 2 + box_w / 2
        for i, node in enumerate(row_nodes):
            x = x0 + i * (box_w + gap_x)
            positions[node["id"]] = (x, y)

    def place_columns(zone_nodes, y_top, box_w=BOX_W, gap_x=GAP_X, row_gap=1.9):
        """Place zone_nodes en colonnes groupées par « famille de rôle »,
        déduite du nom du nœud en retirant son suffixe numérique final
        (proxy01/proxy02 -> "proxy", mail01/02/03 -> "mail"...). Chaque
        famille devient une colonne ; l'ordre des colonnes suit l'ordre
        d'apparition dans la configuration. Retourne le y le plus bas
        atteint (pour positionner la zone suivante)."""
        groups = []
        index_by_prefix = {}
        for node in zone_nodes:
            prefix = re.sub(r"\d+$", "", node["id"]) or node["id"]
            if prefix not in index_by_prefix:
                index_by_prefix[prefix] = len(groups)
                groups.append((prefix, []))
            groups[index_by_prefix[prefix]][1].append(node)

        cols = len(groups)
        if cols == 0:
            return y_top
        total_w = cols * box_w + (cols - 1) * gap_x
        x0 = -total_w / 2 + box_w / 2
        lowest = y_top
        for col_idx, (prefix, members) in enumerate(groups):
            x = x0 + col_idx * (box_w + gap_x)
            for row_idx, node in enumerate(members):
                yy = y_top - row_idx * row_gap
                positions[node["id"]] = (x, yy)
                lowest = min(lowest, yy)
        return lowest, groups

    y = 0.0

    # --- Équipements réseau (Internet / routeur / pare-feu...) ---
    if network_equipment:
        place_row(network_equipment, y, box_w=EQUIP_W, gap_x=EQUIP_GAP_X)
        y -= EQUIP_ROW_GAP

    ext_zones = [z for z in zones if z.get("external")]
    normal_zones = [z for z in zones if not z.get("external")]

    for z in ext_zones:
        zn = nodes_by_zone.get(z["id"], [])
        if zn:
            place_row(zn, y)
            y -= EXT_GAP

    zone_role_groups = {}  # zone_id -> [(prefix, [nodes]), ...] pour les encadrés de sous-groupe
    for z in normal_zones:
        zn = nodes_by_zone.get(z["id"], [])
        if zn:
            bottom_y, groups = place_columns(zn, y)
            zone_role_groups[z["id"]] = groups
            y = bottom_y - ROW_GAP

    min_y = min((p[1] for p in positions.values()), default=0.0)

    out = []
    out.append(r"\begin{tikzpicture}[")
    out.append(r"  comp/.style={draw, rounded corners, fill=lightbg, text width=3.1cm, align=center, inner sep=0.18cm, font=\small},")
    out.append(r"  ext/.style={draw, rounded corners, fill=white, text width=3.4cm, align=center, inner sep=0.18cm, font=\small, dashed},")
    out.append(r"  equip/.style={draw=graytxt, rounded corners, fill=white, text=graytxt, text width=1.9cm, align=center, inner sep=0.14cm, font=\scriptsize},")
    out.append(r"  equipcloud/.style={draw=graytxt, ellipse, fill=white, text=graytxt, text width=1.7cm, align=center, inner sep=0.1cm, font=\scriptsize},")
    out.append(r"  zone/.style={draw, dashed, thick, color=graytxt, inner sep=0.55cm, rounded corners},")
    out.append(r"  colgroup/.style={draw=accent, densely dotted, thin, rounded corners, inner sep=0.22cm},")
    out.append(r"  flow/.style={-{Stealth[length=2.2mm]}, thick},")
    out.append(r"  eqlink/.style={-{Stealth[length=1.8mm]}, thin, color=graytxt},")
    out.append(r"]")

    # --- Nœuds d'équipement réseau ---
    for eq in network_equipment:
        x, yy = positions[eq["id"]]
        style = "equipcloud" if eq.get("type") == "internet" else "equip"
        label = eq.get("label") or eq["id"]
        out.append(f"\\node[{style}] ({safe_id(eq['id'])}) at ({x:.2f},{yy:.2f}) {{{escape_latex(label)}}};")
    for i in range(len(network_equipment) - 1):
        a, b = network_equipment[i]["id"], network_equipment[i + 1]["id"]
        out.append(f"\\draw[eqlink] ({safe_id(a)}.east) -- ({safe_id(b)}.west);")

    # --- Nœuds applicatifs ---
    for z in ext_zones + normal_zones:
        zn = nodes_by_zone.get(z["id"], [])
        style = "ext" if z.get("external") else "comp"
        for node in zn:
            x, yy = positions[node["id"]]
            content = _node_content(node)
            out.append(f"\\node[{style}] ({safe_id(node['id'])}) at ({x:.2f},{yy:.2f}) {{{content}}};")

    # --- Zones (fond) ---
    zone_boxes = []
    zone_titles = []
    for z in normal_zones:
        zn = nodes_by_zone.get(z["id"], [])
        if not zn:
            continue
        box_name = f"{safe_id(z['id'])}_box"
        fit_list = " ".join(f"({safe_id(n['id'])})" for n in zn)
        zone_boxes.append(f"  \\node[zone, fit={fit_list}] ({box_name}) {{}};")
        # Titre de zone inséré DANS le coin supérieur gauche de la boîte
        # (plutôt qu'un label flottant au-dessus, qui entrerait en collision
        # avec les flèches entrantes verticales).
        zone_titles.append(
            f"  \\node[anchor=north west, font=\\scriptsize\\bfseries, color=primary, inner sep=0pt] "
            f"at ([xshift=4pt,yshift=-3pt]{box_name}.north west) {{{escape_latex(z.get('short_label') or z['label'])}}};"
        )
    if zone_boxes:
        out.append(r"\begin{scope}[on background layer]")
        out.extend(zone_boxes)
        out.extend(zone_titles)
        for z in normal_zones:
            groups = zone_role_groups.get(z["id"], [])
            for prefix, members in groups:
                if len(members) < 2:
                    continue  # pas de cadre pour un groupe d'un seul nœud
                fit_list = " ".join(f"({safe_id(n['id'])})" for n in members)
                box_name = f"{safe_id(z['id'])}_{re.sub(r'[^A-Za-z0-9]', '_', prefix)}_grp"
                out.append(f"  \\node[colgroup, fit={fit_list}] ({box_name}) {{}};")
        out.append(r"\end{scope}")

    # --- Flux ---
    # Fusionne les flux qui partagent la même paire (origine, destination,
    # couleur) : cela évite de dessiner deux flèches/étiquettes superposées
    # lorsque plusieurs composants d'un même flux logique sont hébergés sur
    # un seul et même nœud (ex. Proxy + MTA sur le même serveur frontal).
    grouped_flows = []
    seen = {}
    for flow in flows:
        color_name = flow.get("color_name") or "accent"
        key = (flow["from"], flow["to"], bool(flow.get("curved")), color_name)
        if key in seen:
            existing = seen[key]
            if flow.get("label"):
                existing["_labels"].append(flow["label"])
        else:
            merged = dict(flow)
            merged["_labels"] = [flow["label"]] if flow.get("label") else []
            merged["color_name"] = color_name
            seen[key] = merged
            grouped_flows.append(merged)

    curve_index = 0
    for flow in grouped_flows:
        a, b = flow["from"], flow["to"]
        if a not in positions or b not in positions:
            continue
        sa, sb = safe_id(a), safe_id(b)
        xa, ya = positions[a]
        xb, yb = positions[b]
        label = " / ".join(flow["_labels"])
        label = escape_latex(label) if label else ""
        label_tex = f" {{{label}}}" if label else " {}"
        color_name = flow["color_name"]
        style = f"flow, color={color_name}"
        label_color = f", text={color_name}" if label else ""

        if flow.get("curved"):
            offset = -1.8 - 0.9 * curve_index
            curve_index += 1
            out.append(
                f"\\draw[{style}] ({sa}.west) .. controls +({offset:.2f},0) and +({offset:.2f},0) .. "
                f"node[left, font=\\scriptsize{label_color}, pos=0.5]{label_tex} ({sb}.west);"
            )
        elif abs(ya - yb) < 0.01:  # même ligne (même zone)
            if xa < xb:
                out.append(f"\\draw[{style}] ({sa}.east) -- node[above, font=\\scriptsize{label_color}]{label_tex} ({sb}.west);")
            else:
                out.append(f"\\draw[{style}] ({sa}.west) -- node[above, font=\\scriptsize{label_color}]{label_tex} ({sb}.east);")
        else:
            if abs(xa - xb) < 0.01:
                out.append(f"\\draw[{style}] ({sa}.south) -- node[right, font=\\scriptsize{label_color}, pos=0.3]{label_tex} ({sb}.north);")
            else:
                # Le label est placé du côté opposé à la direction du flux
                # (au-dessus si la cible est à gauche, en-dessous si à
                # droite) pour éviter que deux flux divergents depuis le
                # même nœud source ne voient leurs étiquettes se chevaucher.
                side = "above" if xb < xa else "below"
                out.append(
                    f"\\draw[{style}] ({sa}.south) -- "
                    f"node[sloped, {side}, font=\\scriptsize{label_color}, pos=0.3]{label_tex} ({sb}.north);"
                )

    # --- Légende des catégories de flux ---
    if legend_entries:
        legend_y = min_y - 2.4
        out.append(r"\begin{scope}")
        out.append(f"\\node[anchor=north west, font=\\scriptsize\\bfseries, color=graytxt] at (-6.0,{legend_y:.2f}) {{Légende des flux~:}};")
        entries_start_y = legend_y - 0.8
        for i, (color_name, label) in enumerate(legend_entries):
            ly = entries_start_y - i * 0.42
            out.append(f"\\fill[{color_name}] (-6.0,{ly:.2f}) rectangle ({-6.0 + 0.3:.2f},{ly + 0.3:.2f});")
            out.append(f"\\node[anchor=west, font=\\scriptsize, color=graytxt] at ({-6.0 + 0.5:.2f},{ly + 0.15:.2f}) {{{escape_latex(label)}}};")
        out.append(r"\end{scope}")

    out.append(r"\end{tikzpicture}")
    return "\n".join(out)
