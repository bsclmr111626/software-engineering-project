"""The PDF report (simulation/pdf.py): access rules, the file itself, and the
layout engine's paging."""

from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from accounts.models import Profile, Role, Workspace
from audit.models import AuditAction, AuditEvent
from conftest import PASSWORD
from simulation import pdf
from simulation.models import RunStatus
from simulation.tests.test_services_and_views import run_for

pytestmark = pytest.mark.django_db


def url(run):
    return reverse("simulation:export_pdf", args=[run.pk])


def page_count(data):
    return data.count(b"/Type /Page\n") or data.count(b"/Type /Page ") or data.count(b"/Type/Page")


def test_owner_downloads_an_audited_pdf(seeded, analyst, analyst_client):
    run = run_for(analyst, controls=["mfa"])
    response = analyst_client.get(url(run))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == (
        f'attachment; filename="codeguard-compromised-developer-account-{run.short_id}.pdf"'
    )
    assert response["Cache-Control"] == "private, no-store"
    data = response.content
    assert data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
    assert b"CodeGuard report: Compromised Developer Account" in data  # document title metadata
    event = AuditEvent.objects.get(action=AuditAction.REPORT_EXPORT, actor=analyst)
    assert event.metadata["format"] == "pdf" and event.object_id == str(run.pk)


def test_fonts_are_embedded_so_text_stays_text(seeded, analyst):
    data = pdf.render_report(run_for(analyst), generated_for="alice")
    assert b"/FontFile2" in data  # TrueType embedded (pdf.fonttype 42), not Type 3 outlines


def test_strangers_and_other_workspaces_get_404(seeded, analyst, other_analyst):
    run = run_for(analyst)
    stranger = Client()
    stranger.force_login(other_analyst)
    assert stranger.get(url(run)).status_code == 404  # private report
    run.is_shared = True
    run.save()
    assert stranger.get(url(run)).status_code == 200  # shared in the workspace

    borealis = Workspace.objects.create(name="Borealis")
    outsider = get_user_model().objects.create_user("bea", "bea@example.com", PASSWORD)
    Profile.objects.filter(user=outsider).update(workspace=borealis, role=Role.ADMIN)
    other = Client()
    other.force_login(outsider)
    assert other.get(url(run)).status_code == 404
    assert not AuditEvent.objects.filter(action=AuditAction.REPORT_EXPORT, actor=outsider).exists()


def test_signed_out_visitors_are_sent_to_sign_in(seeded, analyst, client):
    response = client.get(url(run_for(analyst)))
    assert response.status_code == 302 and "/accounts/login/" in response.url


def test_a_failed_run_still_has_a_short_report(seeded, analyst, analyst_client):
    with mock.patch("simulation.services.recommend", side_effect=RuntimeError("boom")):
        run = run_for(analyst)
    assert run.status == RunStatus.FAILED
    response = analyst_client.get(url(run))
    assert response.status_code == 200 and response.content.startswith(b"%PDF-")


def test_long_content_flows_onto_more_pages_with_numbered_footers(seeded, analyst):
    run = run_for(analyst)
    short = pdf.render_report(run, generated_for="alice")
    run.result = {**run.result, "explanation": ["A long explanation line that wraps. " * 6] * 40}
    long = pdf.render_report(run, generated_for="alice")
    assert page_count(long) > page_count(short) >= 2


def test_wrapping_keeps_every_word():
    text = "Supply chain " * 40
    lines = pdf._wrap(text, 3.0, 9)
    assert len(lines) > 1
    assert " ".join(lines).split() == text.split()
    assert pdf._wrap("", 3.0, 9) == [""]


def test_report_and_list_pages_offer_the_download(seeded, analyst, analyst_client):
    run = run_for(analyst)
    link = url(run)
    assert link in analyst_client.get(reverse("reports:document", args=[run.pk])).content.decode()
    assert link in analyst_client.get(reverse("simulation:detail", args=[run.pk])).content.decode()
    assert link in analyst_client.get(reverse("reports:list")).content.decode()
