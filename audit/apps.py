from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"

    def ready(self):
        from . import integrity

        # After every migrate, for any app: see audit/integrity.py.
        post_migrate.connect(integrity.install, dispatch_uid="audit.integrity.install")
