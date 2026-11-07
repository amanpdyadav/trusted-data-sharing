"""Which receivers ask for each column: fills ColumnDetection.needed_by from the scenarios' data requests.

Detection says what a column is; `needed_by` says who needs it, so the planner and the reviewer can see that dropping
a column breaks a receiver's analysis. Uses the scenario files only (no answer key).
"""

from collections.abc import Iterable

from pets_transformer.contracts import DetectionReport
from pets_transformer.plan.scenario import Scenario


def annotate_needs(report: DetectionReport, scenarios: Iterable[Scenario]) -> DetectionReport:
    wanted: dict[tuple[str | None, str], set[str]] = {}
    for sc in scenarios:
        if sc.dataset != report.dataset:
            continue
        for need in sc.needs:
            wanted.setdefault((need.table, need.column), set()).add(sc.id)  # table None: any table with the column

    def who(table: str, column: str) -> list[str]:
        return sorted(wanted.get((table, column), set()) | wanted.get((None, column), set()))

    columns = [c.model_copy(update={"needed_by": who(c.table, c.column)}) for c in report.columns]
    return report.model_copy(update={"columns": columns})
