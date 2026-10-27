"""Shared pytest fixtures.

pytest-django creates a fresh, temporary test database for each session, so
these fixtures never touch the developer's db.sqlite3.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from accounts.models import Profile, Role

PASSWORD = "Str0ng-test-passphrase!"


@pytest.fixture
def seeded(db):
    call_command("seed_codeguard", verbosity=0)


def _make_user(username, role):
    user = get_user_model().objects.create_user(username=username, email=f"{username}@example.com", password=PASSWORD)
    Profile.objects.update_or_create(user=user, defaults={"role": role})
    return user


@pytest.fixture
def analyst(db):
    return _make_user("alice", Role.ANALYST)


@pytest.fixture
def other_analyst(db):
    return _make_user("bob", Role.ANALYST)


@pytest.fixture
def viewer(db):
    return _make_user("victor", Role.VIEWER)


@pytest.fixture
def admin_user(db):
    return _make_user("ada", Role.ADMIN)


@pytest.fixture
def analyst_client(client, analyst):
    client.force_login(analyst)
    return client


@pytest.fixture
def viewer_client(client, viewer):
    client.force_login(viewer)
    return client


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client
