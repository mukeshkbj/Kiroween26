"""spirit-map command line.

    python -m seance_spirit explore --app fake-insurance --fake fake-insurance
    python -m seance_spirit replay  --app fake-insurance --fake fake-insurance

The app source is one of ``--fake NAME`` (seance_mcp.fake), ``--capture FILE`` (a recorded
real app) or, when neither is given, the live host from the environment, which the
service refuses unless this checkout is allowed to touch it (docs/contracts.md 2.1).
Artefacts live in ``docs/spirit-map/<app_id>/``.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import anyio

from seance_mcp.paths import REPO_ROOT
from seance_mcp.port import BridgePort

from .explorer import Explorer
from .graph import merge
from .policy import load_approved_policy
from .replay import replay_map
from .seed import SeedError, load_seed
from .store import read_map, write_map


def _port(args: argparse.Namespace) -> BridgePort:
    if args.fake:
        from seance_mcp import fake

        factory = getattr(fake, args.fake.replace("-", "_"), None)
        if factory is None:
            raise SystemExit(f"unknown fake app {args.fake!r}")
        return factory()
    if args.capture:
        from seance_mcp.fake import FakeApp

        return FakeApp.from_capture(args.capture)
    from seance_mcp.config import Settings
    from seance_mcp.port import RealBridgePort

    s = Settings.from_env()
    return RealBridgePort(s.wait_timeout_ms, s.volatile_regions)


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    d = Path(args.dir) if args.dir else REPO_ROOT / "docs" / "spirit-map" / args.app
    return d, d / "explore.seed.json", d / "spirit-map.json", d / "key-policy.json"


def cmd_explore(args: argparse.Namespace) -> int:
    d, seed_p, map_p, policy_p = _paths(args)
    seed = load_seed(seed_p)
    if seed.app_id != args.app:
        raise SystemExit(f"seed is for {seed.app_id!r}, not {args.app!r}")
    audit = REPO_ROOT / "docs" / "audit" / f"explore-{args.app}.audit.jsonl"
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z") if args.stamp else None
    fresh_path = map_p if not map_p.exists() else map_p.with_suffix(".new.json")
    ex = Explorer(_port(args), seed, approved=load_approved_policy(policy_p), attach=args.attach,
                  out_path=fresh_path, audit_path=audit, started_at=stamp)
    rep = anyio.run(ex.run)
    if fresh_path != map_p:
        merged, drift = merge(read_map(map_p), ex.map)
        write_map(map_p, merged)
        fresh_path.unlink()
        print(f"merged into {map_p.name}; drift: layout={drift.layout_changed} edges={drift.edges_changed} "
              f"not_seen={drift.nodes_not_seen}")
    print(f"{rep.status}{' (' + rep.reason + ')' if rep.reason else ''}: {rep.nodes} screens, "
          f"{rep.edges} edges, {rep.frontier} frontier, {rep.steps} steps -> {map_p}")
    return 0 if rep.status in ("completed", "budget") else 2


def cmd_replay(args: argparse.Namespace) -> int:
    d, seed_p, map_p, policy_p = _paths(args)
    audit = REPO_ROOT / "docs" / "audit" / f"replay-{args.app}.audit.jsonl"
    rep = anyio.run(lambda: replay_map(_port(args), read_map(map_p), load_seed(seed_p),
                                       approved=load_approved_policy(policy_p), attach=args.attach,
                                       audit_path=audit))
    print(f"{'ok' if rep.ok else 'DRIFT'}: replayed {len(rep.replayed)} edges, {len(rep.mismatches)} mismatches, "
          f"{len(rep.skipped)} skipped, halted={rep.halted}")
    for mm in rep.mismatches:
        print(f"  {mm.from_node} {mm.key}: expected {mm.expected[:10]}, landed {mm.landed_screen_id[:10]}")
    return 0 if rep.ok else 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="seance_spirit", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("explore", cmd_explore), ("replay", cmd_replay)):
        s = sub.add_parser(name)
        s.add_argument("--app", required=True, help="app id, e.g. fake-insurance")
        s.add_argument("--dir", help="artefact directory (default docs/spirit-map/<app>)")
        s.add_argument("--fake", help="use a fake app from seance_mcp.fake")
        s.add_argument("--capture", help="use a recorded capture file")
        s.add_argument("--attach", action="store_true", help="start from the screen a human left the session on")
        if name == "explore":
            s.add_argument("--stamp", action="store_true", help="record the start time in the map")
        s.set_defaults(fn=fn)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except SeedError as exc:
        print(f"seed error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
