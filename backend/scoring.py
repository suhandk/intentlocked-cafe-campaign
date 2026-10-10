"""Deterministic scoring and paired resampling. No model-authoritative aggregate."""

import itertools
import statistics
from collections import Counter

from backend.guardian.policy import CHANNELS
from backend.optimization_models import Feature, MappedVote, Score


def features(report, channel, poster=None):
    fields = report.rendered.fields if report.rendered else {}
    first = (fields.get("headline") or fields.get("body", "")).split("\n")[0]
    spans = report.rendered.spans if report.rendered else []
    first_field = "headline" if fields.get("headline") else "body"
    offer_first = any(
        s.key == "OFFER" and s.field == first_field and s.end <= min(len(first), 80) for s in spans
    )
    checks = {c.rule: c for c in report.checks}
    length = sum(len(v) for v in fields.values())
    limit = CHANNELS[channel]["limit"]
    result = [
        Feature(
            name="offer_first_line",
            applicable=True,
            value=100.0 if offer_first else 0.0,
            measurement="Approved OFFER span entirely within first line/80 characters",
        ),
        Feature(
            name="cta_presence",
            applicable=True,
            value=100.0 if fields.get("cta", "").strip() else 0.0,
            measurement="Nonempty customer-facing CTA",
        ),
        Feature(
            name="channel_length_fit",
            applicable=True,
            value=100.0 if length <= limit else 20.0,
            measurement=f"{length} code points / product budget {limit}",
        ),
        Feature(
            name="required_fact_completeness",
            applicable=True,
            value=100.0 if checks["G05"].passed is True else 0.0,
            measurement="Guardian G05 required visible facts/conditions",
        ),
        Feature(
            name="script_fit",
            applicable=True,
            value=100.0 if checks["G11"].passed is True else 60.0,
            measurement="Guardian G11 script-fit check; native review remains pending",
        ),
    ]
    contrast = poster.validation.contrast if poster else None
    result.append(
        Feature(
            name="text_contrast",
            applicable=poster is not None,
            value=None
            if contrast is None
            else 100.0
            if contrast >= 4.5
            else 60.0
            if contrast >= 3
            else 20.0,
            measurement="Not applicable to text"
            if contrast is None
            else f"Measured contrast {contrast:g}",
        )
    )
    area = poster.validation.offer_area_ratio if poster else None
    result.append(
        Feature(
            name="offer_area",
            applicable=poster is not None,
            value=None
            if area is None
            else 100.0
            if 0.06 <= area <= 0.18
            else 60.0
            if 0.03 <= area <= 0.25
            else 20.0,
            measurement="Unavailable: no full offer form with measured glyph bounds"
            if area is None
            else f"Measured line area {100 * area:.2f}%; target 6–18%",
        )
    )
    return result


def map_votes(result, personas, order, baseline_id, candidate_id, error=None):
    judgments = result.judgments if result else []
    counts = Counter(j.persona_id for j in judgments)
    known = {p.id for p in personas}
    invalid_batch = any(j.persona_id not in known for j in judgments)
    output = []
    for persona in personas:
        item = next((j for j in judgments if j.persona_id == persona.id), None)
        if invalid_batch or counts[persona.id] != 1 or not item:
            output.append(
                MappedVote(
                    persona_id=persona.id,
                    order=order,
                    winner_id=None,
                    outcome="missing",
                    reason=error or "Missing, duplicate or unknown persona judgment",
                )
            )
            continue
        winner = (
            None
            if item.choice == "tie"
            else (baseline_id if (item.choice == "X") == (order == "AB") else candidate_id)
        )
        output.append(
            MappedVote(
                persona_id=persona.id,
                order=order,
                winner_id=winner,
                outcome="tie"
                if winner is None
                else "candidate"
                if winner == candidate_id
                else "baseline",
                reason=item.reason,
            )
        )
    return output


def score(measured, votes=None, baseline=False):
    values = [f.value for f in measured if f.applicable]
    mean = statistics.mean(values) if values and all(v is not None for v in values) else None
    votes = votes or []
    weights = {"candidate": 1, "tie": 0.5, "baseline": 0, "missing": 0}
    complete = sum(v.outcome != "missing" for v in votes)
    wins = sum(weights[v.outcome] for v in votes)
    tournament = 50.0 if baseline else 10.0 * wins if complete == 10 else None
    pairs = [
        [weights[v.outcome] for v in votes if v.persona_id == pid]
        for pid in dict.fromkeys(v.persona_id for v in votes)
    ]
    disagreement = sum(len(p) == 2 and p[0] != p[1] for p in pairs)
    band = None
    if complete == 10 and len(pairs) == 5 and all(len(p) == 2 for p in pairs):
        # Exact deterministic 5^5 resamples of paired-persona units, not ten independent votes.
        means = sorted(
            100 * sum(sum(pairs[i]) for i in sample) / 10
            for sample in itertools.product(range(5), repeat=5)
        )
        band = [means[int(0.1 * (len(means) - 1))], means[int(0.9 * (len(means) - 1))]]
    return Score(
        features=measured,
        feature_mean=mean,
        tournament=tournament,
        overall=None if mean is None or tournament is None else 0.5 * mean + 0.5 * tournament,
        weighted_wins=wins,
        complete_judgments=complete,
        votes=votes,
        sensitivity_band=band,
        order_disagreement=disagreement,
        baseline_convention=baseline,
    )


def acceptance(current, candidate, report, audit):
    reasons = []
    if report.status == "BLOCKED" or audit.status == "BLOCKED":
        reasons.append("GUARDIAN_BLOCK")
    if report.missing_checks or audit.status == "PENDING":
        reasons.append("VERIFICATION_PENDING")
    if [f.name for f in current.features if f.applicable] != [
        f.name for f in candidate.features if f.applicable
    ]:
        reasons.append("FEATURE_MASK_CHANGED")
    if candidate.complete_judgments != 10 or candidate.overall is None:
        reasons.append("JUDGMENTS_INCOMPLETE")
    elif candidate.weighted_wins < 6:
        reasons.append("FEWER_THAN_SIX_WEIGHTED_WINS")
    if (
        candidate.feature_mean is None
        or current.feature_mean is None
        or current.feature_mean - candidate.feature_mean >= 3
    ):
        reasons.append("FEATURE_DECREASE_THREE_OR_MORE")
    if current.overall is None or candidate.overall is None or candidate.overall <= current.overall:
        reasons.append("NO_STRICT_OVERALL_GAIN")
    return reasons
