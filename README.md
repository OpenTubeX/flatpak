# OpenTubeX Flatpak

This repository builds the official [OpenTubeX](https://github.com/OpenTubeX/OpenTubeX)
Flatpak for `x86_64` and `aarch64` and publishes it to the signed OSTree remote at
[flatpak.opentubex.org](https://flatpak.opentubex.org/), which also has the
installation instructions.

## How publishing works

Once an OpenTubeX release has uploaded its portable Linux archives, the OpenTubeX
repository sends a `repository_dispatch` event with the release tag in
`client_payload.tag`. Stable releases send `opentubex-release` and nightlies send
`opentubex-nightly`. You can also run the **Build and Release Flatpak** workflow
manually with a tag, or without one to use the latest stable release.

The workflow then:

1. points the manifest at that release's portable archives and updates the
   AppStream release entry. For stable releases it adds the release notes and
   commits the manifest to `main`;
2. builds both architectures;
3. restores the live OSTree repository from `flatpak.opentubex.org`, exports the
   builds to the `stable` and `nightly` branches (stable releases update both,
   nightlies only `nightly`), signs the commits and summary, and deploys the
   repository with the landing page to GitHub Pages;
4. attaches `.flatpak` bundles to a GitHub release. Nightlies are prereleases,
   and only the five newest are kept.

Each branch keeps its current build and two older ones. The workflow prunes
older commits on every publish to stay within the GitHub Pages size limit.

## Maintainer setup

- The `FLATPAK_GPG_PRIVATE_KEY` secret holds the armored private key for
  `flatpak@opentubex.org` (`FCB58AF1F41F6E3157A6496438960E78A4EE5B9C`). Its public
  key is the `GPGKey` in `pages/opentubex.flatpakrepo`, so a new key also needs
  an update to that file.
- GitHub Pages must use **GitHub Actions** as its source, with the custom
  domain `flatpak.opentubex.org`.
- The OpenTubeX repository needs a `PUSH_TOKEN` secret with write access to this
  repository to send the dispatch events.

The **Validate Flatpak metadata** workflow checks the manifest, desktop entry,
AppStream metadata and workflow tests on every push and pull request.
