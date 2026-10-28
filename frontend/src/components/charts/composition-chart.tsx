import { useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import type { DatasetStats } from "@/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import type { ChartConfig } from "@/components/ui/chart";

interface CompositionChartProps {
  stats: DatasetStats | undefined;
  isLoading: boolean;
  /** When true, renders charts in a compact row without wrapping Cards */
  compact?: boolean;
}

// Generate a set of distinct colors for bar charts
const BAR_COLORS = [
  "hsl(217, 91%, 60%)",
  "hsl(199, 89%, 48%)",
  "hsl(142, 71%, 45%)",
  "hsl(38, 92%, 50%)",
  "hsl(346, 87%, 60%)",
  "hsl(265, 83%, 57%)",
  "hsl(174, 72%, 46%)",
  "hsl(25, 95%, 53%)",
];

export function CompositionChart({ stats, isLoading, compact }: CompositionChartProps) {
  // Build one chart dataset per attribute
  const attributeCharts = useMemo(() => {
    if (!stats?.by_attribute) return [];
    return Object.entries(stats.by_attribute).map(([attrName, valueCounts]) => {
      const data = Object.entries(valueCounts).map(([value, count]) => ({
        name: value === "" || value === "null" || value === "None" ? "None" : value,
        count,
      }));
      return { attrName, data };
    });
  }, [stats]);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading stats...</p>;
  }

  if (!stats || attributeCharts.length === 0) {
    return <p className="text-sm text-muted-foreground">No data available.</p>;
  }

  const chartConfig: ChartConfig = {
    count: {
      label: "Count",
      color: BAR_COLORS[0],
    },
  };

  // Compact mode: horizontal row of small charts sized to content
  if (compact) {
    return (
      <div className="flex flex-wrap gap-6">
        {attributeCharts.map((chart) => {
          // Size chart width to number of bars: ~50px per bar + 40px for axis
          const chartWidth = Math.max(120, chart.data.length * 50 + 40);
          return (
            <div key={chart.attrName}>
              <p className="text-xs font-medium text-muted-foreground mb-2">
                By {chart.attrName}
              </p>
              {chart.data.length > 0 ? (
                <ChartContainer
                  config={chartConfig}
                  className="h-[140px]"
                  style={{ width: chartWidth }}
                >
                  <BarChart data={chart.data}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 10 }} width={30} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar
                      dataKey="count"
                      fill={BAR_COLORS[0]}
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ChartContainer>
              ) : (
                <p className="text-xs text-muted-foreground">No data</p>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  // Full mode: each chart in its own Card
  return (
    <div className="space-y-4">
      {attributeCharts.map((chart) => (
        <Card key={chart.attrName}>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">By {chart.attrName}</CardTitle>
            <CardDescription>
              Image counts grouped by {chart.attrName}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {chart.data.length > 0 ? (
              <ChartContainer config={chartConfig} className="h-[200px] w-full">
                <BarChart data={chart.data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" />
                  <YAxis allowDecimals={false} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar
                    dataKey="count"
                    fill={BAR_COLORS[0]}
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ChartContainer>
            ) : (
              <p className="text-sm text-muted-foreground">No data</p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
