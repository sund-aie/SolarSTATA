"""Synthetic dental clinic dataset for walkthroughs and the smoke test.

400 fictional patients. The data is fake but the structural relationships
are realistic — smoking → more periodontal depth + caries; higher
education → more brushing → less plaque; age → more periodontal depth;
diabetes → higher gingival index.

Adds ~7% MCAR missingness on plaque_index, gingival_index, and
brushing_freq, and 6 obvious dirty rows (patient_id ≥ 9000) with
impossible values so the "Clean and recode" walkthrough has something
concrete to drop.

Reproducible: fixed seed = 1985 (StataCorp founded 1985).

Run:

    python -m solarstata.walkthroughs.datasets.generate

Outputs:

    clinic_patients.csv
    clinic_patients.dta
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import pyreadstat

SEED = 1985
N_REAL = 400
N_DIRTY = 6
MISSING_RATE = 0.07

EDUCATION_LEVELS = ["primary", "secondary", "university", "postgrad"]
EDUCATION_PROBS = [0.15, 0.40, 0.30, 0.15]
SEX_PROBS = {"M": 0.48, "F": 0.52}


def generate(seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # ---- demographics -------------------------------------------------------
    age = np.clip(rng.gamma(shape=4, scale=8, size=N_REAL) + 18, 18, 80).round().astype(int)
    sex = rng.choice(list(SEX_PROBS.keys()), size=N_REAL, p=list(SEX_PROBS.values()))
    education = rng.choice(EDUCATION_LEVELS, size=N_REAL, p=EDUCATION_PROBS)
    education_score = pd.Series(education).map(
        {"primary": 0, "secondary": 1, "university": 2, "postgrad": 3}
    ).values

    # ---- comorbidities & lifestyle ------------------------------------------
    smoking = rng.binomial(1, 0.25, size=N_REAL)
    diabetes_p = 0.06 + 0.004 * (age - 18)  # rises with age
    diabetes = rng.binomial(1, np.clip(diabetes_p, 0, 0.35), size=N_REAL)

    # brushing_freq: integer 0-3, biased upward by education
    brushing_logit = -1.0 + 0.7 * education_score + rng.normal(0, 0.5, size=N_REAL)
    brushing_p = 1 / (1 + np.exp(-brushing_logit))
    brushing_freq = np.clip(np.round(brushing_p * 3 + rng.uniform(0, 0.6, N_REAL)), 0, 3).astype(int)

    last_visit_months = np.clip(
        rng.exponential(scale=18, size=N_REAL).astype(int), 0, 60
    )

    # ---- oral health outcomes ------------------------------------------------
    # plaque_index 0-3, lower with more brushing, higher with smoking
    plaque_index = np.clip(
        2.2 - 0.45 * brushing_freq + 0.25 * smoking + rng.normal(0, 0.35, size=N_REAL),
        0.0, 3.0,
    )

    # gingival_index 0-3, tracks plaque + diabetes + a noise floor
    gingival_index = np.clip(
        0.6 * plaque_index + 0.45 * diabetes + 0.2 + rng.normal(0, 0.30, size=N_REAL),
        0.0, 3.0,
    )

    # periodontal_pocket_depth_mm 1-8: rises with age + smoking
    periodontal_pocket_depth_mm = np.clip(
        2.0 + 0.025 * (age - 18) + 0.9 * smoking + rng.normal(0, 0.6, size=N_REAL),
        1.0, 8.0,
    )

    # num_decayed_teeth Poisson-ish, rate driven by plaque + smoking
    decay_rate = np.clip(0.4 + 1.2 * plaque_index + 0.8 * smoking, 0.05, 12)
    num_decayed_teeth = np.minimum(rng.poisson(decay_rate), 28)

    # caries: derived from decay > 0 with a tiny flip-noise
    caries_raw = (num_decayed_teeth > 0).astype(int)
    flip = rng.uniform(0, 1, size=N_REAL) < 0.03
    caries = np.where(flip, 1 - caries_raw, caries_raw).astype(int)

    df = pd.DataFrame({
        "patient_id": np.arange(1001, 1001 + N_REAL, dtype=int),
        "age": age,
        "sex": sex,
        "education_level": education,
        "smoking": smoking,
        "diabetes": diabetes,
        "brushing_freq": brushing_freq,
        "last_visit_months": last_visit_months,
        "plaque_index": plaque_index.round(2),
        "gingival_index": gingival_index.round(2),
        "periodontal_pocket_depth_mm": periodontal_pocket_depth_mm.round(2),
        "num_decayed_teeth": num_decayed_teeth.astype(int),
        "caries": caries,
    })

    # ---- inject MCAR missingness on three clinical columns -------------------
    for col in ("plaque_index", "gingival_index", "brushing_freq"):
        miss_mask = rng.uniform(0, 1, size=N_REAL) < MISSING_RATE
        df.loc[miss_mask, col] = np.nan

    # ---- append dirty test rows for the cleaning walkthrough -----------------
    dirty = pd.DataFrame({
        "patient_id":                       [9001, 9002, 9003, 9004, 9005, 9006],
        "age":                              [999,    35,    -5,    47,   120,    52],
        "sex":                              ["M",  "X",  "F",   "F",  "M",   "?"],
        "education_level":                  ["primary","secondary","university","postgrad","unknown","secondary"],
        "smoking":                          [0,     1,     0,     1,    -1,     1],
        "diabetes":                         [0,     0,     0,     1,     0,     2],
        "brushing_freq":                    [-1,    99,     2,     3,     1,     0],
        "last_visit_months":                [12,    -3,    24,   999,     6,    18],
        "plaque_index":                     [1.5,   8.0,   1.2,   2.1,  -0.5,   1.8],
        "gingival_index":                   [1.0,   1.4,  -2.0,   1.5,   1.2,   9.9],
        "periodontal_pocket_depth_mm":      [3.0,   4.0,   2.5,  15.0,   3.5,   2.8],
        "num_decayed_teeth":                [2,     3,    99,     5,     1,    -1],
        "caries":                           [1,     1,     1,     1,     0,     1],
    })

    full = pd.concat([df, dirty], ignore_index=True)
    return full


COLUMN_LABELS = {
    "patient_id":                  "Anonymized patient identifier",
    "age":                         "Age in years at intake",
    "sex":                         "Self-reported sex",
    "education_level":             "Highest completed education",
    "smoking":                     "Current smoker (1=yes, 0=no)",
    "diabetes":                    "Diabetes diagnosis (1=yes, 0=no)",
    "brushing_freq":               "Self-reported brushing times per day",
    "last_visit_months":           "Months since last dental visit",
    "plaque_index":                "Silness-Loe plaque index (0-3)",
    "gingival_index":              "Loe-Silness gingival index (0-3)",
    "periodontal_pocket_depth_mm": "Mean pocket probing depth (mm)",
    "num_decayed_teeth":           "Count of decayed teeth at exam",
    "caries":                      "Any caries present (derived)",
}


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False)


def write_dta(df: pd.DataFrame, path: Path) -> None:
    pyreadstat.write_dta(
        df,
        str(path),
        column_labels=[COLUMN_LABELS.get(c, "") for c in df.columns],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Where to write clinic_patients.csv / .dta",
    )
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    df = generate(seed=args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.out_dir / "clinic_patients.csv"
    dta_path = args.out_dir / "clinic_patients.dta"
    write_csv(df, csv_path)
    write_dta(df, dta_path)

    print(f"Wrote {csv_path} ({len(df)} rows, {df.shape[1]} cols)")
    print(f"Wrote {dta_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
