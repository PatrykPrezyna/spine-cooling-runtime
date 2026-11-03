# Cool Spine roadmap

The schedule is `roadmap.yaml`. The browser editor reads and writes that file.

```bash
python tools/GANTT/server.py
```

Open the address it prints. A task bar is a run of sprints: `start` and `end` are both sprint start dates. Status is `done`, `in_progress`, or `future`.

Fold an epic to hide its tasks and show one bar covering them. Fold all and Unfold all do that for every epic. Done, In progress, and Future filter every epic: click one to show only that status, then click others to add them. A folded bar follows the same filter.

Drag the grip beside a task name to change its order or move it into another epic.

Current sprint is the button above each sprint date. Click one to show tasks whose duration includes that sprint, including tasks that start earlier or end later. Click the same button again to show every task.

Milestones are listed under the last epic. Click a sprint on a milestone to move it. Clear removes its date.

Rebuild the Excel GANTT from that file:

```bash
python tools/GANTT/export_xlsx.py
```

It writes `Cool_Spine_Roadmap_YYYY-MM-DD.xlsx`, using the day it is generated. Green cells are task bars. A blue cell is a milestone.

`roadmap.template.yaml` is the file shape, not a second schedule.
