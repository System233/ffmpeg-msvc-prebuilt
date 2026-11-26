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
   Build All FFmpeg Versions automatic version PRs, explicit main Build FFmpeg
   Release dispatches, and scheduled Build FFmpeg Master runs, or accepts an explicitly supplied completed run ID/attempt. Main Push
   and human/fork PRs cannot become source-repair inputs.
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
   synchronizes the PR description and comments. Only verified complete
   single-version CI success permits GitHub native squash Auto-merge.
   The repair lifecycle ends at merge. Neither successful CI nor merging
   an automatic PR creates a production tag or publishes a release.
   Master is checked on the next Friday or by manual dispatch; stable
   versions are built for publication only by explicit workflow dispatch.

Read-only CLI commands:

- python -m ffbuild autoheal triage --run-id <RUN> [--attempt N]
- python -m ffbuild autoheal inspect --triage autoheal-triage.json
- python -m ffbuild autoheal check-worktree (inside the active Agent session;
  returns structured violations without restarting or changing the candidate)

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
Only the authorized same-repository Bot, matching version label and branch
(auto/ffmpeg-<version> or autoheal/<version>/<incident>) may enter native
validation. The full 16-variant matrix for that single version is forced.
Ordinary PRs and Main Push never compile or scan native ABIs. Master repair
PRs retain the exact upstream snapshot of the original failed Master run/attempt. The exact source pin comes from the verified Build Plan, not a tag.

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
and scope checks. The trusted resolver compares all existing non-target
effective configurations and their inheritance paths before allowing a native
build. New-version PRs may add a previously nonexistent family template
only if it is empty and leaves all old versions unchanged. A source-less
family template can acquire a pinned source only if existing versions remain unchanged.

## Repair limits and recursion

- Maximum local OpenCode attempts per incident: 3.
- Maximum CI-verified Repair rounds per bot PR: 2.
- Maximum concurrent Repair jobs: 2.
- At most one active bot repair PR per version and original error signature.
- Original run attempts and newer PR HEADs are verified before repair.
- Bot PR CI failures continue the same incident, using the original PR
  signature and round metadata; they do **not** spawn independent PRs.
  New-version PRs retain the original proposal commit, then up to two repair
  commits on that same branch.
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
  validation state, and links to authenticated CI evidence.

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

PR description reconciliation and delivery share one version-scoped GitHub
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

Eligibility for bounded diagnosis is not proof that a repair exists.
Readable native build failures are eligible unless a concrete infrastructure,
external dependency, ABI, packaging or other out-of-scope failure is present.
Patch application failures are recognized explicitly. Unknown compiler,
configure, linker and consumer errors receive diagnosis without a filename
allowlist. Different source diagnostics for one version are retained separately
in one incident; the Agent does not assume a common root cause. A normalized
patch identity avoids Hunk offsets and runner paths splitting the same failure.
Missing evidence and mixed out-of-scope failures remain fail closed.
The Agent may explicitly decline with `Decision: no_safe_fix` and leave the
source unchanged; the supervisor emits a source-bound no-op manifest, and
Delivery performs no GitHub writes. A candidate still requires the same strict
scope validation and complete 16-variant CI. Existing retry and round limits
are unchanged.

The legacy standalone repair scripts have been removed. The bounded Agent
runner is now ffbuild.autoheal.runner, using the same independent scope checks.
The portable skill at .agents/skills/ffmpeg-autoheal/SKILL.md is tracked with
the build tools; the repair prompt names it explicitly. No opencode branch is
fetched. OpenCode remains only an execution adapter; client-specific skill
auto-discovery is not required.
The skill is a procedural repair guide rather than a historical patch catalog.
The Agent receives a per-failed-job projection of the matched native Build
Plan (including feature closure, package, triplet, ABI and source pin), plus
exact log paths. These fields are diagnostic evidence only; the existing
trusted-source, scope, round and delivery checks remain authoritative.
For stable versions resolve the pin from the target YAML; Master uses the
recorded full upstream commit and SHA512. No native build or install is
required in the repair job: reconstruct the source and patch sequence,
compare configuration semantics and submit a candidate for remote MSVC CI.
 A pre-relocation failed checkout without this
tool layout must be rebuilt from the new main before automated repair.

## Public GitHub messages

New version PRs use an English proposal template with the upstream source,
configuration inheritance, changed files and a managed CI verification section.
Repair PRs use the validated Agent commit subject and a compact history table.
Incident signatures and event keys remain in hidden HTML comments; old visible
incident fields remain readable for compatibility. Full ABI hashes and compiler
logs stay in CI evidence. Maintainer notes outside managed sections are preserved.
Only authenticated complete matrix verification may be displayed as 16/16 passed.


### Active repair deduplication

Triage checks all active Bot repair branches for the same version and incident,
including later occurrence suffixes. Delivery checks again before creating a
new repair PR. Repair and delivery are serialized by version.
An existing repair PR is never closed automatically by duplicate detection.
