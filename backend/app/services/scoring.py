"""Module 3 - Deterministic Hazard, Vulnerability, Risk & Priority scoring.

Implements the documented Nakshatra deterministic engines in a **pure** (side
effect free) style so they can be invoked both by a live worker and by our unit
tests.

Architecture rule (Rule 3) is respected here by separation of concerns:

* hazard sub-scores come ONLY from physical ``HazardReading`` evidence;
* the vulnerability score is computed ONLY from demographic / service-access data
  and is NEVER blended into hazard;
* ``risk = composite_hazard * vulnerability`` is the single place they meet.

Missing Data (Rule 2): every function returns a score whose ``value`` is ``None``
whenever the underlying evidence is absent. Weighted averaging of composite
hazard iterates over *available* contributors only, dividing by the sum of their
weights - a missing component does not pull the average toward 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.enums import HazardType, RelocationPriority, ZoneBand
from app.schemas.enums import FeatureStatus
from app.services.etl import PhysicalReading


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
@dataclass
class RiskWeights:
    """Tunable engine coefficients. All are experimenter-owned and immutable
    defaults; supply a different instance to vary policy without code edits."""

    # composite hazard weights (only among *available* hazards)
    flood_w: float = 0.35
    landslide_w: float = 0.30
    coastal_w: float = 0.15
    cloudburst_w: float = 0.20

    # zone thresholds (see scoring.run_risk_classification)
    red_threshold: float = 0.60
    yellow_low: float = 0.20
    high_hazard_floor: float = 0.70
    high_vuln_floor: float = 0.65

    # priority blending coefficients (after zone)
    a_hazard: float = 0.75
    b_vulnerability: float = 0.85
    c_history: float = 0.60
    d_exposure: float = 0.55
    e_access_difficulty: float = 0.65


@dataclass
class HazardSubScore:
    """Normalized 0..1 sub-score strictly present-or-absent.

    ``value`` None == evidence missing / not applicable (Rule 2), never 0.0.
    """

    value: Optional[float]
    status: FeatureStatus


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ---------------------------------------------------------------------------
# Normalization helpers (each returns Optional[float] - None kept as-is)
# ---------------------------------------------------------------------------
def _norm_flood(reading: Optional[float], inside: bool = False) -> Optional[float]:
    """Flood from either an inside-footprint marker (1.0) or river km."""
    if reading is None:
        return None
    if inside or reading == 1.0:
        return 1.0
    # river distance km -> nearness score
    return _clip01(math.exp(-reading / 1.8))


def _norm_landslide(raw_index: Optional[float]) -> Optional[float]:
    if raw_index is None:
        return None
    raw = float(raw_index)
    return _clip01(raw / 100.0 if raw > 1.0 else raw)


def _norm_cloudburst(mm_per_event: Optional[float]) -> Optional[float]:
    if mm_per_event is None:
        return None
    # heuristic cap: >= 150 mm event is extreme; scale linearly to it
    return _clip01(float(mm_per_event) / 150.0)


def _norm_coastal(dist_km_from_eroding_coast: Optional[float]) -> Optional[float]:
    if dist_km_from_eroding_coast is None:
        return None
    return _clip01(math.exp(-dist_km_from_eroding_coast / 2.0))


# ---------------------------------------------------------------------------
# Hazard engine
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FloodEvidence:
    river_dist_km: Optional[float]
    inside_inundation: bool = False


@dataclass(frozen=True)
class LandslideEvidence:
    susceptibility_index: Optional[float]  # 0..1 or 0..100 source-agnostic


@dataclass(frozen=True)
class CloudburstEvidence:
    extreme_rainfall_mm: Optional[float]


@dataclass(frozen=True)
class CoastalEvidence:
    eroding_coast_dist_km: Optional[float]


def hazard_flood(ev: FloodEvidence) -> HazardSubScore:
    if ev.inside_inundation:
        return HazardSubScore(1.0, FeatureStatus.AVAILABLE)
    if ev.river_dist_km is not None:
        return HazardSubScore(_norm_flood(ev.river_dist_km), FeatureStatus.AVAILABLE)
    return HazardSubScore(None, FeatureStatus.MISSING)


def hazard_landslide(ev: LandslideEvidence) -> HazardSubScore:
    if ev.susceptibility_index is None:
        return HazardSubScore(None, FeatureStatus.MISSING)
    return HazardSubScore(_norm_landslide(ev.susceptibility_index), FeatureStatus.AVAILABLE)


def hazard_cloudburst(ev: CloudburstEvidence) -> HazardSubScore:
    if ev.extreme_rainfall_mm is None:
        return HazardSubScore(None, FeatureStatus.MISSING)
    return HazardSubScore(_norm_cloudburst(ev.extreme_rainfall_mm), FeatureStatus.AVAILABLE)


def hazard_coastal(ev: CoastalEvidence) -> HazardSubScore:
    if ev.eroding_coast_dist_km is None:
        return HazardSubScore(None, FeatureStatus.NOT_APPLICABLE)
    return HazardSubScore(_norm_coastal(ev.eroding_coast_dist_km), FeatureStatus.AVAILABLE)


def composite_hazard(
    scores: dict[HazardType, HazardSubScore],
    weights: RiskWeights | None = None,
) -> HazardSubScore:
    """Weighted mean over *available* hazard sub-scores only (Rule 2).

    ``sum(weight_i * hazard_i)/sum(weight_i)`` iterates contributors whose value
    is present. Missing/unavailable items contribute neither numerator nor
    denominator, so a missing flood layer cannot bias the average to zero/low.

    Returns ``None``/MISSING when there is no single available hazard reading.
    """
    w = weights or RiskWeights()
    weight_map = {
        HazardType.FLOOD: w.flood_w,
        HazardType.LANDSLIDE: w.landslide_w,
        HazardType.COASTAL_EROSION: w.coastal_w,
        HazardType.CLOUDBURST: w.cloudburst_w,
    }
    num = 0.0
    den = 0.0
    for ht, sub in scores.items():
        if sub.value is None:
            continue
        wi = weight_map.get(ht, 1.0)
        num += wi * sub.value
        den += wi
    if den <= 0:
        return HazardSubScore(None, FeatureStatus.MISSING)
    return HazardSubScore(_clip01(num / den), FeatureStatus.AVAILABLE)


# ---------------------------------------------------------------------------
# Vulnerability engine (kept strictly separate from physical hazard - Rule 3)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class VulnerabilityInput:
    """Demographic / service-access proxies. Optional fractional indicators range
    [0,1]; missing/unknown must be ``None`` (never a fabricated 0)."""

    population_density_idx: Optional[float]      # normalized density vs study area
    housing_quality_score: Optional[float]       # 1=pucca .. 0=poor
    hospital_distance_idx: Optional[float]       # normalized km (1 far away = more vuln)
    road_distance_idx: Optional[float]           # normalized km
    vulnerable_pop_share: Optional[float]        # #scaling of the share of people at risk
    disabled_children_elderly_idx: Optional[float]  # normalized combined demography


def _weighted_avg_01(parts: list[tuple[float, Optional[float]]]) -> HazardSubScore:
    num = 0.0
    den = 0.0
    for w, v in parts:
        if v is None:
            continue
        num += w * _clip01(v)
        den += w
    if den <= 0:
        return HazardSubScore(None, FeatureStatus.MISSING)
    return HazardSubScore(_clip01(num / den), FeatureStatus.AVAILABLE)


def vulnerability_score(
    vi: VulnerabilityInput,
    weights: dict[str, float] | None = None,
) -> HazardSubScore:
    """Composite exposure of people/assets given demographic & access proxies.

    Strictly the converse side of hazard: poorly-housed, dense, demographically
    sensitive settlements or settlements far from services score closer to 1.
    Returns None where insufficient demographic data exist to make a claim.
    """
    w = weights or {
        "density": 0.25,
        "housing": 0.20,
        "hospital": 0.20,
        "road": 0.15,
        "share": 0.10,
        "vulnerable_demog": 0.10,
    }

    # housing quality is reported as score where high means GOOD; invert for
    # vulnerability (we live with an explicit secondary signal to preserve clarity)
    housing_vuln = None if vi.housing_quality_score is None else 1 - vi.housing_quality_score

    return _weighted_avg_01(
        [
            (w["density"], vi.population_density_idx),
            (w["housing"], housing_vuln),
            (w["hospital"], vi.hospital_distance_idx),
            (w["road"], vi.road_distance_idx),
            (w["share"], vi.vulnerable_pop_share),
            (w["vulnerable_demog"], vi.disabled_children_elderly_idx),
        ]
    )


# ---------------------------------------------------------------------------
# Derived composite risk + bands
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RiskResult:
    composite_hazard: HazardSubScore
    vulnerability: HazardSubScore
    risk_score: Optional[float]
    status: FeatureStatus
    zone_band: ZoneBand
    priority: RelocationPriority


def _multiply(a: HazardSubScore, b: HazardSubScore) -> HazardSubScore:
    if a.value is None or b.value is None:
        return HazardSubScore(None, FeatureStatus.MISSING)
    return HazardSubScore(_clip01(a.value * b.value), FeatureStatus.AVAILABLE)


def run_risk_classification(
    composite_hz: HazardSubScore,
    vuln: HazardSubScore,
    weights: RiskWeights | None = None,
) -> RiskResult:
    """Zoning with the documented thresholds:

        RED    : risk >= 0.60  OR  (hazard >= 0.70 AND vuln >= high-vuln-floor)
        YELLOW : 0.20 <= risk < 0.60
        GREEN  : risk < 0.20

    A missing risk (either input is unknown - never automatically a "low/safe"
    assumption) returns GREEN region only after we flag the status so the caller
    prompts for collection (Rule 2 / Human-in-loop).
    """
    risk = _multiply(composite_hz, vuln)
    wd = weights or RiskWeights()

    if risk.value is None:
        # cannot assert a safety band for unknown data (Rule 2)
        band = ZoneBand.GREEN if (composite_hz.value is None) else ZoneBand.YELLOW
        return RiskResult(
            composite_hazard=composite_hz,
            vulnerability=vuln,
            risk_score=None,
            status=FeatureStatus.MISSING,
            zone_band=band,
            priority=RelocationPriority.NOT_ASSESSED,
        )

    r = risk.value
    hz = composite_hz.value
    vn = vuln.value if vuln.value is not None else 0.0

    # RED: explicit high-hazard + high-vuln triggers red even if product < threshold
    if r >= wd.red_threshold or (
        (hz is not None and hz >= wd.high_hazard_floor)
        and vn >= wd.high_vuln_floor
    ):
        band = ZoneBand.RED
    elif r < wd.yellow_low:
        band = ZoneBand.GREEN
    else:
        band = ZoneBand.YELLOW

    # Zone-consistent band (fine-grained priority_score API later enriches this).
    priority_by_band = {
        ZoneBand.RED: RelocationPriority.IMMEDIATE,
        ZoneBand.YELLOW: RelocationPriority.PRIORITY,
        ZoneBand.GREEN: RelocationPriority.MONITOR,
    }

    return RiskResult(
        composite_hazard=composite_hz,
        vulnerability=vuln,
        risk_score=r,
        status=FeatureStatus.AVAILABLE,
        zone_band=band,
        priority=priority_by_band[band],
    )


# ---------------------------------------------------------------------------
# Priority scoring
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PriorityInput:
    composite_hazard: float          # available value
    vulnerability: float             # available value
    history_ratio: float             # historical event frequency 0..1 (0 if none)
    exposure_share: float            # proportion of population physically exposed 0..1
    access_difficulty: float         # normalized remoteness/accessibility 0..1


def priority_score(
    p: PriorityInput,
    weights: RiskWeights | None = None,
) -> tuple[float, RelocationPriority]:
    """priority = a*hazard + b*vuln + c*history + d*exposure + e*access%.

    Bands (documented):
        >= 0.60 -> IMMEDIATE
        >= 0.30 -> PRIORITY
        else    -> MONITOR
    """
    w = weights or RiskWeights()
    raw = (
        w.a_hazard * p.composite_hazard
        + w.b_vulnerability * p.vulnerability
        + w.c_history * p.history_ratio
        + w.d_exposure * p.exposure_share
        + w.e_access_difficulty * p.access_difficulty
    )
    score = _clip01(raw)

    if score >= 0.60:
        band = RelocationPriority.IMMEDIATE
    elif score >= 0.30:
        band = RelocationPriority.PRIORITY
    else:
        band = RelocationPriority.MONITOR
    return score, band
