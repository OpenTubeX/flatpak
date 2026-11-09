import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ElementTree

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/build.yml"
TAG = "v0.35.2-beta"
ASSETS = ["org.opentubex.OpenTubeX-v0.35.2-beta-x86_64.flatpak", "org.opentubex.OpenTubeX-v0.35.2-beta-aarch64.flatpak"]
NIGHTLY_TAG = "v0.35.2-nightly-1757"

FAKE_GH = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with Path(os.environ["GH_CALLS"]).open("a") as calls:
    calls.write(json.dumps(args) + "\\n")
state = json.loads(os.environ["GH_STATE"])
if args[0] == "api" or args[:2] == ["release", "view"]:
    error = state.get("error")
    if error:
        print(f"gh: request failed (HTTP {error})", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(state))
elif args[:2] == ["release", "upload"] and state.get("immutable"):
    print("gh: Cannot upload assets to an immutable release (HTTP 422)", file=sys.stderr)
    sys.exit(1)
elif args[:2] not in (["release", "upload"], ["release", "create"], ["release", "edit"]):
    print(f"Unexpected gh call: {args}", file=sys.stderr)
    sys.exit(1)
"""

PRUNE_GH = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with Path(os.environ["GH_CALLS"]).open("a") as calls:
    calls.write(json.dumps(args) + "\\n")
if args[:2] == ["release", "list"]:
    print(os.environ["RELEASES"])
elif args[:2] != ["release", "delete"]:
    sys.exit(f"Unexpected gh call: {args}")
"""


def step_command(name):
    lines = WORKFLOW.read_text().splitlines()
    start = lines.index(f"      - name: {name}")
    start = lines.index("        run: |", start) + 1
    end = start
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith("          ")):
        end += 1
    return textwrap.dedent("\n".join(lines[start:end]))


def publish_command():
    return step_command("Create or update GitHub release")


class ReleaseWorkflowTest(unittest.TestCase):
    def run_publish(self, state, channel="stable"):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            gh = work / "gh"
            gh.write_text(FAKE_GH)
            gh.chmod(0o755)
            for asset in ASSETS:
                (work / asset).write_bytes(b"rebuilt package with different bytes")
                (work / asset.replace(TAG, NIGHTLY_TAG)).write_bytes(b"nightly package")
            calls = work / "calls.jsonl"
            env = {
                **os.environ,
                "PATH": f"{work}:{os.environ['PATH']}",
                "GH_STATE": json.dumps(state),
                "GH_CALLS": str(calls),
                "GH_REPO": "OpenTubeX/flatpak",
                "TAG": TAG if channel == "stable" else NIGHTLY_TAG,
                "VERSION": "0.35.2" if channel == "stable" else "0.35.2-nightly-1757",
                "CHANNEL": channel,
            }
            result = subprocess.run(
                ["bash", "-c", publish_command()], cwd=work, env=env,
                capture_output=True, text=True,
            )
            commands = [json.loads(line) for line in calls.read_text().splitlines()]
            mutations = [args for args in commands if args[:2] in (
                ["release", "upload"], ["release", "create"], ["release", "edit"],
            )]
            return result, mutations

    def release(self, immutable=False, draft=False, assets=None):
        return {
            "immutable": immutable,
            "draft": draft,
            "assets": [
                {"name": name, "state": "uploaded", "size": 123}
                for name in (ASSETS if assets is None else assets)
            ],
        }

    def test_immutable_rerun_preserves_published_packages(self):
        result, mutations = self.run_publish(self.release(immutable=True))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(mutations, [])

    def test_incomplete_immutable_release_requires_new_tag(self):
        result, mutations = self.run_publish(self.release(immutable=True, assets=ASSETS[:1]))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(mutations, [])
        self.assertIn(ASSETS[1], result.stderr)

    def test_unfinished_immutable_asset_is_not_reused(self):
        state = self.release(immutable=True)
        state["assets"][0]["state"] = "starter"
        result, mutations = self.run_publish(state)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(mutations, [])

    def test_mutable_release_can_still_be_updated(self):
        result, mutations = self.run_publish(self.release())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0][:2], ["release", "upload"])
        self.assertIn("--clobber", mutations[0])
        for asset in ASSETS:
            self.assertIn(asset, mutations[0])

    def test_existing_draft_is_published_after_upload(self):
        result, mutations = self.run_publish(self.release(draft=True, assets=[]))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([args[:2] for args in mutations], [
            ["release", "upload"], ["release", "edit"],
        ])
        self.assertIn("--draft=false", mutations[1])

    def test_new_release_uploads_all_packages_during_creation(self):
        result, mutations = self.run_publish({"error": 404})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0][:2], ["release", "create"])
        self.assertNotIn("--prerelease", mutations[0])
        for asset in ASSETS:
            self.assertIn(asset, mutations[0])

    def test_new_nightly_is_a_prerelease_with_a_warning(self):
        result, mutations = self.run_publish({"error": 404}, channel="nightly")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0][:2], ["release", "create"])
        self.assertIn("--prerelease", mutations[0])
        self.assertIn("nightly build is intended for testing", mutations[0][mutations[0].index("--notes") + 1])
        for asset in ASSETS:
            self.assertIn(asset.replace(TAG, NIGHTLY_TAG), mutations[0])

    def test_prune_keeps_the_newest_nightlies_and_all_stable_releases(self):
        releases = [{"tagName": "v0.35.2-beta", "isPrerelease": False, "createdAt": "2026-01-01T00:00:00Z"}]
        releases += [
            {"tagName": f"v0.35.2-nightly-{n}", "isPrerelease": True, "createdAt": f"2026-01-{n:02d}T02:30:00Z"}
            for n in range(1, 9)
        ]
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            calls = work / "calls.jsonl"
            gh = work / "gh"
            gh.write_text(PRUNE_GH)
            gh.chmod(0o755)
            env = {**os.environ, "PATH": f"{work}:{os.environ['PATH']}", "GH_CALLS": str(calls),
                   "RELEASES": json.dumps(releases), "GH_REPO": "OpenTubeX/flatpak", "KEEP": "5"}
            result = subprocess.run(["bash", "-c", step_command("Prune old nightly releases")],
                                    cwd=work, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            deleted = [args[2] for args in map(json.loads, calls.read_text().splitlines())
                       if args[:2] == ["release", "delete"]]
        self.assertEqual(deleted, ["v0.35.2-nightly-3", "v0.35.2-nightly-2", "v0.35.2-nightly-1"])

    def test_lookup_error_does_not_create_release(self):
        result, mutations = self.run_publish({"error": 403})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(mutations, [])
        self.assertIn("HTTP 403", result.stderr)



def new_release_metainfo():
    """The metainfo as "Update AppStream release entry" leaves it for v0.38.0-beta."""
    release = """  <releases>
    <release version="0.38.0-beta" date="2026-11-10">
      <url type="details">https://github.com/OpenTubeX/OpenTubeX/releases/tag/v0.38.0-beta</url>
    </release>
  </releases>"""
    text = (ROOT / "org.opentubex.OpenTubeX.metainfo.xml").read_text()
    return re.sub(r"  <releases>.*</releases>", release, text, count=1, flags=re.S)


class ReleaseNotesTest(unittest.TestCase):
    def add_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            metainfo = work / "org.opentubex.OpenTubeX.metainfo.xml"
            metainfo.write_text(new_release_metainfo())
            for name, script in {
                "gh": '#!/bin/sh\ntest "$*" = "api repos/OpenTubeX/OpenTubeX/releases/tags/v0.38.0-beta --jq .body" || exit 1\necho "## Highlights"\n',
                "node": '#!/bin/sh\ntest "$2" = appstream && grep -q Highlights "$3" || exit 1\nprintf "<p>Highlights</p>\\n<ul>\\n  <li>Added &amp; groups</li>\\n</ul>\\n"\n',
            }.items():
                (work / name).write_text(script)
                (work / name).chmod(0o755)
            env = {**os.environ, "PATH": f"{work}:{os.environ['PATH']}", "RUNNER_TEMP": str(work), "TAG": "v0.38.0-beta"}
            result = subprocess.run(
                ["bash", "-c", step_command("Add stable release notes to AppStream")], cwd=work, env=env,
                capture_output=True, text=True,
            )
            return result, metainfo.read_text()

    def test_stable_release_notes_become_the_release_description(self):
        result, metainfo = self.add_notes()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("""      <url type="details">""", metainfo)
        self.assertIn("""      <description>
        <p>Highlights</p>
        <ul>
          <li>Added &amp; groups</li>
        </ul>
      </description>
    </release>""", metainfo)
        release = ElementTree.fromstring(metainfo).find("releases/release")
        self.assertEqual(release.get("version"), "0.38.0-beta")
        self.assertEqual(len(release.findall("description")), 1)
        self.assertEqual(release.findtext("description/ul/li"), "Added & groups")


if __name__ == "__main__":
    unittest.main()
