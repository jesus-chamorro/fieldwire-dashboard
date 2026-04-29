"""Main orchestrator — runs the full daily pipeline."""

import os
import sys
from datetime import datetime, timezone, timedelta

EST = timezone(timedelta(hours=-5))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DOCS_DIR = os.path.join(BASE_DIR, "docs")

sys.path.insert(0, os.path.dirname(__file__))

from fetch_email import fetch_emails
from process_csv import process_all, reprocess_existing
from generate_site import generate_site
from check_inactivity import check_inactivity


def commit_and_push():
    """Commit updated files using PyGithub."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo_name = os.environ.get("GITHUB_REPOSITORY", "")

    if not token or not repo_name:
        print("WARNING: GITHUB_TOKEN or GITHUB_REPOSITORY not set. Skipping commit.")
        return

    try:
        from github import Github, InputGitTreeElement

        g = Github(token)
        repo = g.get_repo(repo_name)
        ref = repo.get_git_ref("heads/main")
        latest_sha = ref.object.sha
        base_tree = repo.get_git_tree(latest_sha)

        tree_elements = []

        for root_dir, prefix in [(DOCS_DIR, "docs"), (DATA_DIR, "data")]:
            if not os.path.isdir(root_dir):
                continue
            for dirpath, dirnames, filenames in os.walk(root_dir):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    rel_path = os.path.relpath(filepath, BASE_DIR).replace("\\", "/")
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                        tree_elements.append(InputGitTreeElement(
                            path=rel_path,
                            mode="100644",
                            type="blob",
                            content=content,
                        ))
                    except (UnicodeDecodeError, PermissionError):
                        with open(filepath, "rb") as f:
                            content_bytes = f.read()
                        import base64
                        blob = repo.create_git_blob(base64.b64encode(content_bytes).decode(), "base64")
                        tree_elements.append(InputGitTreeElement(
                            path=rel_path,
                            mode="100644",
                            type="blob",
                            sha=blob.sha,
                        ))

        if not tree_elements:
            print("No files to commit.")
            return

        new_tree = repo.create_git_tree(tree_elements, base_tree)
        now_est = datetime.now(timezone.utc).astimezone(EST).strftime("%Y-%m-%d %I:%M %p EST")
        commit_msg = f"Dashboard update — {now_est}"
        new_commit = repo.create_git_commit(commit_msg, new_tree, [repo.get_git_commit(latest_sha)])
        ref.edit(new_commit.sha)
        print(f"Committed and pushed: {commit_msg}")

    except Exception as e:
        print(f"ERROR: Failed to commit/push: {e}")
        raise


def main():
    now = datetime.now(timezone.utc).astimezone(EST)
    print(f"=== Fieldwire Dashboard Pipeline — {now.strftime('%Y-%m-%d %I:%M %p EST')} ===\n")

    gmail_address = os.environ.get("GMAIL_ADDRESS", "")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not gmail_address or not gmail_app_password:
        print("ERROR: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set.")
        sys.exit(1)

    # Step 1: Fetch emails
    print("--- Step 1: Fetching emails ---")
    fetched = fetch_emails(gmail_address, gmail_app_password, DATA_DIR)
    print(f"Fetched {len(fetched)} new CSV(s).\n")

    # Step 2: Process new CSVs
    print("--- Step 2: Processing CSVs ---")
    if fetched:
        processed = process_all(fetched, DATA_DIR)
        print(f"Processed {len(processed)} new project(s).\n")
    else:
        print("No new CSVs. Reprocessing existing data...")
        reprocess_existing(DATA_DIR)
        print()

    # Step 3: Generate site
    print("--- Step 3: Generating site ---")
    generate_site(DATA_DIR, DOCS_DIR)
    print()

    # Step 4: Check inactivity
    print("--- Step 4: Checking inactivity ---")
    github_repo = os.environ.get("GITHUB_REPOSITORY", "")
    pages_url = f"https://{github_repo.split('/')[0]}.github.io/{github_repo.split('/')[1]}" if "/" in github_repo else ""
    check_inactivity(DATA_DIR, gmail_address, gmail_app_password, pages_url)
    print()

    # Step 5: Commit and push
    print("--- Step 5: Committing changes ---")
    commit_and_push()
    print()

    # Step 6: Summary
    print("=== Pipeline Complete ===")
    print(f"  New CSVs fetched: {len(fetched)}")
    print(f"  Projects in dashboard: {len([d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d))])}")
    print(f"  Timestamp: {now.strftime('%Y-%m-%d %I:%M %p EST')}")


if __name__ == "__main__":
    main()
