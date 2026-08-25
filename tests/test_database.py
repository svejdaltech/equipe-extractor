from app.database import engine, ensure_column


def test_ensure_column_adds_missing_column_idempotently():
    # Regression test: Base.metadata.create_all() never ALTERs an existing table,
    # so adding a new model column (like Meeting.end_on) would crash every
    # already-deployed database on first write without this.
    with engine.connect() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS mig_test")
        conn.exec_driver_sql("CREATE TABLE mig_test (id INTEGER PRIMARY KEY)")
        conn.commit()

    try:
        ensure_column("mig_test", "extra", "VARCHAR")
        ensure_column("mig_test", "extra", "VARCHAR")  # must be idempotent, no error

        with engine.connect() as conn:
            columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(mig_test)")}
        assert "extra" in columns
    finally:
        with engine.connect() as conn:
            conn.exec_driver_sql("DROP TABLE mig_test")
            conn.commit()
