#!/usr/bin/env python3
"""Asana REST API CLI — PAT-based, stdlib-only, JSON output."""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://app.asana.com/api/1.0"


# ── Layer 1: .env handling ───────────────────────────────────────────────────

def load_env(path=".env"):
    """Read key=value lines from a .env file. Skips comments and blanks."""
    env = {}
    if not os.path.isfile(path):
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            env[k.strip()] = v
    return env


def get_pat():
    pat = os.environ.get("ASANA_PAT") or load_env().get("ASANA_PAT")
    if not pat:
        err = {
            "error": "no_pat",
            "message": "No ASANA_PAT found.",
            "setup": (
                "1. Create a PAT at https://app.asana.com/0/developer-console\n"
                "2. Run: python3 .claude/skills/asana-rest-api/scripts/asana.py init --pat \"0/your_token\"\n"
                "   Or add ASANA_PAT=0/your_token to your .env file"
            ),
        }
        print(json.dumps(err, indent=2), file=sys.stderr)
        sys.exit(1)
    return pat


def get_default_project():
    return os.environ.get("ASANA_PROJECT_GID") or load_env().get("ASANA_PROJECT_GID")


def write_env_var(key, value, path=".env"):
    """Set a key in .env — creates, appends, or replaces as needed."""
    lines = []
    replaced = False
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


# ── Layer 2: HTTP ────────────────────────────────────────────────────────────

def api_request(method, path, pat, data=None, params=None):
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)

    body = None
    if data is not None:
        body = json.dumps({"data": data}).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {pat}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    for attempt in range(3):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return {"data": {}}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", "30"))
                if attempt < 2:
                    print(json.dumps({"warning": f"Rate limited, retrying in {retry_after}s"}), file=sys.stderr)
                    time.sleep(retry_after)
                    continue
            if e.code == 401:
                print(json.dumps({
                    "error": "unauthorized",
                    "message": "401 Unauthorized — PAT may be invalid or revoked.",
                    "help": "Create a new PAT at https://app.asana.com/0/developer-console",
                }), file=sys.stderr)
                sys.exit(1)
            try:
                err_json = json.loads(resp_body)
            except json.JSONDecodeError:
                err_json = {"raw": resp_body}
            print(json.dumps({"error": f"HTTP {e.code}", "detail": err_json}), file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(json.dumps({"error": "connection_failed", "message": str(e.reason)}), file=sys.stderr)
            sys.exit(1)
    return {"data": {}}


def paginated_get(path, pat, params=None):
    params = dict(params or {})
    params.setdefault("limit", "100")
    all_items = []
    while True:
        resp = api_request("GET", path, pat, params=params)
        all_items.extend(resp.get("data", []))
        nxt = resp.get("next_page")
        if not nxt or not nxt.get("offset"):
            break
        params["offset"] = nxt["offset"]
    return all_items


def get_workspace_gid(pat):
    resp = api_request("GET", "/users/me", pat, params={"opt_fields": "workspaces.gid,workspaces.name"})
    workspaces = resp.get("data", {}).get("workspaces", [])
    if not workspaces:
        print(json.dumps({"error": "no_workspace", "message": "No workspaces found for this PAT."}), file=sys.stderr)
        sys.exit(1)
    return workspaces[0]["gid"]


def require_project(args_project):
    gid = args_project or get_default_project()
    if not gid:
        print(json.dumps({
            "error": "no_project",
            "message": "No project specified. Use --project GID or set ASANA_PROJECT_GID in .env",
        }), file=sys.stderr)
        sys.exit(1)
    return gid


# ── Layer 3: Commands ────────────────────────────────────────────────────────

def cmd_init(args):
    pat = args.pat
    # Validate the PAT
    headers = {"Authorization": f"Bearer {pat}", "Accept": "application/json"}
    req = urllib.request.Request(f"{BASE_URL}/users/me?opt_fields=name,email,workspaces.gid,workspaces.name", headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            user = json.loads(resp.read().decode("utf-8")).get("data", {})
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": "invalid_pat", "message": f"PAT validation failed: HTTP {e.code}"}), file=sys.stderr)
        sys.exit(1)

    write_env_var("ASANA_PAT", pat)

    if args.project:
        write_env_var("ASANA_PROJECT_GID", args.project)

    result = {
        "status": "ok",
        "user": user.get("name"),
        "email": user.get("email"),
        "workspaces": user.get("workspaces", []),
        "env_file": os.path.abspath(".env"),
        "project_gid": args.project or get_default_project(),
    }
    print(json.dumps(result, indent=2))


def cmd_status(args):
    pat = get_pat()
    resp = api_request("GET", "/users/me", pat, params={"opt_fields": "name,email,workspaces.gid,workspaces.name"})
    user = resp.get("data", {})
    result = {
        "status": "ok",
        "user": user.get("name"),
        "email": user.get("email"),
        "workspaces": user.get("workspaces", []),
        "default_project": get_default_project(),
        "env_file": os.path.abspath(".env") if os.path.isfile(".env") else None,
    }
    print(json.dumps(result, indent=2))


def cmd_list_projects(args):
    pat = get_pat()
    ws = get_workspace_gid(pat)
    params = {"opt_fields": "name,archived"}
    items = paginated_get(f"/workspaces/{ws}/projects", pat, params)
    if not args.archived:
        items = [p for p in items if not p.get("archived")]
    print(json.dumps(items, indent=2))


def cmd_get_sections(args):
    pat = get_pat()
    project = require_project(args.project)
    items = paginated_get(f"/projects/{project}/sections", pat, {"opt_fields": "name"})
    print(json.dumps(items, indent=2))


def cmd_list_tasks(args):
    pat = get_pat()
    project = require_project(args.project)
    params = {
        "project": project,
        "opt_fields": "name,completed,due_on,start_on,assignee.name,memberships.section.name,memberships.section.gid",
    }
    if args.section:
        params["section"] = args.section
    if args.completed is not None:
        if not args.completed:
            params["completed_since"] = "now"
    items = paginated_get("/tasks", pat, params)
    print(json.dumps(items, indent=2))


def cmd_get_task(args):
    pat = get_pat()
    fields = "name,notes,completed,due_on,start_on,assignee.name,dependencies.name,dependents.name,custom_fields,memberships.section.name,memberships.project.name"
    resp = api_request("GET", f"/tasks/{args.task}", pat, params={"opt_fields": fields})
    task = resp.get("data", {})
    # Fetch subtasks
    subtasks = paginated_get(f"/tasks/{args.task}/subtasks", pat, {"opt_fields": "name,completed"})
    task["subtasks"] = subtasks
    print(json.dumps(task, indent=2))


def cmd_search(args):
    pat = get_pat()
    ws = get_workspace_gid(pat)
    params = {"opt_fields": "name,completed,due_on,assignee.name"}
    if args.text:
        params["text"] = args.text
    if args.project:
        params["projects.any"] = args.project
    if args.completed is not None:
        params["completed"] = str(args.completed).lower()
    resp = api_request("GET", f"/workspaces/{ws}/tasks/search", pat, params=params)
    print(json.dumps(resp.get("data", []), indent=2))


def cmd_create_task(args):
    pat = get_pat()
    project = require_project(args.project)
    data = {"name": args.name, "projects": [project]}
    if args.description:
        data["notes"] = args.description
    if args.due:
        data["due_on"] = args.due
    if args.start:
        data["start_on"] = args.start
    if args.assignee:
        data["assignee"] = args.assignee
    if args.section:
        data["memberships"] = [{"project": project, "section": args.section}]
    resp = api_request("POST", "/tasks", pat, data=data)
    print(json.dumps(resp.get("data", {}), indent=2))


def cmd_create_tasks(args):
    pat = get_pat()
    if args.json:
        batch = json.loads(args.json)
    else:
        batch = json.load(sys.stdin)

    project = batch.get("project") or require_project(None)
    default_section = batch.get("section")
    tasks_spec = batch.get("tasks", [])
    created = []

    for spec in tasks_spec:
        data = {"name": spec["name"], "projects": [project]}
        section = spec.get("section", default_section)
        if spec.get("description"):
            data["notes"] = spec["description"]
        if spec.get("due"):
            data["due_on"] = spec["due"]
        if spec.get("start"):
            data["start_on"] = spec["start"]
        if spec.get("assignee"):
            data["assignee"] = spec["assignee"]
        if section:
            data["memberships"] = [{"project": project, "section": section}]

        resp = api_request("POST", "/tasks", pat, data=data)
        task = resp.get("data", {})
        created.append(task)

    # Resolve dependencies after all tasks are created
    for i, spec in enumerate(tasks_spec):
        deps = spec.get("depends_on", [])
        if not deps:
            continue
        resolved = []
        for dep in deps:
            if isinstance(dep, str) and dep.startswith("$"):
                idx = int(dep[1:])
                if idx < len(created) and created[idx].get("gid"):
                    resolved.append(created[idx]["gid"])
            else:
                resolved.append(dep)
        if resolved and created[i].get("gid"):
            api_request("POST", f"/tasks/{created[i]['gid']}/addDependencies", pat, data={"dependencies": resolved})

    print(json.dumps(created, indent=2))


def cmd_update_task(args):
    pat = get_pat()
    data = {}
    if args.name is not None:
        data["name"] = args.name
    if args.completed is not None:
        data["completed"] = args.completed
    if args.due is not None:
        data["due_on"] = args.due if args.due != "null" else None
    if args.start is not None:
        data["start_on"] = args.start if args.start != "null" else None
    if args.description is not None:
        data["notes"] = args.description
    if not data:
        print(json.dumps({"error": "no_fields", "message": "No fields to update."}), file=sys.stderr)
        sys.exit(1)
    resp = api_request("PUT", f"/tasks/{args.task}", pat, data=data)
    print(json.dumps(resp.get("data", {}), indent=2))


def cmd_move_task(args):
    pat = get_pat()
    data = {"task": args.task}
    api_request("POST", f"/sections/{args.section}/addTask", pat, data=data)
    print(json.dumps({"moved": True, "task": args.task, "section": args.section}, indent=2))


def cmd_add_dependency(args):
    pat = get_pat()
    dep_gids = [g.strip() for g in args.depends_on.split(",")]
    api_request("POST", f"/tasks/{args.task}/addDependencies", pat, data={"dependencies": dep_gids})
    print(json.dumps({"task": args.task, "dependencies_added": dep_gids}, indent=2))


def cmd_create_section(args):
    pat = get_pat()
    project = require_project(args.project)
    resp = api_request("POST", f"/projects/{project}/sections", pat, data={"name": args.name})
    print(json.dumps(resp.get("data", {}), indent=2))


def cmd_add_comment(args):
    pat = get_pat()
    resp = api_request("POST", f"/tasks/{args.task}/stories", pat, data={"text": args.text})
    print(json.dumps(resp.get("data", {}), indent=2))


def cmd_delete_task(args):
    pat = get_pat()
    api_request("DELETE", f"/tasks/{args.task}", pat)
    print(json.dumps({"deleted": True, "gid": args.task}, indent=2))


# ── Layer 4: CLI dispatcher ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Asana REST API CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p = sub.add_parser("init", help="Set up PAT in .env")
    p.add_argument("--pat", required=True, help="Personal Access Token (e.g. 0/abc123...)")
    p.add_argument("--project", help="Default project GID")

    # status
    sub.add_parser("status", help="Show auth status and config")

    # list-projects
    p = sub.add_parser("list-projects", help="List workspace projects")
    p.add_argument("--archived", action="store_true", help="Include archived projects")

    # get-sections
    p = sub.add_parser("get-sections", help="List sections in a project")
    p.add_argument("--project", help="Project GID (falls back to ASANA_PROJECT_GID)")

    # list-tasks
    p = sub.add_parser("list-tasks", help="List tasks in a project")
    p.add_argument("--project", help="Project GID")
    p.add_argument("--section", help="Filter by section GID")
    p.add_argument("--completed", type=lambda v: v.lower() == "true", default=None, help="Filter by completion (true/false)")

    # get-task
    p = sub.add_parser("get-task", help="Get full task details")
    p.add_argument("--task", required=True, help="Task GID")

    # search
    p = sub.add_parser("search", help="Search tasks")
    p.add_argument("--text", help="Search text")
    p.add_argument("--project", help="Filter by project GID")
    p.add_argument("--completed", type=lambda v: v.lower() == "true", default=None, help="Filter by completion")

    # create-task
    p = sub.add_parser("create-task", help="Create a single task")
    p.add_argument("--project", help="Project GID")
    p.add_argument("--section", help="Section GID")
    p.add_argument("--name", required=True, help="Task name")
    p.add_argument("--description", help="Task description")
    p.add_argument("--due", help="Due date (YYYY-MM-DD)")
    p.add_argument("--start", help="Start date (YYYY-MM-DD)")
    p.add_argument("--assignee", help="Assignee (\"me\", email, or GID)")

    # create-tasks
    p = sub.add_parser("create-tasks", help="Batch create tasks from JSON")
    p.add_argument("--json", help="JSON string (or pipe via stdin)")

    # update-task
    p = sub.add_parser("update-task", help="Update a task")
    p.add_argument("--task", required=True, help="Task GID")
    p.add_argument("--name", help="New name")
    p.add_argument("--completed", type=lambda v: v.lower() == "true", default=None, help="Mark complete (true/false)")
    p.add_argument("--due", help="Due date (YYYY-MM-DD or 'null' to clear)")
    p.add_argument("--start", help="Start date (YYYY-MM-DD or 'null' to clear)")
    p.add_argument("--description", help="New description")

    # move-task
    p = sub.add_parser("move-task", help="Move task to a section")
    p.add_argument("--task", required=True, help="Task GID")
    p.add_argument("--section", required=True, help="Target section GID")

    # add-dependency
    p = sub.add_parser("add-dependency", help="Add dependencies to a task")
    p.add_argument("--task", required=True, help="Task GID")
    p.add_argument("--depends-on", required=True, help="Comma-separated dependency GIDs")

    # create-section
    p = sub.add_parser("create-section", help="Create a section in a project")
    p.add_argument("--project", help="Project GID")
    p.add_argument("--name", required=True, help="Section name")

    # add-comment
    p = sub.add_parser("add-comment", help="Add a comment to a task")
    p.add_argument("--task", required=True, help="Task GID")
    p.add_argument("--text", required=True, help="Comment text")

    # delete-task
    p = sub.add_parser("delete-task", help="Delete a task")
    p.add_argument("--task", required=True, help="Task GID")

    args = parser.parse_args()
    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "list-projects": cmd_list_projects,
        "get-sections": cmd_get_sections,
        "list-tasks": cmd_list_tasks,
        "get-task": cmd_get_task,
        "search": cmd_search,
        "create-task": cmd_create_task,
        "create-tasks": cmd_create_tasks,
        "update-task": cmd_update_task,
        "move-task": cmd_move_task,
        "add-dependency": cmd_add_dependency,
        "create-section": cmd_create_section,
        "add-comment": cmd_add_comment,
        "delete-task": cmd_delete_task,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
