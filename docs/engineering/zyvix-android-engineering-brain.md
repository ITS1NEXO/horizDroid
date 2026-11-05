# ZYVIX Android Engineering Brain

This is the project-level engineering playbook for making changes to HorizDroid safely. Reuse it for Android features, UI revisions, native build changes and APK releases.

## Non-negotiable workflow
1. Inspect the repository, active branch, recent commits and implementation before editing.
2. Trace the real call path from Android UI to state, worker, storage, native crate and build workflow. Do not infer architecture from filenames alone.
3. Preserve upstream Horizon behaviour unless a change is explicitly requested. Keep Android lifecycle, touch input, renderer selection, Vulkan, OpenGL ES and existing `.hmod` behaviour intact.
4. Make the smallest coherent source change. Avoid broad rewrites and generated-file churn.
5. Add or update tests for parsers, validation, state transitions and path handling. Prefer host-runnable tests for logic that does not require Android.
6. Run formatting, targeted tests, Android ARM64 compilation and APK packaging when the toolchain is available. Report every check separately; never call an unrun check passed.
7. Build on a feature branch. Inspect the diff, then open a pull request; do not silently rewrite the `android` branch.
8. Never expose signing keys, tokens or repository secrets to untrusted pull requests. Never use user secrets in logs or generated artifacts.
9. A feature is complete only after implementation, tests/build and required physical-device verification.

## HorizDroid architecture map
- Android native entry: `crates/horizon-client/src/android_main.rs`.
- Android launcher UI and lifecycle: `crates/horizon-client/src/android/launcher.rs` and `launcher_pages.rs`.
- Android launcher state/catalog: `crates/horizon-client/src/android/catalog.rs`.
- Android document picker/import pipeline: `crates/horizon-client/src/android/documents.rs`, `document_bridge.rs`, `document_store.rs`.
- Shared project browser: `launcher/src/browser.rs`, included by the Android entry point.
- Native-mod desktop implementation: `launcher/src/native_mods.rs`. It is not currently included by Android.
- Native bundle validation: `horizon_mods::index::native::Bundle` (the Android crate enables the `horizon-mods/index` feature).
- Android Rust crate: `crates/horizon-android/Cargo.toml`.
- Workspace and shared dependency versions: root `Cargo.toml`.

## Native mod format: do not confuse the packages
- `.hmod` is a sandboxed content/code package handled by the existing Android import/install path.
- `.hnmod` is a source bundle for `horizon-mixins`. It must be applied to a matching Horizon source revision and compiled into a new client.
- An installed APK cannot safely or correctly treat an arbitrary `.hnmod` as a precompiled shared library. Do not use `dlopen` or invent a runtime loader for it.
- Android support should begin with a controlled build-time pipeline: explicit trusted bundle input, strict archive/manifest validation, immutable Horizon and horizon-mixins pins, isolated workspace, ARM64 cross-compilation, APK audit, SHA-256 and provenance artifact.
- Never pass signing secrets to untrusted PR code. Experimental native builds should be unsigned or use a separately protected release workflow.
- Preserve Vulkan and OpenGL ES paths and the current `.hmod` runtime.

## Current implementation snapshot
- Android recognises Horizon registry entries whose loader is `hnmod`.
- The Android Mods UI now describes these as native bundles requiring a custom APK build, and the selection message explains that the build pipeline is not yet available in the installed app.
- This branch does **not** implement the Android `.hnmod` build pipeline, a native-mod install workflow, or runtime loading. The UI wording is deliberately explicit rather than claiming support.
- The existing `.hmod` install/import flow is not changed by this update.

## Definition of done for Android native mods
- [ ] Explicit trusted bundle selection; no arbitrary URL execution.
- [ ] Validate archive paths, entry count, expanded size, manifest identity, source layout and checksums.
- [ ] Enforce immutable Horizon and horizon-mixins revisions and compatibility metadata.
- [ ] Apply the bundle in a disposable CI workspace.
- [ ] Build the ARM64 Android native library and APK using the repository's verified SDK/NDK toolchain.
- [ ] Audit APK contents and publish SHA-256 plus source/mod/toolchain provenance.
- [ ] Keep signing credentials away from untrusted contributions.
- [ ] Verify Vulkan, OpenGL ES and existing `.hmod` behaviour.
- [ ] Test a known harmless native mod on physical Android hardware before marking support available.

## Required report format
- Files changed and why.
- Tests actually run and their exact result.
- Build status and artifact link, if one was produced.
- Known limitations and device verification still outstanding.

Never report implemented, working, APK ready or supported based only on a plan, a green documentation check or an unverified CI configuration.