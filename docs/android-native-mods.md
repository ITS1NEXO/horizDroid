# Android native-mod investigation

## Purpose

Add a practical Android path for Horizon native mods (`.hnmod`) without turning HorizDroid into a native-mod-only project and without regressing existing `.hmod` content packages.

This document records the current architecture and the constraints that must be solved before claiming that Android can run an imported native mod.

## What the formats mean

- `.hmod` is a content package: data and assets are read by the game. It is not a native source bundle.
- `.hnmod` is a native source/mixin bundle. It contains a `horizon-native.json` registry manifest and mixin/source files; it is applied to a pinned Horizon source revision and compiled into a customised game.

The two formats have different validation, trust, compatibility, and execution requirements. They must not be renamed or treated as interchangeable.

## Current Android baseline

The Android crate depends on `horizon-mods` with the `index` feature, which provides registry/index metadata and package checks. The Android crate's `mods` feature enables the game's existing mod runtime and its bundled native-mod integration.

The Android game currently has a fixed list of bundled native modules in `crates/horizon-client-render/src/mod_list.rs` (`zoom`, `minimap`, `recipes`, and `smartf3`). These are compiled into the APK. This is not the same as compiling an arbitrary user-supplied `.hnmod` after installation.

The desktop launcher implementation lives in `launcher/src/native_mods.rs`. It uses `horizon-mixins` to modify a pinned Horizon source tree, then invokes Cargo to compile a customised game. That workflow assumes a desktop Rust toolchain, source checkout, build cache, and substantial storage/CPU time.

The Android SAF import pipeline in `crates/horizon-client/src/android/documents.rs` currently imports `.hmod`, resource-pack ZIPs, and shader packs. Its archive validator is in `crates/horizon-client/src/content_files.rs`. It does not currently install or execute arbitrary `.hnmod` bundles.

## Engineering constraints

1. **Do not execute imported native code merely because it was selected.** Native mods run with the game's process privileges; importing and reviewing a bundle must be separate from enabling it.
2. **Pin the source revision and hook API.** A build must validate the mod's `horizon_revision` / `hooks` requirements against the exact engine source and native hook API used.
3. **Keep builds reproducible.** Record the source revision, mixins revision, mod hashes, build profile, target ABI, and toolchain used for every generated game library.
4. **Keep generated binaries isolated.** Never overwrite the stock game library. A modded build must have its own identity/cache and a safe fallback to the stock game.
5. **Preserve `.hmod`.** Content mods continue through their existing validation and load path. Native package handling must use a distinct type, directory, and validation path.
6. **Treat Android resource limits as first-class.** A full Rust/Cranelift build on a phone may be impractical on low-memory devices. Any on-device compiler path needs measured RAM, disk, thermal, cancellation, and recovery behaviour.
7. **Do not promise arbitrary native mods until runtime validation exists.** A downloaded or stored `.hnmod` is not proof that it was built, linked, or loaded.

## Proposed implementation stages

### Stage 1 — package inspection and trust boundary

- Add a distinct native-mod package type and SAF import route for `.hnmod`; do not overload the existing `Kind::Mods` / `.hmod` path.
- Validate archive paths, symlinks, file counts, expanded size, required manifest files, and metadata before storing anything.
- Display package identity, author, requested engine revision/hook API, and a clear native-code warning.
- Store packages in `horizon-native-mods/`, separate from `horizon-mods/`.
- Keep imported packages inactive until a later build-and-review stage is available.

### Stage 2 — build strategy decision

Compare two viable approaches before implementation:

- **On-device compilation:** package or download a pinned Rust toolchain, NDK-compatible target support, Cargo dependencies, and the mixin tool. Benchmark feasibility on representative Android devices. This is likely expensive in storage, RAM, heat, and build time.
- **Remote reproducible build:** send only explicitly selected source bundles and pinned build metadata to a controlled build service; verify signed output and bind it to the exact mod hashes and engine revision. This requires a trustworthy service, user consent, secure transport, signing, and a clear privacy model.

Do not silently upload source bundles or compile untrusted native code in a privileged service.

### Stage 3 — runtime selection

- Define a versioned manifest for generated Android game libraries.
- Verify signatures and hashes before activation.
- Keep the stock library available for rollback.
- Load only a build matching the device ABI, engine revision, hook API, and installed package hashes.
- Add crash-safe fallback and tests for interrupted builds, invalid signatures, ABI mismatch, and stale packages.

### Stage 4 — TITANIUM integration

TITANIUM targets `.hnmod`. Once the general pipeline is implemented and tested, use TITANIUM as a real integration test. Keep the TITANIUM repository independent; do not bake its code into HorizDroid.

## Immediate next technical work

The first code change should be the separate `.hnmod` import/inspection path and its tests. It must not claim that the game can run the package yet. After that, choose and prototype the build strategy based on measured feasibility rather than assuming that a full compiler can fit comfortably on every Android device.
