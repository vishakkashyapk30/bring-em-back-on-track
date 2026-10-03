import duckdb

from pipeline.publish import publish


def test_publish_replaces_live_and_reader_sees_new_data(tmp_path):
    live, building = tmp_path / "warehouse.duckdb", tmp_path / "warehouse.building.duckdb"
    with duckdb.connect(str(live)) as c:
        c.execute("create table t as select 1 as v")
    with duckdb.connect(str(building)) as c:
        c.execute("create table t as select 2 as v")
    publish(building, live)
    assert not building.exists()
    with duckdb.connect(str(live), read_only=True) as c:
        assert c.execute("select v from t").fetchone()[0] == 2
