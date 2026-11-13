"""Install the actual wheel outside the checkout; pinned SDK/Fluent resolve from PyPI."""

import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    env = pathlib.Path(tmp) / "venv"
    subprocess.run(["uv", "venv", str(env)], check=True)
    python = str(env / "bin/python")
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            python,
            str(next((root / "dist").glob("*.whl"))),
        ],
        check=True,
    )
    subprocess.run(
        [
            python,
            "-c",
            "from importlib.resources import files; from django.conf import settings; settings.configure(INSTALLED_APPS=['vatly_django'], DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}); import django; django.setup(); from django.core.management import call_command; call_command('migrate', verbosity=0); from vatly_django.models import BillingScope; assert BillingScope.objects.count() == 0; assert files('vatly_django').joinpath('py.typed').is_file(); print('Isolated wheel, migrations and py.typed OK')",
        ],
        cwd=tmp,
        check=True,
    )
