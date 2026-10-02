import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/build.yml"
TAG = "v0.35.2-nightly-1757"
ASSETS = ["org.opentubex.OpenTubeX-v0.35.2-nightly-1757-x86_64.flatpak","org.opentubex.OpenTubeX-v0.35.2-nightly-1757-aarch64.flatpak"]

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


def publish_command():
    lines = WORKFLOW.read_text().splitlines()
    start = lines.index("      - name: Create or update GitHub release")
    start = lines.index("        run: |", start) + 1
    end = start
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith("          ")):
        end += 1
    return textwrap.dedent("\n".join(lines[start:end]))


class ReleaseWorkflowTest(unittest.TestCase):
    def run_publish(self, state, nightly=True):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            gh = work / "gh"
            gh.write_text(FAKE_GH)
            gh.chmod(0o755)
            for asset in ASSETS:
                (work / asset).write_bytes(b"rebuilt package with different bytes")
            calls = work / "calls.jsonl"
            env = {
                **os.environ,
                "PATH": f"{work}:{os.environ['PATH']}",
                "GH_STATE": json.dumps(state),
                "GH_CALLS": str(calls),
                "GH_REPO": "OpenTubeX/flatpak",
                "TAG": TAG,
                "VERSION": "0.35.2-nightly-1757",
                "CHANNEL": "nightly" if nightly else "stable",
                "PRERELEASE": "true" if nightly else "false",
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

    def test_new_nightly_uploads_all_packages_during_creation(self):
        result, mutations = self.run_publish({"error": 404})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0][:2], ["release", "create"])
        self.assertIn("--prerelease", mutations[0])
        for asset in ASSETS:
            self.assertIn(asset, mutations[0])

    def test_new_stable_release_is_not_a_prerelease(self):
        result, mutations = self.run_publish({"error": 404}, nightly=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(mutations[0][:2], ["release", "create"])
        self.assertNotIn("--prerelease", mutations[0])

    def test_lookup_error_does_not_create_release(self):
        result, mutations = self.run_publish({"error": 403})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(mutations, [])
        self.assertIn("HTTP 403", result.stderr)


if __name__ == "__main__":
    unittest.main()
