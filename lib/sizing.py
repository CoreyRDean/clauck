"""Shared sizing helpers for clauck.

Single source of truth for turning a task complexity scale (0.0–1.0) into
concrete execution parameters: (model, effort, max_turns, max_budget_usd).

Imported by both the CLI (lib/clauck) and scheduler.py so doctor invocations,
natural-language-created jobs, scheduled firings, and marketplace installs
all derive parameters from the same formula.

Cost is a first-class transparent policy per INTENT.md §3 non-negotiable #4.
Every number in this module traces to Anthropic API list prices at the
Claude 4.x era (haiku $1/$5 per MTok; sonnet $3/$15; opus $15/$75) with
context-growth and headroom folded in explicitly, so a reader can audit
the arithmetic without running a session.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional


# ── Scale → params lookup table ────────────────────────────────────────────
#
# Each entry: (scale_ceiling, model, effort, turns, base_rate_per_turn_usd)
#
# base_rate_per_turn_usd is the effective steady-state cost per turn for the
# model+effort combo. It already includes tool-chain overhead and a modest
# allowance for output tokens. It does NOT include context-growth (that's
# applied as a separate multiplier in compute_sizing) or context-injection
# tax (paid as input tokens on every turn based on the user-provided context
# size, added by compute_sizing).
#
# The bands are monotone in every dimension so that bumping the scale never
# downgrades any parameter. Adjust this table to retune — do not compute
# model/effort/turns in multiple places.

SCALE_PARAMS: list[tuple[float, str, str, int, float]] = [
    # ceiling   model     effort    turns  base rate (steady-state $/turn)
    (0.10,     "haiku",   "medium",   4,   0.015),
    (0.20,     "haiku",   "high",     8,   0.020),
    (0.35,     "haiku",   "high",    14,   0.025),
    (0.50,     "sonnet",  "medium",  18,   0.055),
    (0.65,     "sonnet",  "high",    25,   0.070),
    (0.80,     "sonnet",  "high",    40,   0.090),
    (0.90,     "opus",    "high",    60,   0.200),
    (1.00,     "opus",    "high",   100,   0.300),
]


# Anthropic API input rates ($ per million input tokens) — used to compute
# the context-injection tax (user context paid as input on every turn).
# Matches published Claude 4.x API pricing.
INPUT_RATE_PER_MTOK: dict[str, float] = {
    "haiku":  1.0,
    "sonnet": 3.0,
    "opus":  15.0,
}


# Default doctor config values (also the baseline for any job-sizing path
# that doesn't override). User can change these in .clauck.config.json.
DEFAULT_DOCTOR_CONFIG: dict = {
    "min_budget_usd": 0.05,
    "max_budget_usd": 10.00,
    "headroom_multiplier": 1.3,
    "scale_skew": 0.0,
    "auto_skew_increment": 0.05,
    "auto_skew_cap": 0.30,
    "auto_skew_bumps_total": 0,
    # Per-turn context growth rate: each turn's input grows ~1.5% over the
    # previous as tool results accumulate. The sizing formula uses a
    # midpoint-average multiplier (1 + turns × growth / 2) so the derived
    # budget represents the expected total cost, not the cost-at-last-turn.
    "context_growth_per_turn": 0.015,
}


# Legacy defaults when a job declares neither `complexity` nor any explicit
# param — keeps pre-scale jobs working unchanged.
LEGACY_DEFAULTS: dict = {
    "model": "",          # empty → claude CLI default
    "effort": "high",
    "max_turns": 50,
    "max_budget_usd": 2.00,
}


# ── Token estimation ───────────────────────────────────────────────────────


def estimate_tokens(text: str) -> int:
    """Rough token count. ~4 chars/token is the standard heuristic for English.

    Overestimates slightly for code-heavy text (shorter tokens) and
    underestimates for whitespace-heavy text. Close enough for sizing decisions
    where the signal is orders of magnitude.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


# ── Scale → params ─────────────────────────────────────────────────────────


def _clamp_scale(scale: float) -> float:
    try:
        s = float(scale)
    except (TypeError, ValueError):
        return 0.5
    if s < 0.0:
        return 0.0
    if s > 1.0:
        return 1.0
    return s


def scale_to_params(scale: float) -> tuple[str, str, int, float]:
    """Map a complexity scale [0.0, 1.0] to (model, effort, turns, base_rate).

    Lookup via SCALE_PARAMS bands. The first band whose ceiling >= scale wins.
    Out-of-range scales are clamped.
    """
    s = _clamp_scale(scale)
    for ceiling, model, effort, turns, rate in SCALE_PARAMS:
        if s <= ceiling:
            return model, effort, turns, rate
    # Fall-through (should be unreachable if SCALE_PARAMS ends at 1.0)
    last = SCALE_PARAMS[-1]
    return last[1], last[2], last[3], last[4]


# ── Budget computation ─────────────────────────────────────────────────────


def compute_sizing(
    scale: float,
    context_tokens: int,
    config: Optional[dict] = None,
) -> dict:
    """Derive full sizing from a complexity scale and a rough context size.

    Returns a dict with keys:
        model, effort, max_turns, max_budget_usd,
        base_cost, context_cost, headroom, skew_applied, scale_effective,
        explanation (human-readable one-liner)

    Math:
        effective_scale = clamp(scale + scale_skew, 0, 1)
        (model, effort, turns, rate) = scale_to_params(effective_scale)
        growth       = 1 + turns × context_growth_per_turn / 2   (midpoint avg)
        base_cost    = turns × rate × growth
        context_cost = turns × context_tokens × INPUT_RATE_PER_MTOK[model] / 1e6
        raw_budget   = (base_cost + context_cost) × headroom_multiplier
        max_budget   = clamp(raw_budget, min_budget_usd, max_budget_usd)

    The /2 in the growth factor converts the per-turn growth rate into the
    midpoint-average multiplier over a session of N turns: if per-turn input
    grows by G×base each turn, the session-total cost is approximately
    N × base × (1 + N × G / 2), not N × base × (1 + N × G).
    """
    cfg = {**DEFAULT_DOCTOR_CONFIG, **(config or {})}

    skew = float(cfg.get("scale_skew", 0.0) or 0.0)
    effective = _clamp_scale(float(scale) + skew)
    model, effort, turns, rate = scale_to_params(effective)

    growth = 1.0 + turns * float(cfg.get("context_growth_per_turn", 0.015)) / 2.0
    base_cost = turns * rate * growth

    input_rate = INPUT_RATE_PER_MTOK.get(model, 1.0)
    ctx_cost = turns * max(0, int(context_tokens)) * input_rate / 1_000_000.0

    headroom = float(cfg.get("headroom_multiplier", 1.3))
    raw = (base_cost + ctx_cost) * headroom

    lo = float(cfg.get("min_budget_usd", 0.05))
    hi = float(cfg.get("max_budget_usd", 5.00))
    budget = max(lo, min(raw, hi))

    explanation = (
        f"scale={_clamp_scale(float(scale)):.2f}"
        + (f"+skew{skew:+.2f}" if abs(skew) > 1e-9 else "")
        + f" → {model}/{effort}, {turns} turns, "
          f"base ${base_cost:.2f}"
        + (f" + ctx ${ctx_cost:.2f}" if ctx_cost >= 0.005 else "")
        + f" × {headroom:.2f} headroom = ${budget:.2f}"
        + (f" (clamped from ${raw:.2f})" if abs(raw - budget) > 0.005 else "")
    )

    return {
        "model": model,
        "effort": effort,
        "max_turns": int(turns),
        "max_budget_usd": round(budget, 2),
        "base_cost": round(base_cost, 4),
        "context_cost": round(ctx_cost, 4),
        "headroom": headroom,
        "skew_applied": skew,
        "scale_effective": effective,
        "explanation": explanation,
    }


# ── Frontmatter → resolved params ──────────────────────────────────────────


def resolve_params(
    frontmatter: dict,
    context_tokens: int = 0,
    config: Optional[dict] = None,
) -> dict:
    """Resolve (model, effort, max_turns, max_budget_usd) from frontmatter.

    Rules (per field):
      1. Explicit frontmatter value → use it (override wins).
      2. `complexity` present → derive via compute_sizing.
      3. Neither → fall back to LEGACY_DEFAULTS.

    Returns a dict with keys:
        model, effort, max_turns, max_budget_usd,
        provenance (per-field: "override" | "derived" | "default"),
        sizing (the full compute_sizing dict if complexity was used, else None)

    Callers can inspect `provenance` to render "derived" vs "override" labels.
    """
    fm = frontmatter or {}
    complexity_raw = fm.get("complexity")
    has_complexity = complexity_raw is not None

    # Normalize explicit overrides. An explicit "" string still counts as
    # override for model (means "no --model flag") — but only if the YAML
    # actually set the key, which _parse_fm_block does not distinguish from
    # absence for strings. Resolution: treat only non-empty strings for
    # model as overrides; for numeric fields, presence at all counts.
    fm_model = fm.get("model")
    fm_effort = fm.get("effort")
    fm_turns = fm.get("max_turns")
    fm_budget = fm.get("max_budget_usd")

    explicit_model = isinstance(fm_model, str) and fm_model.strip() != ""
    explicit_effort = isinstance(fm_effort, str) and fm_effort.strip() != ""
    explicit_turns = fm_turns is not None
    explicit_budget = fm_budget is not None

    sizing = None
    if has_complexity:
        try:
            sizing = compute_sizing(float(complexity_raw), int(context_tokens), config)
        except (TypeError, ValueError):
            sizing = None

    provenance: dict = {}
    resolved: dict = {}

    def _pick(field: str, explicit_flag: bool, explicit_value, derived_key: str):
        if explicit_flag:
            provenance[field] = "override"
            return explicit_value
        if sizing is not None:
            provenance[field] = "derived"
            return sizing[derived_key]
        provenance[field] = "default"
        return LEGACY_DEFAULTS[field]

    resolved["model"] = _pick("model", explicit_model, str(fm_model).strip() if explicit_model else "", "model")
    resolved["effort"] = _pick("effort", explicit_effort, str(fm_effort).strip() if explicit_effort else "", "effort")
    try:
        turns_val = int(fm_turns) if explicit_turns else None
    except (TypeError, ValueError):
        turns_val = None
        explicit_turns = False
    resolved["max_turns"] = _pick("max_turns", explicit_turns, turns_val, "max_turns")
    try:
        budget_val = float(fm_budget) if explicit_budget else None
    except (TypeError, ValueError):
        budget_val = None
        explicit_budget = False
    resolved["max_budget_usd"] = _pick("max_budget_usd", explicit_budget, budget_val, "max_budget_usd")

    return {
        **resolved,
        "provenance": provenance,
        "sizing": sizing,
    }


# ── Config load/save ───────────────────────────────────────────────────────


def _config_path() -> Path:
    return Path(os.path.expanduser("~/.clauck/.clauck.config.json"))


def load_doctor_config(path: Optional[Path] = None) -> dict:
    """Load the full config file; return the `doctor` block merged with defaults.

    Returns just the doctor sub-config (with defaults applied for missing keys),
    not the full config file. Use load_full_config() to get everything.
    """
    full = load_full_config(path)
    doctor = full.get("doctor", {})
    if not isinstance(doctor, dict):
        doctor = {}
    return {**DEFAULT_DOCTOR_CONFIG, **doctor}


def load_full_config(path: Optional[Path] = None) -> dict:
    """Load the full config file, returning {} if missing or malformed."""
    p = path or _config_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_doctor_config(updates: dict, path: Optional[Path] = None) -> dict:
    """Atomically merge `updates` into the config file's `doctor` block.

    Preserves all other top-level keys in the config file. Returns the new
    doctor sub-config (after merge + defaults applied).

    Write is atomic via tempfile + os.replace so a partial write never
    corrupts the config.
    """
    p = path or _config_path()
    full = load_full_config(p)
    doctor = full.get("doctor", {})
    if not isinstance(doctor, dict):
        doctor = {}
    doctor.update(updates)
    full["doctor"] = doctor

    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".config.", suffix=".json", dir=str(p.parent)
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(full, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, p)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return {**DEFAULT_DOCTOR_CONFIG, **doctor}


# ── Auto-skew helpers ──────────────────────────────────────────────────────


def apply_auto_skew_on_budget_hit(config_path: Optional[Path] = None) -> dict:
    """Bump scale_skew by auto_skew_increment, capped at auto_skew_cap.

    Invoked by cmd_doctor when it detects a budget truncation. Returns the
    updated doctor config for logging/display.
    """
    cfg = load_doctor_config(config_path)
    inc = float(cfg.get("auto_skew_increment", 0.05))
    cap = float(cfg.get("auto_skew_cap", 0.30))
    cur = float(cfg.get("scale_skew", 0.0))
    new_skew = min(cap, cur + inc)
    bumps = int(cfg.get("auto_skew_bumps_total", 0)) + 1
    return save_doctor_config(
        {"scale_skew": round(new_skew, 3), "auto_skew_bumps_total": bumps},
        config_path,
    )


def apply_auto_skew_decay(config_path: Optional[Path] = None) -> dict:
    """Decay scale_skew by half the increment on a clean run, floored at 0.

    Keeps the skew self-balancing: it rises on truncation, falls on success.
    """
    cfg = load_doctor_config(config_path)
    inc = float(cfg.get("auto_skew_increment", 0.05))
    cur = float(cfg.get("scale_skew", 0.0))
    if cur <= 0.0:
        return cfg
    new_skew = max(0.0, cur - inc / 2.0)
    return save_doctor_config(
        {"scale_skew": round(new_skew, 3)},
        config_path,
    )
