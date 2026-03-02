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
from alspec.eval.domains import DOMAINS  # noqa: E402
from alspec.llm import AsyncLLMClient  # noqa: E402
from alspec.pipeline import _build_signature_user_prompt  # noqa: E402
from alspec.prompt_chunks import Stage, assemble_prompt  # noqa: E402
from alspec.result import Err, Ok  # noqa: E402

logger = logging.getLogger(__name__)
langfuse = get_client()

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


def _build_prompt_cache(trials: list[TrialConfig]) -> dict[str, str]:
    """Pre-assemble one system prompt per unique chunk configuration.

    This avoids re-running assemble_prompt() for every (domain × replicate)
    pair that shares the same chunk list (same config_hash).  It also prevents
    duplicate dependency-warning spam during execution — warnings fire at most
    once per unique design point here, not once per domain×replicate.
    """
    cache: dict[str, str] = {}
    for trial in trials:
        if trial.config_hash in cache:
            continue
        try:
            prompt = assemble_prompt(
                list(trial.chunk_ids), Stage.SIGNATURE,
                validate_deps=False,
                validate_stage=False,   # cross-stage chunks are intentionally allowed
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
# Single trial execution
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
                domain, trial.trial_id, trial.replicate, config.model,
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
        f"doe/{config.name}/trial{trial.trial_id}"
        f"/rep{trial.replicate}/{domain}"
    )
    factor_levels_json = json.dumps(trial.factor_levels)

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
                        domain, trial.trial_id, trial.replicate, config.model,
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
# Experiment runner
# ---------------------------------------------------------------------------


async def run_experiment(
    config: DoeConfig,
    client: AsyncLLMClient,
    *,
    golden_dir: Path,
    progress_cb: object = None,
) -> list[Stage1Score]:
    """Execute all trials and return all Stage1Score objects.

    Parameters
    ----------
    config:
        Parsed experiment configuration.
    client:
        Initialised LLM client.
    golden_dir:
        Path to the ``golden/`` directory for reference signatures.
    progress_cb:
        Optional callable(completed, total, score, elapsed) for progress reporting.
    """
    trials = generate_trials(config)
    domains = list(config.domains)

    # Fix 3b: pre-assemble one prompt per unique design point (avoids
    # repeated assemble_prompt calls and duplicate warning spam during execution)
    prompt_cache = _build_prompt_cache(trials)

    # Fix 2: one session_id for the whole experiment
    start_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session_id = f"doe/{config.name}/{start_ts}"
    logger.info("Langfuse session_id: %s", session_id)

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

            # Fix 5: structured progress line with timing + status tag
            if score.health == 0.0:
                status = "FAIL"
            elif score.health < 0.5:
                status = "LOW "
            else:
                status = "OK  "

            logger.info(
                "  Trial %4d/%d [%-22s trial=%d rep=%d] %s health=%.3f  %.1fs",
                completed, total, domain,
                trial.trial_id, trial.replicate,
                status, score.health, elapsed,
            )

            # Running summary every 50 completions
            if completed % 50 == 0:
                elapsed_total = time.monotonic() - experiment_start
                rate = completed / elapsed_total  # calls/sec
                eta = (total - completed) / rate if rate > 0 else 0
                mean_health = sum(s.health for s in all_scores) / len(all_scores)
                parse_rate = sum(1 for s in all_scores if s.parse_success) / len(all_scores)
                logger.info(
                    "  --- Progress: %d/%d (%.0f%%) | %.1f calls/min | ETA %.0fm | "
                    "mean_health=%.3f | parse_rate=%.1f%% ---",
                    completed, total, 100 * completed / total,
                    rate * 60, eta / 60,
                    mean_health, 100 * parse_rate,
                )

            if callable(progress_cb):
                progress_cb(completed, total, score, elapsed)  # type: ignore[operator]

        return score

    tasks = [
        run_one(trial, domain)
        for trial in trials
        for domain in domains
    ]

    results: list[Stage1Score | BaseException] = await asyncio.gather(
        *tasks, return_exceptions=True
    )

    scores: list[Stage1Score] = []
    for r in results:
        match r:
            case Stage1Score():
                scores.append(r)
            case BaseException() as exc:
                logger.error("Unexpected exception in trial task: %s", exc)

    langfuse.flush()
    return scores


# ---------------------------------------------------------------------------
# Results writing
# ---------------------------------------------------------------------------


def write_results(
    config: DoeConfig,
    scores: list[Stage1Score],
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


def _write_summary_csv(scores: list[Stage1Score], path: Path) -> None:
    """Aggregate scores by (trial_id, domain) and write summary CSV."""
    from collections import defaultdict

    grouped: dict[tuple[int, str], list[Stage1Score]] = defaultdict(list)
    for s in scores:
        grouped[(s.trial_id, s.domain)].append(s)

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
            mean_health = sum(s.health for s in group) / n
            mean_sort = sum(s.sort_overlap for s in group) / n
            mean_fn = sum(s.function_overlap for s in group) / n
            mean_pred = sum(s.predicate_overlap for s in group) / n
            mean_ctor = sum(s.constructor_overlap for s in group) / n
            mean_delta = sum(s.cell_count_delta for s in group) / n
            f.write(
                f"{tid},{domain},{n},"
                f"{parse_rate:.4f},{wf_rate:.4f},{mean_health:.4f},"
                f"{mean_sort:.4f},{mean_fn:.4f},{mean_pred:.4f},"
                f"{mean_ctor:.4f},{mean_delta:.2f}\n"
            )
