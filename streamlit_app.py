"""Planning Staff - Birdieland Réaumur"""

import streamlit as st
import datetime
from dataclasses import dataclass

APP_VERSION = "2.0.0"

st.set_page_config(page_title="Planning Staff - Birdieland", layout="wide")


# ── Authentification ──────────────────────────────────────────────────────

def check_auth():
    """Vérifie le login/mot de passe via st.secrets."""
    if st.session_state.get("authenticated"):
        return True

    st.markdown("### Connexion")
    login = st.text_input("Identifiant")
    password = st.text_input("Mot de passe", type="password")

    if st.button("Se connecter", type="primary"):
        expected_login = st.secrets["auth"]["login"]
        expected_password = st.secrets["auth"]["password"]
        if login == expected_login and password == expected_password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Identifiant ou mot de passe incorrect")

    st.caption(f"v{APP_VERSION}")
    return False

# ── Données staff ──────────────────────────────────────────────────────────

@dataclass
class Employee:
    name: str
    role: str
    contract_hours: float
    available_days: set  # 0=Lun, 1=Mar, ..., 6=Dim
    is_alternant: bool = False
    max_daily_hours: float = 10.0

STAFF = [
    Employee("Baptiste Le Moing", "Manager", 42, {0,1,2,3,4,5,6}),
    Employee("Joseph Watrinet", "Coach", 42, {0,1,2,3,4,5,6}),
    Employee("Alexandre Corchia", "", 35, {0,1,2,3,4,5,6}),
    Employee("Hippolyte Amy", "Alternant", 21, {0,1,2}, is_alternant=True, max_daily_hours=8.0),
    Employee("Maxime Bancquart", "", 21, {3,4,5}),
]

CDI_NAMES = {"Baptiste Le Moing", "Joseph Watrinet", "Alexandre Corchia"}

JOURS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

# ── Horaires d'ouverture (avec 15min buffer) ──────────────────────────────

# (staff_start_h, staff_start_m, staff_end_h, staff_end_m)
HORAIRES = {
    0: (9, 45, 22, 15),   # Lundi
    1: (9, 45, 23, 15),   # Mardi
    2: (9, 45, 23, 15),   # Mercredi
    3: (9, 45, 23, 15),   # Jeudi
    4: (9, 45, 23, 15),   # Vendredi
    5: (9, 45, 23, 15),   # Samedi
    6: (10, 45, 19, 15),  # Dimanche
}

# ── Rotation 3 semaines (jours off par CDI) ───────────────────────────────
# 0=Lun, 1=Mar, 2=Mer, 3=Jeu, 4=Ven, 5=Sam, 6=Dim

ROTATION = {
    1: {"Baptiste Le Moing": {5, 6}, "Joseph Watrinet": {1, 2}, "Alexandre Corchia": {3, 4}},
    2: {"Baptiste Le Moing": {3, 4}, "Joseph Watrinet": {5, 6}, "Alexandre Corchia": {1, 2}},
    3: {"Baptiste Le Moing": {0, 1}, "Joseph Watrinet": {3, 4}, "Alexandre Corchia": {5, 6}},
}

# Variante W3 : semaine avec réunion direction → Baptiste off Mar+Mer au lieu de Lun+Mar
ROTATION_MEETING_W3 = {"Baptiste Le Moing": {1, 2}, "Joseph Watrinet": {3, 4}, "Alexandre Corchia": {5, 6}}

# ── Réunion direction (1 lundi sur 2) ────────────────────────────────────
REUNION_REF_DATE = datetime.date(2026, 3, 2)  # Prochain lundi avec réunion


def is_meeting_week(monday_date):
    """True si ce lundi est une semaine avec réunion direction."""
    delta_days = (monday_date - REUNION_REF_DATE).days
    delta_weeks = delta_days // 7
    return delta_weeks % 2 == 0


# ── Alternance dimanche (1 CDI par semaine du cycle) ────────────────────
SUNDAY_ROTATION = {
    1: "Joseph Watrinet",      # Bap off Sam+Dim → Jos travaille Dim
    2: "Baptiste Le Moing",    # Jos off Sam+Dim → Bap travaille Dim
    3: "Baptiste Le Moing",    # Alex off Sam+Dim → Bap travaille Dim
}


def time_str(h, m):
    return f"{h}:{m:02d}"


def to_minutes(h, m):
    return h * 60 + m


def from_minutes(minutes):
    h, m = divmod(minutes, 60)
    return h, m


def hours_between(h1, m1, h2, m2):
    return (to_minutes(h2, m2) - to_minutes(h1, m1)) / 60


def make_shift(shift_type, start_h, start_m, end_h, end_m):
    hours = hours_between(start_h, start_m, end_h, end_m)
    return {
        'type': shift_type,
        'start': time_str(start_h, start_m),
        'end': time_str(end_h, end_m),
        'hours': round(hours * 4) / 4,
    }


def get_off_days(week_num, meeting_week=False):
    """Retourne les jours off pour une semaine donnée, avec gestion réunion."""
    if week_num == 3 and meeting_week:
        return ROTATION_MEETING_W3
    return ROTATION[week_num]


def assign_shifts(available, day, schedule, week_num):
    """Assigne matin/soir pour un jour Mon-Sam.

    Règles :
    - Alexandre → toujours soir
    - Baptiste → toujours matin
    - Joseph → flexible (matin par défaut, soir si nécessaire)
    - Part-timers → soir par défaut, matin si un CDI a transition soir→matin
    - Anti-transition : si quelqu'un a fait soir la veille, il ne peut pas faire matin
    - Minimum : 1 matin + 2 soir
    """
    morning_staff = []
    evening_staff = []

    for emp in available:
        # Vérifier si transition soir→matin interdite
        can_do_morning = True
        if day > 0:
            yesterday = schedule[emp.name][day - 1]
            if yesterday and yesterday.get('hours', 0) > 0 and yesterday['type'] == 'soir':
                # Vérifier repos : fin soir veille → début matin lendemain
                end_parts = yesterday['end'].split(':')
                if end_parts[0]:
                    end_min = int(end_parts[0]) * 60 + int(end_parts[1])
                    sh, sm = HORAIRES[day][:2]
                    start_min = to_minutes(sh, sm)
                    rest = 24 * 60 - end_min + start_min
                    if rest < 11 * 60:
                        can_do_morning = False

        # Assignation selon les règles
        if emp.name == "Alexandre Corchia":
            evening_staff.append(emp)
        elif emp.name == "Baptiste Le Moing":
            morning_staff.append(emp)
        elif emp.name == "Joseph Watrinet":
            if can_do_morning:
                # Joseph matin par défaut, sera déplacé soir si nécessaire
                morning_staff.append(emp)
            else:
                evening_staff.append(emp)
        elif emp.name in CDI_NAMES:
            # Autres CDIs (extras CDI éventuels)
            if can_do_morning:
                morning_staff.append(emp)
            else:
                evening_staff.append(emp)
        else:
            # Part-timers : soir par défaut, matin si nécessaire
            if can_do_morning:
                evening_staff.append(emp)  # soir par défaut
            else:
                evening_staff.append(emp)

    # Garantir au moins 2 soir pour la fermeture
    # Déplacer Joseph vers soir si nécessaire
    while len(evening_staff) < 2 and morning_staff:
        # Préférer déplacer Joseph (flexible), puis part-timers
        joseph = [e for e in morning_staff if e.name == "Joseph Watrinet"]
        non_baptiste = [e for e in morning_staff if e.name != "Baptiste Le Moing"]
        if joseph:
            evening_staff.append(joseph[0])
            morning_staff.remove(joseph[0])
        elif non_baptiste:
            evening_staff.append(non_baptiste[0])
            morning_staff.remove(non_baptiste[0])
        else:
            break

    # Si aucun matin et au moins 1 soir peut basculer
    if not morning_staff and len(evening_staff) > 2:
        # Chercher un part-timer qui peut faire matin
        for emp in list(evening_staff):
            if emp.name not in CDI_NAMES:
                # Vérifier la transition
                can_morning = True
                if day > 0:
                    yesterday = schedule[emp.name][day - 1]
                    if yesterday and yesterday.get('hours', 0) > 0 and yesterday['type'] == 'soir':
                        end_parts = yesterday['end'].split(':')
                        if end_parts[0]:
                            end_min = int(end_parts[0]) * 60 + int(end_parts[1])
                            sh, sm = HORAIRES[day][:2]
                            start_min = to_minutes(sh, sm)
                            rest = 24 * 60 - end_min + start_min
                            if rest < 11 * 60:
                                can_morning = False
                if can_morning:
                    morning_staff.append(emp)
                    evening_staff.remove(emp)
                    break

    return morning_staff, evening_staff


def generate_week(week_num, extras=None, meeting_week=False, vacation=None):
    """Génère le planning pour une semaine du cycle de rotation."""
    base_staff = [emp for emp in STAFF if emp.name != vacation] if vacation else list(STAFF)
    all_staff = base_staff + (extras or [])
    off_days = get_off_days(week_num, meeting_week)
    schedule = {emp.name: [None] * 7 for emp in all_staff}
    weekly_hours = {emp.name: 0.0 for emp in all_staff}

    for day in range(7):
        sh, sm, eh, em = HORAIRES[day]
        open_min = to_minutes(sh, sm)
        close_min = to_minutes(eh, em)

        # Qui est disponible ce jour ?
        available = []
        for emp in all_staff:
            if day not in emp.available_days:
                schedule[emp.name][day] = {'type': 'indispo', 'start': '', 'end': '', 'hours': 0}
                continue
            if emp.name in off_days and day in off_days[emp.name]:
                schedule[emp.name][day] = {'type': 'conge', 'start': '', 'end': '', 'hours': 0}
                continue
            available.append(emp)

        if not available:
            continue

        # ── Dimanche : 1 seul CDI en journée complète ──
        if day == 6:
            preferred = SUNDAY_ROTATION.get(week_num)
            available_names = {e.name for e in available}
            if preferred and preferred in available_names:
                chosen = next(e for e in available if e.name == preferred)
            else:
                # Fallback : premier CDI disponible
                fallback = [e for e in available if e.name in CDI_NAMES]
                chosen = fallback[0] if fallback else (available[0] if available else None)
            if chosen:
                h = min(hours_between(sh, sm, eh, em), chosen.max_daily_hours)
                schedule[chosen.name][day] = make_shift('journee', sh, sm, eh, em)
                schedule[chosen.name][day]['hours'] = round(h * 4) / 4
                weekly_hours[chosen.name] += schedule[chosen.name][day]['hours']
            # Marquer les autres comme congé dimanche
            for emp in available:
                if emp.name != (chosen.name if chosen else ''):
                    schedule[emp.name][day] = {'type': 'conge', 'start': '', 'end': '', 'hours': 0}
            continue

        # ── Jours Lun-Sam : assignation matin/soir ──
        morning_staff, evening_staff = assign_shifts(available, day, schedule, week_num)

        # Assigner les shifts matin (depuis l'ouverture)
        for emp in morning_staff:
            if emp.name in CDI_NAMES:
                target_h = emp.contract_hours / 5
                matin_h = min(max(target_h, 8.0), emp.max_daily_hours)
            else:
                matin_h = min(7.0, emp.max_daily_hours)
            matin_h = round(matin_h * 4) / 4
            end = open_min + int(matin_h * 60)
            mh, mm = from_minutes(end)
            schedule[emp.name][day] = make_shift('matin', sh, sm, mh, mm)
            weekly_hours[emp.name] += schedule[emp.name][day]['hours']

        # Assigner les shifts soir (jusqu'à la fermeture)
        for emp in evening_staff:
            if emp.name in CDI_NAMES:
                target_h = emp.contract_hours / 5
                soir_h = min(max(target_h, 8.0), emp.max_daily_hours)
            else:
                soir_h = min(7.0, emp.max_daily_hours)
            soir_h = round(soir_h * 4) / 4
            start = close_min - int(soir_h * 60)
            svh, svm = from_minutes(start)
            schedule[emp.name][day] = make_shift('soir', svh, svm, eh, em)
            weekly_hours[emp.name] += schedule[emp.name][day]['hours']

    # ── Respect du repos 11h entre jours ──
    schedule, weekly_hours = fix_rest_time(schedule, weekly_hours, all_staff)

    # ── Ajustement final des heures ──
    schedule, weekly_hours = adjust_hours(schedule, weekly_hours, all_staff)

    # ── Ajustement manuel semaine 3 : shift partiel dimanche Joseph ──
    if week_num == 3:
        schedule, weekly_hours = _override_week3(schedule, weekly_hours)

    return schedule, weekly_hours


def _override_week3(schedule, weekly_hours):
    """Semaine 3 : Joseph ne travaille que 4 jours (Lun-Mer+Sam ≈ 40h max).

    Compensation : shift partiel dimanche 14h15-19h15 (5h),
    puis réduire les heures des jours travaillés (-1h Lun/Mar/Mer).
    """
    name = "Joseph Watrinet"

    # Vérifier que Joseph ne travaille pas déjà dimanche
    dim_entry = schedule[name][6]
    if dim_entry and dim_entry.get('hours', 0) > 0:
        return schedule, weekly_hours

    # Ajouter shift dimanche 14h15-19h15 (5h)
    schedule[name][6] = make_shift('soir', 14, 15, 19, 15)
    weekly_hours[name] += schedule[name][6]['hours']

    # Compenser en retirant 1h sur Lun/Mar/Mer
    adjustments = [
        (0, 1.0),  # Lundi : -1h
        (1, 1.0),  # Mardi : -1h
        (2, 1.0),  # Mercredi : -1h
    ]

    for day, hours_to_remove in adjustments:
        entry = schedule[name][day]
        if not entry or entry['hours'] <= 0:
            continue

        if entry['type'] == 'soir':
            parts = entry['start'].split(':')
            old_start = int(parts[0]) * 60 + int(parts[1])
            new_start = old_start + int(hours_to_remove * 60)
            ns_h, ns_m = from_minutes(new_start)
            entry['start'] = time_str(ns_h, ns_m)
        elif entry['type'] == 'matin':
            parts = entry['end'].split(':')
            old_end = int(parts[0]) * 60 + int(parts[1])
            new_end = old_end - int(hours_to_remove * 60)
            ne_h, ne_m = from_minutes(new_end)
            entry['end'] = time_str(ne_h, ne_m)

        weekly_hours[name] -= hours_to_remove
        entry['hours'] -= hours_to_remove

    return schedule, weekly_hours


def fix_rest_time(schedule, weekly_hours, staff_list=None):
    """Garantit 11h de repos minimum entre 2 shifts consécutifs.

    Si le shift du lendemain est matin : raccourcir la fin (protège le début 9:45).
    Si le shift du lendemain est soir : retarder le début.
    """
    staff_list = staff_list or STAFF
    MIN_REST = 11 * 60  # en minutes

    for emp in staff_list:
        for d in range(6):
            today = schedule[emp.name][d]
            tomorrow = schedule[emp.name][d + 1]
            if not (today and today.get('hours', 0) > 0 and
                    tomorrow and tomorrow.get('hours', 0) > 0):
                continue

            end_parts = today['end'].split(':')
            start_parts = tomorrow['start'].split(':')
            if not end_parts[0] or not start_parts[0]:
                continue

            end_min = int(end_parts[0]) * 60 + int(end_parts[1])
            start_min = int(start_parts[0]) * 60 + int(start_parts[1])
            rest = 24 * 60 - end_min + start_min

            if rest >= MIN_REST:
                continue

            needed = MIN_REST - rest

            if tomorrow['type'] == 'matin':
                # Protéger le début 9:45 : raccourcir la fin du shift matin
                end_tomorrow = tomorrow['end'].split(':')
                end_tom_min = int(end_tomorrow[0]) * 60 + int(end_tomorrow[1])
                new_end = end_tom_min - needed
                ne_h, ne_m = from_minutes(new_end)
                new_hours = (new_end - start_min) / 60
                new_hours = round(new_hours * 4) / 4

                old_hours = tomorrow['hours']
                tomorrow['end'] = time_str(ne_h, ne_m)
                tomorrow['hours'] = new_hours
                weekly_hours[emp.name] += (new_hours - old_hours)
            else:
                # Shift soir ou journée : retarder le début
                new_start = start_min + needed
                ns_h, ns_m = from_minutes(new_start)

                end_tomorrow = tomorrow['end'].split(':')
                end_tom_min = int(end_tomorrow[0]) * 60 + int(end_tomorrow[1])
                new_hours = (end_tom_min - new_start) / 60
                new_hours = round(new_hours * 4) / 4

                old_hours = tomorrow['hours']
                tomorrow['start'] = time_str(ns_h, ns_m)
                tomorrow['hours'] = new_hours
                weekly_hours[emp.name] += (new_hours - old_hours)

    return schedule, weekly_hours


def adjust_hours(schedule, weekly_hours, staff_list=None):
    """Ajuste les shifts pour rapprocher les heures hebdo des contrats."""
    staff_list = staff_list or STAFF
    for emp in staff_list:
        target = emp.contract_hours
        if emp.contract_hours <= 21:
            continue

        current = weekly_hours[emp.name]
        diff = target - current

        if abs(diff) < 0.25:
            continue

        worked_days = [d for d in range(7) if schedule[emp.name][d]
                       and schedule[emp.name][d]['type'] in ('matin', 'soir', 'journee')]

        if not worked_days:
            continue

        # Répartir sur les jours non-dimanche (plus flexibles)
        adjustable = [d for d in worked_days if d != 6]
        if not adjustable:
            adjustable = worked_days

        per_day = diff / len(adjustable)

        for d in adjustable:
            entry = schedule[emp.name][d]
            new_hours = entry['hours'] + per_day
            new_hours = min(new_hours, emp.max_daily_hours)
            new_hours = max(new_hours, 5.0)
            new_hours = round(new_hours * 4) / 4

            sh, sm, eh, em = HORAIRES[d]

            if entry['type'] == 'soir':
                start = to_minutes(eh, em) - int(new_hours * 60)
                svh, svm = from_minutes(start)
                entry['start'] = time_str(svh, svm)
            elif entry['type'] == 'matin':
                end = to_minutes(sh, sm) + int(new_hours * 60)
                mh, mm = from_minutes(end)
                entry['end'] = time_str(mh, mm)

            actual_diff = new_hours - entry['hours']
            weekly_hours[emp.name] += actual_diff
            entry['hours'] = new_hours

    return schedule, weekly_hours


def check_labor_law(schedule, weekly_hours, staff_list=None):
    """Vérifie la conformité avec le droit du travail français."""
    staff_list = staff_list or STAFF
    warnings = []
    staffing_issues = []

    for emp in staff_list:
        # Max heures par jour
        for d in range(7):
            entry = schedule[emp.name][d]
            if entry and entry.get('hours', 0) > emp.max_daily_hours + 0.01:
                label = '8h alternant' if emp.is_alternant else '10h'
                warnings.append(
                    f"{emp.name} : {entry['hours']:.1f}h le {JOURS[d]} (max {label})"
                )

        # Max 48h/semaine
        total = weekly_hours[emp.name]
        if total > 48:
            warnings.append(f"{emp.name} : {total:.1f}h/semaine (max 48h)")

        # Max 6 jours consécutifs
        consecutive = 0
        max_consecutive = 0
        for d in range(7):
            entry = schedule[emp.name][d]
            if entry and entry.get('hours', 0) > 0:
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0
        if max_consecutive > 6:
            warnings.append(f"{emp.name} : {max_consecutive} jours consécutifs (max 6)")

        # Min 11h repos entre shifts
        for d in range(6):
            entry_today = schedule[emp.name][d]
            entry_tomorrow = schedule[emp.name][d + 1]
            if (entry_today and entry_today.get('hours', 0) > 0 and
                    entry_tomorrow and entry_tomorrow.get('hours', 0) > 0):
                end_parts = entry_today['end'].split(':')
                start_parts = entry_tomorrow['start'].split(':')
                if end_parts[0] and start_parts[0]:
                    end_min = int(end_parts[0]) * 60 + int(end_parts[1])
                    start_min = int(start_parts[0]) * 60 + int(start_parts[1])
                    rest = (24 * 60 - end_min + start_min) / 60
                    if rest < 11:
                        warnings.append(
                            f"{emp.name} : {rest:.1f}h de repos entre "
                            f"{JOURS[d]} et {JOURS[d+1]} (min 11h)"
                        )

    # Vérifier 2 jours de repos consécutifs (CDI uniquement)
    for emp in staff_list:
        if emp.name not in CDI_NAMES:
            continue
        off_days = [d for d in range(7) if not (schedule[emp.name][d]
                    and schedule[emp.name][d].get('hours', 0) > 0)]
        has_consecutive = any(
            off_days[i + 1] - off_days[i] == 1
            for i in range(len(off_days) - 1)
        )
        # Wrap-around : Dimanche(6) + Lundi(0) = consécutifs
        if not has_consecutive and 6 in off_days and 0 in off_days:
            has_consecutive = True
        if not has_consecutive and off_days:
            warnings.append(
                f"{emp.name} : pas de 2 jours de repos consécutifs "
                f"(off : {', '.join(JOURS[d] for d in off_days)})"
            )

    # Vérifier 2 personnes à la fermeture (Lun-Sam uniquement, pas dimanche)
    for d in range(7):
        if d == 6:  # Dimanche : pas de contrainte 2 personnes fermeture
            continue
        sh, sm, eh, em = HORAIRES[d]
        closing_time = time_str(eh, em)
        closers = []
        for emp in staff_list:
            entry = schedule[emp.name][d]
            if entry and entry.get('end') == closing_time and entry.get('hours', 0) > 0:
                closers.append(emp.name.split()[0])

        if len(closers) < 2:
            staffing_issues.append({
                'day': JOURS[d],
                'closers': closers,
                'count': len(closers),
            })

    return warnings, staffing_issues


# ── Export Connecteam ─────────────────────────────────────────────────────

def time_24_to_12(t):
    """Convertit '09:45' → '09:45am', '15:00' → '03:00pm', '23:15' → '11:15pm'."""
    parts = t.split(':')
    h, m = int(parts[0]), int(parts[1])
    if h == 0:
        return f"12:{m:02d}am"
    elif h < 12:
        return f"{h:02d}:{m:02d}am"
    elif h == 12:
        return f"12:{m:02d}pm"
    else:
        return f"{h - 12:02d}:{m:02d}pm"


SHIFT_TITLES = {'matin': 'Matin', 'soir': 'Soir', 'journee': 'Journée'}


def export_connecteam_csv(start_date, num_weeks, first_week_type, extras=None, vacation=None):
    """Génère un CSV Connecteam pour une plage de dates."""
    base_staff = [emp for emp in STAFF if emp.name != vacation] if vacation else list(STAFF)
    all_staff = base_staff + (extras or [])
    header = "Date,Start,End,Timezone,Unpaid break,Paid break,Shift title,Job,Sub item,Shift tags,Users,Address,Note,Number of users,Require Approval,Tasks"
    rows = [header]

    current_monday = start_date
    for week_offset in range(num_weeks):
        week_type = ((first_week_type - 1 + week_offset) % 3) + 1
        # Détection réunion automatique par date
        mw = is_meeting_week(current_monday) if week_type == 3 else False
        schedule, _ = generate_week(week_type, extras=extras, meeting_week=mw, vacation=vacation)

        for day in range(7):
            current_date = current_monday + datetime.timedelta(days=day)
            for emp in all_staff:
                entry = schedule[emp.name][day]
                if not entry or entry.get('hours', 0) == 0:
                    continue
                if entry['type'] in ('conge', 'indispo'):
                    continue

                date_str = current_date.strftime('%m/%d/%Y')
                start = time_24_to_12(entry['start'])
                end = time_24_to_12(entry['end'])
                title = SHIFT_TITLES.get(entry['type'], entry['type'])

                rows.append(
                    f"{date_str},{start},{end},,,,{title},,,,{emp.name},,,,,,"
                )

        current_monday += datetime.timedelta(weeks=1)

    return '\n'.join(rows)


# ── Interface Streamlit ────────────────────────────────────────────────────

def main():
    if not check_auth():
        return

    st.title("Planning Staff - Birdieland Réaumur")
    st.caption(f"v{APP_VERSION}")

    st.markdown(
        "**Horaires** : Lun 10h-22h | Mar-Sam 10h-23h | Dim 11h-19h "
        "*(staff : +15min avant/après)*"
    )

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        week_num = st.selectbox(
            "Semaine du cycle",
            [1, 2, 3],
            format_func=lambda w: f"Semaine {w}/3",
        )
    with col2:
        meeting_week = st.checkbox(
            "Réunion direction ce lundi",
            value=False,
            help="Cocher si Baptiste a sa réunion direction ce lundi (1 lundi sur 2). Impacte uniquement la Semaine 3.",
        )
        if meeting_week and week_num == 3:
            st.caption("Baptiste off Mar+Mer (travaille Lundi)")
        elif week_num == 3:
            st.caption("Baptiste off Lun+Mar")

    # ── Vacances ──
    with col3:
        vacation_options = ["Aucun"] + [emp.name for emp in STAFF]
        vacation_choice = st.selectbox(
            "Employé en vacances",
            vacation_options,
            help="Sélectionner un employé absent cette semaine. Le planning sera ajusté.",
        )

    # ── Extra ──
    extras = []
    with st.expander("Ajouter un extra"):
        ex_col1, ex_col2, ex_col3 = st.columns(3)
        with ex_col1:
            extra_name = st.text_input("Nom complet de l'extra")
        with ex_col2:
            extra_hours = st.number_input("Heures par jour", min_value=3.0, max_value=10.0, value=7.0, step=0.5)
        with ex_col3:
            jour_options = {j: i for i, j in enumerate(JOURS)}
            extra_days = st.multiselect("Jours disponibles", JOURS, default=[])

        if extra_name and extra_days:
            day_set = {jour_options[j] for j in extra_days}
            extras.append(Employee(
                extra_name, "Extra",
                extra_hours * len(extra_days),
                day_set,
            ))
            st.success(f"Extra ajouté : **{extra_name}** — {', '.join(extra_days)} ({extra_hours}h/jour)")

    # Filtrer le staff en vacances
    active_staff = [emp for emp in STAFF if emp.name != vacation_choice]
    all_staff = list(active_staff) + extras

    if vacation_choice != "Aucun":
        st.warning(f"**{vacation_choice}** est en vacances cette semaine. Planning ajusté.")

    # Afficher les congés
    off = get_off_days(week_num, meeting_week)
    off_text = " | ".join(
        f"**{name.split()[0]}** : {', '.join(JOURS[d] for d in sorted(days))}"
        for name, days in off.items()
        if name != vacation_choice
    )
    st.info(f"Congés : {off_text}")

    # Générer
    vacation = vacation_choice if vacation_choice != "Aucun" else None
    schedule, weekly_hours = generate_week(week_num, extras=extras, meeting_week=meeting_week, vacation=vacation)
    warnings, staffing_issues = check_labor_law(schedule, weekly_hours, all_staff)

    # ── Grille planning ──
    st.subheader("Planning de la semaine")
    html = build_schedule_html(schedule, weekly_hours, all_staff)
    st.markdown(html, unsafe_allow_html=True)

    # ── Couverture journalière ──
    st.subheader("Couverture journalière")
    coverage_html = build_coverage_html(schedule, all_staff)
    st.markdown(coverage_html, unsafe_allow_html=True)

    # ── Récap heures ──
    st.subheader("Heures par personne")
    import pandas as pd

    rows = []
    for emp in all_staff:
        total = weekly_hours[emp.name]
        target = emp.contract_hours
        ecart = total - target
        days_worked = sum(
            1 for d in range(7)
            if schedule[emp.name][d] and schedule[emp.name][d].get('hours', 0) > 0
        )
        rows.append({
            'Nom': emp.name,
            'Rôle': emp.role,
            'Contrat': f"{target:.0f}h",
            'Planifié': f"{total:.1f}h",
            'Ecart': f"{ecart:+.1f}h",
            'Jours': days_worked,
        })

    df = pd.DataFrame(rows)

    def color_ecart(val):
        try:
            v = float(val.replace('h', '').replace('+', ''))
            if abs(v) <= 0.5:
                return 'color: green; font-weight: bold'
            return 'color: orange; font-weight: bold'
        except (ValueError, AttributeError):
            return ''

    styled = df.style.map(color_ecart, subset=['Ecart'])
    st.dataframe(styled, hide_index=True, width=700)

    # ── Alertes ──
    if staffing_issues:
        st.subheader("Sous-effectif fermeture")
        for issue in staffing_issues:
            closers = ', '.join(issue['closers']) if issue['closers'] else 'personne'
            st.error(
                f"**{issue['day']}** : {issue['count']} personne(s) a la fermeture "
                f"(min 2). Présent(s) : {closers}. "
                f"Effectif insuffisant — envisager un renfort."
            )

    if warnings:
        st.subheader("Alertes droit du travail")
        for w in warnings:
            st.warning(w)

    if not warnings and not staffing_issues:
        st.success("Planning conforme — aucune alerte")

    # ── Vue 3 semaines ──
    with st.expander("Voir les 3 semaines du cycle"):
        for w in [1, 2, 3]:
            meeting_label = " (réunion)" if w == 3 and meeting_week else ""
            st.markdown(f"#### Semaine {w}{meeting_label}")
            s, wh = generate_week(w, extras=extras, meeting_week=(meeting_week if w == 3 else False), vacation=vacation)
            st.markdown(build_schedule_html(s, wh, all_staff), unsafe_allow_html=True)
            _, issues = check_labor_law(s, wh, all_staff)
            if issues:
                for issue in issues:
                    st.error(f"{issue['day']} : {issue['count']} personne(s) a la fermeture")

    # ── Export Connecteam ──
    st.markdown("---")
    st.subheader("Export Connecteam")

    today = datetime.date.today()
    # Prochain lundi
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + datetime.timedelta(days=days_until_monday)

    ec1, ec2, ec3 = st.columns(3)
    with ec1:
        start_date = st.date_input(
            "Date de début (lundi)",
            value=next_monday,
        )
    with ec2:
        num_weeks = st.number_input(
            "Nombre de semaines",
            min_value=1, max_value=12, value=3,
        )
    with ec3:
        first_week = st.selectbox(
            "Commence par la semaine type...",
            [1, 2, 3],
            format_func=lambda w: f"Semaine {w}/3",
        )

    # Vérifier que c'est un lundi
    if start_date.weekday() != 0:
        st.warning("La date de début doit être un lundi. Le prochain lundi sera utilisé.")
        days_to_add = (7 - start_date.weekday()) % 7
        if days_to_add == 0:
            days_to_add = 7
        start_date = start_date + datetime.timedelta(days=days_to_add)
        st.info(f"Date ajustée : {start_date.strftime('%d/%m/%Y')}")

    end_date = start_date + datetime.timedelta(weeks=num_weeks) - datetime.timedelta(days=1)
    st.caption(
        f"Planning du {start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')} "
        f"({num_weeks} semaines, rotation {first_week}→{((first_week - 1 + num_weeks - 1) % 3) + 1})"
    )

    csv_data = export_connecteam_csv(start_date, num_weeks, first_week, extras=extras, vacation=vacation)
    st.download_button(
        "Télécharger le CSV Connecteam",
        data=csv_data,
        file_name=f"connecteam_{start_date.strftime('%Y%m%d')}_{num_weeks}sem.csv",
        mime="text/csv",
        type="primary",
    )


JOURS_SHORT = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']


def _planning_css():
    """CSS adaptatif light/dark mode + responsive mobile."""
    return """<style>
    .pl-scroll { width:100%; overflow-x:auto; -webkit-overflow-scrolling:touch; }
    .pl-table { width:100%; border-collapse:collapse; font-size:13px; font-family:sans-serif; min-width:700px; }
    .pl-table th, .pl-table td { padding:8px; border:1px solid rgba(128,128,128,0.3); }
    .pl-table th { text-align:center; }
    .pl-hdr { background:rgba(44,62,80,0.9); color:white; }
    .pl-name { font-weight:bold; text-align:left; white-space:nowrap; }
    .pl-role { font-size:11px; font-weight:normal; opacity:0.65; }
    .pl-matin { background:rgba(52,152,219,0.2); }
    .pl-soir { background:rgba(230,126,34,0.2); }
    .pl-journee { background:rgba(46,204,113,0.2); }
    .pl-conge { background:rgba(128,128,128,0.15); }
    .pl-indispo { background:rgba(128,128,128,0.08); }
    .pl-empty { opacity:0.5; }
    .pl-total { font-weight:bold; text-align:center; }
    .pl-hours { font-size:11px; opacity:0.65; }
    .pl-ok { color:#27ae60; }
    .pl-warn { color:#e67e22; }
    .pl-cov0 { background:rgba(231,76,60,0.25); }
    .pl-cov1 { background:rgba(241,196,15,0.25); }
    .pl-cov2 { background:rgba(46,204,113,0.25); }
    .pl-cov3 { background:rgba(52,152,219,0.25); }
    .pl-covoff { background:rgba(128,128,128,0.1); opacity:0.4; }
    .pl-covtip { font-size:10px; opacity:0.6; }
    .pl-day-full { display:inline; }
    .pl-day-short { display:none; }
    @media (prefers-color-scheme: dark) {
        .pl-matin { background:rgba(52,152,219,0.3); }
        .pl-soir { background:rgba(230,126,34,0.3); }
        .pl-journee { background:rgba(46,204,113,0.3); }
        .pl-conge { background:rgba(128,128,128,0.25); }
        .pl-cov0 { background:rgba(231,76,60,0.35); }
        .pl-cov1 { background:rgba(241,196,15,0.3); }
        .pl-cov2 { background:rgba(46,204,113,0.3); }
        .pl-cov3 { background:rgba(52,152,219,0.35); }
    }
    @media (max-width: 768px) {
        .pl-table { font-size:11px; min-width:580px; }
        .pl-table th, .pl-table td { padding:4px 3px; }
        .pl-name { font-size:11px; }
        .pl-role { font-size:9px; }
        .pl-hours { font-size:9px; }
        .pl-covtip { font-size:8px; }
        .pl-total { font-size:11px; }
        .pl-day-full { display:none; }
        .pl-day-short { display:inline; }
    }
    </style>"""


def build_schedule_html(schedule, weekly_hours=None, staff_list=None):
    """Construit un tableau HTML coloré du planning."""
    staff_list = staff_list or STAFF
    css_class = {
        'matin': 'pl-matin',
        'soir': 'pl-soir',
        'journee': 'pl-journee',
        'conge': 'pl-conge',
        'indispo': 'pl-indispo',
    }
    labels = {
        'matin': 'MATIN',
        'soir': 'SOIR',
        'journee': 'JOURNEE',
        'conge': 'CONGE',
        'indispo': '—',
    }

    html = _planning_css()
    html += '<div class="pl-scroll"><table class="pl-table">'

    # Header
    html += '<tr class="pl-hdr">'
    html += '<th style="text-align:left; width:100px;">Staff</th>'
    for i, jour in enumerate(JOURS):
        short = JOURS_SHORT[i]
        html += f'<th><span class="pl-day-full">{jour}</span><span class="pl-day-short">{short}</span></th>'
    html += '<th style="width:70px;">Total</th>'
    html += '</tr>'

    for emp in staff_list:
        html += '<tr>'
        first_name = emp.name.split()[0]
        html += (
            f'<td class="pl-name">{first_name}<br>'
            f'<span class="pl-role">'
            f'{emp.role if emp.role else ""}</span></td>'
        )
        total = 0.0
        for d in range(7):
            entry = schedule[emp.name][d]
            if entry is None or entry.get('hours', 0) == 0:
                cls = css_class.get(entry['type'], '') if entry else ''
                label = labels.get(entry['type'], '') if entry else ''
                html += (
                    f'<td class="{cls} pl-empty" style="text-align:center;">'
                    f'{label}</td>'
                )
            else:
                cls = css_class[entry['type']]
                label = labels[entry['type']]
                total += entry['hours']
                html += (
                    f'<td class="{cls}" style="text-align:center; padding:6px;">'
                    f'<strong style="font-size:12px;">{label}</strong><br>'
                    f'<span style="font-size:12px;">'
                    f'{entry["start"]} - {entry["end"]}</span><br>'
                    f'<span class="pl-hours">'
                    f'{entry["hours"]:.1f}h</span></td>'
                )

        # Colonne total + indicateur contrat
        target = emp.contract_hours
        ecart = total - target
        ecart_cls = 'pl-ok' if abs(ecart) < 1 else 'pl-warn'
        html += (
            f'<td class="pl-total">'
            f'<span style="font-size:15px;">{total:.1f}h</span><br>'
            f'<span class="{ecart_cls}" style="font-size:11px;">'
            f'({ecart:+.1f}h vs {target:.0f}h)</span></td>'
        )
        html += '</tr>'

    html += '</table></div>'
    return html


def build_coverage_html(schedule, staff_list=None):
    """Tableau de couverture : nombre de personnes par créneau horaire."""
    staff_list = staff_list or STAFF
    html = '<div class="pl-scroll"><table class="pl-table" style="font-size:12px;">'
    html += '<tr class="pl-hdr">'
    html += '<th style="padding:6px;">Créneau</th>'
    for i, jour in enumerate(JOURS):
        short = JOURS_SHORT[i]
        html += f'<th style="padding:6px;"><span class="pl-day-full">{jour}</span><span class="pl-day-short">{short}</span></th>'
    html += '</tr>'

    # Créneaux de 2h
    slots = [
        (9, 45, 12, 0),
        (12, 0, 14, 0),
        (14, 0, 16, 0),
        (16, 0, 18, 0),
        (18, 0, 20, 0),
        (20, 0, 22, 0),
        (22, 0, 23, 15),
    ]

    for s_sh, s_sm, s_eh, s_em in slots:
        slot_start = to_minutes(s_sh, s_sm)
        slot_end = to_minutes(s_eh, s_em)
        html += '<tr>'
        html += (
            f'<td style="padding:4px; font-weight:bold;">'
            f'{time_str(s_sh, s_sm)}-{time_str(s_eh, s_em)}</td>'
        )

        for d in range(7):
            open_min = to_minutes(*HORAIRES[d][:2])
            close_min = to_minutes(*HORAIRES[d][2:])

            # Hors horaires d'ouverture
            if slot_start >= close_min or slot_end <= open_min:
                html += '<td class="pl-covoff" style="padding:4px; text-align:center;">—</td>'
                continue

            # Compter les personnes présentes dans ce créneau
            count = 0
            names = []
            for emp in staff_list:
                entry = schedule[emp.name][d]
                if entry and entry.get('hours', 0) > 0:
                    parts_start = entry['start'].split(':')
                    parts_end = entry['end'].split(':')
                    emp_start = int(parts_start[0]) * 60 + int(parts_start[1])
                    emp_end = int(parts_end[0]) * 60 + int(parts_end[1])
                    # L'employé couvre le créneau s'il chevauche
                    if emp_start < slot_end and emp_end > slot_start:
                        count += 1
                        names.append(emp.name.split()[0][:3])

            if count == 0:
                cls = 'pl-cov0'
            elif count == 1:
                cls = 'pl-cov1'
            elif count == 2:
                cls = 'pl-cov2'
            else:
                cls = 'pl-cov3'

            tooltip = ', '.join(names)
            html += (
                f'<td class="{cls}" style="padding:4px; text-align:center;" '
                f'title="{tooltip}">'
                f'<strong>{count}</strong>'
                f'<span class="pl-covtip"><br>{tooltip}</span>'
                f'</td>'
            )

        html += '</tr>'

    html += '</table></div>'
    return html


if __name__ == '__main__':
    main()
