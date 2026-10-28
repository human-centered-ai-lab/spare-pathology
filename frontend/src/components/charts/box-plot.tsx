import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ErrorBar,
  ResponsiveContainer,
} from "recharts";

interface GroupDistribution {
  label: string;
  scores: number[];
  mean: number;
  median: number;
  q1: number;
  q3: number;
  count: number;
}

interface BoxPlotProps {
  data: GroupDistribution[];
}

const BAR_COLORS = [
  "hsl(217, 91%, 60%)",
  "hsl(199, 89%, 48%)",
  "hsl(142, 71%, 45%)",
  "hsl(38, 92%, 50%)",
  "hsl(346, 87%, 60%)",
  "hsl(265, 83%, 57%)",
];

export function BoxPlot({ data }: BoxPlotProps) {
  const chartData = data.map((group, idx) => {
    const std = computeStd(group.scores, group.mean);
    return {
      name: group.label,
      mean: round(group.mean),
      errorPos: round(std),
      errorNeg: round(std),
      fill: BAR_COLORS[idx % BAR_COLORS.length],
    };
  });

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} barCategoryGap="30%">
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis dataKey="name" className="text-xs" />
        <YAxis className="text-xs" />
        <Tooltip
          contentStyle={{
            backgroundColor: "hsl(var(--popover))",
            border: "1px solid hsl(var(--border))",
            borderRadius: "0.375rem",
            fontSize: "0.75rem",
          }}
          formatter={(value: number, name: string) => {
            if (name === "mean") return [value.toFixed(2), "Mean"];
            return [value, name];
          }}
        />
        <Legend />
        <Bar dataKey="mean" name="Mean Score" fill="currentColor" radius={[4, 4, 0, 0]}>
          <ErrorBar
            dataKey="errorPos"
            direction="y"
            width={8}
            strokeWidth={2}
            stroke="hsl(var(--foreground))"
          />
          {chartData.map((entry, index) => (
            <rect key={`cell-${index}`} fill={entry.fill} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function computeStd(scores: number[], mean: number): number {
  if (scores.length < 2) return 0;
  const variance =
    scores.reduce((sum, s) => sum + (s - mean) ** 2, 0) / (scores.length - 1);
  return Math.sqrt(variance);
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}
