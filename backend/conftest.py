import copy
import os


def pytest_configure(config):
    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = "sqlite:///test.db"

    # Django 5.0's BaseContext.__copy__ is broken on Python 3.14 because
    # copy(super()) returns a superproxy instead of a new instance.
    # Patch it here so template rendering works in tests.
    from django.template.context import BaseContext

    def _py314_compat_copy(self):
        new = object.__new__(type(self))
        new.__dict__.update(self.__dict__)
        new.dicts = self.dicts[:]
        return new

    BaseContext.__copy__ = _py314_compat_copy
