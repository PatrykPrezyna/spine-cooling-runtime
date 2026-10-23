# Cool Spine roadmap agent script

The script edits the existing workbook without requiring macros. It uses column A for task names, column B for sprint status, row 3 for 2-week sprint dates, and row 5 as the filter header.

## Install

```bash
pip install openpyxl
```

## Examples

```bash
# Inspect the workbook
python roadmap_agent.py --file Cool_Spine_GANTT.xlsx analyze

# Which 2-week column contains today, and the full sprint list
python roadmap_agent.py --file Cool_Spine_GANTT.xlsx current-sprint

# Epic sections and the tasks already under each
python roadmap_agent.py --file Cool_Spine_GANTT.xlsx epics

# Add a task, mark the sprint filter, and color the bar in one save.
# --start and --end take YYYY-MM-DD, current, or next.
# current is the sprint column that contains today. next is the following column.
# --as-of YYYY-MM-DD resolves those words against another date.
python roadmap_agent.py --file Cool_Spine_GANTT.xlsx add-task \
  --task "Verify cooling loop V2" --epic "Probes" \
  --status "Current Sprint" --start current --end current

# Color an existing task. Every overlapping sprint cell uses the sheet's theme green.
# A new row does not keep the green cells of the row it was copied from.
python roadmap_agent.py --file Cool_Spine_GANTT.xlsx set-period \
  --task "Verify cooling loop V2" --start 2026-11-05 --end 2026-11-18

# List tasks for an agent to consume as JSON
python roadmap_agent.py --file Cool_Spine_GANTT.xlsx list --sprint "Current Sprint"
python roadmap_agent.py --file Cool_Spine_GANTT.xlsx list --sprint "Last Sprint"
python roadmap_agent.py --file Cool_Spine_GANTT.xlsx list --sprint "Next Sprint"

# Mark one task complete
python roadmap_agent.py --file Cool_Spine_GANTT.xlsx mark-done \
  --task "Verify cooling loop V2" --green-bar

# Move the sprint cycle forward in one operation
# Last Sprint -> Done, Current Sprint -> Last Sprint, Next Sprint -> Current Sprint
python roadmap_agent.py --file Cool_Spine_GANTT.xlsx advance-sprint
```

## Agent integration

Every command writes structured JSON to standard output. A successful response has `"ok": true`; a failed command has `"ok": false` and exits with a non-zero exit code. Task matching first tries an exact case-insensitive match, then a unique partial match. Ambiguous matches return an error plus possible matches.

Before each write, the script creates `Cool_Spine_GANTT.xlsx.bak`. Use `--no-backup` only if another versioning system already protects the file.

Meeting notes go through the `roadmap-meeting-notes` skill: propose each task with its section, start sprint, and end sprint, and wait for a yes before editing the workbook.

For any other edit:

1. Run `current-sprint` and `epics`.
2. Run the requested edit command.
3. Inspect the JSON result. `period_start` and `period_end` are the colored bar.
4. Run `list --sprint "Current Sprint"` or another read command to verify the final state.
