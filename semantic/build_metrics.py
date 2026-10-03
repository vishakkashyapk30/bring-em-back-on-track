"""Generate semantic/metrics/*.yaml (MetricFlow-shaped) from metric_definitions.

Fields used: metric_id, metric_name, business_definition, formula, grain, time_basis, default_filters,
unit, good_direction, synonyms, source_tables, owner, certified_flag.
"""


def main() -> None:
    raise NotImplementedError("TODO(WS-B): read bronze/metric_definitions.parquet -> metrics yaml")


if __name__ == "__main__":
    main()
