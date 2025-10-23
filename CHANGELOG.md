# Changelog

## Unreleased (2025-10-22)

### Added

- Feat: add automated changelog generation and release process.
    
  - Add generate-changelog dependency for automated changelog generation
  - Configure generate-changelog with pipeline-based configuration
  - Add changelog and changelog-preview tasks to Taskfile
  - Integrate changelog generation into release tasks
  - Add comprehensive documentation for changelog and release process
  - Support conventional commits and breaking change detection
  - Filter irrelevant commits (chore, ci, build) automatically
### Fixed

- Fix: aggregate model-level metrics correctly across multiple entities (#5).
    
### Other

- Chore: update changelog.
    
## v1.3.0 (2025-10-21)

### Added

- Feat(deploy): Improve db table handling and logging.
    
- Feat(deploy): Replace tini by propper sginal handling.
    
### Fixed

- Fix(ci): Fix Bump version config.
    
- Fix(deploy): Sync git tag with version.
    
- Fix(code): Formating.
    
- Fix(ci): Rebuild e2e test.
    
- Fix(ci): Always build the container for e2e and local start.
    
- Fix(deploy): Sync python version with uv.
    
### Other

- Bump version: 1.2.0 → 1.3.0.
    
- Chore(docs): Update readme.
    
## v1.2.0 (2025-10-20)

### Added

- Feat: Add new metrics (budget, budget spend, TPM, RPM) (#1).
    
  * feat: Add metric for key budget and key spend budget
  * feat: Enhance doc for litellm_key_spend
  * feat: Add metrics for current TPM/RPM usage

  ---------

  **co-authored-by:** LukasPoque <lukas.poque@lime.tech>

### Other

- Modernize (#2).
    
  * chore(repo): Cleanup
  * feat(deploy): Replace pip by uv
  * feat(tests): Add e2e tests
  * feat(ci): Replace make with taskfile
  * feat(ci): Add py and md lint
  * feat(ci): Add CI GHA workflow
  * fix(ci): Add container build to ci task
## v1.1.4 (2025-08-07)

### Fixed

- Fix: Problem with commits for selects.
    
## v1.1.3 (2025-08-07)

### Other

- Chore: prepair build on my dockerhub.
    
## v1.1.2 (2025-06-11)

### Added

- Feat: Add docs for metric for spend by key.
    
- Feat: add makefile for easy local build and testing.
    
- Feat: Add metric for spend by key.
    
### Fixed

- Fix: sort imports.
    
- Fix: add tini bin for the right arch.
    
### Other

- Chore: fix formating.
    
- Docs: update documentation.
    
## v1.1.1 (2024-12-07)

### Changed

- Update container path.
    
- Update.
    
### Other

- Ci: update and push to docker hub.
    
- Build: Update CI.
    
- Build: add ci files.
    
## v1.0.0 (2024-12-07)

### Added

- Add missing git files.
    
### Changed

- Refactor: split into multiple files.
    
### Other

- Chore: prepare release v1.0.0.
    
- Docs: Update documentation.
    
- Init.
    

