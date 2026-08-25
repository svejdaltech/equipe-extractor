import os
import tempfile

os.environ.setdefault("AUTH_USERNAME", "user")
os.environ.setdefault("AUTH_PASSWORD", "pass")
_test_db_dir = tempfile.mkdtemp(prefix="equipe-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_test_db_dir}/equipe_test.db")

import pytest


@pytest.fixture(autouse=True)
def _reset_db():
    from app.database import Base, engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
