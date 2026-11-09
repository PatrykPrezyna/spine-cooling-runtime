---
name: roadmap-meeting-notes
description: >-
  Turn Cool Spine meeting notes into GANTT roadmap tasks. Use when the user
  pastes meeting notes, minutes, or action items and wants roadmap tasks,
  sprint tasks, or GANTT bars in C:\sources\cool-spine-roadmap\roadmap.yaml.
---

# Roadmap meeting notes

Schedule: `C:\sources\cool-spine-roadmap\roadmap.yaml`

That folder is its own private git repository: https://github.com/PatrykPrezyna/cool-spine-roadmap. It is not part of spine-cooling-runtime. The view-only site is https://patrykprezyna.github.io/cool-spine-roadmap-site/. Publish it with `python publish_site.py` from the roadmap folder after the schedule changes. People edit the schedule in the browser with `python server.py` there. Agents edit `roadmap.yaml` through `roadmap_io`. The Excel file is an export: `python export_xlsx.py` writes `Cool_Spine_Roadmap_YYYY-MM-DD.xlsx` for the day it runs. Do not edit the workbook by hand.

The GitHub Pages site is a view-only encrypted copy. Do not edit the schedule there, and do not put the site password in this file.

Sprints are `timeline.sprint_days` long and begin at `timeline.start`. A bar stores sprint start dates. `start` and `end` are both the first day of a sprint, and a one-sprint task uses the same date twice. Omit both when there is no bar. Status is `done`, `in_progress`, or `future`.

## Before any edit

Read `C:\sources\cool-spine-roadmap\roadmap.yaml`. The sprint that contains today is `current`. The following sprint is `next`. Take those dates from the file. Do not invent sprint boundaries.

## Propose, then wait

The first reply is only the proposed list. Do not edit the file in that turn.

Use epic names exactly as they appear in the file. Put each task in the epic the notes belong to. Place a follow-on directly under the task it continues. Otherwise add it at the end of that epic. Do not create an epic unless the user asks. The Milestones epic stays last. Milestones belong there. Do not add tasks to it.

Status is **in_progress** unless the user said the work is later or already finished. One sprint is the default when the notes do not give a longer window: the sprint that contains today.

Fix obvious typos in task names. Keep names short, in the same style as the tasks already in that epic.

Reply with this table and nothing written to the file.

| Task | Epic | Status | Start sprint | End sprint |
|---|---|---|---|---|
| Design new probes for the animal study | Probes | in_progress | 22 Oct – 4 Nov 2026 | 22 Oct – 4 Nov 2026 |

Start sprint and end sprint are the first and last fortnights on the bar. When they are the same sprint, both columns show that fortnight.

Stop there. Write only after the user accepts the list. A correction is a new list: show the revised table and wait again. Apply on the same turn when the user accepts and corrects in one reply ("yes, and end the second task one sprint later").

## Write

From the roadmap folder, one task at a time. `add_task` takes the epic id, such as `probes` for Probes, and appends the task. `start` and `end` are sprint start dates (`YYYY-MM-DD`), not the last day of a sprint.

```python
import sys
from pathlib import Path

root = Path(r"C:\sources\cool-spine-roadmap")
sys.path.insert(0, str(root))
from roadmap_io import add_task, load_roadmap, save_roadmap, update_task

path = root / "roadmap.yaml"
data = load_roadmap(path)
item_id = add_task(data, "probes", "Design new probes for the animal study")
update_task(data, item_id, {
    "status": "in_progress",
    "start": "2026-10-22",
    "end": "2026-10-22",
})
save_roadmap(path, data)
```

To place a follow-on under an existing task, move the new item to sit immediately after that item's id before `save_roadmap`. Leave every other row where it is.

Then load the file again and check each new task's name, status, start, and end against the accepted table before telling the user it is done.
