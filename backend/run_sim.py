"""
run_sim.py  —  CLI entry point for running simulations.

Usage:
    # Static mode (default) — deterministic baseline, no LLM calls
    python run_sim.py

    # LLM mode — Gemini-enriched personas with per-run variation
    python run_sim.py --mode llm

    # Explicit scenario
    python run_sim.py --scenario mobile_checkout_fee --mode llm
"""

import argparse
from dotenv import load_dotenv
load_dotenv()

from app.simulation.simulator import run_simulation

parser = argparse.ArgumentParser(description="Run First Customer simulation")
parser.add_argument(
    "--scenario",
    default="mobile_checkout_fee",
    help="Scenario name (default: mobile_checkout_fee)",
)
parser.add_argument(
    "--mode",
    choices=["static", "llm"],
    default="static",
    help="Persona mode: 'static' uses fixed personas (default), 'llm' generates per-run variation via Gemini",
)
args = parser.parse_args()

run_simulation(args.scenario, mode=args.mode)
