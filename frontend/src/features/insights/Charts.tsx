import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const BAR_SIZE = 12; // <= 24px marks; the design draws slim bars
const AXIS = { fontSize: 12, fill: "var(--muted-foreground)" };

export interface Datum {
  label: string;
  value: number;
  /** What the tooltip and label say, e.g. "3 of 12 (25%)". */
  text: string;
}

function ChartTooltip({ active, payload }: TooltipProps<number, string>) {
  const datum = active ? (payload?.[0]?.payload as Datum | undefined) : undefined;
  if (!datum) return null;
  return (
    <div className="rounded-md border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md">
      <p className="font-medium">{datum.label}</p>
      <p className="text-muted-foreground">{datum.text}</p>
    </div>
  );
}

export function ChartCard({
  title,
  description,
  table,
  children,
}: {
  title: string;
  description?: string;
  table: { headers: string[]; rows: (string | number)[][] };
  children: React.ReactNode;
}) {
  return (
    <Card className="gap-3">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-2">
        {children}
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground select-none">
            Show as a table
          </summary>
          <table className="mt-2 w-full text-left text-sm">
            <thead>
              <tr className="text-xs text-muted-foreground">
                {table.headers.map((h) => (
                  <th key={h} scope="col" className="py-1 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row) => (
                <tr key={String(row[0])} className="border-t">
                  {row.map((cell, i) => (
                    <td key={i} className="py-1 tabular-nums">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </CardContent>
    </Card>
  );
}

/** The value at the bar's tip, on one line (Recharts would wrap it to the bar's width). */
function TipLabel(props: {
  x?: number | string;
  y?: number | string;
  width?: number | string;
  height?: number | string;
  value?: number | string;
}) {
  const x = Number(props.x ?? 0) + Number(props.width ?? 0) + 6;
  const y = Number(props.y ?? 0) + Number(props.height ?? 0) / 2;
  return (
    <text x={x} y={y} dominantBaseline="middle" fontSize={12} fill="var(--foreground)">
      {props.value}
    </text>
  );
}

/** Ranked horizontal bars, one series, value at the tip. */
export function HorizontalBars({
  data,
  label,
  max,
}: {
  data: Datum[];
  label: string;
  max?: number;
}) {
  const height = Math.max(data.length * (BAR_SIZE + 18) + 16, 80);
  return (
    <div role="img" aria-label={label} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 96, bottom: 4, left: 4 }}>
          <CartesianGrid horizontal={false} stroke="var(--chart-grid)" strokeWidth={1} />
          <XAxis type="number" hide domain={[0, max ?? "dataMax"]} />
          <YAxis
            type="category"
            dataKey="label"
            width={110}
            interval={0}
            tick={AXIS}
            tickLine={false}
            axisLine={{ stroke: "var(--chart-grid)" }}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--muted)", opacity: 0.6 }} />
          <Bar
            dataKey="value"
            fill="var(--chart-1)"
            barSize={BAR_SIZE}
            radius={[0, 2, 2, 0]}
            isAnimationActive={false}
          >
            <LabelList dataKey="text" content={TipLabel} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Columns over time, one series; the axis carries the values. */
export function Columns({ data, label }: { data: Datum[]; label: string }) {
  return (
    <div role="img" aria-label={label} className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeWidth={1} />
          <XAxis
            dataKey="label"
            tick={AXIS}
            tickLine={false}
            axisLine={{ stroke: "var(--chart-grid)" }}
            interval={1}
          />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--muted)", opacity: 0.6 }} />
          <Bar
            dataKey="value"
            fill="var(--chart-1)"
            barSize={BAR_SIZE}
            radius={[2, 2, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
