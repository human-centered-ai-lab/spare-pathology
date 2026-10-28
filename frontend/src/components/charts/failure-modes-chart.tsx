import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface FailureModesChartProps {
  data: {
    overall: Record<string, number>;
    by_center?: Record<string, Record<string, number>>;
  };
}

export function FailureModesChart({ data }: FailureModesChartProps) {
  const chartData = Object.entries(data.overall)
    .sort(([, a], [, b]) => b - a)
    .map(([reason, count]) => ({
      reason,
      count,
    }));

  if (chartData.length === 0) {
    return (
      <p className="text-muted-foreground text-sm py-8 text-center">
        No failure mode data available.
      </p>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={Math.max(200, chartData.length * 35 + 40)}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 120 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis type="number" className="text-xs" />
        <YAxis
          type="category"
          dataKey="reason"
          className="text-xs"
          width={110}
          tick={{ fontSize: 11 }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "hsl(var(--popover))",
            border: "1px solid hsl(var(--border))",
            borderRadius: "0.375rem",
            fontSize: "0.75rem",
          }}
          formatter={(value: number) => [value, "Count"]}
        />
        <Bar
          dataKey="count"
          name="Count"
          fill="hsl(217, 91%, 60%)"
          radius={[0, 4, 4, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
