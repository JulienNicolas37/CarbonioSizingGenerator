"""
gantt_builder.py — Construit le LaTeX (pgfgantt) du planning de migration
et la table de charge par ressource, à partir du planning déjà calculé
par gantt_engine.py. Aucune dépendance Jinja : produit directement des
chaînes LaTeX prêtes à être injectées telles quelles dans un template
(comme tikz_builder.py pour le schéma d'architecture).
"""
from datetime import timedelta

from gantt_engine import format_date_fr

WEEKDAY_ABBR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

CONDITION_COLORS = {
    "toujours": "condToujours",
    "migration": "condMigration",
    "build": "condBuild",
}
DEFAULT_BAR_COLOR = "accent"


def _escape(text: str) -> str:
    repl = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
            "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}"}
    return "".join(repl.get(c, c) for c in str(text))


def _bar_color(task: dict) -> str:
    if task.get("couleur"):
        return None  # traité à part (couleur hexadécimale directe, voir usage)
    cond = (task.get("condition") or "").strip().lower()
    return CONDITION_COLORS.get(cond, DEFAULT_BAR_COLOR)


def build_day_index(calendar, date_debut, date_fin) -> dict:
    """Associe à chaque jour travaillé entre date_debut et date_fin un
    index séquentiel 1..N (les jours non travaillés n'ont pas de colonne :
    le planning n'affiche pas de trou visuel pour les week-ends/fériés)."""
    days = calendar.working_days_between(date_debut, date_fin)
    return {d: i + 1 for i, d in enumerate(days)}


def build_pgfgantt(tasks: dict, calendar, date_debut_projet, date_fin_projet, max_rows_per_page: int = 34) -> list:
    """Construit le diagramme pgfgantt, découpé en plusieurs pages si le
    nombre de lignes dépasse ce qui tient sur une page. NB (vérifié
    empiriquement) : dans ce document, l'espace utile disponible à
    l'intérieur de \\begin{landscape} est d'environ 16,4 cm à la fois en
    largeur ET en hauteur (\\textwidth == \\textheight dans ce contexte
    précis, pas un simple échange des deux comme on pourrait s'y
    attendre) — d'où le calcul de x_unit ci-dessous et le
    max_rows_per_page inchangé. Retourne une LISTE de fragments LaTeX,
    un par page."""
    AVAILABLE_CM = 14.5  # 16,4 cm avec marge de sécurité
    day_index = build_day_index(calendar, date_debut_projet, date_fin_projet)
    total_days = max(day_index.values()) if day_index else 1
    x_unit_cm = min(0.5, max(0.1, AVAILABLE_CM / total_days))

    title_cells = []
    for d, idx in sorted(day_index.items(), key=lambda kv: kv[1]):
        label = r"\rotatebox{90}{\tiny " + d.strftime("%d/%m") + "}" if d.weekday() == 0 else ""
        title_cells.append(f'"{label}"')
    title_row = r"\gantttitlelist{" + ",".join(title_cells) + "}{1}"

    ordered_ids = sorted(tasks.keys(), key=lambda tid: tasks[tid]["start"])
    groups = []
    seen = set()
    for tid in ordered_ids:
        t = tasks[tid]
        key = (t["phase"], t.get("lot"))
        if key not in seen:
            seen.add(key)
            groups.append(key)

    custom_colors = "\n".join(
        r"\definecolor{customcolor%s}{HTML}{%s}" % (tid.replace("_", ""), t["couleur"])
        for tid, t in tasks.items() if t.get("couleur")
    )

    lots_present = sorted({t["lot"] for t in tasks.values() if t.get("lot")})
    suppressed_targets = set()
    for lot in lots_present:
        if lot == 1:
            continue
        lot_ids = [tid for tid, t in tasks.items() if t.get("lot") == lot]
        group_ids = set(lot_ids)
        for tid in lot_ids:
            if tasks[tid]["demarre_apres"] not in group_ids:
                suppressed_targets.add(tid)

    # --- Découpage en pages, par groupes (phase, lot) complets ---
    pages_groups = []
    current_page, current_rows = [], 0
    for phase, lot in groups:
        group_task_ids = [tid for tid in ordered_ids if tasks[tid]["phase"] == phase and tasks[tid].get("lot") == lot]
        rows_needed = len(group_task_ids) + (1 if len(group_task_ids) > 1 else 0)
        if current_rows + rows_needed > max_rows_per_page and current_page:
            pages_groups.append(current_page)
            current_page, current_rows = [], 0
        current_page.append((phase, lot, group_task_ids))
        current_rows += rows_needed
    if current_page:
        pages_groups.append(current_page)

    page_fragments = []
    for page_groups in pages_groups:
        lines = []
        page_task_ids = set()
        for phase, lot, group_task_ids in page_groups:
            label = phase if lot is None else f"{phase} (lot {lot})"
            starts = [day_index.get(tasks[tid]["start"], 1) for tid in group_task_ids]
            ends = [day_index.get(tasks[tid]["end"], 1) for tid in group_task_ids]
            multi = len(group_task_ids) > 1
            if multi:
                lines.append(r"\ganttgroup{%s}{%d}{%d} \\" % (_escape(label), min(starts), max(ends)))
            for tid in group_task_ids:
                page_task_ids.add(tid)
                t = tasks[tid]
                name = f"t{tid}"
                start_idx = day_index.get(t["start"], 1)
                end_idx = day_index.get(t["end"], 1)
                display_label = _escape(t["tache"]) if multi else f"{_escape(label)} --- {_escape(t['tache'])}"
                if t.get("couleur"):
                    style = f"fill=customcolor{tid.replace('_', '')}"
                else:
                    style = f"fill={_bar_color(t)}"
                if t.get("jalon"):
                    lines.append(r"\ganttmilestone[name=%s, milestone/.append style={%s}]{%s}{%d} \\"
                                  % (name, style, display_label, start_idx))
                else:
                    lines.append(r"\ganttbar[name=%s, bar/.append style={%s}]{%s}{%d}{%d} \\"
                                  % (name, style, display_label, start_idx, end_idx))

        link_lines = []
        for tid in page_task_ids:
            pred = tasks[tid].get("demarre_apres")
            if pred and pred in page_task_ids and tid not in suppressed_targets:
                link_lines.append(r"\ganttlink{t%s}{t%s}" % (pred, tid))

        body = "\n".join(lines)
        links = "\n".join(link_lines)
        page_fragments.append(f"""
{custom_colors}
\\ganttset{{
    group label font=\\bfseries\\footnotesize\\color{{primary}},
    bar label font=\\scriptsize,
    milestone label font=\\bfseries\\scriptsize,
    bar height=0.45,
    group height=0.45,
    title height=4,
    link/.style={{-{{Stealth[length=5pt]}}, thick, draw=gray}},
}}
\\begin{{ganttchart}}[hgrid, vgrid, x unit={x_unit_cm}cm, y unit chart=0.42cm]{{1}}{{{total_days}}}
{title_row} \\\\
{body}

{links}
\\end{{ganttchart}}
""")
    return page_fragments


def build_charge_table(load: dict, calendar, date_debut_projet, date_fin_projet, seuils: dict,
                        max_days_per_page: int = 16) -> list:
    """Construit la/les table(s) de charge par ressource et par jour (1
    ligne par ressource). Découpée en plusieurs pages si le nombre de
    jours dépasse ce qui tient en largeur (vérifié empiriquement : la
    largeur utile disponible à l'intérieur de \\begin{landscape} dans ce
    document est d'environ 16,4 cm, pas la largeur de page physique)."""
    from gantt_engine import classify_charge

    days = calendar.working_days_between(date_debut_projet, date_fin_projet)
    color_map = {"vert": "chargeVert", "orange": "chargeOrange", "rouge": "chargeRouge"}

    chunks = [days[i:i + max_days_per_page] for i in range(0, len(days), max_days_per_page)] or [[]]

    tables = []
    for chunk in chunks:
        header_cells = " & ".join(r"\tblhead{%s}" % d.strftime("%d/%m") for d in chunk)
        col_spec = "|p{2.2cm}|" + "p{0.75cm}|" * len(chunk)

        rows = []
        for resource in load.keys():
            cells = []
            for d in chunk:
                pct = load[resource].get(d, 0)
                if pct == 0:
                    cells.append("---")
                    continue
                cls = classify_charge(pct, seuils)
                cells.append(r"\cellcolor{" + color_map[cls] + "}" + str(int(round(pct))) + r"\%")
            rows.append(_escape(resource) + " & " + " & ".join(cells) + r" \\" + "\n\\hline")

        tables.append(f"""
{{\\small
\\renewcommand{{\\arraystretch}}{{1.3}}
\\begin{{longtable}}{{{col_spec}}}
\\hline
\\rowcolor{{primary}}
\\tblhead{{Ressource}} & {header_cells} \\\\
\\hline
\\endhead
{chr(10).join(rows)}
\\end{{longtable}}
}}
""")
    return tables
