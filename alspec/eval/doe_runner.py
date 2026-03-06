"""Async experiment runner for DoE.

Executes all trials in the design (TrialConfig × domain × replicate) with
semaphore-bounded parallelism, scores each Stage 1 output, and writes results
to a structured output directory.

Output layout::

    results/{experiment_name}/
    ├── config.toml          # frozen copy of the experiment config
    ├── design_matrix.csv    # (trial_id, factor_A, ...) design matrix
    ├── scores.jsonl         # one Stage1Score per line
    ├── summary.csv          # one row per (trial_id, domain), averaged over replicates
    └── effects.csv          # main effects and 2FI estimates
"""

from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import dataclass
import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from langfuse import get_client, propagate_attributes  # noqa: E402

from alspec.eval.doe_config import DoeConfig  # noqa: E402
from alspec.eval.doe_design import TrialConfig, generate_trials  # noqa: E402
from alspec.eval.stage1_score import Stage1Score, _make_zero_score, score_stage1_output  # noqa: E402
from alspec.eval.stage4_score import Stage4Score, _make_zero_stage4_score, score_stage4_output  # noqa: E402
from alspec.eval.domains import DOMAINS  # noqa: E402
from alspec.llm import AsyncLLMClient  # noqa: E402
from alspec.obligation import build_obligation_table, ObligationTable  # noqa: E402

from alspec.pipeline import (
    _build_signature_user_prompt,
    _build_axioms_user_prompt,
    run_pipeline_signature_only,
)
from alspec.axiom_gen import generate_mechanical_axioms
from alspec.obligation_render import render_obligation_prompt
from alspec.prompt_chunks import Stage, assemble_prompt  # noqa: E402
from alspec.result import Err, Ok  # noqa: E402
from alspec.signature import Signature  # noqa: E402

logger = logging.getLogger(__name__)
langfuse = get_client()

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UpstreamCache:
    """Cached output from stages 1-2-3 for a single domain."""

    domain: str
    signature: Signature
    obligation_table: ObligationTable
    signature_code: str  # raw code string to include in Stage 4 user prompt
    signature_analysis: str
    obligation_prompt_md: str
    analysis_text: str | None  # Stage 1 output (if lens used)
    spec_name: str  # domain ID formatted as spec name
    upstream_trace_name: str  # for Langfuse cross-referencing


# ---------------------------------------------------------------------------
# Domain description helper
# ---------------------------------------------------------------------------

_DOMAIN_DESCRIPTIONS: dict[str, str] = {d.id: d.description for d in DOMAINS}


def _get_domain_description(domain: str) -> str:
    desc = _DOMAIN_DESCRIPTIONS.get(domain)
    if desc is None:
        raise ValueError(
            f"No description found for domain {domain!r}. "
            f"Available: {sorted(_DOMAIN_DESCRIPTIONS.keys())}"
        )
    return desc


# ---------------------------------------------------------------------------
# System-prompt cache: one assembly per unique config_hash
# ---------------------------------------------------------------------------


def _build_prompt_cache(trials: list[TrialConfig], stage: str) -> dict[str, str]:
    """Pre-assemble one system prompt per unique chunk configuration.

    This avoids re-running assemble_prompt() for every (domain × replicate)
    pair that shares the same chunk list (same config_hash).  It also prevents
    duplicate dependency-warning spam during execution — warnings fire at most
    once per unique design point here, not once per domain×replicate.
    """
    target_stage = Stage.AXIOMS if stage == "stage4" else Stage.SIGNATURE
    cache: dict[str, str] = {}
    for trial in trials:
        if trial.config_hash in cache:
            continue
        try:
            prompt = assemble_prompt(
                list(trial.chunk_ids),
                target_stage,
                validate_deps=False,
                validate_stage=False,  # cross-stage chunks are intentionally allowed
            )
            cache[trial.config_hash] = prompt
        except Exception as exc:
            logger.error(
                "assemble_prompt failed for trial=%d (hash=%s): %s",
                trial.trial_id,
                trial.config_hash[:12],
                exc,
            )
            cache[trial.config_hash] = ""  # sentinel; will produce a parse failure
    return cache


# ---------------------------------------------------------------------------
# Phase A: Upstream Cache Builder
# ---------------------------------------------------------------------------


async def _build_upstream_cache(
    config: DoeConfig,
    client: AsyncLLMClient,
    domains: list[str],
    session_id: str,
) -> dict[str, UpstreamCache]:
    """Run stages 1-2-3 for each domain and cache results."""
    logger.info("Building upstream cache (Stages 1-2-3) for %d domains...", len(domains))
    cache: dict[str, UpstreamCache] = {}
    semaphore = asyncio.Semaphore(config.max_concurrent)

    async def run_one(domain: str) -> UpstreamCache | None:
        async with semaphore:
            upstream_trace_name = f"doe/{config.name}/upstream/{domain}"
            desc = _get_domain_description(domain)

            with langfuse.start_as_current_observation(
                as_type="span",
                name=upstream_trace_name,
            ):
                with propagate_attributes(
                    trace_name=upstream_trace_name,
                    session_id=session_id,
                    metadata={
                        "doe_experiment": config.name,
                        "phase": "upstream",
                        "domain": domain,
                        "model": config.upstream_model,
                        "lens": config.upstream_lens,
                    },
                    tags=[
                        f"doe:{config.name}",
                        "phase:upstream",
                        f"domain:{domain}",
                    ],
                ):
                    langfuse.update_current_trace(input=desc)

                    result = await run_pipeline_signature_only(
                        client=client,
                        domain_id=domain,
                        domain_description=desc,
                        model=config.upstream_model,
                        lens=config.upstream_lens,
                    )

                    if not result.success:
                        logger.warning(
                            "Upstream failed for domain %s: %s", domain, result.error
                        )
                        langfuse.score_current_trace(name="upstream_parse", value=0.0)
                        return None

                    sig = result.signature
                    assert sig is not None

                    try:
                        table = build_obligation_table(sig)
                        mech_report = generate_mechanical_axioms(sig, table)
                        prompt_md = render_obligation_prompt(sig, table, mech_report)
                    except Exception as e:
                        logger.warning(
                            "Upstream obligation table failed for domain %s: %s", domain, e
                        )
                        langfuse.score_current_trace(name="upstream_well_formed", value=0.0)
                        return None

                    langfuse.update_current_trace(output=result.signature_code)
                    langfuse.score_current_trace(name="upstream_parse", value=1.0)
                    langfuse.score_current_trace(name="upstream_well_formed", value=1.0)

                    return UpstreamCache(
                        domain=domain,
                        signature=sig,
                        obligation_table=table,
                        signature_code=result.signature_code or "",
                        signature_analysis=result.signature_analysis or "",
                        obligation_prompt_md=prompt_md,
                        analysis_text=result.domain_analysis,
                        spec_name=domain.replace("-", " ").title().replace(" ", ""),
                        upstream_trace_name=upstream_trace_name,
                    )

    tasks = [run_one(d) for d in domains]
    results = await asyncio.gather(*tasks)

    for r in results:
        if r:
            cache[r.domain] = r

    await asyncio.to_thread(langfuse.flush)
    logger.info("Upstream cache built: %d/%d succeeded", len(cache), len(domains))
    return cache


# ---------------------------------------------------------------------------
# Single trial execution (Stage 1)
# ---------------------------------------------------------------------------


async def execute_trial(
    client: AsyncLLMClient,
    trial: TrialConfig,
    domain: str,
    config: DoeConfig,
    golden_dir: Path,
    system_prompt: str,
    session_id: str,
) -> tuple[Stage1Score, float]:
    """Execute one (trial, domain) pair and return (Stage1Score, elapsed_seconds).

    Never raises — all errors are recorded as parse_failure scores.
    """
    t0 = time.monotonic()
    desc = _get_domain_description(domain)

    # Empty prompt means assembly failed during the cache-build phase
    if not system_prompt:
        elapsed = time.monotonic() - t0
        return (
            _make_zero_score(
                domain,
                trial.trial_id,
                trial.replicate,
                config.model,
                "assemble_prompt failed (empty prompt)",
                trial.factor_levels,
            ),
            elapsed,
        )

    user_prompt = _build_signature_user_prompt(desc)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Langfuse span — Fix 1: all metadata values must be strings
    trace_name = (
        f"doe/{config.name}/trial{trial.trial_id}" f"/rep{trial.replicate}/{domain}"
    )
    factor_levels_json = json.dumps(trial.factor_levels)

    with langfuse.start_as_current_observation(
        as_type="span",
        name=trace_name,
    ):
        with propagate_attributes(
            trace_name=trace_name,
            session_id=session_id,
            metadata={
                "doe_experiment": config.name,
                "doe_trial_id": str(trial.trial_id),
                "doe_replicate": str(trial.replicate),
                "doe_config_hash": trial.config_hash,
                "doe_factor_levels": factor_levels_json,
                "domain": domain,
                "model": config.model,
            },
            tags=[
                f"doe:{config.name}",
                f"trial:{trial.trial_id}",
                f"domain:{domain}",
                *[f"chunk:{c.name}" for c in trial.chunk_ids],
            ],
        ):
            result = await client.generate_with_tool_call(
                messages, model=config.model, tool_name="submit_signature"
            )

            elapsed = time.monotonic() - t0

            # Warn on suspiciously slow calls (possible rate limit / backoff)
            if elapsed > 30.0:
                logger.warning(
                    "Slow call: %.1fs for trial=%d domain=%s rep=%d — possible rate limit",
                    elapsed,
                    trial.trial_id,
                    domain,
                    trial.replicate,
                )

            match result:
                case Err(exc):
                    logger.warning(
                        "LLM call failed trial=%d domain=%s rep=%d: %s",
                        trial.trial_id,
                        domain,
                        trial.replicate,
                        exc,
                    )
                    langfuse.score_current_trace(
                        name="stage1_health",
                        value=0.0,
                        comment=f"LLM error: {exc}",
                    )
                    return (
                        _make_zero_score(
                            domain,
                            trial.trial_id,
                            trial.replicate,
                            config.model,
                            f"LLM error: {exc}",
                            trial.factor_levels,
                        ),
                        elapsed,
                    )
                case Ok((_, code, _)):
                    pass

            score = score_stage1_output(
                code=code,
                domain=domain,
                trial_id=trial.trial_id,
                replicate=trial.replicate,
                model=config.model,
                golden_dir=golden_dir,
                factor_levels=trial.factor_levels,
            )

            # score_current_trace must be called inside the propagate_attributes
            # context — outside it there is no active span and the call is a no-op.
            langfuse.score_current_trace(
                name="stage1_health",
                value=score.health,
                comment=f"parse={score.parse_success} wf={score.well_formed}",
            )

    return score, elapsed


# ---------------------------------------------------------------------------
# Phase B: Stage 4 Trial Execution
# ---------------------------------------------------------------------------


async def execute_stage4_trial(
    client: AsyncLLMClient,
    trial: TrialConfig,
    domain: str,
    config: DoeConfig,
    upstream: UpstreamCache,
    system_prompt: str,
    session_id: str,
    golden_dir: Path,
) -> tuple[Stage4Score, float]:
    """Execute one Stage 4 (trial, domain) pair."""
    t0 = time.monotonic()
    desc = _get_domain_description(domain)

    if not system_prompt:
        elapsed = time.monotonic() - t0
        return (
            _make_zero_stage4_score(
                domain,
                trial.trial_id,
                trial.replicate,
                config.model,
                "assemble_prompt failed (empty prompt)",
                trial.factor_levels,
            ),
            elapsed,
        )

    user_prompt = _build_axioms_user_prompt(
        domain_description=desc,
        spec_name=upstream.spec_name,
        signature_code=upstream.signature_code,
        signature_analysis=upstream.signature_analysis,
        obligation_prompt_md=upstream.obligation_prompt_md,
        domain_analysis=upstream.analysis_text,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    trace_name = (
        f"doe/{config.name}/trial{trial.trial_id}" f"/rep{trial.replicate}/{domain}"
    )
    factor_levels_json = json.dumps(trial.factor_levels)

    with langfuse.start_as_current_observation(
        as_type="span",
        name=trace_name,
    ):
        with propagate_attributes(
            trace_name=trace_name,
            session_id=session_id,
            metadata={
                "doe_experiment": config.name,
                "doe_trial_id": str(trial.trial_id),
                "doe_replicate": str(trial.replicate),
                "doe_config_hash": trial.config_hash,
                "doe_factor_levels": factor_levels_json,
                "phase": "ablation",
                "stage": "4",
                "domain": domain,
                "model": config.model,
                "upstream_trace_name": upstream.upstream_trace_name,
            },
            tags=[
                f"doe:{config.name}",
                "phase:ablation",
                "stage:axioms",
                f"trial:{trial.trial_id}",
                f"domain:{domain}",
                *[f"chunk:{c.name}" for c in trial.chunk_ids],
            ],
        ):
            langfuse.update_current_trace(
                input={
                    "domain": domain,
                    "signature_code": upstream.signature_code,
                    "obligation_prompt": upstream.obligation_prompt_md,
                    "system_prompt_chunks": [c.name for c in trial.chunk_ids],
                }
            )

            result = await client.generate_with_tool_call(
                messages, model=config.model, tool_name="submit_spec"
            )

            elapsed = time.monotonic() - t0

            match result:
                case Err(exc):
                    langfuse.score_current_trace(
                        name="parse_success",
                        value=0.0,
                        comment=f"LLM error: {exc}",
                    )
                    return (
                        _make_zero_stage4_score(
                            domain,
                            trial.trial_id,
                            trial.replicate,
                            config.model,
                            f"LLM error: {exc}",
                            trial.factor_levels,
                        ),
                        elapsed,
                    )
                case Ok((_, code, _)):
                    langfuse.update_current_trace(output=code)

            score = await score_stage4_output(
                code=code,
                domain=domain,
                sig=upstream.signature,
                trial_id=trial.trial_id,
                replicate=trial.replicate,
                model=config.model,
                factor_levels=trial.factor_levels,
                golden_dir=golden_dir,
            )

            # Scores
            langfuse.score_current_trace(
                name="parse_success",
                value=1.0 if score.parse_success else 0.0,
            )
            langfuse.score_current_trace(
                name="well_formed",
                value=1.0 if score.well_formed else 0.0,
            )
            langfuse.score_current_trace(
                name="intrinsic_health",
                value=score.intrinsic_health,
            )
            langfuse.score_current_trace(
                name="coverage",
                value=score.coverage_ratio,
                comment=f"{score.covered_cells}/{score.total_cells}",
            )
            langfuse.score_current_trace(
                name="unmatched_count",
                value=float(score.unmatched_axiom_count),
            )

    return score, elapsed


# ---------------------------------------------------------------------------
# Stage 1 Experiment runner
# ---------------------------------------------------------------------------


async def _run_stage1_experiment(
    config: DoeConfig,
    client: AsyncLLMClient,
    golden_dir: Path,
    session_id: str,
    progress_cb: object = None,
) -> list[Stage1Score]:
    trials = generate_trials(config)
    domains = list(config.domains)
    prompt_cache = _build_prompt_cache(trials, config.stage)

    semaphore = asyncio.Semaphore(config.max_concurrent)
    total = len(trials) * len(domains)
    completed = 0
    all_scores: list[Stage1Score] = []
    lock = asyncio.Lock()
    experiment_start = time.monotonic()

    async def run_one(trial: TrialConfig, domain: str) -> Stage1Score:
        nonlocal completed
        system_prompt = prompt_cache.get(trial.config_hash, "")
        async with semaphore:
            score, elapsed = await execute_trial(
                client, trial, domain, config, golden_dir, system_prompt, session_id
            )
        async with lock:
            completed += 1
            all_scores.append(score)

            # Structured progress line
            status = (
                "FAIL"
                if score.health == 0.0
                else "LOW " if score.health < 0.5 else "OK  "
            )
            logger.info(
                "  Trial %4d/%d [%-22s trial=%d rep=%d] %s health=%.3f  %.1fs",
                completed,
                total,
                domain,
                trial.trial_id,
                trial.replicate,
                status,
                score.health,
                elapsed,
            )

            if completed % 50 == 0:
                elapsed_total = time.monotonic() - experiment_start
                rate = completed / elapsed_total
                eta = (total - completed) / rate if rate > 0 else 0
                mean_health = sum(s.health for s in all_scores) / len(all_scores)
                parse_rate = sum(1 for s in all_scores if s.parse_success) / len(
                    all_scores
                )
                logger.info(
                    "  --- Progress: %d/%d (%.0f%%) | %.1f calls/min | ETA %.0fm | "
                    "mean_health=%.3f | parse_rate=%.1f%% ---",
                    completed,
                    total,
                    100 * completed / total,
                    rate * 60,
                    eta / 60,
                    mean_health,
                    100 * parse_rate,
                )
                await asyncio.to_thread(langfuse.flush)

            if callable(progress_cb):
                progress_cb(completed, total, score, elapsed)  # type: ignore[operator]

        return score

    tasks = [run_one(trial, domain) for trial in trials for domain in domains]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scores: list[Stage1Score] = []
    for r in results:
        match r:
            case Stage1Score():
                scores.append(r)
            case BaseException() as exc:
                import traceback
                tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                logger.error("Unexpected exception in trial task: %s\n%s", exc, tb)

    return scores


# ---------------------------------------------------------------------------
# Stage 4 Experiment runner
# ---------------------------------------------------------------------------


async def _run_stage4_experiment(
    config: DoeConfig,
    client: AsyncLLMClient,
    golden_dir: Path,
    session_id: str,
    progress_cb: object = None,
) -> list[Stage4Score]:
    upstream_cache = await _build_upstream_cache(
        config, client, list(config.domains), session_id
    )
    if not upstream_cache:
        logger.error("All upstream runs failed. Aborting Stage 4 experiment.")
        return []

    # Filter domains to those that succeeded upstream
    usable_domains = sorted(upstream_cache.keys())
    trials = generate_trials(config)
    prompt_cache = _build_prompt_cache(trials, config.stage)

    semaphore = asyncio.Semaphore(config.max_concurrent)
    total = len(trials) * len(usable_domains)
    completed = 0
    all_scores: list[Stage4Score] = []
    lock = asyncio.Lock()
    experiment_start = time.monotonic()

    async def run_one(trial: TrialConfig, domain: str) -> Stage4Score:
        nonlocal completed
        system_prompt = prompt_cache.get(trial.config_hash, "")
        upstream = upstream_cache[domain]
        async with semaphore:
            score, elapsed = await execute_stage4_trial(
                client,
                trial,
                domain,
                config,
                upstream,
                system_prompt,
                session_id,
                golden_dir,
            )
        async with lock:
            completed += 1
            all_scores.append(score)

            status = (
                "FAIL"
                if not score.parse_success
                else "LOW " if score.intrinsic_health < 0.5 else "OK  "
            )
            logger.info(
                "  Trial %4d/%d [%-22s trial=%d rep=%d] %s health=%.3f  %.1fs",
                completed,
                total,
                domain,
                trial.trial_id,
                trial.replicate,
                status,
                score.intrinsic_health,
                elapsed,
            )

            if completed % 50 == 0:
                elapsed_total = time.monotonic() - experiment_start
                rate = completed / elapsed_total
                eta = (total - completed) / rate if rate > 0 else 0
                mean_health = sum(s.intrinsic_health for s in all_scores) / len(
                    all_scores
                )
                parse_rate = sum(1 for s in all_scores if s.parse_success) / len(
                    all_scores
                )
                logger.info(
                    "  --- Progress: %d/%d (%.0f%%) | %.1f calls/min | ETA %.0fm | "
                    "mean_health=%.3f | parse_rate=%.1f%% ---",
                    completed,
                    total,
                    100 * completed / total,
                    rate * 60,
                    eta / 60,
                    mean_health,
                    100 * parse_rate,
                )
                await asyncio.to_thread(langfuse.flush)

            if callable(progress_cb):
                progress_cb(completed, total, score, elapsed)  # type: ignore[operator]

        return score

    tasks = [run_one(trial, domain) for trial in trials for domain in usable_domains]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scores: list[Stage4Score] = []
    for r in results:
        match r:
            case Stage4Score():
                scores.append(r)
            case BaseException() as exc:
                import traceback
                tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                logger.error("Unexpected exception in trial task: %s\n%s", exc, tb)

    _emit_stage4_session_scores(session_id, scores)
    return scores


def _emit_stage4_session_scores(session_id: str, scores: list[Stage4Score]) -> None:
    successful = [s for s in scores if s.parse_success]

    langfuse.create_score(
        name="parse_rate",
        value=len(successful) / len(scores) if scores else 0.0,
        session_id=session_id,
        comment=f"{len(successful)}/{len(scores)}",
    )
    langfuse.create_score(
        name="mean_intrinsic_health",
        value=(sum(s.intrinsic_health for s in successful) / len(successful))
        if successful
        else 0.0,
        session_id=session_id,
    )
    langfuse.create_score(
        name="mean_coverage",
        value=(sum(s.coverage_ratio for s in successful) / len(successful))
        if successful
        else 0.0,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# Main Experiment runner
# ---------------------------------------------------------------------------


async def run_experiment(
    config: DoeConfig,
    client: AsyncLLMClient,
    *,
    golden_dir: Path,
    progress_cb: object = None,
) -> list[Stage1Score] | list[Stage4Score]:
    """Execute all trials and return score objects."""
    start_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_id = f"doe/{config.name}/{start_ts}"
    logger.info("Langfuse session_id: %s", session_id)

    if config.stage == "stage4":
        scores = await _run_stage4_experiment(
            config, client, golden_dir, session_id, progress_cb
        )
    else:
        scores = await _run_stage1_experiment(
            config, client, golden_dir, session_id, progress_cb
        )

    await asyncio.to_thread(langfuse.flush)
    return scores


# ---------------------------------------------------------------------------
# Results writing
# ---------------------------------------------------------------------------


def write_results(
    config: DoeConfig,
    scores: list[Stage1Score] | list[Stage4Score],
    config_path: Path,
) -> None:
    """Write all results to the configured output directory."""
    out_dir = config.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Frozen config copy
    shutil.copy(config_path, out_dir / "config.toml")

    # 2. Design matrix CSV
    trials = generate_trials(config)
    # Collect unique (trial_id, factor_levels) pairs
    seen_trials: dict[int, dict[str, int]] = {}
    for t in trials:
        if t.trial_id not in seen_trials:
            seen_trials[t.trial_id] = t.factor_levels

    factor_labels = [label for label, _ in config.factors]
    dm_path = out_dir / "design_matrix.csv"
    with dm_path.open("w") as f:
        f.write("trial_id," + ",".join(factor_labels) + "\n")
        for tid in sorted(seen_trials):
            levels = seen_trials[tid]
            row = str(tid) + "," + ",".join(str(levels[lbl]) for lbl in factor_labels)
            f.write(row + "\n")

    # 3. scores.jsonl
    scores_path = out_dir / "scores.jsonl"
    with scores_path.open("w") as f:
        for s in scores:
            f.write(json.dumps(dataclasses.asdict(s)) + "\n")

    # 4. summary.csv — one row per (trial_id, domain), averaged over replicates
    summary_path = out_dir / "summary.csv"
    _write_summary_csv(scores, summary_path)

    logger.info("Results written to %s", out_dir)


def _write_summary_csv(
    scores: list[Stage1Score] | list[Stage4Score], path: Path
) -> None:
    """Aggregate scores by (trial_id, domain) and write summary CSV."""
    from collections import defaultdict
    from typing import Any

    if not scores:
        return

    grouped: dict[tuple[int, str], list[Any]] = defaultdict(list)
    for s in scores:
        grouped[(s.trial_id, s.domain)].append(s)

    is_stage4 = isinstance(scores[0], Stage4Score)

    if is_stage4:
        header = (
            "trial_id,domain,replicates,"
            "parse_rate,wf_rate,mean_intrinsic_health,mean_coverage,"
            "mean_unmatched,mean_uncovered"
        )
    else:
        header = (
            "trial_id,domain,replicates,"
            "parse_rate,wf_rate,mean_health,mean_sort_overlap,"
            "mean_fn_overlap,mean_pred_overlap,mean_ctor_overlap,mean_cell_delta"
        )

    with path.open("w") as f:
        f.write(header + "\n")
        for (tid, domain), group in sorted(grouped.items()):
            n = len(group)
            parse_rate = sum(1 for s in group if s.parse_success) / n
            wf_rate = sum(1 for s in group if s.well_formed) / n

            if is_stage4:
                mean_intrinsic = sum(getattr(s, "intrinsic_health", 0.0) for s in group) / n
                mean_coverage = sum(getattr(s, "coverage_ratio", 0.0) for s in group) / n
                mean_unmatched = (
                    sum(getattr(s, "unmatched_axiom_count", 0) for s in group) / n
                )
                mean_uncovered = (
                    sum(getattr(s, "uncovered_cell_count", 0) for s in group) / n
                )
                f.write(
                    f"{tid},{domain},{n},"
                    f"{parse_rate:.4f},{wf_rate:.4f},{mean_intrinsic:.4f},"
                    f"{mean_coverage:.4f},{mean_unmatched:.2f},{mean_uncovered:.2f}\n"
                )
            else:
                mean_health = sum(getattr(s, "health", 0.0) for s in group) / n
                mean_sort = sum(getattr(s, "sort_overlap", 0.0) for s in group) / n
                mean_fn = sum(getattr(s, "function_overlap", 0.0) for s in group) / n
                mean_pred = sum(getattr(s, "predicate_overlap", 0.0) for s in group) / n
                mean_ctor = sum(getattr(s, "constructor_overlap", 0.0) for s in group) / n
                mean_delta = sum(getattr(s, "cell_count_delta", 0) for s in group) / n
                f.write(
                    f"{tid},{domain},{n},"
                    f"{parse_rate:.4f},{wf_rate:.4f},{mean_health:.4f},"
                    f"{mean_sort:.4f},{mean_fn:.4f},{mean_pred:.4f},"
                    f"{mean_ctor:.4f},{mean_delta:.2f}\n"
                )
