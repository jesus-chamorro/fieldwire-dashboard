"""Process Fieldwire CSV exports into summary JSON files."""

import csv
import io
import json
import os
import re
from datetime import datetime, timezone, timedelta


# ── Status classification ─────────────────────────────────
NOT_STARTED_STATUSES = {
    "",
    "Not Started",
}

# Truly finished, signed-off statuses (adjust to your workflow)
COMPLETED_STATUSES = {
    "Tested - PASS - Photo Uploaded",
    "Tested - Passed - Photo uploaded",
    "Verified",
    "SM - Phase 3: Trim Out",
}

# Everything else is considered In Progress


EST = timezone(timedelta(hours=-5))


def parse_timestamp(ts_str):
    if not ts_str or not ts_str.strip():
        return None
    for fmt in (
        "%Y-%m-%d %I:%M:%S %p",   # 2026-04-28 11:12:09 AM  ← Fieldwire default
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(ts_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def extract_floor(location):
    """Return the top-level location name, or 'Unassigned' if empty."""
    if not location or not location.strip():
        return "Unassigned"
    return location.strip().split(" > ")[0].strip() or "Unassigned"


def normalize_category(raw):
    """
    '10-Access Control'      → 'Access Control'
    '03-Wireless Access Point' → 'Wireless Access Point'
    'Verified'               → 'Verified'
    ''                       → 'Other'
    """
    raw = (raw or "").strip()
    if not raw:
        return "Other"
    if "-" in raw:
        _, rest = raw.split("-", 1)
        return rest.strip() or raw
    return raw


def _read_csv_tasks(csv_path):
    """
    Open a Fieldwire CSV (UTF-16 or UTF-8), skip the 3 metadata lines,
    parse as tab-delimited, and return a list of row dicts.
    """
    # 1. Detect encoding from BOM
    with open(csv_path, "rb") as f:
        bom = f.read(2)
    encoding = "utf-16" if bom in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"

    # 2. Read all lines
    with open(csv_path, "r", encoding=encoding) as f:
        lines = f.readlines()

    # 3. Find the real header row — it starts with "ID\t" (per-project) or "Project name\t" (account-wide)
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("ID\t") or line.strip().startswith("Project name\t"):
            header_idx = i
            break

    if header_idx is None:
        raise ValueError(f"Cannot find header row in {csv_path}")

    # 4. Feed only header + data into DictReader with tab delimiter
    content = "".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(content), delimiter="\t")
    return list(reader)


def process_csv_file(csv_path, project_name):
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # ── Read tasks ──────────────────────────────────────────
    try:
        tasks = _read_csv_tasks(csv_path)
    except Exception as e:
        print(f"ERROR: Failed to read CSV {csv_path}: {e}")
        return None

    if not tasks:
        print(f"WARNING: CSV {csv_path} has no data rows.")
        return None

    # ── Aggregate ───────────────────────────────────────────
    floors = {}
    blocked_tasks = []
    todays_activity = []
    category_counts = {}

    for task in tasks:
        task_name    = task.get("Title", "")
        status       = (task.get("Status", "") or "").strip()
        tier1        = (task.get("Tier 1", "") or "").strip()
        collection   = (task.get("Collection", "") or "").strip()
        assignee     = task.get("Assignee", "")
        updated_at_str = task.get("Last Updated", "")
        raw_cat      = task.get("Category", "")

        # Build location: prefer "Collection > Tier 1", fall back to whichever exists
        if tier1 and collection:
            location = f"{collection} > {tier1}"
        elif tier1:
            location = tier1
        elif collection:
            location = collection
        else:
            location = ""

        floor = extract_floor(location)
        updated_at = parse_timestamp(updated_at_str)

        # Determine task state
        status_clean = status.strip()
        if status_clean in NOT_STARTED_STATUSES:
            task_state = "not_started"
        elif status_clean in COMPLETED_STATUSES:
            task_state = "completed"
        else:
            task_state = "in_progress"

        # Floor tracking
        if floor not in floors:
            floors[floor] = {
                "total": 0,
                "not_started": 0,
                "in_progress": 0,
                "completed": 0,
                "last_activity": None,
            }

        floors[floor]["total"] += 1
        floors[floor][task_state] += 1

        if updated_at:
            prev = floors[floor]["last_activity"]
            if prev is None or updated_at > prev:
                floors[floor]["last_activity"] = updated_at

        # Blocked tasks (tag contains "blocked")
        tags = " ".join([
            task.get("Tag 1", "") or "",
            task.get("Tag 2", "") or "",
            task.get("Tag 3", "") or "",
        ])
        if "blocked" in tags.lower():
            blocked_tasks.append({
                "task_name": task_name,
                "location": location,
                "assignee": assignee,
                "last_updated": updated_at_str,
            })

        # Today's activity
        if updated_at and updated_at.strftime("%Y-%m-%d") == today_str:
            todays_activity.append({
                "task_name": task_name,
                "status": status,
                "location": location,
                "assignee": assignee,
                "updated_at": updated_at_str,
            })

        # Category breakdown (text after first hyphen)
        cat = normalize_category(raw_cat)
        category_counts[cat] = category_counts.get(cat, 0) + 1

    # ── Build floor list ────────────────────────────────────
    floor_list = []
    stale_floors = []
    total_tasks = 0
    completed_tasks = 0
    in_progress_tasks = 0
    not_started_tasks = 0

    for floor_name, info in sorted(floors.items()):
        total_tasks        += info["total"]
        completed_tasks    += info["completed"]
        in_progress_tasks  += info["in_progress"]
        not_started_tasks  += info["not_started"]

        total_floor = info["total"] or 1
        pct_completed       = round(info["completed"] / total_floor * 100, 1)
        pct_in_progress     = round(info["in_progress"] / total_floor * 100, 1)
        pct_touched = round((info["in_progress"] + info["completed"]) / total_floor * 100, 1)

        last_act = info["last_activity"]
        days_since = None
        is_stale = False
        last_act_iso = None
        if last_act:
            last_act_iso = last_act.isoformat()
            days_since = (now - last_act).days
            is_stale = days_since >= 7

        if is_stale:
            stale_floors.append(floor_name)

        floor_list.append({
            "name": floor_name,
            "total_tasks": info["total"],
            "completed_tasks": info["completed"],
            "in_progress_tasks": info["in_progress"],
            "not_started_tasks": info["not_started"],
            "percent_complete": pct_completed,
            "percent_in_progress": pct_in_progress,
            "percent_touched": pct_touched,
            "last_activity": last_act_iso,
            "days_since_activity": days_since if days_since is not None else -1,
            "is_stale": is_stale,
        })

    touched_tasks = in_progress_tasks + completed_tasks
    overall_pct_touched = round(touched_tasks / total_tasks * 100, 1) if total_tasks else 0
    overall_pct_completed = round(completed_tasks / total_tasks * 100, 1) if total_tasks else 0

    return {
        "project_name": project_name,
        "last_updated": now.isoformat(),
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "in_progress_tasks": in_progress_tasks,
        "not_started_tasks": not_started_tasks,
        "touched_tasks": touched_tasks,
        "percent_touched": overall_pct_touched,
        "percent_complete": overall_pct_completed,
        "floors": floor_list,
        "blocked_tasks": blocked_tasks,
        "todays_activity": todays_activity,
        "category_breakdown": category_counts,
        "has_stale_floors": len(stale_floors) > 0,
        "stale_floors": stale_floors,
    }


def process_all(fetched_items, data_dir):
    processed = []

    for item in fetched_items:
        project_name = item["project_name"]
        csv_path     = item["csv_path"]
        project_slug = item.get("project_slug", "")

        print(f"Processing CSV for '{project_name}'...")
        try:
            summary = process_csv_file(csv_path, project_name)
            if summary is None:
                continue

            project_dir  = os.path.dirname(csv_path)
            summary_path = os.path.join(project_dir, "summary.json")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)

            print(f"  Saved summary: {summary_path}")
            processed.append({
                "project_name": project_name,
                "project_slug": project_slug,
                "summary_path": summary_path,
            })
        except Exception as e:
            print(f"ERROR: Failed to process {csv_path}: {e}")
            continue

    return processed


def reprocess_existing(data_dir):
    """Reprocess the latest CSV for every project folder that has one."""
    processed = []
    if not os.path.isdir(data_dir):
        return processed

    for entry in os.listdir(data_dir):
        project_dir = os.path.join(data_dir, entry)
        if not os.path.isdir(project_dir):
            continue

        csvs = sorted([f for f in os.listdir(project_dir) if f.endswith(".csv")])
        if not csvs:
            continue

        latest_csv   = os.path.join(project_dir, csvs[-1])
        project_name = entry.replace("-", " ").title()

        # Preserve stored project name if summary already exists
        existing_summary = os.path.join(project_dir, "summary.json")
        if os.path.exists(existing_summary):
            try:
                with open(existing_summary, "r") as f:
                    old = json.load(f)
                project_name = old.get("project_name", project_name)
            except Exception:
                pass

        print(f"Reprocessing '{project_name}' from {latest_csv}...")
        try:
            summary = process_csv_file(latest_csv, project_name)
            if summary:
                summary_path = os.path.join(project_dir, "summary.json")
                with open(summary_path, "w", encoding="utf-8") as f:
                    json.dump(summary, f, indent=2)
                processed.append({
                    "project_name": project_name,
                    "project_slug": entry,
                    "summary_path": summary_path,
                })
        except Exception as e:
            print(f"ERROR: Failed to reprocess {latest_csv}: {e}")

    return processed

if __name__ == '__main__':
    reprocess_existing('data')
