# Multi-version FFmpeg CI Auto-Heal

## Scope and ownership

FFmpeg's normal build remains owned by the existing ffbuild planner, native vcpkg
ABI scanner, central dependency Seed, and native MSVC build workers. The new
ffbuild.autoheal Python package **consumes CI evidence**; it reuses native vcpkg ABI and verifies representative FFmpeg builds in the same repair Runner, not the full production matrix.

GitHub workflows are maintained as repository code. The autonomous repair
worker may change only the exact failed version YAML and newly added,
version-exclusive FFmpeg source patches. It cannot modify any workflow,
build script, third-party Port, data branch content, or another version YAML.

## Trigger and lifecycle

1. The independently triggered FFmpeg Auto-Heal workflow observes completed
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
   A Windows 2022 worker restores the exact dependency Seed and pinned source,
   then runs Pi with native FFmpeg/Tester build access. The supervisor rebuilds
   each chosen representative from a clean install root before committing.
   The worker produces repair.patch, manifest.json, and repair-report.md;
   it receives no GitHub write permission or GitHub App token.
5. An independent read-only Audit job reviews the exact native-verified patch.
   Only a matching approval receipt permits delivery.
6. An independent privileged Delivery job verifies the source run identity,
   exact source SHA, target YAML, patch checksum, path additions/changes,
   patch ownership, staged modes, and branch ancestry **again**. Fail closed
   if any material is missing, ambiguous, or out of scope.
7. The bot pushes without force, creates or updates only its own repair PR,
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

A run attempt is different from a Pi invocation and from a Repair round.
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

- One persistent Pi session per incident, with a 180-minute repair budget and a
  300-minute Runner job timeout. Three consecutive Agent invocation failures abort.
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
results. A candidate is marked locally verified only after an actual native build and
Tester pass; full production matrix CI is a separate merge gate. Remaining operational limitations must be recorded rather
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
scope validation and complete 16-variant CI. The two-round production repair limit remains unchanged.

## In-Runner repair

The worker uses pinned Pi with OPENAI_BASE_URL (default https://api.openai.com/v1),
OPENAI_API_KEY (secret) and OPENAI_MODEL. OPENAI_AUDIT_MODEL optionally selects
a separate review model. The endpoint must implement OpenAI Responses, native
web_search, streaming for Pi, and strict JSON Schema structured outputs for audit.
No Chat Completions fallback is allowed. GitHub write
credentials remain exclusive to Delivery. Agent tooling runs as the Runner
user; scope checks and independent verification are acceptance gates, not
an OS sandbox.

Preparation binds the exact failed commit, pinned source and dependency
contract, generates the Seed key, restores the required architecture caches
and verifies every external native ABI before Pi starts. Cache restoration also supports the historical runner paths; a legacy hit is moved into the current cache before native ABI validation. Missing cache entries
may be prepared in preflight; no external dependency may be built during
repair. Incompatible historical tool layouts must be rebuilt first.

The repository-owned skill guides diagnosis, source changes and variant selection.
The Agent runs:

- python -m ffbuild autoheal build "ffmpeg[all-gpl]:x64-windows"
- python -m ffbuild autoheal test "ffmpeg[all-gpl]:x64-windows"
- python -m ffbuild autoheal smoke "ffmpeg[all-gpl]:x64-windows"
- python -m ffbuild autoheal status

Use GPL/nonfree shared by default, static for static-only failure groups,
and LGPL fallback for LGPL-specific failures. Select affected architectures
and explain which failed jobs each representative covers in validation-plan.json.
Do not execute the full matrix in the repair job. Tester compilation/linking
and PE/COFF architecture verification are mandatory; executable smoke tests
run only on compatible Windows hosts. A cross-target runtime skip is explicit.

Supervisor feedback returns to the same session until clean verification
passes or the budget/environment fails. The supervisor commits the exact
verified tree; manifest schema 2 binds the patch, candidate commit/tree and
representative ABI/test evidence. Delivery independently checks those bindings
and scope before any write. Normal full-matrix CI is still mandatory for merge.

A separate Ubuntu audit job replays the candidate Git tree without executing
its code, compares the full dependency/feature/license contract, and reviews
the diff and effective configurations with an independent Responses session.
It has only bounded read-only context tools (referenced patch files and SHA512-
verified pristine upstream source) and native Web Search. The strict structured
verdict is bound by the controller to the manifest SHA256, patch SHA256, source
incident and candidate tree. Missing, rejected, inconclusive, invalid or mismatched
audit results block GitHub App credentials and delivery. Artifacts are scoped to the workflow attempt; rerun all jobs rather than only failed jobs to regenerate the entire chain. An approved audit is
not a proof of security; production CI remains mandatory. Audit rejection ends
the incident without automatic delivery; no candidate code is executed in audit.

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
