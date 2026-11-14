"""Account emails: verification, invitations and security notices.

Each message is a plain-text template pair in ``templates/emails/``
(``<name>_subject.txt`` and ``<name>.txt``). Sending never raises: a failure
is logged without the message content and reported to the caller as False,
so a view can tell the user instead of showing an error page.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

logger = logging.getLogger("codeguard.email")


def send(template, to, context):
    context = {"site_name": "CodeGuard", "contact_email": settings.CODEGUARD_CONTACT_EMAIL, **context}
    subject = " ".join(render_to_string(f"emails/{template}_subject.txt", context).split())
    body = render_to_string(f"emails/{template}.txt", context)
    try:
        EmailMessage(subject=subject, body=body, to=[to]).send(fail_silently=False)
    except Exception as error:  # provider, network or configuration problem
        logger.error("account email not sent template=%s error=%s", template, type(error).__name__)
        return False
    return True


def absolute(request, path):
    return request.build_absolute_uri(path)
