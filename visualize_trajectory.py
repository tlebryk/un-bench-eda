#!/usr/bin/env python3
"""
Visualize UN resolution trajectories for MARL analysis.

Shows individual country actions at each timestep.
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Any


def print_trajectory_summary(traj: Dict[str, Any]):
    """Print human-readable trajectory summary."""

    print("=" * 80)
    print(f"TRAJECTORY: {traj['trajectory_id']}")
    print("=" * 80)
    print(f"Title: {traj['metadata']['title']}")
    print(f"Session: {traj['metadata']['session']}")
    print(f"Committee: {traj['metadata']['committee']}")
    print(f"Agenda Item: {traj['metadata']['agenda_item']}")
    print(f"Final Outcome: {traj['metadata']['final_outcome'].upper()}")
    print(f"Total Timesteps: {len(traj['timesteps'])}")
    print()


def print_timestep(ts: Dict[str, Any], verbose: bool = False):
    """Print a single timestep showing country actions."""

    print(f"\n{'─' * 80}")
    print(f"T{ts['t']}: {ts['stage'].upper().replace('_', ' ')}")
    print(f"{'─' * 80}")
    print(f"Date: {ts['date']}")
    print(f"Action Type: {ts['action_type']}")

    # STATE
    print(f"\n📊 STATE:")
    for key, val in ts['state'].items():
        if isinstance(val, str) and len(val) > 100:
            print(f"  {key}: {val[:100]}...")
        else:
            print(f"  {key}: {val}")

    # ACTION (showing individual countries)
    print(f"\n⚡ ACTION:")
    action = ts['action']

    if action['type'] == 'vote_on_draft' or action['type'] == 'vote_on_resolution':
        # VOTING: Show individual country votes
        if 'votes' in action and isinstance(action['votes'], dict):
            votes = action['votes']

            if 'in_favour' in votes:
                print(f"\n  ✅ IN FAVOUR ({len(votes['in_favour'])} countries):")
                if verbose:
                    for country in sorted(votes['in_favour']):
                        print(f"     • {country}")
                else:
                    print(f"     {', '.join(votes['in_favour'][:10])}")
                    if len(votes['in_favour']) > 10:
                        print(f"     ... and {len(votes['in_favour']) - 10} more")

            if 'against' in votes:
                print(f"\n  ❌ AGAINST ({len(votes['against'])} countries):")
                if verbose:
                    for country in sorted(votes['against']):
                        print(f"     • {country}")
                else:
                    print(f"     {', '.join(votes['against'][:10])}")
                    if len(votes['against']) > 10:
                        print(f"     ... and {len(votes['against']) - 10} more")

            if 'abstaining' in votes:
                print(f"\n  ⚪ ABSTAINING ({len(votes['abstaining'])} countries):")
                if verbose:
                    for country in sorted(votes['abstaining']):
                        print(f"     • {country}")
                else:
                    print(f"     {', '.join(votes['abstaining'][:10])}")
                    if len(votes['abstaining']) > 10:
                        print(f"     ... and {len(votes['abstaining']) - 10} more")

        elif 'vote_tally' in action:
            # Aggregate votes (plenary)
            tally = action['vote_tally']
            print(f"  Aggregate Vote: {tally['yes']} YES / {tally['no']} NO / {tally['abstain']} ABSTAIN")
            print(f"  ⚠️  Individual country votes not available (plenary aggregated)")

    elif action['type'] == 'submit_draft_resolution':
        # DRAFTING: Show sponsors
        print(f"  Primary Sponsor: {action['actor']}")
        if action.get('sponsors'):
            print(f"  Co-Sponsors ({len(action['sponsors'])} countries):")
            for sponsor in action['sponsors'][:10]:
                print(f"    • {sponsor}")
            if len(action['sponsors']) > 10:
                print(f"    ... and {len(action['sponsors']) - 10} more")

        if verbose and action.get('draft_text'):
            print(f"\n  Draft Text Preview:")
            print(f"    {action['draft_text'][:300]}...")
            print(f"    [Full length: {action['draft_text_full_length']} characters]")

    elif action['type'] == 'make_statements':
        # STATEMENTS: Show who spoke
        utterances = action.get('utterances', [])
        print(f"  Speakers ({len(utterances)} statements):")
        for utt in utterances[:5]:
            speaker = utt['speaker']
            word_count = utt.get('word_count', 0)
            print(f"    • {speaker} ({word_count} words)")
            if verbose:
                print(f"      \"{utt['text_preview'][:100]}...\"")
        if len(utterances) > 5:
            print(f"    ... and {len(utterances) - 5} more speakers")

    else:
        # Generic action
        print(f"  Actor: {action.get('actor', 'N/A')}")
        print(f"  Type: {action.get('type', 'N/A')}")

    # OBSERVATION
    print(f"\n👁️  OBSERVATION:")
    obs = ts['observation']
    for key, val in obs.items():
        if key == 'vote_tally':
            print(f"  {key}: {val['yes']}-{val['no']}-{val['abstain']}")
        elif isinstance(val, (list, dict)) and len(str(val)) > 100:
            print(f"  {key}: {type(val).__name__} with {len(val)} items")
        else:
            print(f"  {key}: {val}")


def print_voting_comparison(traj: Dict[str, Any]):
    """Compare voting across stages."""

    print(f"\n{'=' * 80}")
    print("VOTING COMPARISON (Committee vs Plenary)")
    print("=" * 80)

    committee_vote = None
    plenary_vote = None

    for ts in traj['timesteps']:
        if ts['stage'] == 'committee_vote':
            committee_vote = ts
        elif ts['stage'] == 'plenary_vote':
            plenary_vote = ts

    if committee_vote:
        comm_tally = committee_vote['observation']['vote_tally']
        print(f"\n📋 COMMITTEE (Third Committee):")
        print(f"   Yes: {comm_tally['yes']} | No: {comm_tally['no']} | Abstain: {comm_tally['abstain']}")
        print(f"   Result: {committee_vote['observation']['outcome'].upper()}")

        # Show some example countries
        votes = committee_vote['action']['votes']
        print(f"\n   Example Yes voters: {', '.join(votes['in_favour'][:5])}")
        print(f"   Example No voters: {', '.join(votes['against'][:5])}")

    if plenary_vote:
        # Check if we have individual votes or just tally
        action = plenary_vote['action']
        if 'votes' in action:
            # Individual votes available
            votes = action['votes']
            yes_count = len(votes.get('in_favour', []))
            no_count = len(votes.get('against', []))
            abs_count = len(votes.get('abstaining', []))
            print(f"\n🏛️  PLENARY (General Assembly):")
            print(f"   Yes: {yes_count} | No: {no_count} | Abstain: {abs_count}")
            print(f"   Result: {plenary_vote['observation']['outcome'].upper()}")
            print(f"\n   Example Yes voters: {', '.join(votes['in_favour'][:5])}")
            print(f"   Example No voters: {', '.join(votes['against'][:5])}")
        elif 'vote_tally' in action:
            # Only aggregate tally
            plen_tally = action['vote_tally']
            print(f"\n🏛️  PLENARY (General Assembly):")
            print(f"   Yes: {plen_tally['yes']} | No: {plen_tally['no']} | Abstain: {plen_tally['abstain']}")
            print(f"   Result: {plenary_vote['observation']['outcome'].upper()}")
            print(f"\n   ⚠️  Individual votes not captured at plenary stage")

    if committee_vote and plenary_vote:
        comm_tally = committee_vote['observation']['vote_tally']
        plen_tally = plenary_vote['observation']['vote_tally']

        print(f"\n📊 CHANGES:")
        yes_diff = plen_tally['yes'] - comm_tally['yes']
        no_diff = plen_tally['no'] - comm_tally['no']
        abs_diff = plen_tally['abstain'] - comm_tally['abstain']

        print(f"   Yes: {comm_tally['yes']} → {plen_tally['yes']} ({yes_diff:+d})")
        print(f"   No:  {comm_tally['no']} → {plen_tally['no']} ({no_diff:+d})")
        print(f"   Abs: {comm_tally['abstain']} → {plen_tally['abstain']} ({abs_diff:+d})")


def analyze_country_actions(traj: Dict[str, Any]):
    """Analyze what each country did across the trajectory."""

    print(f"\n{'=' * 80}")
    print("COUNTRY ACTION SUMMARY (MARL Perspective)")
    print("=" * 80)

    country_actions = {}

    for ts in traj['timesteps']:
        action = ts['action']

        # Track voting
        if 'votes' in action and isinstance(action['votes'], dict):
            for position, countries in action['votes'].items():
                for country in countries:
                    if country not in country_actions:
                        country_actions[country] = []
                    country_actions[country].append({
                        't': ts['t'],
                        'stage': ts['stage'],
                        'action': f"voted_{position}"
                    })

        # Track sponsorship
        if action['type'] == 'submit_draft_resolution':
            sponsor = action['actor']
            if sponsor != 'Unknown' and sponsor not in country_actions:
                country_actions[sponsor] = []
            if sponsor != 'Unknown':
                country_actions[sponsor].append({
                    't': ts['t'],
                    'stage': ts['stage'],
                    'action': 'submit_draft'
                })

            for cosponsor in action.get('sponsors', []):
                if cosponsor not in country_actions:
                    country_actions[cosponsor] = []
                country_actions[cosponsor].append({
                    't': ts['t'],
                    'stage': ts['stage'],
                    'action': 'co_sponsor'
                })

    # Print summary for a few key countries
    sample_countries = ['United States of America', 'China', 'Russian Federation',
                       'France', 'Iran (Islamic Republic of)', 'Albania']

    print("\n🌍 Sample Country Trajectories:")
    for country in sample_countries:
        if country in country_actions:
            print(f"\n  {country}:")
            for act in country_actions[country]:
                print(f"    T{act['t']} ({act['stage']}): {act['action']}")
        else:
            print(f"\n  {country}: No actions recorded")

    print(f"\n📈 Total countries with recorded actions: {len(country_actions)}")


def main():
    parser = argparse.ArgumentParser(
        description="Visualize UN resolution trajectory"
    )
    parser.add_argument(
        "trajectory_file",
        help="Trajectory JSON file"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed information"
    )
    parser.add_argument(
        "--timestep",
        type=int,
        help="Show only specific timestep"
    )
    parser.add_argument(
        "--comparison",
        action="store_true",
        help="Show voting comparison"
    )
    parser.add_argument(
        "--countries",
        action="store_true",
        help="Show country action summary"
    )

    args = parser.parse_args()

    # Load trajectory
    with open(args.trajectory_file) as f:
        traj = json.load(f)

    # Print summary
    print_trajectory_summary(traj)

    # Show specific timestep or all
    if args.timestep is not None:
        ts = traj['timesteps'][args.timestep]
        print_timestep(ts, verbose=args.verbose)
    else:
        for ts in traj['timesteps']:
            print_timestep(ts, verbose=args.verbose)

    # Optional analyses
    if args.comparison:
        print_voting_comparison(traj)

    if args.countries:
        analyze_country_actions(traj)


if __name__ == "__main__":
    main()
