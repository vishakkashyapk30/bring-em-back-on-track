import duckdb

from pipeline.publish import publish


def test_publish_replaces_live_and_reader_sees_new_data(tmp_path):
    live = tmp_path / "warehouse.duckdb"
    building = tmp_path / "building" / "warehouse.duckdb"
    building.parent.mkdir()
    with duckdb.connect(str(live)) as c:
        c.execute("create table t as select 1 as v")
    with duckdb.connect(str(building)) as c:
        c.execute("create table t as select 2 as v")
    publish(building, live)
    assert not building.exists()
    with duckdb.connect(str(live), read_only=True) as c:
        assert c.execute("select v from t").fetchone()[0] == 2


def test_views_survive_publish(tmp_path):
    """Views store the database name; building under the same file name keeps them valid after the swap."""
    live = tmp_path / "warehouse.duckdb"
    building = tmp_path / "building" / "warehouse.duckdb"
    building.parent.mkdir()
    with duckdb.connect(str(building)) as c:
        c.execute("create schema gold; create table gold.t as select 1 as v")
        c.execute("create view gold.v as select * from warehouse.gold.t")
    publish(building, live)
    with duckdb.connect(str(live), read_only=True) as c:
        assert c.execute("select v from gold.v").fetchone()[0] == 1
