# Multi-version FFmpeg CI Auto-Heal

## Scope and ownership

FFmpeg's normal build remains owned by the existing ffbuild planner, native vcpkg
ABI scanner, central dependency Seed, and native MSVC build workers. The new
ffbuild.autoheal Python package **consumes CI evidence**; it never computes a
second dependency ABI or builds a local FFmpeg matrix.

GitHub workflows are maintained as repository code. The autonomous repair
worker may change only the exact failed version YAML and newly added,
version-exclusive FFmpeg source patches. It cannot modify any workflow,
build script, third-party Port, data branch content, or another version YAML.

## Trigger and lifecycle

1. The independently triggered OpenCode Auto-Heal workflow observes completed
   Build All FFmpeg Versions, Build FFmpeg Release, and Build FFmpeg Master runs,
   or accepts an explicitly supplied completed run ID/attempt.
2. A read-only Triage job combines the GitHub run/attempt, job/step conclusions,
   native ffbuild-plan, exact matrix identity, vcpkg ABI, and build log artifacts.
   Artifacts include their exact run attempt in the names (e.g. `ffbuild-plan-a2`
   and `build-logs-a2-8.1.1-<variant-id>`) to prevent cross-attempt confusion.
   It produces autoheal-triage.json and a matrix of eligible version incidents.
3. Triage does not guess missing plan or artifact identities. Shared Plan,
   Download, Prepare/Seed, ABI, Runner, Package, and Publish failures are
   diagnosed, not sent to the source repair agent.
4. Eligible versions run as separate Repair matrix jobs (parallelism at most 2).
   The worker produces repair.patch, manifest.json, and repair-report.md;
   it receives no GitHub write permission or GitHub App token.
5. An independent privileged Delivery job verifies the source run identity,
   exact source SHA, target YAML, patch checksum, path additions/changes,
   patch ownership, staged modes, and branch ancestry **again**. Fail closed
   if any material is missing, ambiguous, or out of scope.
6. The bot pushes without force, creates or updates only its own repair PR,
   synchronizes the PR description and comments, and requests GitHub's native
   squash Auto-merge. The repository's required CI gates control the merge.

Read-only CLI commands:

- python -m ffbuild autoheal triage --run-id <RUN> [--attempt N]
- python -m ffbuild autoheal inspect --triage autoheal-triage.json

CI-only commands:

- python -m ffbuild autoheal repair --triage ... --yaml <VERSION>
- python -m ffbuild autoheal deliver --triage ... --yaml <VERSION>
- python -m ffbuild autoheal sync-pr --triage ...
- python -m ffbuild autoheal check-pr --yaml <VERSION> --base SHA --head SHA

## Provenance and identity

The report schema (version 1) contains:

- source: run_id, run_attempt, head_sha, event, branch, conclusion, URL;
- groups: YAML, phase, classification, repairable decision, signature, jobs;
- per job: GitHub job ID, native variant ID, triplet, native ABI, exact artifact;
- additional nonrepairable diagnostic jobs and an eligible Repair matrix.

A run attempt is different from an OpenCode attempt and from a Repair round.
The JSON record must always match the authenticated GitHub API source.

The matrix job name is explicitly "ffbuild-<native variant ID>" so no build
job is assigned merely by finding an architecture string in its display name.
The PR scanner selects **all impacted source-backed versions** based on
inherited configuration, used source patches, triplets, and shared build inputs;
it does not silently fall back to latest_per_family for PR checks. PR build
planning uses forced native ABI coverage. An empty PR build matrix fails.

When a PR affects master, generate and scan reuse a single upstream source
metadata file, preventing mismatched snapshot identities.

## File and patch policy

Permitted:

- modify ffmpeg/<exact version>.yaml;
- add patches/<major>.x/<name>.patch, only when newly referenced by this
  version and not referenced by any other version YAML.

Rejected:

- missing, deleted or renamed target YAML;
- modifying or deleting any existing source patch, including shared patches;
- editing another YAML, workflows, scripts, Port overlays, data, or any other
  file; adding symlinks or executable files;
- no patch, incorrect checksum, corrupted manifest, invalid Git delta,
  ambiguous job identity, stale HEAD, or missing target.

GitHub pull-request checks repeat the scope check against the **entire bot PR
diff** rather than only its latest commit. The final required
all-checks-passed job aggregates the actual build workflow and PR validation
and scope checks.

## Repair limits and recursion

- Maximum local OpenCode attempts per incident: 3.
- Maximum CI-verified Repair rounds per bot PR: 2.
- Maximum concurrent Repair jobs: 2.
- Exactly one bot branch/PR per version and original error signature.
- Original run attempts and newer PR HEADs are verified before repair.
- Bot PR CI failures continue the same incident, using the original PR
  signature and round metadata; they do **not** spawn independent PRs.
- Human-authored or fork PRs remain diagnostic only. The worker never
  force-pushes a developer branch.
- Infrastructure retries are only recommended by diagnostics at this stage;
  no unattended cache, release, or publication rerun is performed.

The PR branch name is deterministic:
autoheal/<version>/<incident key>. Git commit trailers store
Autoheal-Round, Autoheal-Incident, and Autoheal-Source-Run.

## PR message history (cumulative)

The PR title remains tied to the original FFmpeg failure. Its body is a
**derived cumulative view**, never a projection of only the latest Agent fix.

Durable contracts:

- **RepairRound (ffbuild.autoheal.ledger)**: every bot commit records
  Autoheal-Round, Autoheal-Incident, Autoheal-Source-Run,
  Autoheal-Source-Attempt and Autoheal-Hypothesis trailers.
  pr_history.load_rounds reads **all** PR commits, validating the incident,
  consecutive round numbers, exact HEAD and linear parent chain. It loads
  the files changed during each round.
- **RepairEvent**: each repair submission and completed CI run/attempt
  produces a dedicated bot issue comment with a deterministic key:
  incident + round + type + run + attempt + SHA. Retried notifications are
  deduplicated; comments are appended rather than edited or overwritten.
- **PR body**: pr_history.render_history rebuilds all rounds with their
  commit, root-cause hypothesis, source CI, changed paths, and CI attempts.
  It also displays the cumulative PR diff from GitHub, the most recent
  validation state, and available latest failure evidence.

Only the owned PR section is refreshed; manually authored text outside it
is preserved byte-for-byte. Delivery appends each new round. CI sync reads
the entire commit and bot event history before re-rendering the PR body.

Failure recovery:

- If the PR body loses its managed markers, the bot reconstructs the incident
  from the authenticated Git commit trailers; hand-authored notes are retained
  ahead of the reconstructed section. A fresh PR read immediately precedes
  updates to minimize the risk of overwriting concurrent maintainer edits.
- Cumulative descriptions retain **every repair round**, but bound displayed
  file paths and CI-attempt details. Complete events remain append-only in PR
  comments and GitHub Actions; summaries remain below the PR body size budget.
- A closed historical PR does not permanently reserve the original error
  signature. A new failure run receives an occurrence-scoped bot branch,
  while an existing active PR continues the same original incident.
- If a previous push/PR creation succeeded but messages or Auto-merge failed,
  Delivery validates the bot commit's exact source Run and parent, then
  reconciles the existing PR instead of consuming another repair round.
- A pushed branch with no PR may be recovered **only** if GitHub maps both
  commit identities to the dedicated bot, the original run/parent match, and
  applying the candidate patch to the original source produces the **exact
  same Git tree** with no out-of-scope files. Otherwise recovery fails closed.

1. If push succeeds but updating the description or event comment fails,
   later sync reconstructs missing submission comments from bot commits
   and re-renders all history, rather than trusting stale body fields.
2. If GitHub accepted a comment but its HTTP response was lost, the next
   attempt finds the event key and does not duplicate it.
3. Old CI results remain in the timeline, but cannot overwrite newer HEAD
   information. For one HEAD, the latest run ID and attempt determine
   current status, independent of webhook arrival order.
4. Unmarked or inconsistent repair commit sequences fail closed; a human
   comment cannot masquerade as a bot repair event.

PR description reconciliation and delivery share one branch-scoped GitHub
Actions concurrency group, so independent CI run notifications cannot
concurrently rewrite the same bot PR. A normal repair job still runs without
GitHub write credentials; only the dedicated writer and message-sync jobs
receive the short-lived GitHub App token.

The bot never marks an untested FFmpeg patch MSVC-verified. GitHub Auto-merge
remains gated on the repository's required all-checks-passed check.

## Validation and deployment

Control-plane acceptance uses **offline simulations**: mocked GitHub
run/attempt/job/artifact responses, mixed-error classification, untrusted
log-marker injection, PR body/trailer reconciliation after partial writes,
branch-collision rejection, scope policy, tiny Git patch replay, Python tests,
ffbuild validate, and actionlint. No remote end-to-end test or local full
MSVC FFmpeg build matrix is required for mechanism acceptance.

Simulations validate policy and state transitions, not actual Windows compiler
results. A real FFmpeg patch may only be marked as successfully compiled when
its normal required GitHub CI passes; that production build is separate from
mechanism testing. Remaining operational limitations must be recorded rather
than mislabeled as tests passed.

### Simulated review, 2026-11-23

The four new failure-injection scenarios first reproduced three concrete
control-plane defects: unrelated source errors collapsed into one incident,
untrusted log text could impersonate a PR managed-section end marker, and a
partial PR update could leave the body round behind its authoritative bot
commit. After repairs, all 4/4 injection scenarios pass. Existing Auto-Heal
scenarios: 35/35 pass; full offline Python regression: 581/581 pass.
`actionlint` passes for the modified workflows and `ffbuild validate` covers
26 source-backed versions and three template configurations.

Recovery after a successful branch push but failed first PR creation remains
**fail closed**: the orphan branch is detected and never overwritten, but the
current automatic workflow does not yet construct a trusted PR from it. This
is an availability limitation rather than a privilege bypass. A future
idempotent reconcile operation should validate the branch commit parent,
bot trailers and full file scope before creating its missing PR and enabling
GitHub Auto-merge. It must never take ownership of arbitrary branches.

### Multi-round PR message revision

In the latest revision, the obsolete single-round managed_block/reconcile
path was removed. The new pr_history.py reads all bot commits, validates
linear parent relationships, derives a complete per-round history, and
reconciles keyed bot comments without duplication. Offline simulations cover
round-1 failure followed by round-2 pending/success, CI reruns, delayed CI
notifications, missed/duplicated comments, a failed PR body write, forged
comment metadata, manual text retention, and inconsistent Git commit history.
The complete offline Python regression passed **597/597**; CI syntax and Port
configuration validation were also performed locally. No online PR mutations,
commit, push or real FFmpeg build were executed for this revision.

Signature equality is deliberately conservative: if multiple variants of one
version show different compiler diagnostics, Auto-Heal performs diagnosis only
instead of claiming a shared root cause. A later normalized root-cause
clustering algorithm could improve repair coverage without weakening scope
checks.

The legacy scripts/ci auto_heal_decide.py, auto_heal_context.py and
apply_fix.py are no longer referenced by GitHub workflows; the existing
agent_repair.py loop remains as a bounded implementation detail behind the
new target scope validator.
