from django.contrib.auth.backends import ModelBackend

from .throttling import canonical_username


class UsernameOrEmailBackend(ModelBackend):
    """Sign in with either the username or the account's email address.

    Email addresses are unique ignoring case (accounts migration 0008), so an
    address names at most one account. Everything else, including refusing
    inactive (suspended) accounts, is Django's ModelBackend.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is not None:
            username = canonical_username(username)
        return super().authenticate(request, username=username, password=password, **kwargs)
