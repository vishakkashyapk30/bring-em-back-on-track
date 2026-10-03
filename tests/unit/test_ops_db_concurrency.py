from concurrent.futures import ProcessPoolExecutor

from common.db import init_ops_db


def test_concurrent_init_does_not_lock(tmp_path):
    path = tmp_path / "ops.db"
    with ProcessPoolExecutor(max_workers=4) as ex:
        list(ex.map(init_ops_db, [path] * 8))
    assert path.exists()
