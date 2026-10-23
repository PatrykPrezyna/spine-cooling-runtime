---
name: roadmap-meeting-notes
description: >-
  Turn Cool Spine meeting notes into GANTT roadmap tasks. Use when the user
  pastes meeting notes, minutes, or action items and wants roadmap tasks,
  sprint tasks, or GANTT bars, including tasks marked Current Sprint with the
  green sprint cell colored.
---

# Roadmap meeting notes

Workbook: `tools/GANTT/Cool_Spine_GANTT.xlsx`

Editor: `tools/GANTT/roadmap_agent.py`

Run both from the repo root. Pass `--file tools/GANTT/Cool_Spine_GANTT.xlsx` on every command.

Column B is the sprint filter (`Current Sprint`, `Next Sprint`, and the other allowed values). The green cells are a separate bar: one cell per 2-week sprint, from the start sprint through the end sprint. A task can be filtered as Current Sprint and still have a bar that runs into later sprints.

## Before any edit

Run:

```bash
python tools/GANTT/roadmap_agent.py --file tools/GANTT/Cool_Spine_GANTT.xlsx current-sprint
python tools/GANTT/roadmap_agent.py --file tools/GANTT/Cool_Spine_GANTT.xlsx epics
```

`current-sprint` names the sprint that contains today. Use those dates. Do not invent sprint boundaries. `current` and `next` in later commands mean that column and the following one.

## Propose, then wait

The first reply is only the proposed list. Do not edit the workbook in that turn.

Use the epic names exactly as `epics` prints them. Put each task in the section the notes belong to. Place a follow-on directly under the task it continues (`--after`). Otherwise add it at the end of the epic (`--epic`). The opening block has `"epic": null`; insert those with `--after` and the `after` value from that section. Do not create a new epic unless the user asks.

Sprint filter is **Current Sprint** unless the user said otherwise. Choose the start sprint and end sprint from the notes. One sprint is the default when the notes do not give a longer window: the sprint that contains today.

Fix obvious typos in task names. Keep names short, in the same style as the tasks already in that section.

Reply with this table and nothing written to the file. The Epic column is the workbook epic name, copied exactly from `epics`. When that value is null, write Opening block.

| Task | Epic | Start sprint | End sprint |
|---|---|---|---|
| Design new probes for the animal study | Probes | 22 Oct – 4 Nov 2026 | 22 Oct – 4 Nov 2026 |

State above the table that the sprint filter will be Current Sprint. Start sprint and end sprint are the first and last colored fortnights. When they are the same sprint, both columns show that fortnight.

Stop there. Write only after the user accepts the list. A correction is a new list: show the revised table and wait again. Apply on the same turn when the user accepts and corrects in one reply ("yes, and end the second task one sprint later").

## Write

For each accepted row, one command:

```bash
python tools/GANTT/roadmap_agent.py --file tools/GANTT/Cool_Spine_GANTT.xlsx add-task \
  --task "Design new probes for the animal study" --epic "Probes" \
  --status "Current Sprint" --start 2026-10-22 --end 2026-11-04
```

`--start` and `--end` are `YYYY-MM-DD`, `current`, or `next`. Pass the first sprint's start date and the last sprint's end date from `current-sprint`. The command colors every overlapping column with the sheet's theme green and leaves the row above unchanged.

If the save fails because the workbook is open, ask the user to close Excel and stop.

Then run `list --sprint "Current Sprint"` and check each new task's `sprint_status`, `period_start`, and `period_end` against the accepted table before telling the user it is done.
