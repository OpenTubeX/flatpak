# Agent brief: GitHub Pages + static OSTree Flatpak repository

Copy this entire document into a new Cursor chat when you want an agent to implement the Flatpak **remote repository** (not just release bundles).

---

## Goal

Host an installable Flatpak **remote** at:

**https://flatpak.opentubex.org**

Users should be able to run:

```bash
flatpak remote-add --user --if-not-exists opentubex \
  https://flatpak.opentubex.org/opentubex.flatpakrepo \
  --no-gpg-verify

flatpak install --user opentubex org.opentubex.OpenTubeX

flatpak update --user org.opentubex.OpenTubeX
```

Keep the existing **GitHub Release `.flatpak` bundles** workflow unless explicitly asked to remove it. The remote is an additional distribution channel.

---

## Current state (already done)

Repository: **https://github.com/OpenTubeX/flatpak**

| Item | Value |
|------|-------|
| App ID | `org.opentubex.OpenTubeX` |
| Manifest | `org.opentubex.OpenTubeX.yml` |
| Runtime | `org.freedesktop.Platform` 25.08 + `org.electronjs.Electron2.BaseApp` 25.08 |
| Upstream app | https://github.com/OpenTubeX/OpenTubeX |
| Portable zip source | OpenTubeX GitHub releases (`opentubex-*-linux-x64-portable.zip`, `*-arm64-portable.zip`) |
| CI workflow | `.github/workflows/build.yml` |
| CI jobs today | `prepare` → `build` (x86_64 + aarch64 matrix) → `release` (upload `.flatpak` to GitHub Releases) |

Local build was validated with `flatpak-builder`. CI has been iterated several times; read `.github/workflows/build.yml` before changing it.

Related repos:

- **OpenTubeX/OpenTubeX** — main application
- **OpenTubeX/opentubex.github.io** — website (`opentubex.org`); do **not** use this for the Flatpak repo unless there is a strong reason. Prefer Pages on `OpenTubeX/flatpak` itself.

Flathub submission is **not** planned (AI-generated app policy). This is a self-hosted unofficial repo.

---

## Target architecture

```text
OpenTubeX release (portable zip)
        │
        ▼
GitHub Actions (OpenTubeX/flatpak)
  ├─ build x86_64 + aarch64 (existing)
  ├─ export both arches into one OSTree repo
  ├─ flatpak update-repo
  ├─ publish static site to gh-pages branch
  └─ (optional, keep) upload .flatpak bundles to GitHub Releases
        │
        ▼
GitHub Pages  →  https://flatpak.opentubex.org
  ├─ CNAME
  ├─ opentubex.flatpakrepo
  ├─ index.html (short install instructions)
  └─ repo/          ← OSTree static repository
      ├─ config
      ├─ refs/
      ├─ objects/
      └─ summaries/
```

DNS (Namecheap):

```text
flatpak.opentubex.org  CNAME  opentubex.github.io
```

Status: **configured** (CNAME on Namecheap). GitHub Pages custom domain + Enforce HTTPS still required after first `gh-pages` deploy (see below).

GitHub Pages on **OpenTubeX/flatpak** with custom domain `flatpak.opentubex.org`.

---

## Manual setup the repo owner must do (document in PR / final summary)

These steps require the GitHub org owner and Namecheap access. The agent should implement code/workflow changes; the owner does DNS + Pages settings if the agent cannot.

### 1. Namecheap DNS (`opentubex.org`)

1. Log in to Namecheap → Domain List → **opentubex.org** → **Advanced DNS**.
2. Add record:

   | Type | Host | Value | TTL |
   |------|------|-------|-----|
   | CNAME Record | `flatpak` | `opentubex.github.io.` | Automatic |

3. Remove conflicting records on `flatpak` if any exist.
4. Wait for propagation (often minutes, sometimes up to 24–48 h).

Verify:

```bash
dig flatpak.opentubex.org CNAME +short
# expected: opentubex.github.io.
```

### 2. GitHub Pages (OpenTubeX/flatpak)

After the workflow first deploys the `gh-pages` branch:

1. **Settings → Pages**
2. Source: deploy from **`gh-pages`** branch, root `/`
3. Custom domain: `flatpak.opentubex.org`
4. Wait for DNS check → enable **Enforce HTTPS**
5. Confirm `https://flatpak.opentubex.org/opentubex.flatpakrepo` is reachable

---

## Implementation tasks for the agent

### A. Add static site files (committed to `main`, copied into Pages output by CI)

Create something like `pages/` in this repo:

#### `pages/CNAME`

```text
flatpak.opentubex.org
```

#### `pages/opentubex.flatpakrepo`

```ini
[Flatpak Repo]
Version=1
Title=OpenTubeX
Homepage=https://opentubex.org/
Description=Unofficial OpenTubeX Flatpak builds
Url=https://flatpak.opentubex.org/repo
DefaultBranch=stable
```

No `GPG-Key` — this is an **unsigned** user repo. Install/update commands must use `--no-gpg-verify` on `remote-add` (document that in `index.html`).

#### `pages/index.html`

Minimal page with:

- Link to https://opentubex.org/
- Install commands (remote-add + install)
- Update command
- Note that this is an unofficial build, not Flathub
- Link to GitHub Releases for offline `.flatpak` bundles

### B. Extend CI to build and publish an OSTree repo

Add a **`publish-repo`** job (or extend existing jobs) after successful builds.

High-level algorithm:

```bash
# 1. Fetch previous OSTree repo from gh-pages (if branch exists), else start fresh
git fetch origin gh-pages:gh-pages || true
mkdir -p site/repo
if git show gh-pages:repo/config >/dev/null 2>&1; then
  git archive gh-pages repo | tar -x -C site
fi

# 2. For each architecture, export into the SAME repo directory
#    (reuse build dirs from flatpak-builder or rebuild with --repo=...)
flatpak build-export --arch=x86_64 site/repo <build-dir-x86_64> org.opentubex.OpenTubeX stable
flatpak build-export --arch=aarch64 site/repo <build-dir-aarch64> org.opentubex.OpenTubeX stable

# 3. Refresh repo metadata
flatpak update-repo site/repo

# 4. Assemble Pages site
cp pages/CNAME pages/opentubex.flatpakrepo pages/index.html site/

# 5. Deploy site/ to gh-pages branch
```

**Important details:**

- Both architectures must land in **one** `repo/` directory so a single remote works for x86_64 and aarch64.
- Reuse the existing `flatpak-github-actions/flatpak-builder@v6` container (`ghcr.io/flathub-infra/flatpak-github-actions:freedesktop-25.08`) for export commands.
- `flatpak-builder` may need `build-bundle: false` and/or `keep-build-dirs: true` — check action inputs. If build dirs are not kept, add explicit `flatpak-builder --repo=...` export steps per arch.
- On subsequent releases, **pull the existing `gh-pages` repo/** and run `flatpak build-export` on top so old versions remain available (unless you intentionally want a single-version repo).
- Add `.gitignore` entries for local `site/`, `repo/`, etc.

Suggested deploy action: **`peaceiris/actions-gh-pages`** or native **`actions/upload-pages-artifact` + `actions/deploy-pages`**.

If using `peaceiris/actions-gh-pages`:

```yaml
permissions:
  contents: write   # push gh-pages
  pages: write
  id-token: write

- uses: peaceiris/actions-gh-pages@v4
  with:
    github_token: ${{ secrets.GITHUB_TOKEN }}
    publish_dir: ./site
    cname: flatpak.opentubex.org
    keep_files: false   # only if full site/ is rebuilt each time
```

Prefer rebuilding the full `site/` directory each run (including merged `repo/`) so deploy is deterministic.

### C. Workflow permissions

Top-level or job-level permissions will likely need:

```yaml
permissions:
  contents: write   # push gh-pages + manifest commits
  actions: read     # download artifacts
  pages: write      # if using deploy-pages
  id-token: write   # if using deploy-pages OIDC
```

### D. Update user-facing install docs

After implementation, add install instructions to:

- `pages/index.html` (required)
- Optionally link from **OpenTubeX/OpenTubeX** README or **opentubex.org** (separate PR, ask owner)

Suggested install block:

```bash
# one-time
flatpak remote-add --user --if-not-exists opentubex \
  https://flatpak.opentubex.org/opentubex.flatpakrepo \
  --no-gpg-verify

flatpak install --user opentubex org.opentubex.OpenTubeX

# updates
flatpak update --user org.opentubex.OpenTubeX
```

### E. Optional: trigger from OpenTubeX releases

The flatpak workflow already supports:

```yaml
repository_dispatch:
  types: [opentubex-release]
```

In **OpenTubeX/OpenTubeX** `release.yml`, add a step after publishing:

```yaml
- uses: peter-evans/repository-dispatch@v3
  with:
    token: ${{ secrets.FLATPAK_REPO_TOKEN }}  # PAT with repo scope on OpenTubeX/flatpak
    repository: OpenTubeX/flatpak
    event-type: opentubex-release
    client-payload: '{"tag": "${{ github.ref_name }}"}'
```

Only do this if the owner wants fully automatic flatpak remote updates.

---

## Verification checklist (agent must run or document)

1. `curl -fsSL https://flatpak.opentubex.org/opentubex.flatpakrepo` returns the repo file.
2. `curl -fsSL https://flatpak.opentubex.org/repo/config` returns OSTree config (after deploy).
3. On x86_64 Linux with Flatpak installed:

   ```bash
   flatpak remote-add --user --if-not-exists opentubex-test \
     https://flatpak.opentubex.org/opentubex.flatpakrepo --no-gpg-verify
   flatpak install --user -y opentubex-test org.opentubex.OpenTubeX
   flatpak run org.opentubex.OpenTubeX
   flatpak remote-delete --user opentubex-test
   ```

4. Re-run workflow for the same tag → remote still works, `flatpak update` finds the build.
5. GitHub Release `.flatpak` bundles still publish (if kept).

---

## Constraints and gotchas

| Topic | Notes |
|-------|-------|
| **Unsigned repo** | No GPG key. Users need `--no-gpg-verify`. Cannot be mixed with Flathub’s signed remote without a separate remote name. |
| **GitHub Pages bandwidth** | Free tier ~100 GB/month — fine for a single app at moderate scale. |
| **Repo size** | OSTree `objects/` grows with each release. Monitor `gh-pages` size; prune old refs later if needed. |
| **HTTPS** | Flatpak requires HTTPS. Enable “Enforce HTTPS” in Pages settings after DNS validates. |
| **Custom domain** | Must be set in **OpenTubeX/flatpak** Pages settings, not only via CNAME file. |
| **Namecheap CNAME** | Point `flatpak` → `opentubex.github.io` (trailing dot optional in UI). |
| **Do not commit zips** | Portable archives are >100 MB. Never commit them (see existing `.gitignore`). |
| **Electron / Zypak** | Existing `run.sh` + manifest are correct; do not change unless build breaks. |

---

## Files in this repo the agent should read first

```text
org.opentubex.OpenTubeX.yml
org.opentubex.OpenTubeX.desktop
org.opentubex.OpenTubeX.metainfo.xml
run.sh
.github/workflows/build.yml
.gitignore
```

Use `gh` for GitHub operations:

```bash
gh repo view OpenTubeX/flatpak
gh workflow run build.yml --repo OpenTubeX/flatpak
gh run list --repo OpenTubeX/flatpak
```

---

## Suggested PR / commit scope

Keep changes focused:

1. `pages/` static site files (`CNAME`, `opentubex.flatpakrepo`, `index.html`)
2. `.github/workflows/build.yml` — add OSTree export + gh-pages deploy job
3. `.gitignore` — ignore `site/`, local `repo/`, etc.
4. This brief — update with any deviations or owner action items

Do **not** unrelated-refactor the manifest or rename the app ID.

---

## Success criteria

- [ ] https://flatpak.opentubex.org serves the Flatpak repo over HTTPS
- [ ] `flatpak install` from the remote works on x86_64 and aarch64
- [ ] `flatpak update` works after a new OpenTubeX release is published
- [ ] DNS on Namecheap documented and verified
- [ ] Existing GitHub Release bundle publishing still works (unless owner opts out)

---

## Owner context for the agent

- Domain registrar: **Namecheap** (`opentubex.org`)
- Desired subdomain: **flatpak.opentubex.org** (DNS CNAME configured on Namecheap)
- GitHub org: **OpenTubeX**
- Main app path on disk (for reference): `/home/nico/projects/OpenTubeX`
- Query GitHub with: `gh ... --repo OpenTubeX/OpenTubeX` or `OpenTubeX/flatpak`
