// Recharts wrappers with one consistent look. Every chart takes live numbers
// from the API; nothing is generated in the browser.
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export const COLORS = {
  brand: '#1f4aa8',
  brandSoft: '#9db3e3',
  accent: '#f07c1b',
  violet: '#7c3aed',
  green: '#059669',
  amber: '#d97706',
  red: '#dc2626',
  slate: '#94a3b8',
  sky: '#0284c7',
}

export const PRIORITY_COLORS = { Low: COLORS.slate, Medium: COLORS.sky, High: COLORS.amber, Critical: COLORS.red }

const axis = { fontSize: 11, fill: '#64748b' }
const tooltipStyle = {
  contentStyle: { borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12, boxShadow: '0 4px 12px rgb(15 23 42 / 0.08)' },
  cursor: { fill: 'rgb(148 163 184 / 0.12)' },
}

function Empty({ height }) {
  return (
    <div className="grid place-items-center text-sm text-slate-400" style={{ height }}>
      No data yet
    </div>
  )
}

export function HorizontalBars({ data, height = 260, color = COLORS.brand, valueKey = 'count', labelKey = 'label' }) {
  if (!data?.some((d) => d[valueKey] > 0)) return <Empty height={height} />
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        <CartesianGrid horizontal={false} stroke="#f1f5f9" />
        <XAxis type="number" allowDecimals={false} tick={axis} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey={labelKey} tick={axis} width={150} axisLine={false} tickLine={false} />
        <Tooltip {...tooltipStyle} />
        <Bar dataKey={valueKey} name="Complaints" fill={color} radius={[0, 4, 4, 0]} barSize={14} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function Donut({ data, colors, height = 220, centerLabel, centerValue }) {
  const total = data?.reduce((s, d) => s + d.count, 0) ?? 0
  if (!total) return <Empty height={height} />
  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={data} dataKey="count" nameKey="label" innerRadius="62%" outerRadius="88%" paddingAngle={2} stroke="none">
            {data.map((d, i) => (
              <Cell key={d.label} fill={colors?.[d.label] ?? Object.values(COLORS)[i % 9]} />
            ))}
          </Pie>
          <Tooltip {...tooltipStyle} />
          <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
        </PieChart>
      </ResponsiveContainer>
      {centerLabel && (
        <div className="pointer-events-none absolute inset-x-0 top-[38%] text-center">
          <p className="text-xl font-semibold text-slate-900 tabular-nums">{centerValue}</p>
          <p className="text-xs text-slate-500">{centerLabel}</p>
        </div>
      )}
    </div>
  )
}

/** Confidence histogram: bars below the review threshold in violet, above in green. */
export function ConfidenceHistogram({ bins, threshold, height = 220 }) {
  if (!bins?.some((b) => b.count > 0)) return <Empty height={height} />
  const data = bins.map((b) => ({ ...b, label: `${Math.round(b.from * 100)}–${Math.round(b.to * 100)}%` }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ left: -16, right: 8, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="#f1f5f9" />
        <XAxis dataKey="label" tick={{ ...axis, fontSize: 10 }} axisLine={false} tickLine={false} interval={0} angle={-30} textAnchor="end" height={44} />
        <YAxis allowDecimals={false} tick={axis} axisLine={false} tickLine={false} />
        <Tooltip {...tooltipStyle} />
        <Bar dataKey="count" name="Complaints" radius={[4, 4, 0, 0]}>
          {data.map((b) => (
            <Cell key={b.label} fill={threshold != null && b.to <= threshold + 1e-9 ? COLORS.violet : COLORS.green} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function DailyArea({ data, height = 200 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="fillBrand" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={COLORS.brand} stopOpacity={0.25} />
            <stop offset="100%" stopColor={COLORS.brand} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="#f1f5f9" />
        <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} tick={axis} axisLine={false} tickLine={false} />
        <YAxis allowDecimals={false} tick={axis} axisLine={false} tickLine={false} />
        <Tooltip {...tooltipStyle} />
        <Area type="monotone" dataKey="count" name="Submitted" stroke={COLORS.brand} strokeWidth={2} fill="url(#fillBrand)" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/** Grouped bars: one group per label, one bar per series. */
export function GroupedBars({ data, series, height = 280, percent = false, labelKey = 'label' }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ left: -8, right: 8, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="#f1f5f9" />
        <XAxis dataKey={labelKey} tick={{ ...axis, fontSize: 10 }} interval={0} axisLine={false} tickLine={false} height={48} angle={-20} textAnchor="end" />
        <YAxis tick={axis} axisLine={false} tickLine={false} domain={percent ? [0, 1] : undefined} tickFormatter={percent ? (v) => `${Math.round(v * 100)}%` : undefined} />
        <Tooltip {...tooltipStyle} formatter={percent ? (v) => `${(v * 100).toFixed(1)}%` : undefined} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
        {series.map((s) => (
          <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={[3, 3, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Coverage / selective-accuracy curve against the threshold, with the chosen threshold marked. */
export function ThresholdCurve({ data, threshold, height = 260 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ left: -8, right: 12, top: 8, bottom: 0 }}>
        <CartesianGrid stroke="#f1f5f9" />
        <XAxis dataKey="threshold" type="number" domain={[0.05, 0.95]} tick={axis} tickFormatter={(v) => v.toFixed(1)} />
        <YAxis domain={[0, 1]} tick={axis} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
        <Tooltip {...tooltipStyle} formatter={(v) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)} labelFormatter={(v) => `Threshold ${v}`} />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
        <ReferenceLine x={threshold} stroke={COLORS.accent} strokeDasharray="4 3" label={{ value: `chosen ${threshold}`, fontSize: 11, fill: COLORS.accent, position: 'insideTopRight' }} />
        <Line dataKey="category_selective_accuracy" name="Category correct (auto cases)" stroke={COLORS.brand} dot={false} strokeWidth={2} />
        <Line dataKey="priority_selective_accuracy" name="Priority correct (auto cases)" stroke={COLORS.violet} dot={false} strokeWidth={2} />
        <Line dataKey="joint_coverage" name="Share handled automatically" stroke={COLORS.green} dot={false} strokeWidth={2} strokeDasharray="5 3" />
      </LineChart>
    </ResponsiveContainer>
  )
}
