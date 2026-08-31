"""
gantt_engine.py — Calcul du planning de migration : calendrier de jours
travaillés (jours fériés exclus), expansion du groupe répétable de
bascule (#1 / #last), règle de calage des dates de bascule, et charge
par ressource et par jour.

Aucune dépendance LaTeX : entièrement testable en isolation.
"""
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

WEEKDAY_NAMES = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


# ---------------------------------------------------------------------
# Dates et calendrier de travail
# ---------------------------------------------------------------------

def parse_date_fr(s) -> Optional[date]:
    """'JJ/MM/AAAA' -> date, ou None si vide/invalide."""
    if not s:
        return None
    try:
        j, m, a = str(s).split("/")
        return date(int(a), int(m), int(j))
    except Exception:
        return None


def format_date_fr(d: Optional[date]) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def parse_ics_dates(ics_path: str) -> set:
    """Extrait les dates (DTSTART;VALUE=DATE:AAAAMMJJ) d'un fichier ICS
    simple (pas de récurrence, pas de fuseau horaire — suffisant pour un
    calendrier de jours fériés)."""
    dates = set()
    if not ics_path:
        return dates
    try:
        with open(ics_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return dates
    for m in re.finditer(r"DTSTART;VALUE=DATE:(\d{8})", content):
        d = m.group(1)
        dates.add(date(int(d[0:4]), int(d[4:6]), int(d[6:8])))
    return dates


class WorkCalendar:
    """Jours travaillés = jours de semaine cochés dans jours_travailles,
    moins les jours fériés du calendrier ICS."""

    def __init__(self, jours_travailles: dict, jours_feries: set):
        self.working_weekdays = {i for i, name in enumerate(WEEKDAY_NAMES) if jours_travailles.get(name, False)}
        self.holidays = jours_feries

    def is_working_day(self, d: date) -> bool:
        return d.weekday() in self.working_weekdays and d not in self.holidays

    def next_working_day(self, d: date) -> date:
        while not self.is_working_day(d):
            d += timedelta(days=1)
        return d

    def next_after(self, d: date) -> date:
        """Premier jour travaillé strictement après d."""
        return self.next_working_day(d + timedelta(days=1))

    def add_working_days(self, start: date, n: int) -> date:
        """Dernier jour d'une tâche de n jours travaillés démarrant à
        start (start doit déjà être un jour travaillé). n<=1 -> start."""
        if n is None or n <= 1:
            return start
        d = start
        remaining = n - 1
        while remaining > 0:
            d += timedelta(days=1)
            if self.is_working_day(d):
                remaining -= 1
        return d

    def snap_to_mon_tue_wed(self, d: date) -> date:
        """Avance d (jour travaillé) jusqu'au premier lundi/mardi/mercredi
        qui suit ou est égal à d."""
        d = self.next_working_day(d)
        while d.weekday() not in (0, 1, 2):
            d = self.next_working_day(d + timedelta(days=1))
        return d

    def working_days_between(self, start: date, end: date) -> list:
        days = []
        d = start
        while d <= end:
            if self.is_working_day(d):
                days.append(d)
            d += timedelta(days=1)
        return days


# ---------------------------------------------------------------------
# Expansion du groupe répétable (#1 / #last)
# ---------------------------------------------------------------------

def resolve_ref(ref, group_ids: set, nombre_bascules: int) -> Optional[str]:
    """Résout une référence demarre_apres brute (avec #1/#last/#N
    éventuel) en id concret d'une tâche déjà dépliée."""
    if ref is None or ref == "":
        return None
    ref = str(ref)
    if "#" in ref:
        base, marker = ref.split("#", 1)
        base = base.strip()
        if marker == "1":
            lot = 1
        elif marker == "last":
            lot = nombre_bascules
        else:
            lot = int(marker)
        return f"{base}_lot{lot}"
    return ref


def expand_tasks(raw_tasks: list, nombre_bascules: int) -> list:
    """Duplique les tâches marquées groupe_repetition en `nombre_bascules`
    occurrences (ids suffixés _lotN), réécrit les références internes
    (vers une autre tâche du même groupe -> même lot) et externes
    (#1/#last résolus via resolve_ref)."""
    group_ids = {str(t["id"]) for t in raw_tasks if t.get("groupe_repetition")}
    expanded = []
    for t in raw_tasks:
        tid = str(t["id"])
        if t.get("groupe_repetition"):
            for lot in range(1, nombre_bascules + 1):
                nt = dict(t)
                nt["id"] = f"{tid}_lot{lot}"
                nt["lot"] = lot
                da = t.get("demarre_apres")
                da = str(da) if da is not None else None
                if da is not None and da in group_ids:
                    nt["demarre_apres"] = f"{da}_lot{lot}"
                else:
                    nt["demarre_apres"] = resolve_ref(da, group_ids, nombre_bascules)
                expanded.append(nt)
        else:
            nt = dict(t)
            nt["id"] = tid
            nt["lot"] = None
            da = t.get("demarre_apres")
            nt["demarre_apres"] = resolve_ref(str(da) if da is not None else None, group_ids, nombre_bascules)
            expanded.append(nt)
    return expanded


# ---------------------------------------------------------------------
# Calcul du planning
# ---------------------------------------------------------------------

def compute_schedule(raw_tasks: list, calendar: WorkCalendar, date_debut_projet: date,
                      nombre_bascules: int, date_premiere_bascule_souhaitee: Optional[date],
                      bascules_overrides: list, bascule_phase_name: str = "Bascule") -> dict:
    """
    Calcule les dates de chaque tâche (dépliée). Retourne :
      {"tasks": {id: {..., "start": date, "end": date}}, "bascule_dates": {lot: date},
       "date_fin_projet": date}

    Règle de calage de la bascule (jour de cutover = 1ère tâche de la
    phase "Bascule" au sein du lot, PAS le début du groupe répétable
    entier — hypothèse retenue après échange) :
      - Lot 1 : fin des tâches dont dépend le groupe, ou date souhaitée
        si postérieure, puis avancé au premier lundi/mardi/mercredi.
      - Lot 2 : +14 jours calendaires par rapport au lot 1 (même jour de
        semaine, garanti par construction).
      - Lot N>=3 : +7 jours calendaires par rapport au lot N-1.
      - Surcharge manuelle (bascules_overrides) prioritaire sur tout le
        reste pour le(s) lot(s) concerné(s).
    """
    tasks = {str(t["id"]): dict(t) for t in expand_tasks(raw_tasks, nombre_bascules)}

    lots = sorted({t["lot"] for t in tasks.values() if t.get("lot")})
    lot_task_ids = {lot: [tid for tid, t in tasks.items() if t.get("lot") == lot] for lot in lots}

    def entry_task_of(lot):
        ids = set(lot_task_ids[lot])
        for tid in lot_task_ids[lot]:
            if tasks[tid]["demarre_apres"] not in ids:
                return tid
        return lot_task_ids[lot][0]

    def cutover_task_of(lot):
        candidates = [tid for tid in lot_task_ids[lot] if tasks[tid]["phase"] == bascule_phase_name]
        cand_ids = set(candidates)
        for tid in candidates:
            if tasks[tid]["demarre_apres"] not in cand_ids:
                return tid
        return candidates[0] if candidates else None

    entry_ids = {lot: entry_task_of(lot) for lot in lots}
    cutover_ids = {lot: cutover_task_of(lot) for lot in lots}

    schedule = {}

    def schedule_task(tid, start, end):
        schedule[tid] = (start, end)

    def end_of(tid):
        return schedule[tid][1]

    non_repeat_ids = [tid for tid, t in tasks.items() if t.get("lot") is None]

    def try_schedule_simple(tid):
        if tid in schedule:
            return True
        t = tasks[tid]
        pred = t["demarre_apres"]
        if pred is None:
            start = calendar.next_working_day(date_debut_projet)
        elif pred in schedule:
            pred_end = end_of(pred)
            start = pred_end if t["jalon"] else calendar.next_after(pred_end)
        else:
            return False
        end = start if t["jalon"] else calendar.add_working_days(start, t.get("duree_jours") or 1)
        schedule_task(tid, start, end)
        return True

    # 1. Tâches hors groupe : boucle à point fixe (celles qui dépendent du
    # groupe répétable échouent pour l'instant, rattrapées à l'étape 4).
    remaining = list(non_repeat_ids)
    progress = True
    while remaining and progress:
        progress = False
        still = []
        for tid in remaining:
            if try_schedule_simple(tid):
                progress = True
            else:
                still.append(tid)
        remaining = still

    # 2/3. Dates de bascule (cutover) par lot + déroulé de chaque lot
    def working_days_span(entry_id, cutover_id, lot):
        """Écart (en jours calendaires) entre le début de entry_id et le
        début de cutover_id, déroulé à blanc à partir d'une date de
        référence arbitraire (lundi)."""
        ref = date(2000, 1, 3)
        temp = {}

        def sched(tid, start):
            t = tasks[tid]
            temp[tid] = (start, start) if t["jalon"] else (start, calendar.add_working_days(start, t.get("duree_jours") or 1))

        sched(entry_id, ref)
        ids_in_lot = lot_task_ids[lot]
        remaining_ids = [tid for tid in ids_in_lot if tid != entry_id]
        progress2 = True
        while remaining_ids and progress2:
            progress2 = False
            still2 = []
            for tid in remaining_ids:
                pred = tasks[tid]["demarre_apres"]
                if pred in temp:
                    pend = temp[pred][1]
                    nstart = pend if tasks[tid]["jalon"] else calendar.next_after(pend)
                    sched(tid, nstart)
                    progress2 = True
                else:
                    still2.append(tid)
            remaining_ids = still2
        return (temp[cutover_id][0] - ref).days

    bascule_dates = {}
    for lot in lots:
        override = next((o.get("date") for o in (bascules_overrides or []) if o.get("lot") == lot), None)
        entry_id, cutover_id = entry_ids[lot], cutover_ids[lot]
        gap_days = working_days_span(entry_id, cutover_id, lot) if cutover_id else 0

        if override:
            cutover = parse_date_fr(override) if isinstance(override, str) else override
        elif lot == 1:
            pred = tasks[entry_id]["demarre_apres"]
            if pred and pred in schedule:
                earliest_entry = calendar.next_after(end_of(pred))
            else:
                earliest_entry = calendar.next_working_day(date_debut_projet)
            base_entry = date_premiere_bascule_souhaitee if (
                date_premiere_bascule_souhaitee and date_premiere_bascule_souhaitee >= earliest_entry
            ) else earliest_entry
            provisional_cutover = base_entry + timedelta(days=gap_days)
            cutover = calendar.snap_to_mon_tue_wed(provisional_cutover)
        elif lot == 2:
            cutover = bascule_dates[1] + timedelta(days=14)
        else:
            cutover = bascule_dates[lot - 1] + timedelta(days=7)

        bascule_dates[lot] = cutover
        entry_start = calendar.next_working_day(cutover - timedelta(days=gap_days))

        schedule_task(entry_id, entry_start,
                      entry_start if tasks[entry_id]["jalon"] else calendar.add_working_days(entry_start, tasks[entry_id].get("duree_jours") or 1))
        remaining_lot = [tid for tid in lot_task_ids[lot] if tid != entry_id]
        progress3 = True
        while remaining_lot and progress3:
            progress3 = False
            still3 = []
            for tid in remaining_lot:
                pred = tasks[tid]["demarre_apres"]
                if pred in schedule:
                    pred_end = end_of(pred)
                    start = pred_end if tasks[tid]["jalon"] else calendar.next_after(pred_end)
                    end = start if tasks[tid]["jalon"] else calendar.add_working_days(start, tasks[tid].get("duree_jours") or 1)
                    schedule_task(tid, start, end)
                    progress3 = True
                else:
                    still3.append(tid)
            remaining_lot = still3

    # 4. Rattrapage : tâches hors groupe dépendant du groupe répétable (17,18,19,20,21)
    remaining = [tid for tid in non_repeat_ids if tid not in schedule]
    progress = True
    while remaining and progress:
        progress = False
        still = []
        for tid in remaining:
            if try_schedule_simple(tid):
                progress = True
            else:
                still.append(tid)
        remaining = still

    date_fin_projet = max(end for _, end in schedule.values())

    for tid, (s, e) in schedule.items():
        tasks[tid]["start"] = s
        tasks[tid]["end"] = e

    return {"tasks": tasks, "bascule_dates": bascule_dates, "date_fin_projet": date_fin_projet}


# ---------------------------------------------------------------------
# Charge par ressource et par jour
# ---------------------------------------------------------------------

def compute_resource_load(tasks: dict, calendar: WorkCalendar, resources: list) -> dict:
    """Retourne {resource: {date: charge_pct_cumulee}} — les jalons ne
    comptent jamais (ni durée ni charge)."""
    load = {r: {} for r in resources}
    for t in tasks.values():
        if t.get("jalon") or "start" not in t:
            continue
        days = calendar.working_days_between(t["start"], t["end"])
        for slot in (1, 2):
            res = t.get(f"ressource_{slot}")
            pct = t.get(f"charge_ressource_{slot}_pct")
            if not res or not pct:
                continue
            for d in days:
                load[res][d] = load[res].get(d, 0) + pct
    return load


def classify_charge(pct: float, seuils: dict) -> str:
    if pct <= seuils.get("vert_max", 80):
        return "vert"
    if pct <= seuils.get("orange_max", 100):
        return "orange"
    return "rouge"
