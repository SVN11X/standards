#!/usr/bin/env python3
"""Export linear commits as a patch for git am, verify it on a clean copy, and build a full ZIP. No dependencies."""
import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def git(repo, *arguments):
    result = subprocess.run(["git", "-C", str(repo), *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git {arguments[0]} failed: {detail}")
    return result.stdout


def text_git(repo, *arguments):
    return git(repo, *arguments).decode("utf-8").strip()


def manifest(repo, commit):
    entries = []
    for entry in git(repo, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.split(b" ")
        if kind != b"blob":
            raise ValueError("Submodules need an explicit, separate export.")
        entries.append((raw_path.decode("utf-8"), int(mode, 8), oid.decode("ascii")))
    return entries


def write_archive(repo, target, name, entries):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, mode, oid in entries:
            info = zipfile.ZipInfo(f"{name}/{path}")
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = mode << 16
            archive.writestr(info, git(repo, "cat-file", "blob", oid))
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError("The ZIP failed its integrity check.")
        expected = {f"{name}/{path}": (mode, oid) for path, mode, oid in entries}
        if set(archive.namelist()) != set(expected):
            raise ValueError("The ZIP does not contain exactly the files of the commit.")
        for filename, (mode, oid) in expected.items():
            content = archive.read(filename)
            blob = b"blob " + str(len(content)).encode("ascii") + b"\0" + content
            algorithm = hashlib.sha256 if len(oid) == 64 else hashlib.sha1
            if algorithm(blob).hexdigest() != oid:
                raise ValueError(f"A file does not match git: {filename}")
            stored_mode = archive.getinfo(filename).external_attr >> 16
            if stat.S_IFMT(stored_mode) != stat.S_IFMT(mode) or stored_mode & 0o777 != mode & 0o777:
                raise ValueError(f"Permissions do not match git: {filename}")


def deliver(args):
    repo = Path(text_git(args.repo.expanduser().resolve(), "rev-parse", "--show-toplevel")).resolve()
    base = text_git(repo, "rev-parse", "--verify", args.base + "^{commit}")
    commit = text_git(repo, "rev-parse", "--verify", args.commit + "^{commit}")
    if base == commit:
        raise ValueError("There are no changes between the base and the final commit.")
    git(repo, "merge-base", "--is-ancestor", base, commit)
    if git(repo, "rev-list", "--merges", f"{base}..{commit}").strip():
        raise ValueError("The series contains merges. Prepare a linear branch with the authorized changes.")
    if git(repo, "status", "--porcelain", "--untracked-files=normal").strip():
        raise ValueError("The repository has uncommitted changes. Settle the scope before exporting.")
    output = args.output.expanduser().resolve()
    if output == repo or repo in output.parents:
        raise ValueError("Choose a delivery folder outside the repository.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.name):
        raise ValueError("Use a name of 1 to 80 letters, digits, hyphens or underscores.")
    patch_name = args.name + "_changes_git_am.patch"
    zip_name = args.name + "_full_repository.zip"
    destinations = [output / patch_name, output / zip_name]
    if any(path.exists() for path in destinations):
        raise ValueError("A delivery file already exists. Choose another folder or name.")
    entries = manifest(repo, commit)
    with tempfile.TemporaryDirectory(prefix="verify-delivery-") as temporary:
        directory = Path(temporary)
        patch = directory / patch_name
        patch.write_bytes(git(repo, "format-patch", "--stdout", "--full-index", "--binary", "--no-signature",
                              "--base=" + base, f"{base}..{commit}"))
        if not patch.read_bytes().startswith(b"From "):
            raise ValueError("git did not produce a mail-format patch.")
        clone = directory / "verification"
        git(repo, "clone", "--quiet", "--no-checkout", "--no-hardlinks", str(repo), str(clone))
        git(clone, "checkout", "--quiet", "--detach", base)
        hooks = directory / "empty-hooks"
        hooks.mkdir()
        git(clone, "-c", "core.hooksPath=" + str(hooks), "-c", "user.name=Local verification",
            "-c", "user.email=verification@example.invalid", "am", str(patch))
        tree = text_git(repo, "rev-parse", commit + "^{tree}")
        if text_git(clone, "rev-parse", "HEAD^{tree}") != tree:
            raise ValueError("The applied patch does not reproduce the final tree.")
        archive = directory / zip_name
        write_archive(repo, archive, args.name, entries)
        output.mkdir(parents=True, exist_ok=True)
        created = []
        try:
            for source, destination in zip((patch, archive), destinations):
                with destination.open("xb") as stream:
                    created.append(destination)
                    with source.open("rb") as content:
                        shutil.copyfileobj(content, stream)
        except OSError:
            for path in created:
                path.unlink(missing_ok=True)
            raise
    return {"base": base, "commit": commit, "tree": tree, "git_am_verified": True, "zip_verified": True,
            "versioned_files": len(entries), "patch": str(destinations[0]), "zip": str(destinations[1])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path, help="Local git repository with a clean working tree.")
    parser.add_argument("--base", required=True, help="Real base commit of the changes.")
    parser.add_argument("--commit", default="HEAD", help="Final commit. Default: HEAD.")
    parser.add_argument("--output", required=True, type=Path, help="Delivery folder outside the repository.")
    parser.add_argument("--name", required=True, help="Prefix for the files and the folder inside the ZIP.")
    args = parser.parse_args()
    try:
        result = deliver(args)
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f"Delivery failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
