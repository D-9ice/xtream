# Android Companion

**Status: development-only scaffold — not a shipped production feature.**

This directory contains the Kotlin + Jetpack Compose foundation for a future Pro Creator Pro Android companion. The current production product is the approved web application; this scaffold must not be represented as a completed mobile client.

## Local development

Open `android_companion/` in Android Studio, let Gradle sync, and run the `app` configuration on a device or emulator.

## Required work before any Android release

- Connect authenticated Pro Creator Pro API sessions.
- Load project/library data from the production backend.
- Display production/job status.
- Provide secure playback/download access.
- Add error/session-expiry handling.
- Add Android integration tests and release signing.
- Complete a production security review.

Until those gates are complete, Android remains development-only.
