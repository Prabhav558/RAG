"""Frozen copy of the Cycle 2 schema (commit 22c3800), used to test upgrading real pilot databases."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
