"""Process Fieldwire CSV exports into summary JSON files."""

import csv
import json
import os
import re
from datetime import datetime, timezone, timedelta


CATEGORY_CODES = {
    "00": "Site Mgmt",
    "10": "Access Control",
    "11": "Smart Locks",
    "20": "CCTV",
    "30": "WAPs",
    "40": "Data Ports",
    "50": "Intercom",
    "60": "AV",
    "70": "Infrastructure",
}

COMPLETED_STATUSES = {"SM - Phase 1: Rough-In", "SM - Phase 2: Terminating& Testing", "SM - Phase 3: Trim Out", "Tested - Failed - Photo uploaded", "Wire Roughed-in", "Tested - Passed - Photo uploaded", "Terminated", "Verified", "Device & MAC-Photo Uploaded"}

EST = timezone(timedelta(hours=-5))


def parse_timestamp(ts_str):
    if not ts_str or not ts_str.strip():
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%Y-%m-%d %I:%M:%S %p",
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
    if not location or not location.strip():
        return "Unassigned"
    return location.strip().split(" > ")[0].strip()


def extract_category(task_name):
    if not task_name:
        return "Other"
    match = re.match(r"^(\d{2})\b", task_name.strip())
    if match:
        code = match.group(1)
        return CATEGORY_CODES.get(code, "Other")
    return "Other"


def process_csv_file(csv_path, project_name):
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    tasks = []
    try:
        encoding = "utf-16" if open(csv_path, "rb").read(2) in (b'\xff\xfe', b'\xfe\xff') else "utf-8-sig"
        with open(csv_path, "r", encoding=encoding) as f:
            reader = csv.DictReader(f)
            for row in reader:
                tasks.append(row)
    except Exception as e:
        print(f"ERROR: Failed to read CSV {csv_path}: {e}")
        return None

    if not tasks:
        print(f"WARNING: CSV {csv_path} has no rows.")
        return None

    floors = {}
    blocked_tasks = []
    todays_activity = []
    category_counts = {}

    for task in tasks:
        task_name = task.get("Title", "")
        status = task.get("Status", "")
        tier1 = task.get("Tier 1", "").strip()
        tier2 = task.get("Tier 2", "").strip()
        tier3 = task.get("Tier 3", "").strip()
        tier4 = task.get("Tier 4", "").strip()
        tier5 = task.get("Tier 5", "").strip()
        collection = task.get("Collection", "").strip()
        location = f"{collection} > {tier1}" if tier1 else collection
        assignee = task.get("Assignee", "")
        updated_at_str = task.get("Last Updated", "")
        tags = task.get("Tag 1", "")

        floor = extract_floor(location)
        updated_at = parse_timestamp(updated_at_str)

        if floor not in floors:
            floors[floor] = {
                "total": 0,
                "completed": 0,
                "last_activity": None,
            }

        floors[floor]["total"] += 1
        if status.strip() in COMPLETED_STATUSES:
            floors[floor]["completed"] += 1

        if updated_at:
            prev = floors[floor]["last_activity"]
            if prev is None or updated_at > prev:
                floors[floor]["last_activity"] = updated_at

        if tags and "#blocked" in tags.lower():
            blocked_tasks.append({
                "task_name": task_name,
                "location": location,
                "assignee": assignee,
                "last_updated": updated_at_str,
            })

        if updated_at and updated_at.strftime("%Y-%m-%d") == today_str:
            todays_activity.append({
                "task_name": task_name,
                "status": status,
                "location": location,
                "assignee": assignee,
                "updated_at": updated_at_str,
            })

        raw_cat = task.get("Category", "")
        cat = raw_cat.split("-", 1)[1].strip() if "-" in raw_cat else raw_cat or "Other"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    floor_list = []
    stale_floors = []
    total_tasks = 0
    completed_tasks = 0

    for floor_name, info in sorted(floors.items()):
        total_tasks += info["total"]
        completed_tasks += info["completed"]

        pct = (info["completed"] / info["total"] * 100) if info["total"] > 0 else 0

        last_act = info["last_activity"]
        days_since = None
        is_stale = False
        last_act_iso = None

        if last_act:
            last_act_iso = last_act.isoformat()
            delta = now - last_act
            days_since = delta.days
            is_stale = days_since >= 7

        if is_stale:
            stale_floors.append(floor_name)

        floor_list.append({
            "name": floor_name,
            "total_tasks": info["total"],
            "completed_tasks": info["completed"],
            "percent_complete": round(pct, 1),
            "last_activity": last_act_iso,
            "days_since_activity": days_since if days_since is not None else -1,
            "is_stale": is_stale,
        })

    overall_pct = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    summary = {
        "project_name": project_name,
        "last_updated": now.isoformat(),
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "percent_complete": round(overall_pct, 1),
        "floors": floor_list,
        "blocked_tasks": blocked_tasks,
        "todays_activity": todays_activity,
        "category_breakdown": category_counts,
        "has_stale_floors": len(stale_floors) > 0,
        "stale_floors": stale_floors,
    }

    return summary


def process_all(fetched_items, data_dir):
    processed = []

    for item in fetched_items:
        project_name = item["project_name"]
        csv_path = item["csv_path"]
        project_slug = item.get("project_slug", "")

        print(f"Processing CSV for '{project_name}'...")
        try:
            summary = process_csv_file(csv_path, project_name)
            if summary is None:
                continue

            project_dir = os.path.dirname(csv_path)
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
    """Reprocess latest CSVs for all existing projects."""
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

        latest_csv = os.path.join(project_dir, csvs[-1])
        project_name = entry.replace("-", " ").title()

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
