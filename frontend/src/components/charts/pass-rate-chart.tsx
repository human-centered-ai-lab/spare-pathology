import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface PassRateChartProps {
  data: Record<string, number>;
}

function getColor(rate: number): string {
  if (rate >= 80) return "hsl(217, 91%, 60%)";
  if (rate >= 50) return "hsl(199, 89%, 48%)";
  return "hsl(215, 60%, 75%)";
}

export function PassRateChart({ data }: PassRateChartProps) {
  const chartData = Object.entries(data).map(([group, rate]) => ({
    group,
    rate: Math.round(rate * 100) / 100,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} barCategoryGap="20%">
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis dataKey="group" className="text-xs" />
        <YAxis domain={[0, 100]} className="text-xs" unit="%" />
        <Tooltip
          contentStyle={{
            backgroundColor: "hsl(var(--popover))",
            border: "1px solid hsl(var(--border))",
            borderRadius: "0.375rem",
            fontSize: "0.75rem",
          }}
          formatter={(value: number) => [`${value.toFixed(1)}%`, "Pass Rate"]}
        />
        <Bar dataKey="rate" name="Pass Rate" radius={[4, 4, 0, 0]}>
          {chartData.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={getColor(entry.rate)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
