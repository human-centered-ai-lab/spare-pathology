import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ErrorBar,
  ResponsiveContainer,
} from "recharts";

interface EffectEstimate {
  center: string;
  effect: number;
  ci_lower: number;
  ci_upper: number;
  is_reference: boolean;
}

interface ForestPlotProps {
  data: {
    effects: EffectEstimate[];
    converged: boolean;
  };
}

export function ForestPlot({ data }: ForestPlotProps) {
  const chartData = data.effects.map((e, idx) => ({
    y: idx,
    x: e.effect,
    errorX: [e.effect - e.ci_lower, e.ci_upper - e.effect],
    center: e.center,
    isReference: e.is_reference,
    ciLower: e.ci_lower,
    ciUpper: e.ci_upper,
  }));

  const ticks = data.effects.map((_, i) => i);
  const centerNames = data.effects.map((e) => e.center);

  return (
    <div>
      {!data.converged && (
        <p className="text-amber-600 text-xs mb-2">
          Model did not converge. Estimates may be unreliable.
        </p>
      )}
      <ResponsiveContainer width="100%" height={Math.max(250, data.effects.length * 50 + 60)}>
        <ScatterChart margin={{ top: 10, right: 30, bottom: 10, left: 20 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            type="number"
            dataKey="x"
            name="Effect"
            className="text-xs"
            label={{ value: "Effect Size", position: "insideBottom", offset: -5, className: "text-[10px] fill-muted-foreground" }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Center"
            domain={[-0.5, data.effects.length - 0.5]}
            ticks={ticks}
            tickFormatter={(value: number) => centerNames[value] ?? ""}
            className="text-xs"
            width={140}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "hsl(var(--popover))",
              border: "1px solid hsl(var(--border))",
              borderRadius: "0.375rem",
              fontSize: "0.75rem",
            }}
            formatter={(_value: number, name: string, props: { payload?: { center?: string; x?: number; ciLower?: number; ciUpper?: number } }) => {
              const p = props.payload;
              if (name === "x" && p) {
                return [
                  `${p.x?.toFixed(3)} [${p.ciLower?.toFixed(3)}, ${p.ciUpper?.toFixed(3)}]`,
                  p.center,
                ];
              }
              return [_value, name];
            }}
          />
          <ReferenceLine x={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3" />
          <Scatter
            data={chartData}
            fill="hsl(217, 91%, 60%)"
            shape="circle"
          >
            <ErrorBar
              dataKey="errorX"
              direction="x"
              width={4}
              strokeWidth={2}
              stroke="hsl(var(--foreground))"
            />
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
