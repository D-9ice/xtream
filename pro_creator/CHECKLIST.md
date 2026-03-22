# ProCreator Simplified Workflow Upgrade Checklist

This checklist tracks the remaining work required to finish the guided workflow upgrade defined in the technical document.

## Phase 1: Workflow Core Hardening

- [x] Finalize the workflow state machine.
- [x] Explicitly set and use `production_ready` before production starts.
- [x] Ensure legal transitions only:
  - `draft -> script_generating -> script_generated -> script_approved`
  - `script_approved -> characters_in_progress -> characters_approved`
  - `characters_approved -> production_ready -> production_queued -> production_running -> video_completed`
  - `production_running -> production_failed`
- [x] Prevent illegal transitions at the API/service layer, not just in the UI.
- [x] Add transition tests for all invalid state jumps.

## Phase 2: Production Queue And Retry Flow

- [x] Change production start from mostly inline execution to a real queued lifecycle.
- [x] Create durable production job records or queue payloads for guided workflow production.
- [x] Update `start-production` to set `production_queued` first.
- [x] Move execution into worker/background processing where appropriate.
- [x] Update project state to `production_running` when the job begins.
- [x] Update project state to `video_completed` on success.
- [x] Update project state to `production_failed` on failure.
- [x] Add retry support from Stage 4 without forcing earlier steps to repeat unless upstream data changed.
- [x] Add `production-status` polling/refresh behavior tests.

## Phase 3: Approval Reset Rules

- [x] When regenerating a script after approval, clear script approval and require re-approval.
- [x] When editing script after approval, clear downstream approvals and show explicit warning messaging.
- [x] When changing selected characters after character approval, clear character approval and require re-approval.
- [x] When changing approved script after character approval, clear character approval and production readiness.
- [x] Preserve existing approved package snapshots even if later character records change.
- [x] Add tests for each approval reset case.

## Phase 4: Character DNA Completion

- [x] Expand Character DNA support to fully match the document.
- [x] Support richer reusable character library behavior.
- [x] Support reference image bundle handling, not only single reference/canonical URLs.
- [x] Preserve and enforce:
  - identity hash
  - consistency seed
  - lock identity
  - canonical prompt base
  - reference imagery
- [x] Ensure approved character package snapshots are frozen for production.
- [x] Add tests for DNA snapshot generation and reuse integrity.

## Phase 5: Resolver And Pipeline Injection

- [x] Strengthen `resolveApprovedProductionPackage(projectId)` behavior.
- [x] Ensure it always returns:
  - approved script snapshot
  - approved character package snapshot
  - resolved Character DNA
  - prompt payloads
  - references
  - seeds
- [x] Inject resolved DNA data into downstream image/video generation consistently.
- [x] Verify character identity is preserved scene to scene as far as current generation stack allows.
- [x] Add resolver-specific unit tests.

## Phase 6: Create Screen UX Completion

- [x] Polish the guided Create screen for production use.
- [x] Improve per-step loading, success, warning, and failure states.
- [x] Add explicit “what happens next” guidance inside the Create screen.
- [x] Add clearer “final approval” UX before video production.
- [x] Add better progress messaging while production is queued/running.
- [x] Improve empty-state behavior for first-time users.
- [x] Improve validation messaging for incomplete character inputs.
- [x] Add responsive mobile navigation and tighten Create-screen layouts for smaller screens.
- [x] Run responsive/mobile QA and fix layout issues.

## Phase 7: Projects Screen Completion

- [x] Add archive project behavior.
- [x] Add duplicate project behavior.
- [x] Improve project card workflow-stage presentation.
- [x] Ensure opening a project always lands on the correct active Create stage.

## Phase 8: Library Completion

- [x] Add character search.
- [x] Add character role filters.
- [x] Improve approved script reuse flows.
- [x] Improve completed video actions:
  - play
  - download
  - reuse/duplicate where appropriate
- [x] Keep the library simple and non-engine-oriented.

## Phase 9: Legacy UI Demotion

- [x] Move legacy engine-centric surfaces out of the normal user path.
- [x] Hide or demote:
  - Engines
  - Automation
  - Orchestration
  - Logs
- [x] Keep internal routes only for admin/developer use where necessary.
- [x] Ensure normal users only see the simplified guided workflow shell.

## Phase 10: API Shape Cleanup

- [x] Decide whether to keep `/workflow/...` routes as the public workflow surface or alias them to the final `/api/projects/:id/...` style from the document.
- [x] Standardize route naming and payloads.
- [x] Remove any UI dependence on legacy engine APIs for the main workflow path.

## Phase 11: Data And Migration Verification

- [x] Apply and verify the workflow migration in the real runtime environment.
- [x] Validate old project rows upgrade safely.
- [x] Validate fallback schema sync does not break local/dev startup.
- [x] Verify the new tables/columns are populated correctly through the guided flow.

## Phase 12: Testing Completion

- [x] Run backend tests in a proper Python environment with dependencies installed.
- [x] Run frontend tests in supported Node 20.
- [x] Add missing backend tests for:
  - state transitions
  - approval resets
  - production retry/failure behavior
  - resolver payload integrity
  - character DNA snapshots
- [x] Add missing frontend tests for:
  - full guided flow rendering
  - state-accurate step enable/disable behavior
  - script review visibility
  - character approval unlocking production
  - production failure/retry messaging
- [x] Add integration tests for:
  - create project -> generate script -> approve script
  - approve script -> add/select characters -> approve characters
  - approve characters -> start production

## Phase 13: Full Integration Hardening

- [x] Start the app in the correct runtime environment.
- [x] Run the guided workflow end to end manually.
- [x] Fix live integration bugs revealed by real execution.
- [x] Confirm credits behavior matches the simplified UX checkpoints.
- [x] Confirm final video outputs land in both project view and library.
- [x] Confirm no unfinished engine-centric behavior leaks into the main path.

## Immediate Next Order

- [x] 1. Finish state machine and `production_ready`.
- [x] 2. Convert production to a real queued lifecycle with retry.
- [x] 3. Implement approval reset rules completely.
- [x] 4. Strengthen resolver + Character DNA injection.
- [x] 5. Run live integration verification and fix discovered bugs.
- [x] 6. Finish UX/library/projects polish.
