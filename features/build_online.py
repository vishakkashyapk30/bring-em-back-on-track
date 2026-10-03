"""Online store check: the online tables are built by dbt (features.f_ptp_online, features.f_customer_online);
this reports their size and as-of time. Run: python -m features.build_online"""

from __future__ import annotations

import duckdb

from common.config import get_settings


def main() -> None:
    con = duckdb.connect(str(get_settings().warehouse_path), read_only=True)
    for t in ("f_ptp_online", "f_customer_online"):
        n, as_of = con.execute(f"SELECT count(*), max(as_of_ts) FROM features.{t}").fetchone()
        print(f"online store features.{t}: {n} rows as of {as_of}")
    con.close()


if __name__ == "__main__":
    main()
