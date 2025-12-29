# IGO‑Gym: A Benchmark for Language‑Mediated Multilateral Decision‑Making

## Stakes (Why now)

* **Real impact**: Intergovernmental organizations (IGOs) coordinate crisis response, budgets, and norms; small text changes can shift outcomes.
* **Scientific gap**: Few standardized environments test algorithms that must **plan + negotiate + draft** under procedural constraints.
* **What we enable**: Comparative, reproducible research on mechanism design, multi‑agent learning, and robustness to language‑model (LM) delegate bias.

## Scope (What the gym is)

A suite of benchmark environments modeling committee-style decision processes with:

* **Document state**: Resolutions as a **document abstract syntax tree (AST)** (preambular and operative sections). Agents change state via **validated deltas** (insert/edit/delete/set‑parameter/add‑condition).
* **Procedure engine**: Encodes agenda, debate windows, voting thresholds, veto, and deadlines as a finite‑state machine.
* **Communication**: Tracks with (i) no communication, (ii) **speech‑acts** (templated messages), and (iii) **free text** with a required JSON payload the simulator executes.
* **Agents**: Scripted baselines, learned policies, LM “delegates,” and optional human seats.

Terms: **MARL** = multi-agent reinforcement learning. **AST** = abstract syntax tree. **OPE** = off-policy evaluation.

## Current focus (2025-12)

- **UN genealogy coverage**: use `trace_genealogy.py` + `UNDocumentIndex` to link agenda items, committee drafts, reports, plenary meetings, and final resolutions for GA session 78 (Iran case study is the template).
- **Trajectory builder loop**: convert each genealogy into MARL-ready JSON via `build_trajectory.py`, capture the five coarse stages (agenda allocation → plenary vote), and surface them with `visualize_trajectory.py` and the `viz/` assets.
- **Data readiness checks**: keep the README + `analysis_iran_genealogy_report.md` in sync so we know exactly which documents (and vote rolls/utterances) exist before scaling to additional sessions.
- **Future fit**: design the above tooling to plug cleanly into the Track A/B environments—structured deltas, procedure FSM, and agent policies stay untouched by data refreshes.

## Data sources (to ground scenarios & build a training set)

* **UN General Assembly / Main Committees**: Drafts (L.), **Rev.**, **Add.**, **Corr.**, final resolutions; meeting records; voting metadata.
* **UN Security Council**: Final texts; partial draft visibility plus process trackers; meeting records.
* **Specialized agencies** (e.g., WHO/WHA): Draft resolutions/decisions with revision history and budget notes.
* **Other legislatures** (for tooling patterns): EU Parliament, US Congress (multiple bill versions, official XML), UK Parliament amendment lists.
* Use version chains (Draft → Rev. → Add. → Final) to learn **edit distributions** and evaluate structured diffs.

## Methodology (modeling + data pipeline)

1. **Schema**: Typed clause records (e.g., `POSITION`, `DIRECTIVE`, `REPORTING_REQUEST`, `BUDGET`), with slots for verb, addressee, action head, object, means, purpose, triggers, reporting, deadlines, budgets, and tags.
2. **Surface realizer**: Deterministic rules map JSON → canonical prose (IGO style: numbered operative paragraphs; semicolons/periods; organ‑specific verbs).
3. **Parser**: Rule‑first extractor (plus optional spaCy patterns) for prose → JSON. Handles clause segmentation, verb/type detection, addressees, action head/object, means (e.g., “including by …”), purpose (“with a view to …”), reporting, deadlines, recipients. Human‑in‑the‑loop adjudication for low‑confidence cases.
4. **Environment**: PettingZoo/Gym‑compatible API; JSON deltas validated by schema; procedure FSM enforces legal moves.
5. **Policies**: (a) scripted heuristics; (b) constrained RL for planning; (c) **planner + communicator** factorization for LM delegates; (d) OPE using archival logs where available.

## Versions / Levels (difficulty & realism ladder)

* **Track A (No‑Press)**: No communication; only structured actions. Tasks: T0 allocation; T1 coalition formation; T2 amendment queue management.
* **Track B (Speech‑Acts)**: Propose/sponsor/call‑vote/justify via templated messages; commitments with penalties.
* **Track C (Free‑Text)**: Natural language; proposals must include a **STRUCTURED_DELTA** block; parser enforces schema.
* **Population**: Single‑agent vs MARL vs human‑in‑the‑loop; opponent pools for cross‑play and zero‑shot generalization.

## Evaluation & metrics

* **Outcome**: social welfare (sum or max‑min of agent utilities), adoption rate, time‑to‑decision, stability (no profitable deviations), and rule‑compliance.
* **Fairness/robustness**: bounded group regret; sensitivity of outcomes to LM family/prompt (delegate bias); commitment‑honor rate.
* **Language**: calibration of promises, messaging cost, public/private transparency ratio.
* **Reproducibility**: fixed seeds, population protocols, ablations (remove communication; swap delegates; change rules).

## Roadmap snapshot

**Now**

- Harden genealogy coverage + trajectory export for A/RES/78/220-style cases (session 78) and document completeness gaps.
- Keep the clause schema + parser scaffolding in sync with the data we actually have (agenda/draft/report text, voting rolls, utterances).
- Finalize scripted baselines + procedure FSM API surface so Trajectory JSON slots directly into Track A simulations.

**Next**

- Extend scraping/indexing to additional GA sessions (75–79) and prioritize ones with full committee + plenary coverage.
- Wire trajectory outputs into Track B (speech-acts) once statement metadata is reliable; begin OPE using historical votes.
- Publish a minimal dataset bundle (genealogies + trajectories + viz) together with the README instructions for reproducibility.

## Extensions (v0.2+)

* **Track C** free‑text; LM delegates with tool‑use; robust parsing via JSON payloads.
* **Domains**: budgeted crises, sanctions/assistance framing, mandate renewals, reporting calendars.
* **Mechanism design**: learn agenda/voting mechanisms with constraints; impossibility and regret bounds.
* **Data expansion**: semi‑automated harvesting of version chains; active learning for parser improvements.

## Risks & mitigations

* **Realism gap**: use forum profiles and calibrated utility generators; include sovereignty/framing clauses.
* **Parsing brittleness**: keep speech‑act track; require STRUCTURED_DELTA in free‑text track; human review for low confidence.
* **Compute**: no‑press track is cheap; LM usage optional and budgeted.

## Deliverables

* Open‑source gym (engine + tasks + baselines); parser/realizer; small dataset of versioned clauses; docs + leaderboard spec; v0.1 paper/README.

## Success criteria

* ≥2 tasks with strong baselines and ablations; ≥80% parser coverage on the gold set with ≤25% residual text by length; reproducible improvements from communication or mechanism variants; external users can run and score.

Resources: parsed notes and example material [uploaded notes](/mnt/data/ml ndcm.pdf).
