#!/usr/bin/env python3
"""Generate standalone web visualization for UN gym with trajectory data."""

import sys
import json
import argparse
from pathlib import Path

from un_gym import load_trajectory
from un_gym.data_adapter import trajectory_to_episode, extract_country_action


def generate_html(trajectory_path: str, country: str, output_path: str):
    """Generate HTML with embedded trajectory data."""

    # Load trajectory
    traj = load_trajectory(trajectory_path)

    # Extract metadata
    metadata = traj.get('metadata', {})
    traj_id = traj.get('trajectory_id', 'unknown')
    title = metadata.get('title', 'UN Resolution')

    # Extract draft text
    draft_step = next(
        (t for t in traj['timesteps'] if t['stage'] == 'draft_submission'),
        None
    )
    draft_text = ''
    if draft_step:
        draft_text = draft_step['action'].get('draft_text', '')
        draft_text_full_length = draft_step['action'].get('draft_text_full_length', 0)
        if len(draft_text) < draft_text_full_length:
            draft_text += f"\n\n... [Full text: {draft_text_full_length} characters]"

    # Extract expert trajectory
    try:
        expert_episode = trajectory_to_episode(traj, country)
        expert_actions = [int(action) for _, action, _, _, _ in expert_episode]
    except Exception as e:
        print(f"Warning: Could not load expert trajectory: {e}")
        expert_actions = []

    # Extract key data
    sponsors = []
    if draft_step:
        sponsors = draft_step['action'].get('sponsors', [])

    committee_step = next((t for t in traj['timesteps'] if t['stage'] == 'committee_vote'), None)
    plenary_step = next((t for t in traj['timesteps'] if t['stage'] == 'plenary_vote'), None)

    committee_votes = {}
    plenary_votes = {}

    if committee_step:
        committee_votes = committee_step['observation'].get('vote_tally', {})
    if plenary_step:
        plenary_votes = plenary_step['observation'].get('vote_tally', {})

    # Determine if country is sponsor
    is_sponsor = country in sponsors

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UN Deliberation Gym - {traj_id}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}

        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}

        header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}

        header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}

        .content {{
            padding: 30px;
        }}

        .controls {{
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: center;
        }}

        .controls button {{
            padding: 10px 20px;
            border-radius: 8px;
            border: 2px solid #667eea;
            background: #667eea;
            color: white;
            cursor: pointer;
            font-size: 1em;
            font-weight: 600;
            transition: all 0.2s;
        }}

        .controls button:hover {{
            background: #5568d3;
            border-color: #5568d3;
        }}

        .controls button.secondary {{
            background: white;
            color: #667eea;
        }}

        .controls button.secondary:hover {{
            background: #f0f0f0;
        }}

        .toggle-container {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .toggle {{
            position: relative;
            width: 60px;
            height: 30px;
            background: #ccc;
            border-radius: 15px;
            cursor: pointer;
            transition: background 0.3s;
        }}

        .toggle.active {{
            background: #28a745;
        }}

        .toggle-knob {{
            position: absolute;
            top: 3px;
            left: 3px;
            width: 24px;
            height: 24px;
            background: white;
            border-radius: 50%;
            transition: left 0.3s;
        }}

        .toggle.active .toggle-knob {{
            left: 33px;
        }}

        .text-panel {{
            background: #f8f9fa;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            border: 2px solid #e9ecef;
            max-height: 400px;
            overflow-y: auto;
        }}

        .text-panel h2 {{
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.5em;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            position: sticky;
            top: 0;
            background: #f8f9fa;
            z-index: 1;
        }}

        .text-content {{
            white-space: pre-wrap;
            line-height: 1.6;
            color: #495057;
        }}

        .state-panel {{
            background: #f8f9fa;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            border: 2px solid #e9ecef;
        }}

        .state-panel h2 {{
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.5em;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}

        .state-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
        }}

        .state-item {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #dee2e6;
        }}

        .state-item label {{
            font-weight: 600;
            color: #6c757d;
            display: block;
            margin-bottom: 5px;
            font-size: 0.9em;
        }}

        .state-item .value {{
            font-size: 1.3em;
            color: #495057;
            font-weight: 600;
        }}

        .stage-indicator {{
            display: flex;
            justify-content: space-between;
            margin: 20px 0;
            position: relative;
        }}

        .stage-indicator::before {{
            content: '';
            position: absolute;
            top: 20px;
            left: 0;
            right: 0;
            height: 4px;
            background: #dee2e6;
            z-index: 0;
        }}

        .stage-step {{
            flex: 1;
            text-align: center;
            position: relative;
            z-index: 1;
        }}

        .stage-dot {{
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: #dee2e6;
            border: 4px solid white;
            margin: 0 auto 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            transition: all 0.3s;
        }}

        .stage-step.active .stage-dot {{
            background: #667eea;
            color: white;
            transform: scale(1.2);
        }}

        .stage-step.completed .stage-dot {{
            background: #28a745;
            color: white;
        }}

        .stage-label {{
            font-size: 0.9em;
            font-weight: 600;
            color: #6c757d;
        }}

        .stage-step.active .stage-label {{
            color: #667eea;
        }}

        .actions-panel {{
            background: #f8f9fa;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
        }}

        .actions-panel h2 {{
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.5em;
        }}

        .action-buttons {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}

        .action-btn {{
            padding: 20px;
            border: 2px solid #dee2e6;
            border-radius: 10px;
            background: white;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 1em;
            font-weight: 600;
            text-align: center;
        }}

        .action-btn:hover:not(:disabled) {{
            transform: translateY(-3px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            border-color: #667eea;
        }}

        .action-btn:disabled {{
            opacity: 0.4;
            cursor: not-allowed;
        }}

        .action-btn.expert-action {{
            border: 3px solid #ffc107;
            background: #fff9e6;
        }}

        .action-btn.cosponsor {{ border-color: #28a745; }}
        .action-btn.vote-yes {{ border-color: #007bff; }}
        .action-btn.vote-no {{ border-color: #dc3545; }}
        .action-btn.vote-abstain {{ border-color: #6c757d; }}

        .action-btn:hover:not(:disabled).cosponsor {{ background: #28a745; color: white; }}
        .action-btn:hover:not(:disabled).vote-yes {{ background: #007bff; color: white; }}
        .action-btn:hover:not(:disabled).vote-no {{ background: #dc3545; color: white; }}
        .action-btn:hover:not(:disabled).vote-abstain {{ background: #6c757d; color: white; }}

        .history-panel {{
            background: #f8f9fa;
            border-radius: 12px;
            padding: 25px;
        }}

        .history-panel h2 {{
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.5em;
        }}

        .history-item {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 10px;
            border-left: 4px solid #667eea;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .reward-badge {{
            background: #28a745;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: 600;
        }}

        .reward-badge.negative {{
            background: #dc3545;
        }}

        .reward-badge.neutral {{
            background: #6c757d;
        }}

        .final-panel {{
            background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            text-align: center;
            margin-top: 25px;
        }}

        .final-panel h2 {{
            font-size: 2em;
            margin-bottom: 15px;
        }}

        .final-stats {{
            display: flex;
            justify-content: center;
            gap: 40px;
            margin-top: 20px;
        }}

        .stat {{
            text-align: center;
        }}

        .stat-value {{
            font-size: 2.5em;
            font-weight: bold;
            display: block;
        }}

        .stat-label {{
            font-size: 1em;
            opacity: 0.9;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🌍 UN Deliberation Gym</h1>
            <p>{traj_id}: {title}</p>
        </header>

        <div class="content">
            <div class="controls">
                <button onclick="resetEpisode()">Reset Episode</button>
                <div class="toggle-container">
                    <span style="font-weight: 600;">Expert Mode:</span>
                    <div class="toggle" id="expertToggle" onclick="toggleExpertMode()">
                        <div class="toggle-knob"></div>
                    </div>
                </div>
                <button id="nextBtn" onclick="takeExpertAction()" style="display: none;">
                    Next (Expert Action)
                </button>
            </div>

            <!-- Resolution Text -->
            <div class="text-panel">
                <h2>📄 Resolution Text</h2>
                <div class="text-content">{draft_text}</div>
            </div>

            <!-- Stage Indicator -->
            <div class="stage-indicator" id="stageIndicator">
                <div class="stage-step" data-stage="0">
                    <div class="stage-dot">1</div>
                    <div class="stage-label">DRAFT</div>
                </div>
                <div class="stage-step" data-stage="1">
                    <div class="stage-dot">2</div>
                    <div class="stage-label">COMMITTEE</div>
                </div>
                <div class="stage-step" data-stage="2">
                    <div class="stage-dot">3</div>
                    <div class="stage-label">PLENARY</div>
                </div>
                <div class="stage-step" data-stage="3">
                    <div class="stage-dot">✓</div>
                    <div class="stage-label">DONE</div>
                </div>
            </div>

            <!-- Current State -->
            <div class="state-panel" id="statePanel">
                <h2>📊 Current State</h2>
                <div class="state-grid">
                    <div class="state-item">
                        <label>Country</label>
                        <div class="value">{country}</div>
                    </div>
                    <div class="state-item">
                        <label>Timestep</label>
                        <div class="value" id="timestep">0</div>
                    </div>
                    <div class="state-item">
                        <label>Sponsor Count</label>
                        <div class="value" id="sponsorCount">{len(sponsors)}</div>
                    </div>
                    <div class="state-item">
                        <label>Is Sponsor</label>
                        <div class="value" id="isSponsor">{"✓ Yes" if is_sponsor else "✗ No"}</div>
                    </div>
                </div>
                <div id="voteResults"></div>
            </div>

            <!-- Actions -->
            <div class="actions-panel" id="actionsPanel">
                <h2>🎮 Choose Action</h2>
                <div class="action-buttons">
                    <button class="action-btn cosponsor" onclick="takeAction(0)" data-action="0">
                        COSPONSOR
                    </button>
                    <button class="action-btn vote-yes" onclick="takeAction(1)" data-action="1">
                        VOTE YES
                    </button>
                    <button class="action-btn vote-no" onclick="takeAction(2)" data-action="2">
                        VOTE NO
                    </button>
                    <button class="action-btn vote-abstain" onclick="takeAction(3)" data-action="3">
                        VOTE ABSTAIN
                    </button>
                    <button class="action-btn" onclick="takeAction(4)" data-action="4">
                        NO ACTION
                    </button>
                </div>
            </div>

            <!-- History -->
            <div class="history-panel">
                <h2>📜 History</h2>
                <div id="historyList">
                    <p style="color: #6c757d; text-align: center;">No actions taken yet</p>
                </div>
            </div>

            <!-- Final Results -->
            <div class="final-panel" id="finalPanel" style="display: none;">
                <h2>🎉 Episode Complete!</h2>
                <div class="final-stats">
                    <div class="stat">
                        <span class="stat-value" id="finalReward">+0.0</span>
                        <span class="stat-label">Total Reward</span>
                    </div>
                    <div class="stat">
                        <span class="stat-value" id="finalSteps">0</span>
                        <span class="stat-label">Steps Taken</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Trajectory data
        const EXPERT_ACTIONS = {json.dumps(expert_actions)};
        const COMMITTEE_VOTES = {json.dumps(committee_votes)};
        const PLENARY_VOTES = {json.dumps(plenary_votes)};
        const IS_INITIAL_SPONSOR = {json.dumps(is_sponsor)};

        // State
        let currentStage = 0;
        let timestep = 0;
        let sponsorCount = {len(sponsors)};
        let isSponsor = false;
        let history = [];
        let totalReward = 0;
        let committeeYes = 0, committeeNo = 0, committeeAbstain = 0;
        let plenaryYes = 0, plenaryNo = 0, plenaryAbstain = 0;
        let done = false;
        let expertMode = false;

        const ACTION_NAMES = ['COSPONSOR', 'VOTE YES', 'VOTE NO', 'VOTE ABSTAIN', 'NO ACTION'];
        const STAGE_NAMES = ['DRAFT', 'COMMITTEE_VOTE', 'PLENARY_VOTE', 'TERMINAL'];

        function toggleExpertMode() {{
            expertMode = !expertMode;
            const toggle = document.getElementById('expertToggle');
            const nextBtn = document.getElementById('nextBtn');

            toggle.classList.toggle('active');
            nextBtn.style.display = expertMode ? 'block' : 'none';

            updateUI();
        }}

        function resetEpisode() {{
            currentStage = 0;
            timestep = 0;
            sponsorCount = {len(sponsors)};
            isSponsor = false;
            history = [];
            totalReward = 0;
            committeeYes = 0; committeeNo = 0; committeeAbstain = 0;
            plenaryYes = 0; plenaryNo = 0; plenaryAbstain = 0;
            done = false;
            updateUI();
            document.getElementById('finalPanel').style.display = 'none';
        }}

        function takeExpertAction() {{
            if (done || !expertMode) return;

            const stepIdx = history.length;
            if (stepIdx < EXPERT_ACTIONS.length) {{
                takeAction(EXPERT_ACTIONS[stepIdx]);
            }}
        }}

        function takeAction(actionId) {{
            if (done) return;

            const actionName = ACTION_NAMES[actionId];
            let reward = 0;

            // Transition logic based on actual trajectory
            if (currentStage === 0) {{ // DRAFT
                if (actionId === 0) {{ // COSPONSOR
                    isSponsor = true;
                }} else if (actionId === 4 && IS_INITIAL_SPONSOR) {{
                    isSponsor = true;
                }}

                if (timestep === 0) {{
                    timestep = 1;
                }} else {{
                    currentStage = 1; // COMMITTEE_VOTE
                    timestep = 2;
                }}
            }} else if (currentStage === 1) {{ // COMMITTEE_VOTE
                // Use actual vote results
                committeeYes = COMMITTEE_VOTES.yes || 0;
                committeeNo = COMMITTEE_VOTES.no || 0;
                committeeAbstain = COMMITTEE_VOTES.abstain || 0;
                currentStage = 2; // PLENARY_VOTE
                timestep = 3;
            }} else if (currentStage === 2) {{ // PLENARY_VOTE
                // Use actual vote results
                plenaryYes = PLENARY_VOTES.yes || 0;
                plenaryNo = PLENARY_VOTES.no || 0;
                plenaryAbstain = PLENARY_VOTES.abstain || 0;
                currentStage = 3; // TERMINAL
                timestep = 4;

                // Calculate reward
                const outcome = plenaryYes > plenaryNo ? 'adopted' : 'rejected';
                if (isSponsor) {{
                    reward = outcome === 'adopted' ? 1.0 : -1.0;
                }}

                done = true;
                totalReward += reward;
            }}

            // Add to history
            history.push({{ action: actionName, reward }});

            updateUI();

            if (done) {{
                document.getElementById('finalPanel').style.display = 'block';
                document.getElementById('finalReward').textContent = totalReward >= 0 ? `+${{totalReward.toFixed(1)}}` : totalReward.toFixed(1);
                document.getElementById('finalSteps').textContent = history.length;
            }}
        }}

        function updateUI() {{
            // Update stage indicator
            document.querySelectorAll('.stage-step').forEach((step, idx) => {{
                step.classList.remove('active', 'completed');
                if (idx === currentStage) {{
                    step.classList.add('active');
                }} else if (idx < currentStage) {{
                    step.classList.add('completed');
                }}
            }});

            // Update state
            document.getElementById('timestep').textContent = timestep;
            document.getElementById('sponsorCount').textContent = sponsorCount;
            document.getElementById('isSponsor').textContent = isSponsor ? '✓ Yes' : '✗ No';

            // Update vote results
            let voteHTML = '';
            if (committeeYes > 0) {{
                voteHTML += `
                    <div class="state-grid" style="margin-top: 15px;">
                        <div class="state-item">
                            <label>Committee Yes</label>
                            <div class="value">${{committeeYes}}</div>
                        </div>
                        <div class="state-item">
                            <label>Committee No</label>
                            <div class="value">${{committeeNo}}</div>
                        </div>
                        <div class="state-item">
                            <label>Committee Abstain</label>
                            <div class="value">${{committeeAbstain}}</div>
                        </div>
                    </div>
                `;
            }}
            if (plenaryYes > 0) {{
                voteHTML += `
                    <div class="state-grid" style="margin-top: 15px;">
                        <div class="state-item">
                            <label>Plenary Yes</label>
                            <div class="value">${{plenaryYes}}</div>
                        </div>
                        <div class="state-item">
                            <label>Plenary No</label>
                            <div class="value">${{plenaryNo}}</div>
                        </div>
                        <div class="state-item">
                            <label>Plenary Abstain</label>
                            <div class="value">${{plenaryAbstain}}</div>
                        </div>
                    </div>
                `;
            }}
            document.getElementById('voteResults').innerHTML = voteHTML;

            // Update action buttons
            const buttons = document.querySelectorAll('.action-btn');
            const validActions = getValidActions();
            const nextExpertAction = expertMode && history.length < EXPERT_ACTIONS.length ? EXPERT_ACTIONS[history.length] : -1;

            buttons.forEach((btn, idx) => {{
                btn.disabled = !validActions[idx] || done;
                btn.classList.remove('expert-action');
                if (expertMode && idx === nextExpertAction) {{
                    btn.classList.add('expert-action');
                }}
            }});

            // Update history
            const historyHTML = history.map((item, idx) => {{
                const badgeClass = item.reward > 0 ? '' : (item.reward < 0 ? 'negative' : 'neutral');
                const rewardText = item.reward !== 0 ? `${{item.reward > 0 ? '+' : ''}}${{item.reward.toFixed(1)}}` : '-';
                return `
                    <div class="history-item">
                        <span><strong>Step ${{idx}}:</strong> ${{item.action}}</span>
                        <span class="reward-badge ${{badgeClass}}">${{rewardText}}</span>
                    </div>
                `;
            }}).join('');
            document.getElementById('historyList').innerHTML = historyHTML || '<p style="color: #6c757d; text-align: center;">No actions taken yet</p>';
        }}

        function getValidActions() {{
            if (currentStage === 0) {{
                return [true, false, false, false, true]; // COSPONSOR or NO_ACTION
            }} else if (currentStage === 1 || currentStage === 2) {{
                return [false, true, true, true, false]; // Vote options
            }} else {{
                return [false, false, false, false, true]; // Only NO_ACTION
            }}
        }}

        // Initialize
        resetEpisode();
    </script>
</body>
</html>'''

    # Write HTML file
    with open(output_path, 'w') as f:
        f.write(html)

    print(f"Generated web visualization: {output_path}")
    print(f"Country: {country}")
    print(f"Is sponsor: {is_sponsor}")
    print(f"Expert actions: {expert_actions}")


def main():
    parser = argparse.ArgumentParser(description='Generate web visualization for UN gym')
    parser.add_argument(
        '--trajectory', '-t',
        default='scratch/220.json',
        help='Trajectory JSON file'
    )
    parser.add_argument(
        '--country', '-c',
        default='France',
        help='Country perspective'
    )
    parser.add_argument(
        '--output', '-o',
        default='scratch/gym_viz_enhanced.html',
        help='Output HTML file'
    )

    args = parser.parse_args()

    generate_html(args.trajectory, args.country, args.output)


if __name__ == '__main__':
    main()
