"""Emit the pump-control scenarios canvas with embedded simulation data."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "pump_control_scenarios.json"
CANVAS_PATH = Path(
    r"C:\Users\patry\.cursor\projects\c-sources-spine-cooling-runtime"
    r"\canvases\pump-flow-control-scenarios.canvas.tsx"
)

HEADER = r'''import {
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  LineChart,
  Pill,
  Row,
  Select,
  Stack,
  Stat,
  Text,
  useCanvasState,
  useHostTheme,
} from "cursor/canvas";

type RowPt = { t: number; temp: number; flow: number; set: number; error: number };
type Scenario = { name: string; rows: RowPt[] };
type PlotData = {
  map: { error: number; flow: number }[];
  controller: { max: number; min: number; band: number; kp: number; ki: number; kd: number };
  plant: { description: string; tau_cool_s: number; t_coolant: number; t_body: number };
  scenarios: Scenario[];
};

const DATA: PlotData = '''

FOOTER = r''';

function fmtTime(t: number): string {
  return `${t}s`;
}

export default function PumpControlScenariosCanvas() {
  const theme = useHostTheme();
  const [scenarioIdx, setScenarioIdx] = useCanvasState("scenarioIdx", 0);
  const scenario = DATA.scenarios[Math.min(scenarioIdx, DATA.scenarios.length - 1)];
  const rows = scenario.rows;
  const cats = rows.map((r) => fmtTime(r.t));
  const last = rows[rows.length - 1];
  const peakFlow = Math.max(...rows.map((r) => r.flow));
  const minTemp = Math.min(...rows.map((r) => r.temp));
  const maxTemp = Math.max(...rows.map((r) => r.temp));

  const mapCats = DATA.map.map((p) => String(p.error));
  const mapFlows = DATA.map.map((p) => p.flow);

  void theme;

  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 1100 }}>
      <Stack gap={8}>
        <H1>Pump flow control vs CSF temperature</H1>
        <Text tone="secondary">
          Control input is pump flow (ml/min); plant output is CSF temperature (C).
          Closed-loop runs use the configured banded PID (max {DATA.controller.max} /
          min {DATA.controller.min} ml/min, full speed above {DATA.controller.band} C
          error). Source: simulated plant + PumpFlowController.
        </Text>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat value={`${DATA.controller.max}`} label="Max flow (ml/min)" />
        <Stat value={`${DATA.controller.min}`} label="Min flow (ml/min)" />
        <Stat value={`${DATA.controller.band} C`} label="Full-speed error band" />
        <Stat
          value={`Kp ${DATA.controller.kp}`}
          label={`Ki ${DATA.controller.ki} / Kd ${DATA.controller.kd}`}
        />
      </Grid>

      <Card>
        <CardHeader trailing={<Pill size="sm">P-only snapshot</Pill>}>
          Controller map: CSF error to commanded flow
        </CardHeader>
        <CardBody>
          <Stack gap={8}>
            <Text tone="secondary" size="small">
              X = CSF minus set temp (C). Above +0.5 C locks 100 ml/min; at/below 0
              locks 10 ml/min; inside (0, 0.5] uses PID (I/D off for this static curve).
            </Text>
            <LineChart
              categories={mapCats}
              series={[{ name: "Commanded flow (ml/min)", data: mapFlows, tone: "info" }]}
              height={220}
              yMin={0}
              yMax={110}
              valueSuffix=" ml/min"
              referenceLines={[
                { value: 100, label: "Max", tone: "warning" },
                { value: 10, label: "Min", tone: "neutral" },
              ]}
            />
            <Text tone="tertiary" size="small">
              Categories are error (C) from -0.5 to +1.5
            </Text>
          </Stack>
        </CardBody>
      </Card>

      <Divider />

      <Stack gap={12}>
        <Row gap={12} align="center" wrap>
          <H2 style={{ margin: 0 }}>Closed-loop scenarios</H2>
          <Select
            value={String(scenarioIdx)}
            onChange={(v) => setScenarioIdx(Number(v))}
            options={DATA.scenarios.map((s, i) => ({
              value: String(i),
              label: s.name,
            }))}
          />
        </Row>
        <Text tone="secondary" size="small">
          {DATA.plant.description} tau_cool={DATA.plant.tau_cool_s}s, coolant=
          {DATA.plant.t_coolant} C, body={DATA.plant.t_body} C. Samples every 5 s.
        </Text>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat value={`${rows[0].temp.toFixed(2)} C`} label="Start CSF" />
        <Stat value={`${last.temp.toFixed(2)} C`} label="End CSF" tone="success" />
        <Stat value={`${peakFlow.toFixed(0)} ml/min`} label="Peak flow" />
        <Stat value={`${last.flow.toFixed(1)} ml/min`} label="End flow" />
      </Grid>

      <Card>
        <CardHeader>{`Output: CSF temperature — ${scenario.name}`}</CardHeader>
        <CardBody>
          <LineChart
            categories={cats}
            series={[
              { name: "CSF temp (C)", data: rows.map((r) => r.temp), tone: "danger" },
              { name: "Set temp (C)", data: rows.map((r) => r.set), tone: "neutral" },
            ]}
            height={260}
            beginAtZero={false}
            yMin={Math.floor(minTemp) - 0.5}
            yMax={Math.ceil(maxTemp) + 0.5}
            valueSuffix=" C"
          />
          <Text tone="tertiary" size="small">
            Time (s) · plant output
          </Text>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>{`Input: commanded pump flow — ${scenario.name}`}</CardHeader>
        <CardBody>
          <LineChart
            categories={cats}
            series={[{ name: "Flow (ml/min)", data: rows.map((r) => r.flow), tone: "info" }]}
            height={240}
            yMin={0}
            yMax={110}
            valueSuffix=" ml/min"
            fill
            referenceLines={[
              { value: 100, label: "Max", tone: "warning" },
              { value: 10, label: "Min", tone: "neutral" },
            ]}
          />
          <Text tone="tertiary" size="small">
            Time (s) · control input
          </Text>
        </CardBody>
      </Card>

      <H3>All scenarios — CSF temperature overlay</H3>
      <LineChart
        categories={DATA.scenarios[0].rows.map((r) => fmtTime(r.t))}
        series={DATA.scenarios
          .filter((s) => s.rows.length === DATA.scenarios[0].rows.length)
          .map((s) => ({
            name: s.name,
            data: s.rows.map((r) => r.temp),
          }))}
        height={280}
        beginAtZero={false}
        valueSuffix=" C"
      />
      <Text tone="tertiary" size="small">
        Overlay shows 0–240 s runs only (same sample grid). Use the scenario
        selector above for the shorter cases.
      </Text>

      <Callout tone="info" title="How to read the plots">
        When CSF is more than 0.5 C above set, flow saturates at 100 ml/min. Inside
        the band the PID trims flow. At or below set, flow floors at 10 ml/min.
        Steady hold near set often settles a bit above 10 ml/min to balance
        simulated body heat leak.
      </Callout>
    </Stack>
  );
}
'''


def main() -> None:
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    scenarios = []
    for sc in raw["scenarios"]:
        rows = [
            row
            for i, row in enumerate(sc["rows"])
            if row["t"] % 5 == 0 or i == len(sc["rows"]) - 1
        ]
        scenarios.append({"name": sc["name"], "rows": rows})
    compact = {
        "map": raw["map"],
        "controller": raw["controller"],
        "plant": raw["plant"],
        "scenarios": scenarios,
    }
    payload = json.dumps(compact, separators=(",", ":"))
    CANVAS_PATH.write_text(HEADER + payload + FOOTER, encoding="utf-8")
    print(f"Wrote {CANVAS_PATH} ({CANVAS_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
