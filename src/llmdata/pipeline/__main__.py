"""Command line: list stages, run one stage, or run a pipeline."""

from __future__ import annotations

import argparse
import json
import os
import time

from llmdata.config import settings
from llmdata.loader import load_object
from llmdata.pipeline import spec
from llmdata.pipeline.context import Context

SKIP = 99


def run_stage(stage: spec.Stage, ctx: Context) -> None:
    started = time.monotonic()
    load_object(stage.callable)(ctx)
    took = time.monotonic() - started
    print(f"{ctx.pipeline}/{stage.name} done in {took:.1f}s")


def main(argv: list[str] | None = None) -> int:
    env = os.environ.get
    parser = argparse.ArgumentParser(prog="llmdata.pipeline")
    parser.add_argument("command", choices=["stages", "stage", "run"])
    parser.add_argument("pipeline")
    parser.add_argument("stage", nargs="?")
    parser.add_argument("--until", default=env("LLMDATA_UNTIL"))
    parser.add_argument("--run-id", default=env("LLMDATA_RUN_ID"))
    args = parser.parse_args(argv)
    cfg = settings()
    stages = spec.load(
        cfg.pipelines_dir,
        args.pipeline,
        args.until,
        env("LLMDATA_PROFILE") or None,
    )
    if args.command == "stages":
        for s in stages:
            print(f"{s.name}\tch{s.chapter:02d}\t{s.callable}")
        return 0
    run_id = args.run_id or time.strftime("local__%Y%m%dT%H%M%S")

    def context(stage: spec.Stage) -> Context:
        return Context(
            run_id=run_id,
            pipeline=args.pipeline,
            stage=stage.name,
            settings=cfg,
            params=stage.params,
            conf=json.loads(env("LLMDATA_CONF") or "{}") or {},
            try_number=int(env("LLMDATA_TRY") or 1),
        )

    if args.command == "stage":
        chosen = [s for s in stages if s.name == args.stage]
        if not chosen:
            print(f"{args.stage} is beyond --until; skipped")
            return SKIP
        run_stage(chosen[0], context(chosen[0]))
        return 0
    for stage in stages:
        run_stage(stage, context(stage))
    print(f"run {run_id} complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
