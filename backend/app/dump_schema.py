"""Print the DDL for the current models: python -m app.dump_schema > ../docs/schema.sql"""

from sqlalchemy import create_mock_engine

from .db import Base
from . import models  # noqa: F401


def main():
    out = []
    engine = create_mock_engine("sqlite://", lambda sql, *a, **k: out.append(str(sql.compile(dialect=engine.dialect)).strip() + ";\n"))
    Base.metadata.create_all(engine, checkfirst=False)
    print("-- Generated from backend/app/models.py. Do not edit by hand.\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
