# CI/CD Architecture Specification

Current build and operations contracts are maintained in:

- [Build tools and release operations](build-tools.md): native ABI planning,
  dependency caches, event gates, packaging, Data migration, publication,
  retention and recovery.
- [Auto-Heal lifecycle](ci-autoheal.md): failure classification, version scope,
  repair limits, PR state and verification.

The previous architecture is preserved in Git history. It is not the
operational specification for the native-ABI build pipeline.
