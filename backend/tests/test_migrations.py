"""Production readiness: Alembic builds exactly the model schema, and upgrades real Cycle 2 pilot databases."""

import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

BACKEND = Path(__file__).resolve().parents[1]
PG = os.environ.get("SCORECARD_MIGRATION_TEST_DB_URL")


def _fresh_url() -> str:
    if PG:
        eng = create_engine(PG, isolation_level="AUTOCOMMIT")
        with eng.connect() as c:
            c.execute(text("drop schema public cascade"))
            c.execute(text("create schema public"))
        return PG
    return f"sqlite:///{tempfile.mkdtemp()}/mig.db"


@pytest.fixture()
def alembic_for(monkeypatch):
    def make(url):
        monkeypatch.setenv("SCORECARD_DB_URL", url)
        import app.db

        importlib.reload(app.db)
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "migrations"))
        return cfg

    yield make
    monkeypatch.undo()
    import app.db

    importlib.reload(app.db)


def _diff(url):
    from app.models import Base

    with create_engine(url).connect() as conn:
        return compare_metadata(MigrationContext.configure(conn), Base.metadata)


def test_upgrade_from_empty_matches_models_and_downgrades(alembic_for):
    url = _fresh_url()
    cfg = alembic_for(url)
    command.upgrade(cfg, "head")
    assert _diff(url) == []
    command.downgrade(cfg, "base")
    assert set(inspect(create_engine(url)).get_table_names()) <= {"alembic_version"}


def test_cycle2_pilot_database_upgrades_with_its_data(alembic_for):
    """A database created by the Cycle 2 code (create_all, no Alembic) is stamped and upgraded in place."""
    url = _fresh_url()
    sys.path.insert(0, str(BACKEND))
    from migrations.cycle2_models.models import Base as Cycle2Base

    engine = create_engine(url)
    Cycle2Base.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(text("insert into rating_scale (id, code, name, min_value, max_value) values (1,'0-10','s',0,10)"))
        c.execute(text("insert into rating_band (id, scale_id, label, lower_bound, color_hex, font_hex, rag) "
                       "values (1,1,'Low',0,'#C00000','#FFFFFF','RED')"))
        c.execute(text("insert into subject_type (id, code, name) values (1,'task','Task')"))
        c.execute(text("insert into scorecard (id, code, name, subject_type_id, tags, is_template, created_at) "
                       "values (1,'legacy','Legacy card',1,'[]',false,CURRENT_TIMESTAMP)"))
        c.execute(text("insert into scorecard_version (id, scorecard_id, version_no, status, purpose, scope, objective, "
                       "rating_scale_id, target_score, aggregation, max_depth, qtc_enabled, created_at) "
                       "values (1,1,1,'draft','p','s','o',1,8,'weighted_mean',4,false,CURRENT_TIMESTAMP)"))
        c.execute(text("insert into evaluation (id, version_id, subject_name, evaluator_type, is_private, status, "
                       "target_score, attempt_no, origin, gate_failures, created_at) values "
                       "(1,1,'Old work','human',false,'completed',8,1,'app','[{\"code\": \"1\"}]',CURRENT_TIMESTAMP)"))
    cfg = alembic_for(url)
    command.stamp(cfg, "0001_cycle2")
    command.upgrade(cfg, "head")
    assert _diff(url) == []
    with create_engine(url).begin() as c:
        assert c.execute(text("select gate_failure_count, row_version from evaluation")).one() == (1, 1)
        assert c.execute(text("select required_judges, requires_review from scorecard_version "
                              "join scorecard on scorecard.id = scorecard_version.scorecard_id")).one() == (1, False)
        c.execute(text("update scorecard_version set status = 'in_review' where id = 1"))  # new CHECK allows it
        with pytest.raises(Exception):
            with c.begin_nested():
                c.execute(text("update scorecard_version set required_judges = 9 where id = 1"))  # new CHECK bounds
