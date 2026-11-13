#!/usr/bin/env python3
"""Populate an already provisioned public demo account; preview unless --apply is supplied."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app.pilot.demo_seed import seed_demo
from app.workspace.routes import service

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--team-id', required=True, help='Expected public demo team ID (checked against its name and membership).')
parser.add_argument('--apply', action='store_true', help='Write additive sample records; existing records are preserved.')
parser.add_argument('--retime-existing', action='store_true',
                    help='Also spread records from an earlier seed run over the past four weeks, once. '
                         'This moves the timestamps of any visitor edits to seeded records too.')
args = parser.parse_args()
print(json.dumps(seed_demo(service.store, service.media, team_id=args.team_id, apply=args.apply,
                           retime_existing=args.retime_existing), indent=2))
