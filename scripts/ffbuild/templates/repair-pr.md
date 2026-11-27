## Auto-Heal

**Status:** $status
**Repair round:** $round/$max_rounds
**Source failure:** $source_failure

### Summary

$summary

Root-cause hypotheses remain unverified by full production CI until the required matrix passes.

### Changes

$changes

### Repair history

| Round | Commit | Root-cause hypothesis | CI |
| --- | --- | --- | --- |
$history
$earlier_attempts
### Repair reports and independent security audit

$round_reports

### Verification

Required CI verifies the current PR HEAD.
