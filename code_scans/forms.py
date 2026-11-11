
from pathlib import Path

from django import forms
from django.conf import settings


class CodeScanUploadForm(forms.Form):
    project_name = forms.CharField(
        label="Project name",
        max_length=150,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "e.g. Inventory Management System",
            }
        ),
    )

    archive = forms.FileField(
        label="Source code ZIP file",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".zip,application/zip",
            }
        ),
    )

    def clean_archive(self):
        archive = self.cleaned_data["archive"]

        if Path(archive.name).suffix.lower() != ".zip":
            raise forms.ValidationError(
                "Please upload a ZIP archive (.zip)."
            )

        max_size = getattr(
            settings,
            "CODE_SCAN_MAX_UPLOAD_SIZE",
            25 * 1024 * 1024,
        )

        if archive.size > max_size:
            max_mb = max_size // (1024 * 1024)
            raise forms.ValidationError(
                f"The ZIP file must not exceed {max_mb} MB."
            )

        return archive
