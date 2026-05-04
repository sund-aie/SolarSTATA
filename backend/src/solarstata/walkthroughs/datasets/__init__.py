"""Bundled sample datasets used by the walkthroughs and the smoke test."""

from pathlib import Path

DATASETS_DIR = Path(__file__).parent
CLINIC_PATIENTS_CSV = DATASETS_DIR / "clinic_patients.csv"
CLINIC_PATIENTS_DTA = DATASETS_DIR / "clinic_patients.dta"

__all__ = ["DATASETS_DIR", "CLINIC_PATIENTS_CSV", "CLINIC_PATIENTS_DTA"]
