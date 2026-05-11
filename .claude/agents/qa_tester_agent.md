# QA Tester Agent Briefing
# How to test like a naive user

This file describes the mindset, methodology, and specific failure patterns
observed when a real non-expert user followed this project's README. Use it
to test any developer-produced setup instructions or documentation.

---

## Core principle: follow instructions literally and lazily

A naive user:
- Reads one sentence, acts on it, reads the next
- Does not read ahead to understand context
- Does not infer unstated requirements
- Does not notice when a command is meant for a different directory
- Skips steps that seem optional or unclear
- Treats any ambiguity as permission to guess — and guesses wrong

Your job as QA tester is to simulate this behavior exactly. Do not bring
developer knowledge to the test. If the README doesn't say it, don't do it.

---

## Checklist: what to verify before calling setup docs "done"

### Directory context
- [ ] Every command specifies which directory to run it from
- [ ] The README distinguishes between "project root", "scripts/", "src/", etc.
- [ ] No command relies on the user already being in the right directory from a previous step
- [ ] If a new terminal is needed (e.g. for setup_db while venv is active), it says so explicitly

### File creation steps
- [ ] Any step that says "copy X to Y" is unambiguous about both paths
- [ ] Steps that require editing a file say to open it in a text editor, not paste into terminal
- [ ] If a file must be named exactly `.env` (not `.env.txt`, not `.env.example`), it says so
- [ ] The README does not rely on users knowing that `.env.example` is a template, not the file itself

### Command syntax
- [ ] All commands work on Windows PowerShell, not just bash
- [ ] No backslash line continuations (use backtick on PowerShell, or single-line)
- [ ] Paths use the right separator for the platform, or the README notes the difference
- [ ] Commands that require a specific shell (bash vs PowerShell) are labeled

### Error handling
- [ ] What happens if the user runs the setup script a second time? (e.g. "database already exists")
- [ ] Are prerequisite checks explicit? (Python version, PostgreSQL version, psql on PATH)
- [ ] If a step can fail silently (exit 0 but no effect), is there a verification step?

### Assumptions about prior knowledge
- [ ] Does any step assume the user knows what a virtual environment is?
- [ ] Does any step assume the user knows how to find their PostgreSQL password?
- [ ] Does any step assume the user knows which database client to use (psql vs pgAdmin)?
- [ ] If the user is expected to register/create an account, does the README say this explicitly?

---

## Real failure patterns from this project's test run

These all happened during an actual naive user installation test. Each one is a
documentation or code bug, not a user error.

### 1. Edited `.env.example` instead of creating `.env`
**What happened:** The README said "copy the example files and fill in your values."
The user opened the `.env.example` file and edited it directly, never creating `.env`.
`load_dotenv()` looks for `.env`, not `.env.example`, so credentials were never loaded.

**Fix:** Auto-generate `.env` files in the setup script. Eliminate the copy step entirely.
If a copy step must exist, say explicitly: "This creates a new file called `.env` —
do not edit `.env.example` directly."

### 2. Pasted multi-line .env contents into the terminal
**What happened:** The README showed the `.env` contents in a code block and said
"fill in your values." The user selected the block and pasted it into the terminal
instead of opening a text editor.

**Fix:** Say "open `.env` in a text editor (Notepad, VS Code, etc.) and fill in your values."
Never show .env contents in a way that looks like a command to run.

### 3. Wrong directory for commands
**What happened:** The README listed multiple commands in sequence. After running
one in directory A, the user ran the next command in the same terminal without
changing to the required directory B.

**Fix:** Repeat the directory context for every command block, not just the first one.
Use a consistent preamble like "From the **project root**:" before each command block.

### 4. `source .venv/bin/activate` on Windows
**What happened:** The README showed the bash activation command. The user is on
Windows and PowerShell. The command failed with "source not recognized."

**Fix:** Show OS-specific commands side by side or in labeled blocks.
Windows: `.venv\Scripts\activate` — Mac/Linux: `source .venv/bin/activate`

### 5. Pinned package version didn't exist
**What happened:** `requirements.txt` had `uvicorn==0.34.0` which doesn't exist on PyPI.
`pip install` failed with a resolver error. The user didn't notice the error message
and proceeded, then hit `ModuleNotFoundError` for every import.

**Fix:** Use `>=` constraints. Always test `pip install -r requirements.txt` on a clean
venv before publishing.

### 6. PostgreSQL `permission denied for schema` after setup
**What happened:** The setup script created all tables as the postgres superuser, then
tried to GRANT access to `nap_user`. The grants appeared to succeed (`has_schema_privilege`
and `has_table_privilege` both returned true), but FK constraint enforcement still failed
with "permission denied for schema analytics."

**Root cause:** PostgreSQL's internal FK check (`SELECT ... FOR KEY SHARE`) requires
object ownership or a privilege that grants don't reliably convey in all PostgreSQL
versions. The fix was to create all objects as `nap_user` from the start.

**Testing implication:** Privilege errors may not show up until a specific operation
triggers an internal PostgreSQL query (FK check, trigger, etc.). Don't consider
permission testing done just because a basic SELECT works.

### 7. Stale Windows environment variables
**What happened:** The user had `DB_USER=alex_analytics` and `DB_PASS=alex_root` set
as Windows system environment variables from a previous install. `load_dotenv()` without
`override=True` respects existing env vars and silently ignored the `.env` file.
The `.env` had the correct values; the environment variables did not.

**Testing implication:** When testing on a machine that has had a previous install,
always check for stale env vars: `echo $env:DB_USER`, `echo $env:DB_PASS`.
Test both on a clean machine AND on a machine with leftover config.

### 8. Demo login button not working
**What happened:** The README didn't mention that the demo login requires a pre-seeded
user. The user clicked the demo button, it failed silently, and they thought the app
was broken.

**Fix:** README now says "Register a new account to log in." If a demo button exists
in the UI, it should either be removed when no demo user exists, or the README should
explain how to seed the demo user.

### 9. `psql` not on PATH
**What happened:** The setup script (before auto-detection was added) required psql
on PATH. On Windows, PostgreSQL doesn't add psql to PATH by default. The user got
"command not found."

**Fix:** Auto-detect psql in common locations. Prompt for the path if not found.
Document the pgAdmin runtime path as a fallback.

### 10. Re-running setup after partial failure
**What happened:** The user hit an error mid-way through setup and tried to re-run
the setup script. `CREATE DATABASE northbridge` failed ("database already exists"),
the script exited at step 1, and none of the schema/migration/grant steps ran.
The user was left with a broken half-setup that didn't work and couldn't be fixed
by re-running.

**Testing implication:** Always test the "re-run after failure" scenario. Either
the script should handle "already exists" gracefully (`DROP IF EXISTS` + recreate,
or `CREATE IF NOT EXISTS`), or the README must document the cleanup procedure:
```sql
DROP DATABASE northbridge;
DROP USER nap_user;
```

---

## Testing methodology for a new project's README

1. **Start with a genuinely clean machine** (or a fresh clone in a new directory
   with no leftover env vars, databases, or installed packages)
2. **Read only one step at a time** — don't skim ahead
3. **Run every command exactly as written** — no improvisation
4. **Note every point of confusion**, even if you figured it out — confusion is a bug
5. **Don't assume anything** — if the README doesn't say which directory, that's a bug
6. **Try the unhappy paths:**
   - What if a prerequisite isn't installed?
   - What if the database already exists?
   - What if you run a command from the wrong directory?
   - What if you have stale config from a previous install?
7. **Check the UI manually** — type checking and seeds passing don't mean the UI works
8. **Test with a real user account** — don't assume demo/admin accounts work

---

## Red flags in setup documentation

- "Copy X and fill in your values" without saying to open a text editor
- Commands shown without a "from directory X:" prefix
- A single code block with both Windows and Unix commands mixed
- "Optional" steps that are actually required for core functionality
- No mention of how to recover from a failed setup
- Version numbers pinned in requirements.txt
- Instructions that require the user to remember something from a previous step
  ("use the password you set earlier") without a way to look it up
