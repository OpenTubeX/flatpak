from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def update_command(repo):
    lines = (ROOT / ".github/workflows/build.yml").read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if "flatpak build-update-repo " in line)
    command = lines[start].strip()
    while command.endswith("\\"):
        start += 1
        command = command[:-1] + lines[start].strip()
    # Synthetic commits are unsigned; exercise the production update/prune options.
    return [
        str(repo) if arg == "site/repo" else arg
        for arg in shlex.split(command)
        if not arg.startswith("--gpg-sign=")
    ]


class RepositoryRetentionTest(unittest.TestCase):
    def run_command(self, *args):
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_prunes_history_and_preserves_current_builds_and_rollbacks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            source = root / "source"
            (source / "files").mkdir(parents=True)
            self.run_command("ostree", f"--repo={repo}", "init", "--mode=archive-z2")
            (source / "files/payload").write_text("Unreferenced build")
            orphan = self.run_command(
                "ostree", f"--repo={repo}", "commit", "--branch=deleted-build",
                f"--tree=dir={source}", "--subject=Unreferenced build",
            )
            self.run_command("ostree", f"--repo={repo}", "refs", "--delete", "deleted-build")
            history = {}
            for arch in ("x86_64", "aarch64"):
                (source / "metadata").write_text(
                    "[Application]\nname=org.opentubex.OpenTubeX\n"
                    f"runtime=org.freedesktop.Platform/{arch}/25.08\n"
                    f"sdk=org.freedesktop.Sdk/{arch}/25.08\n"
                )
                for channel in ("stable", "nightly"):
                    ref = f"app/org.opentubex.OpenTubeX/{arch}/{channel}"
                    commits = []
                    for revision in range(5):
                        (source / "files/payload").write_text(f"{ref}: {revision}")
                        commits.append(self.run_command(
                            "ostree", f"--repo={repo}", "commit", f"--branch={ref}",
                            f"--tree=dir={source}", f"--subject=Build {revision}",
                        ))
                    history[ref] = commits

            self.run_command(*update_command(repo))

            for ref, commits in history.items():
                with self.subTest(ref=ref):
                    self.assertEqual(self.run_command(
                        "ostree", f"--repo={repo}", "rev-parse", ref,
                    ), commits[-1])
                    for revision, commit in enumerate(commits[-3:], start=2):
                        self.run_command("ostree", f"--repo={repo}", "show", commit)
                        self.assertEqual(self.run_command(
                            "ostree", f"--repo={repo}", "cat", commit, "/files/payload",
                        ), f"{ref}: {revision}")
                    for commit in commits[:-3]:
                        result = subprocess.run(
                            ["ostree", f"--repo={repo}", "show", commit],
                            capture_output=True, text=True,
                        )
                        self.assertNotEqual(result.returncode, 0, "Old history was retained")
            result = subprocess.run(
                ["ostree", f"--repo={repo}", "show", orphan], capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0, "Unreferenced history was retained")
            self.run_command("ostree", f"--repo={repo}", "fsck")


if __name__ == "__main__":
    unittest.main()
