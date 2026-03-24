import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import { PricePoint } from "../types";

interface Props {
  history: PricePoint[];
  lowestPrice: number | null;
  currentEstimate: number | null;
}

function formatSEK(value: number) {
  return `${new Intl.NumberFormat("sv-SE").format(value)} kr`;
}

export function PriceHistoryChart({ history, lowestPrice, currentEstimate }: Props) {
  if (!history || history.length === 0) return null;

  const data = history.map((p) => ({
    date: p.date.slice(0, 7), // YYYY-MM
    price: p.price,
  }));

  const allPrices = data.map((d) => d.price);
  const minY = Math.floor(Math.min(...allPrices) * 0.9 / 100) * 100;
  const maxY = Math.ceil(Math.max(...allPrices) * 1.1 / 100) * 100;

  return (
    <div className="space-y-2">
      <h3
        className="uppercase"
        style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px" }}
      >
        NYPRISHISTORIK (6 MÅN)
      </h3>
      <div className="h-40 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <XAxis
              dataKey="date"
              tick={{ fill: "#8A8578", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              domain={[minY, maxY]}
              tick={{ fill: "#8A8578", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
              width={32}
            />
            <Tooltip
              contentStyle={{ background: "#FFFFFF", border: "1px solid #E8E4DB", borderRadius: 8 }}
              labelStyle={{ color: "#8A8578" }}
              itemStyle={{ color: "#2C2A25" }}
              formatter={(v) => [formatSEK(Number(v)), "Pris"]}
            />
            {lowestPrice && (
              <ReferenceLine
                y={lowestPrice}
                stroke="#d4a017"
                strokeDasharray="4 2"
                label={{ value: "Lägst", fill: "#d4a017", fontSize: 10, position: "insideTopRight" }}
              />
            )}
            {currentEstimate && (
              <ReferenceLine
                y={currentEstimate}
                stroke="#34a873"
                strokeDasharray="4 2"
                label={{ value: "Estimat", fill: "#34a873", fontSize: 10, position: "insideBottomRight" }}
              />
            )}
            <Line
              type="monotone"
              dataKey="price"
              stroke="#2C2A25"
              strokeWidth={2}
              dot={{ fill: "#2C2A25", r: 3 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
