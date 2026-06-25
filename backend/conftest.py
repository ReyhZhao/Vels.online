import copy
import os
import sys


def pytest_configure(config):
    if not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = "sqlite:///test.db"

    # WeasyPrint (incident report PDF rendering, ADR-0029) loads its native libs —
    # pango/cairo/gobject — via the dynamic loader. On a macOS dev host those come
    # from Homebrew; make the report renderer smoke test work with a plain `pytest`
    # by adding Homebrew's lib dir to the fallback search path before WeasyPrint is
    # imported. No-op off darwin / where the path is absent. In Docker (Linux) the
    # libs are on the default loader path, installed via the Dockerfile.
    if sys.platform == "darwin":
        for libdir in ("/opt/homebrew/lib", "/usr/local/lib"):
            if os.path.isdir(libdir):
                existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
                parts = [p for p in existing.split(":") if p]
                if libdir not in parts:
                    parts.append(libdir)
                os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(parts)

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
