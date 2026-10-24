"""Deterministic, tenant-scoped natural-language queries over loaded student CSV data."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .data_service import DataService
from .config import DATASET_SCHEMAS

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "student_id": ("student id", "roll number", "roll no", "registration number"),
    "student_name": ("student name", "student names", "full name", "names", "name"),
    "student_email": ("student email", "email address", "email"),
    "section": ("class section", "section"),
    "admission_year": ("admission year", "year of admission", "joining year", "batch"),
    "department": ("department", "departments", "dept", "branch", "stream"),
    "year_of_study": ("year of study", "study year", "year", "academic year"),
    "cgpa": ("cgpa", "gpa", "grade point"),
    "backlogs": ("backlogs", "backlog", "arrears"),
    "internal_score_pct": ("internal score", "internal marks", "internal percentage", "internals"),
    "semester_score_pct": ("semester score", "semester marks", "semester percentage"),
    "subjects_below_attendance_threshold": ("subjects below attendance threshold", "attendance shortage subjects"),
    "overall_attendance_pct": ("overall attendance", "attendance percentage", "attendance pct", "attendance"),
    "coding_score": ("coding score", "coding marks", "coding"),
    "aptitude_score": ("aptitude score", "aptitude"),
    "mock_interview_score": ("mock interview score", "interview score", "mock interview"),
    "resume_readiness_pct": ("resume readiness", "resume score"),
    "placement_readiness_score": ("placement readiness score", "placement readiness"),
    "placement_status": ("placement status", "placement", "unplaced", "placed", "eligible"),
    "logins_last_30_days": ("lms logins", "logins last 30 days", "monthly logins", "logins"),
    "assignment_completion_pct": ("assignment completion", "assignments completed", "incomplete assignments", "assignments", "assignment"),
    "avg_weekly_learning_hours": ("weekly learning hours", "learning hours", "study hours"),
    "events_attended": ("events attended", "events", "event"),
    "hackathons_participated": ("hackathons participated", "hackathons attended", "hackathons", "hackathon"),
    "club_participation": ("club participation", "participation", "clubs"),
    "volunteer_hours": ("volunteer hours",),
    "technical_skill_score": ("technical skill score", "technical skills"),
    "soft_skill_score": ("soft skill score", "soft skills"),
    "certifications_count": ("certifications count", "certifications", "certificates", "certification"),
    "projects_count": ("projects count", "projects", "project"),
    "student_satisfaction_1_to_5": ("student satisfaction", "satisfaction"),
    "faculty_feedback_1_to_5": ("faculty feedback",),
    "support_requested": ("support requested", "support needed"),
    "feedback_topic": ("feedback topic", "feedback topics"),
    "success_score": ("success score", "student success", "overall performance"),
    "academic_risk_level": ("academic risk", "academic risk level"),
    "placement_risk_level": ("placement risk", "placement risk level"),
    "academic_risk_points": ("academic risk points",),
    "placement_risk_points": ("placement risk points",),
    "segment": ("student segment", "segment"),
    "data_completeness_pct": ("data completeness", "missing data"),
}

# Include every persisted student field, including its exact CSV spelling. This
# keeps chat coverage in step with the data/import schema instead of a fixed list.
for _dataset, _schema in DATASET_SCHEMAS.items():
    if _dataset == "interventions":
        continue
    for _field in _schema["required"]:
        FIELD_ALIASES[_field] = tuple(dict.fromkeys(
            (*FIELD_ALIASES.get(_field, ()), _field, _field.replace("_", " "))
        ))
for _field in tuple(FIELD_ALIASES):
    FIELD_ALIASES[_field] = tuple(dict.fromkeys((*FIELD_ALIASES[_field], _field)))

GROUP_ALIASES = {
    "department": ("department", "departments", "dept", "branch"),
    "year_of_study": ("year of study", "study year", "each year", "per year", "year"),
    "placement_status": ("placement status", "each placement status", "per status"),
    "academic_risk_level": ("academic risk", "academic risk level"),
    "placement_risk_level": ("placement risk", "placement risk level"),
    "segment": ("segment", "segments"),
}

NUMERIC_FIELDS = {
    "cgpa", "backlogs", "overall_attendance_pct", "coding_score", "aptitude_score",
    "mock_interview_score", "resume_readiness_pct", "placement_readiness_score",
    "logins_last_30_days", "assignment_completion_pct", "avg_weekly_learning_hours",
    "events_attended", "hackathons_participated", "volunteer_hours",
    "technical_skill_score", "soft_skill_score", "certifications_count", "projects_count",
    "student_satisfaction_1_to_5", "faculty_feedback_1_to_5", "success_score",
    "academic_risk_points", "placement_risk_points", "data_completeness_pct",
}
NUMERIC_FIELDS.update(column for name, schema in DATASET_SCHEMAS.items()
                      if name != "interventions" for column in schema["ranges"])


class QueryClarification(Exception):
    """The request cannot be executed completely; do not return a partial match."""


@dataclass(frozen=True)
class Filter:
    column: str
    operator: str
    value: Any


def _matches(text: str, phrase: str) -> list[re.Match[str]]:
    return list(re.finditer(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text, re.I))


def _column_matches(question: str) -> dict[str, list[re.Match[str]]]:
    found: dict[str, list[re.Match[str]]] = {}
    aliases = sorted(((phrase, column) for column, phrases in FIELD_ALIASES.items()
                      for phrase in phrases), key=lambda item: len(item[0]), reverse=True)
    occupied: list[tuple[int, int]] = []
    for phrase, column in aliases:
        for match in _matches(question, phrase):
            if any(start < match.end() and match.start() < end for start, end in occupied):
                continue
            found.setdefault(column, []).append(match)
            occupied.append(match.span())
    return dict(sorted(found.items(), key=lambda item: min(m.start() for m in item[1])))


def _department_values(service: DataService, question: str) -> list[str]:
    found = []
    for department in service.departments():
        words = re.findall(r"[a-z]+", department.casefold())
        initials = "".join(w[0] for w in words if w not in {"and", "of", "the"})
        aliases = [department]
        # Two-letter initials collide with ordinary words (e.g. "ME" in
        # "give me"), so only use abbreviations that are unambiguous in prose.
        if len(initials) >= 3:
            aliases.append(initials)
        meaningful = [w for w in words if w not in {"and", "of", "the", "engineering"}]
        if len(meaningful) == 1:
            aliases.append(meaningful[0])
        if any(_matches(question, alias) for alias in aliases):
            found.append(department)
    return sorted(set(found))


def _group_column(question: str, columns: dict) -> str | None:
    for column, mentions in columns.items():
        for mention in mentions:
            before = question[max(0, mention.start() - 20):mention.start()]
            after = question[mention.end():mention.end() + 20]
            if (re.search(r"\b(?:by|per|each|across|among|which)\s+(?:the\s+)?$", before)
                    or re.match(r"\s*[- ]?wise\b|\s+(?:distribution|breakdown)\b", after)):
                if column not in NUMERIC_FIELDS or column in {"year_of_study", "admission_year"}:
                    return column
    if re.search(r"\b(?:distribution|breakdown)\b", question):
        return next((c for c in columns if c not in NUMERIC_FIELDS), None)
    return None


NUMBER = r"-?\d+(?:\.\d+)?"
OPERATOR = (r">=|<=|!=|==|>|<|=|at least|at most|no less than|no more than|"
            r"greater than or equal to|less than or equal to|greater than|more than|"
            r"less than|lower than|minimum of|maximum of|above|below|over|under|"
            r"equals?|exactly")
OP_MAP = {
    ">=": "ge", "at least": "ge", "no less than": "ge", "minimum of": "ge",
    "greater than or equal to": "ge", "<=": "le", "at most": "le", "no more than": "le",
    "maximum of": "le", "less than or equal to": "le", ">": "gt", "above": "gt",
    "over": "gt", "greater than": "gt", "more than": "gt", "<": "lt", "below": "lt",
    "under": "lt", "less than": "lt", "lower than": "lt", "!=": "ne",
}
LOWER_RANK = r"\b(?:lowest|least|fewest|bottom|worst)\b"
RANK = r"\b(?:top|bottom|highest|lowest|most|least|fewest|best|worst|rank|ranked)\b"


def _rank_requested(q: str) -> bool:
    # "at most 5" and "at least 8" are filters, not rankings.
    return bool(re.search(RANK, re.sub(r"\b(?:at|no)\s+(?:most|least)\b", "", q)))


def _limit(q: str, default: int = 100) -> int:
    match = re.search(r"\b(?:top|bottom|first|last|limit(?: to)?|only)\s+(\d+)\b|"
                      r"\b(\d+)\s+(?:students?|learners?|names?|records?)\b|"
                      r"\b(?:give|show|list)(?:\s+me)?\s+(\d+)\b", q)
    return min(max(1, int(next(v for v in match.groups() if v is not None))), 100) if match else default


def _is_count(q: str) -> bool:
    return bool(re.search(r"\b(?:how many|count|number of|total)\s+(?:the\s+)?(?:students?|learners?|records?)\b", q)
                or re.search(r"\b(?:student|students)\s+count\b", q))


def _is_list(q: str) -> bool:
    return bool(re.search(r"\b(?:students?|learners?|list|show|who|names?|give|details|profile)\b", q))


def _numeric_filters(q: str, columns: dict) -> list[Filter]:
    """Bind comparisons immediately to a field, never to a nearby other field."""
    conditions: list[Filter] = []
    consumed: list[tuple[int, int]] = []
    mentions = sorted((m.start(), m.end(), c) for c, ms in columns.items() for m in ms)
    for i, (start, end, column) in enumerate(mentions):
        if column not in NUMERIC_FIELDS:
            continue
        left = mentions[i - 1][1] if i else 0
        right = mentions[i + 1][0] if i + 1 < len(mentions) else len(q)
        before, after = q[left:start], q[end:right]
        # A small grammatical connector is allowed, but no other field/condition.
        connector = r"\s*(?:(?:is|of|are|was|score|scores|percentage|count|:|has|have)\s*)?"
        expressions = [
            (rf"between\s+({NUMBER})\s*%?\s+and\s+({NUMBER})\s*%?", "range"),
            (rf"({NUMBER})\s*%?\s*(?:to|-)\s*({NUMBER})\s*%?", "range"),
            (rf"({OPERATOR})\s*({NUMBER})\s*%?", "op"),
            (rf"({NUMBER})\s*%?\s*(\+|plus\b|or more\b|and above\b|or above\b|and higher\b)", "ge"),
            (rf"({NUMBER})\s*%?\s*(or less\b|and below\b|or below\b)", "le"),
            (rf"({NUMBER})\s*%?", "eq"),
        ]
        parsed = False
        for expression, kind in expressions:
            match = re.match(connector + expression, after)
            offset = end
            if not match:
                match = re.search(expression + r"\s*$", before)
                offset = left
                # "give me 5 students ... CGPA" is a limit, not CGPA = 5.
                if match and kind == "eq" and re.search(r"\b(?:top|bottom|give|show|list|first|only)\s*(?:me\s*)?$", before[:match.start()]):
                    match = None
            if not match:
                continue
            span = (offset + match.start(), offset + match.end())
            if any(a < span[1] and span[0] < b for a, b in consumed):
                continue
            consumed.append(span)
            if kind == "range":
                low, high = map(float, match.groups())
                if low > high:
                    raise QueryClarification("The lower end of a range must be smaller than the upper end.")
                conditions.extend([Filter(column, "ge", low), Filter(column, "le", high)])
            elif kind == "op":
                conditions.append(Filter(column, OP_MAP.get(match.group(1), "eq"), float(match.group(2))))
            else:
                conditions.append(Filter(column, kind, float(match.group(1))))
            parsed = True
            break
        if parsed:
            continue
        if column == "year_of_study":
            year = re.search(r"\b([1-8])(?:st|nd|rd|th)\s*$", before)
            if year:
                conditions.append(Filter(column, "eq", int(year.group(1))))
        if column == "backlogs":
            if re.search(r"\b(?:no|zero|without)\s+(?:any\s+)?$", before):
                conditions.append(Filter(column, "eq", 0))
            elif re.search(r"\b(?:with|has|have|having)\s+(?:any\s+)?$", before):
                conditions.append(Filter(column, "gt", 0))
        if re.search(r"\b(?:low|poor)\s*$", before):
            threshold = {"overall_attendance_pct": 75, "cgpa": 6}.get(column)
            if threshold is None:
                raise QueryClarification(f"Specify a numeric threshold for {column}, for example '{column} below 50'.")
            conditions.append(Filter(column, "lt", threshold))
        if column == "assignment_completion_pct" and re.search(r"\bincomplete assignments?\b", q[start:end]):
            conditions.append(Filter(column, "lt", 100))
    # Refuse any numeric comparison not understood in full instead of silently
    # dropping it while applying an unrelated branch/department filter.
    for match in re.finditer(rf"(?:{OPERATOR})\s*{NUMBER}|{NUMBER}\s*(?:\+|plus\b)", q):
        if not any(a <= match.start() and match.end() <= b for a, b in consumed):
            raise QueryClarification("I couldn't identify the field for every numeric condition. Use, for example, 'CGPA >= 8 and attendance >= 75'.")
    return conditions


def _categorical_filters(service: DataService, q: str, columns: dict) -> list[Filter]:
    filters: list[Filter] = []
    departments = _department_values(service, q)
    if departments:
        filters.append(Filter("department", "in", departments))
    df = service.students
    for column in ("student_id", "student_name"):
        if column in df:
            values = [str(v) for v in df[column].dropna().unique() if _matches(q, str(v))]
            if values:
                filters.append(Filter(column, "in", values))
    # Match categories only next to their own field, so 'high academic risk and
    # low placement risk' cannot accidentally use the same level for both.
    for column, mentions in columns.items():
        if column in NUMERIC_FIELDS or column in {"department", "student_name", "student_id"}:
            continue
        if column not in df:
            raise ValueError(f"The loaded student data does not include the requested field '{column}'.")
        values = [str(v) for v in df[column].dropna().unique()]
        matches = []
        for mention in mentions:
            before, after = q[:mention.start()], q[mention.end():]
            for value in sorted(values, key=len, reverse=True):
                escaped = re.escape(value.casefold())
                if (re.match(r"\s*(?:is\s+|=\s*|of\s+)?['\"]?" + escaped + r"(?![a-z0-9])", after)
                        or re.search(r"(?<![a-z0-9])" + escaped + r"['\"]?\s*$", before)):
                    matches.append(value)
        if column == "placement_status":
            if re.search(r"\b(?:not placed|unplaced)\b", q):
                filters.append(Filter(column, "ne", "Placed"))
                continue
            matches.extend(v for v in ("Not started", "Eligible", "Training", "Placed") if _matches(q, v))
        if column == "club_participation" and re.search(r"\b(?:no|low)\s+(?:club\s+)?participation\b", q):
            matches.append("None")
        if matches:
            filters.append(Filter(column, "in", list(dict.fromkeys(matches))))
    # Shared risk modifier: high academic or placement risk.
    shared = re.search(r"\b(high|medium|low)\s+academic\s+(and|or)\s+placement\s+risk\b", q)
    if shared:
        filters = [f for f in filters if f.column not in {"academic_risk_level", "placement_risk_level"}]
        if shared.group(2) == "or":
            filters.append(Filter("__risk_any", "eq", shared.group(1).title()))
        else:
            filters.extend(Filter(c, "eq", shared.group(1).title())
                           for c in ("academic_risk_level", "placement_risk_level"))
    return filters


def _apply_filter(frame: pd.DataFrame, condition: Filter) -> pd.DataFrame:
    column, op, value = condition.column, condition.operator, condition.value
    if column == "__risk_any":
        return frame[frame["academic_risk_level"].eq(value) | frame["placement_risk_level"].eq(value)]
    if column not in frame:
        raise ValueError(f"The loaded student data does not include the requested field '{column}'.")
    series = frame[column]
    if op == "missing":
        return frame[series.isna() | series.astype(str).str.strip().eq("")]
    if column in NUMERIC_FIELDS:
        series = pd.to_numeric(series, errors="coerce")
    else:
        series = series.astype("string").str.strip().str.casefold()
        value = [str(v).casefold() for v in value] if op == "in" else str(value).casefold()
    if op == "in":
        mask = series.isin(value)
    else:
        mask = getattr(series, op)(value)
    return frame[mask.fillna(False) & series.notna()]


def _select_rows(frame: pd.DataFrame, filters: list[Filter], question: str = "") -> pd.DataFrame:
    selected = frame
    for condition in filters:
        selected = _apply_filter(selected, condition)
    return selected


def _value_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return "Not recorded"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "No matching students were found."
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(_value_text(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _answer(text: str, scope: str = "Calculated from this institution's student records") -> dict[str, str]:
    return {"answer": text, "context_scope": scope}


def _student_table(selected: pd.DataFrame, fields: list[str], limit: int, ranked: bool = False) -> str:
    shown = list(dict.fromkeys(["student_name", "department", *fields]))
    rows = [[row.get(c) for c in shown] for _, row in selected.head(limit).iterrows()]
    headers = ["Student" if c == "student_name" else "Department" if ranked and c == "department" else c for c in shown]
    answer = _table(headers, rows)
    if len(selected) > limit:
        answer += f"\n\nShowing {limit} of {len(selected)} matching students."
    return answer


def _skill_selection(service: DataService, q: str, columns: dict) -> tuple[set[str], dict[str, str], list[str]] | None:
    skills = getattr(service, "student_skills", pd.DataFrame())
    available = not skills.empty and {"Student ID", "Skill Name"}.issubset(skills.columns)
    names = sorted({str(v).strip() for v in skills["Skill Name"].dropna()} if available else [], key=len, reverse=True)
    matched = []
    occupied = []
    for name in names:
        suffix = r"(?![a-z0-9+#])" if name.casefold() == "c" else r"(?![a-z0-9])"
        for match in re.finditer(r"(?<![a-z0-9])" + re.escape(name.casefold()) + suffix, q):
            if not any(a <= match.start() and match.end() <= b for a, b in occupied):
                matched.append(name)
                occupied.append(match.span())
    matched = list(dict.fromkeys(matched))
    residual = q
    for column in ("technical_skill_score", "soft_skill_score"):
        for mention in columns.get(column, []):
            residual = residual[:mention.start()] + " " * (mention.end() - mention.start()) + residual[mention.end():]
    explicit = bool(re.search(r"\b(?:skills?|knows?|proficient|proficiency)\b", residual))
    if not matched and not explicit:
        return None
    if not available:
        raise QueryClarification(
            "Named skill records (such as Java or Python) are not available in this institution's loaded dataset. "
            "Skill scores alone do not identify which skills a student has. Add this institution's named skill records to answer this question."
        )
    skill_rows = skills.copy()
    skill_rows["Student ID"] = skill_rows["Student ID"].astype(str).str.strip().str.upper()
    skill_rows["Skill Name"] = skill_rows["Skill Name"].astype(str).str.strip()
    # Never use orphan IDs or a different institution's source sheet.
    skill_rows = skill_rows[skill_rows["Student ID"].isin(service.students.index.astype(str))]
    if matched:
        skill_rows = skill_rows[skill_rows["Skill Name"].str.casefold().isin([n.casefold() for n in matched])]
        if len(matched) > 1 and not re.search(r"\bor\b", q):
            counts = skill_rows.groupby("Student ID")["Skill Name"].nunique()
            skill_rows = skill_rows[skill_rows["Student ID"].isin(counts[counts == len(matched)].index)]
    elif not any(f.column in {"student_id", "student_name"} for f in _categorical_filters(service, q, columns)):
        # An unrecognised skill is not a request for every skill in the file.
        if not re.search(r"\b(?:available|all|recorded|which|what)\s+(?:student\s+)?skills\b", q):
            raise QueryClarification("No matching named skill was found in this institution's skill records. Ask 'Which skills are available?' to see the recorded skills.")
    if re.search(r"\b(?:without|not|no)\s+(?:any\s+)?(?:" + "|".join(re.escape(n.casefold()) for n in matched) + r")\b", q) if matched else False:
        raise QueryClarification("Missing skill records do not prove that a student lacks a skill. Ask for students with a recorded skill instead.")
    by_student = skill_rows.groupby("Student ID")["Skill Name"].agg(lambda vs: ", ".join(sorted(set(vs))))
    return set(by_student.index), by_student.to_dict(), matched


def _filtered_students(service: DataService, q: str, columns: dict) -> tuple[pd.DataFrame, list[Filter]]:
    filters = _categorical_filters(service, q, columns)
    filters.extend(_numeric_filters(q, columns))
    for column, mentions in columns.items():
        if any(re.search(r"\b(?:missing|unknown|unrecorded)\s*$", q[:m.start()])
               or re.match(r"\s+(?:is\s+)?(?:missing|unknown|not recorded)\b", q[m.end():]) for m in mentions):
            filters.append(Filter(column, "missing", None))
    # OR is handled only between complete conditions. A department union remains
    # a single categorical condition, and ranges remain intersections.
    branches = re.split(r"\bor\b(?!\s+(?:more|less|above|below|equal)\b)", q)
    if len(branches) > 1 and not any(f.column == "__risk_any" for f in filters):
        branch_filters = []
        for branch in branches:
            branch_columns = _column_matches(branch)
            branch_filters.append(_categorical_filters(service, branch, branch_columns)
                                  + _numeric_filters(branch, branch_columns))
        non_departments = [[f for f in fs if f.column != "department"] for fs in branch_filters]
        if all(non_departments):
            if any(re.search(r"\band\b", b) and not re.search(r"\bbetween\b", b) for b in branches):
                raise QueryClarification("Please separate mixed AND/OR conditions into simpler questions so the grouping is unambiguous.")
            ids: set[str] = set()
            for fs in branch_filters:
                ids.update(_select_rows(service.students, fs).index)
            return service.students[service.students.index.isin(ids)], filters
    return _select_rows(service.students, filters), filters


def _intervention_query(service: DataService, q: str) -> dict[str, str]:
    selected = service.interventions
    if re.search(r"\bopen\b", q):
        selected = selected[selected["status"].isin(["Recommended", "Assigned", "In progress"])]
    if re.search(r"\b(?:distribution|breakdown|status)\b", q):
        counts = selected["status"].fillna("Not recorded").value_counts().sort_index()
        return _answer(_table(["Intervention status", "Count"], [[k, int(v)] for k, v in counts.items()]),
                       "Calculated from this institution's intervention records")
    if re.search(r"\b(?:count|how many|total|number of)\b", q):
        return _answer(f"Matching interventions: {len(selected)}.", "Counted this institution's intervention records")
    joined = selected.merge(service.students[["student_name", "department"]], left_on="student_id", right_index=True, how="inner")
    fields = ["student_name", "department", "intervention_type", "status", "assigned_date"]
    return _answer(_table(["Student", "Department", "Intervention", "Status", "Assigned"],
                          [[row.get(c) for c in fields] for _, row in joined.head(_limit(q)).iterrows()]),
                   "Listed this institution's intervention records")


def query_students(service: DataService, question: str) -> dict[str, str] | None:
    """Execute supported questions locally; clarify instead of answering partially."""
    try:
        return _query_students(service, question)
    except QueryClarification as exc:
        return _answer(str(exc), "No student records returned; clarification or missing data required")


def _query_students(service: DataService, question: str) -> dict[str, str] | None:
    q = re.sub(r"\s+", " ", question.casefold().strip()).replace("≥", ">=").replace("≤", "<=")
    df = service.students
    columns = _column_matches(q)
    if re.search(r"\b(?:available fields|what fields|which fields|columns|data fields)\b", q):
        return _answer("Available student fields: " + ", ".join(df.columns)
                       + ". Named skills are available only when this institution has detailed skill records.",
                       "Loaded institution student CSV fields")
    if "intervention" in q:
        return _intervention_query(service, q)
    # Advice remains an optional AI operation. Factual retrieval below never uses
    # an aggregate-only prompt or sampled rows to invent a list or calculate values.
    if re.search(r"\b(?:recommend|recommendations|suggest|advice|patterns|improve|explain why)\b", q):
        return None
    for column in columns:
        if column not in df:
            raise ValueError(f"The loaded student data does not include the requested field '{column}'.")
    skill_selection = _skill_selection(service, q, columns)
    selected, filters = _filtered_students(service, q, columns)
    if skill_selection is not None:
        ids, skill_labels, skill_names = skill_selection
        selected = selected[selected.index.isin(ids)].copy()
        selected["skills"] = selected.index.map(skill_labels)
        if re.search(r"\b(?:available|which|what|all)\s+(?:student\s+)?skills\b", q) and not filters:
            available = sorted({skill for value in skill_labels.values() for skill in value.split(", ")})
            return _answer("Recorded skills: " + ", ".join(available), "Named skills recorded for this institution's students")

    group = _group_column(q, columns)
    metrics = [c for c in columns if c in NUMERIC_FIELDS and c != group]
    aggregate_match = re.search(r"\b(average|avg|mean|median|sum|total|minimum|maximum)\b", q)
    aggregate = aggregate_match.group(1) if aggregate_match else None
    if _is_count(q):
        aggregate = None
    if aggregate in {"minimum", "maximum"} and re.search(r"\b(?:minimum|maximum) of\b", q):
        aggregate = None
    operation = {"average": "mean", "avg": "mean", "mean": "mean", "total": "sum",
                 "minimum": "min", "maximum": "max"}.get(aggregate, aggregate)
    label = {"mean": "Average", "median": "Median", "sum": "Total", "min": "Minimum", "max": "Maximum"}.get(operation, "")
    ranked = _rank_requested(q)
    descending = not bool(re.search(LOWER_RANK, q))

    if re.search(r"\bcompare\b", q) and metrics:
        departments = _department_values(service, q)
        if len(departments) < 2:
            return _answer("Name at least two departments to compare.", "No records queried")
        group, operation, label = "department", operation or "mean", label or "Average"

    if operation:
        if not metrics:
            asked = q[aggregate_match.end():].strip(" .?") if aggregate_match else "requested field"
            return _answer(f"I couldn't match '{asked}' to an available numeric student-data field. Try CGPA, attendance, backlogs, coding score, or ask which fields are available.", "No records queried")
        # Aggregate target fields precede 'with/where/having'; later fields only filter.
        cutoff = re.search(r"\b(?:with|where|having|whose|who have|who has)\b", q)
        targets = [c for c in metrics if not cutoff or min(m.start() for m in columns[c]) < cutoff.start()] or metrics[:1]
        numeric = selected.copy()
        for metric in targets:
            numeric[metric] = pd.to_numeric(numeric[metric], errors="coerce")
        def calculate(values):
            values = values.dropna()
            return getattr(values, operation)() if len(values) else None
        if group:
            result = numeric.groupby(group, dropna=False, sort=True)[targets].agg(calculate)
            if ranked:
                result = result.sort_values(targets[0], ascending=not descending, na_position="last", kind="stable")
            rows = [[key, *[row[c] for c in targets]] for key, row in result.head(_limit(q)).iterrows()]
            return _answer(_table([group, *[f"{label} {c}" for c in targets]], rows))
        if len(targets) == 1:
            metric = targets[0]
            values = numeric[metric].dropna()
            value = calculate(values)
            return _answer(f"{label} {metric}: {round(float(value), 2)} across {len(values)} recorded value(s)."
                           if value is not None else f"No recorded values are available for {metric}.")
        return _answer(_table(["Field", label, "Recorded values"], [[c, calculate(numeric[c]), int(numeric[c].notna().sum())] for c in targets]))

    if re.search(r"\b(?:summari[sz]e|overview)\b", q):
        rows = [["Total students", len(selected)]]
        for c, title in (("cgpa", "Average CGPA"), ("overall_attendance_pct", "Average attendance"), ("success_score", "Average success score")):
            if c in selected:
                rows.append([title, pd.to_numeric(selected[c], errors="coerce").mean()])
        return _answer(_table(["Measure", "Value"], rows))
    if group and (re.search(r"\b(?:distribution|breakdown|count|number|total|each|per)\b", q) or _is_count(q)):
        counts = selected[group].fillna("Not recorded").value_counts().sort_index()
        return _answer(_table([group, "Students"], [[k, int(v)] for k, v in counts.items()]))
    if _is_count(q):
        return _answer(f"Matching students: {len(selected)}.", "Counted matching institution student records")

    fields = list(columns)
    if skill_selection is not None:
        fields.append("skills")
    explicitly_named_student = any(condition.column == "student_name" for condition in filters)
    if explicitly_named_student and re.search(r"\b(?:data|information|record|details|profile)\b", q):
        persisted_fields = [
            field
            for dataset, schema in DATASET_SCHEMAS.items()
            if dataset != "interventions"
            for field in schema["required"]
            if field in selected.columns
        ]
        derived_summary_fields = [
            field for field in (
                "placement_readiness_score", "success_score", "academic_risk_level",
                "placement_risk_level", "segment", "data_completeness_pct",
            )
            if field in selected.columns
        ]
        fields = list(dict.fromkeys([*persisted_fields, *derived_summary_fields]))
    if ranked:
        # Choose the field attached to the ranking phrase, rather than whichever
        # filter field happened to be mentioned first in the sentence.
        rank_q = re.sub(r"\bat (?:least|most)\b", "", q)
        rank_mentions = list(re.finditer(RANK, rank_q))
        metric = next((c for c in metrics if any(
            re.search(RANK + r"\s*(?:number of\s+)?$", q[:m.start()])
            or re.match(r"\s*(?:score\s*)?" + RANK, q[m.end():]) for m in columns[c])), None)
        by = re.search(r"\b(?:by|in|on)\s+(.+)", q)
        if metric is None and by:
            metric = next((c for c in _column_matches(by.group(1)) if c in metrics), None)
        if metric is None and len(metrics) == 1:
            metric = metrics[0]
        if metric is None:
            raise QueryClarification("Specify which numeric field to rank, for example 'top 5 students by hackathons' or 'highest CGPA'.")
        selected = selected.copy()
        selected[metric] = pd.to_numeric(selected[metric], errors="coerce")
        selected = selected.dropna(subset=[metric]).sort_values([metric, "student_id"], ascending=[not descending, True], kind="stable")
        fields = list(dict.fromkeys([metric, *fields]))
        return _answer(_student_table(selected, fields, _limit(q, 5), ranked=True), f"Ranked institution student records by {metric}")
    if _is_list(q) or filters or skill_selection is not None:
        if not fields and not filters and skill_selection is None and not re.search(r"\b(?:list|show|give)(?:\s+me)?\s+(?:all\s+|\d+\s+)?(?:students?|student names|names)\b", q):
            raise QueryClarification("Specify the student field and condition to retrieve, or ask 'Which fields are available?'.")
        if re.search(r"\b(?:all fields|all details|profile|full details)\b", q):
            fields = list(selected.columns)
        prefix = ""
        if skill_selection is not None and len(skill_selection[2]) == 1:
            prefix = f"{skill_selection[2][0]} ({len(selected)} student(s)):\n\n"
        return _answer(prefix + _student_table(selected, fields, _limit(q)), "Filtered institution student records")
    if columns:
        raise QueryClarification("Specify whether to list students, filter values, rank students, or calculate an average/count for these fields.")
    return None
