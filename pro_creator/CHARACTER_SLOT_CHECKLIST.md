# Character Slot Pricing Checklist

## Phase 1. Policy and Settings
- [x] Add a dedicated character-slot feature checklist to the repo
- [x] Store tier credits, tier prices, base character slots, and add-on pricing in runtime-editable settings
- [x] Add subscription storage for purchased extra character slots
- [x] Add migration and fallback schema sync for the new fields

## Phase 2. Backend Quota Logic
- [x] Build a character-slot policy resolver from admin-managed settings
- [x] Count tenant character library usage against the active subscription allowance
- [x] Enforce the character-library limit on manual create
- [x] Enforce the character-library limit on AI generate
- [x] Enforce the character-library limit on uploaded characters
- [x] Keep approved project snapshots valid after a user hits the slot limit

## Phase 3. Billing and Admin Controls
- [x] Replace hardcoded tier plan values with settings-backed plan definitions
- [x] Expose admin pricing endpoints for plan credits, plan prices, plan slot counts, and add-on pricing
- [x] Add a credit-backed add-on purchase endpoint for `+N` character slots
- [x] Return slot usage and remaining capacity in the existing credit balance response

## Phase 4. Admin and Workflow UI
- [x] Add a pricing editor to the admin dashboard
- [x] Show character slot usage in the guided workflow UI
- [x] Disable character creation controls when the slot library is full
- [x] Add a guided CTA to buy more character slots from credits
- [x] Keep the top-right credit summary aligned with slot purchases and remaining balance

## Phase 5. Tests and Verification
- [x] Add backend tests for plan settings and slot resolution
- [x] Add backend tests for create, generate, and upload blocking at the slot limit
- [x] Add backend tests for credit-backed slot-pack purchases
- [x] Add backend tests for admin pricing updates
- [x] Add frontend tests for slot display and full-library lock state
- [x] Run focused backend and frontend verification for the new slot workflow
