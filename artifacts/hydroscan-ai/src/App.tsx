import { useEffect, useMemo, useState, type ReactNode, type ChangeEvent, type FormEvent } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import {
  Activity, ArrowDownToLine, ArrowRight, BookOpen, Check, ChevronDown,
  CircleAlert, CircleHelp, Clock3, Database, Droplets, FileImage, FileText,
  Gauge, Layers3, MapPinned, Menu, Radio, Satellite, ScanLine, Search, ShieldCheck,
  SlidersHorizontal, Sparkles, Upload, Waves, X,
} from 'lucide-react';
import {
  useHealthCheck, getHealthCheckQueryKey, useGetOverview, getGetOverviewQueryKey,
  useListAnalyses, getListAnalysesQueryKey, useCreateAnalysis, useGetAnalysis,
  getGetAnalysisQueryKey, useUpdateAnalysisThreshold, useGetAnalysisAsset,
  getGetAnalysisAssetQueryKey, useExportAnalysisCsv, getExportAnalysisCsvQueryKey,
  useDownloadAnalysisReport, getDownloadAnalysisReportQueryKey, useGetTrends,
  getGetTrendsQueryKey, useGetSystemHealth, getGetSystemHealthQueryKey,
} from '@workspace/api-client-react';
import type { Analysis, AnalysisSummary, TrendPoint } from '@workspace/api-client-react';
import { Link, Route, Switch, useLocation, useParams, Router as WouterRouter } from 'wouter';
import L from 'leaflet';
import { ImageOverlay, MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import NotFound from '@/pages/not-found';
import './index.css';

const queryClient = new QueryClient();
const ASSETS = ['rgb.png', 'ndwi.png', 'mask.png', 'mask-raw.png', 'comparison.png'] as const;
type AssetName = typeof ASSETS[number];

const navItems = [
  { href: '/', label: 'Overview', icon: Gauge },
  { href: '/explorer', label: 'Image explorer', icon: ScanLine },
  { href: '/map', label: 'Map view', icon: MapPinned },
  { href: '/history', label: 'Analysis history', icon: Clock3 },
  { href: '/methodology', label: 'Methodology', icon: BookOpen },
  { href: '/health', label: 'System health', icon: Activity },
];

function AppShell({ children }: { children: ReactNode }) {
  const [path] = useLocation();
  const [mobileNav, setMobileNav] = useState(false);
  const current = navItems.find((item) => item.href === path)?.label ?? (path.startsWith('/analysis/') ? 'Analysis detail' : 'HydroScan');
  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
      <Link href="/" className="brand" data-testid="link-brand">
        <span className="brand-mark"><Waves size={20} strokeWidth={1.8} /></span>
        <span className="brand-name">hydroscan<span> / AI</span></span>
      </Link>
      <div className="workspace-label">FIELD NOTEBOOK <span>01</span></div>
      <nav className="side-nav" aria-label="Main navigation">
        {navItems.map(({ href, label, icon: Icon }) => <Link key={href} href={href}
          data-testid={`link-nav-${label.toLowerCase().replaceAll(' ', '-')}`}
          className={`nav-link ${path === href ? 'nav-active' : ''}`} onClick={() => setMobileNav(false)}>
          <Icon size={17} strokeWidth={1.8} /><span>{label}</span>{path === href && <span className="nav-mark" />}
        </Link>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-status"><span className="status-dot" /><span>RESEARCH MODE</span><span className="mono">v0.8</span></div>
        <p>Built for careful interpretation of Earth observation data.</p>
      </div>
    </aside>
    {mobileNav && <button aria-label="Close navigation" className="mobile-scrim" onClick={() => setMobileNav(false)} />}
    <main className="main-frame">
      <header className="topbar">
        <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMobileNav(true)}><Menu size={20} /></button>
        <div className="crumb"><span>HYDROSCAN</span><span className="crumb-slash">/</span><b>{current}</b></div>
        <div className="topbar-right"><span className="region-indicator"><span className="status-dot" /> GODAVARI BASIN</span><span className="topbar-divider" /><span className="student-badge">STUDENT WORKSPACE</span></div>
      </header>
      <div className="page-content">{children}</div>
    </main>
  </div>;
}

function PageTitle({ eyebrow, title, subtitle, action }: { eyebrow: string; title: string; subtitle: string; action?: ReactNode }) {
  return <div className="page-title">
    <div><div className="eyebrow"><span className="eyebrow-line" />{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></div>
    {action && <div className="title-action">{action}</div>}
  </div>;
}

function LoadingPanel({ label = 'Reading the observation archive' }: { label?: string }) {
  return <div className="loading-panel" aria-label="Loading"><span className="loading-bar" /><span className="loading-bar short" /><span className="loading-label">{label}</span></div>;
}

function QueryError({ retry }: { retry: () => void }) {
  return <div className="error-panel"><CircleAlert size={20} /><div><b>We could not reach the archive.</b><p>Check the service connection, then try again.</p><button className="text-button" onClick={retry}>Retry request <ArrowRight size={14} /></button></div></div>;
}

function EmptyState({ title, copy, action }: { title: string; copy: string; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-orbit"><Waves size={23} /></div><h3>{title}</h3><p>{copy}</p>{action}</div>;
}

function formatDate(value?: string | null) {
  if (!value) return 'Undated';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
}
function pct(value: number) { return `${Number(value).toFixed(1)}%`; }
function fmt(value: number) { return new Intl.NumberFormat('en').format(value); }

function ModeChip({ mode }: { mode: AnalysisSummary['mode'] }) {
  return <span className={`mode-chip ${mode === 'satellite' ? 'mode-real' : 'mode-demo'}`}><span />{mode === 'satellite' ? 'Satellite' : 'Demonstration'}</span>;
}

function Dashboard() {
  const overview = useGetOverview({ query: { queryKey: getGetOverviewQueryKey() } });
  const trends = useGetTrends({ query: { queryKey: getGetTrendsQueryKey() } });
  const analyses = useListAnalyses({ query: { queryKey: getListAnalysesQueryKey() } });
  const overviewData = overview.data;
  const recent = (analyses.data ?? []).slice(0, 4);
  return <div className="page-wrap">
    <PageTitle eyebrow="OBSERVATION DESK · GODAVARI / NASHIK" title="Read the river, carefully." subtitle="A student research workspace for inspecting satellite-derived water signals — with evidence and limits kept in view."
      action={<Link href="/explorer" className="button button-primary"><ScanLine size={16} /> Open image explorer <ArrowRight size={15} /></Link>} />
    {overview.isLoading ? <LoadingPanel /> : overview.isError ? <QueryError retry={() => overview.refetch()} /> :
      <section className="overview-hero">
        <div className="hero-copy">
          <div className="hero-kicker"><span className="live-pip" /> {overviewData?.dataModeLabel ?? 'OBSERVATION SUMMARY'}</div>
          <h2>Water is a signal.<br /><em>Context is the finding.</em></h2>
          <p>Compare visible patterns, inspect the calculation, and keep every claim proportional to the pixels behind it.</p>
          <div className="hero-foot"><span><Satellite size={15} /> Sentinel-2 band workflow</span><span className="hero-sep" /><span>Central Maharashtra</span></div>
        </div>
        <div className="hero-visual" aria-label="Stylized satellite image of river channels">
          <div className="visual-coordinate">SCHEMATIC · NOT GEOREFERENCED</div>
          <div className="terrain-grid" />
          <svg className="river-art" viewBox="0 0 550 330" role="img" aria-label="Abstract braided river channel">
            <path className="river-shadow" d="M-20 215 C70 183 75 92 160 111 C227 126 225 217 312 189 C393 164 367 68 450 71 C497 73 519 116 580 92" />
            <path className="river-main" d="M-20 205 C72 174 82 84 164 104 C234 120 231 206 314 180 C393 155 378 63 453 62 C506 61 527 106 580 82" />
            <path className="river-branch" d="M153 109 C112 154 165 193 200 230 C229 261 210 301 178 344" />
            <path className="river-branch second" d="M316 181 C352 209 346 245 316 281 C300 301 306 321 323 342" />
            <path className="contour" d="M0 72 C93 21 170 55 235 40 S388 12 551 22M4 278 C89 250 133 276 189 258 S292 236 350 255 466 302 556 266" />
            <circle cx="316" cy="180" r="6" className="observation-point" /><circle cx="316" cy="180" r="14" className="point-ring" />
          </svg>
          <div className="visual-stamp"><span>FIELD AREA</span><b>Nashik district</b><small>Godavari headwaters</small></div>
        </div>
      </section>}
    <section className="metric-grid">
      <Metric label="Saved analyses" value={overviewData ? fmt(overviewData.analysisCount) : '—'} note="All observation modes" icon={<Layers3 size={17} />} />
      <Metric label="Flagged regions" value={overviewData ? fmt(overviewData.totalFlaggedRegions) : '—'} note="Review candidates, not diagnoses" icon={<CircleAlert size={17} />} />
      <Metric label="Dated real observations" value={overviewData ? fmt(overviewData.compatibleDatedObservations) : '—'} note="Comparable satellite dates" icon={<Radio size={17} />} />
      <Metric label="Latest coverage" value={overviewData?.latestAnalysis ? pct(overviewData.latestAnalysis.waterCoveragePercent) : '—'} note={overviewData?.latestAnalysis?.areaLabel ?? 'Awaiting first analysis'} icon={<Droplets size={17} />} />
    </section>
    <div className="dashboard-columns">
      <section className="panel trend-panel">
        <div className="panel-heading"><div><div className="eyebrow">TEMPORAL CONTEXT</div><h2>Water coverage over time</h2></div><span className="chart-badge"><span className="chart-dot" /> Satellite dates</span></div>
        {trends.isLoading ? <LoadingPanel label="Checking dated observations" /> : trends.isError ? <QueryError retry={() => trends.refetch()} /> :
          trends.data?.available && trends.data.observations.length > 1 ?
            <TrendChart observations={trends.data.observations} /> :
            <div className="trend-empty"><div className="mini-chart"><span /><span /><span /><span /><span /><span /></div><p>{trends.data?.message ?? 'No compatible dated observations are available yet.'}</p><small>Demonstration runs are excluded from this comparison.</small></div>}
        <div className="panel-footnote"><CircleHelp size={14} /> Only compatible, dated satellite analyses can support this comparison.</div>
      </section>
      <section className="panel latest-panel">
        <div className="panel-heading"><div><div className="eyebrow">MOST RECENT</div><h2>Latest observation</h2></div><ArrowRight size={16} className="muted-icon" /></div>
        {overviewData?.latestAnalysis ? <LatestCard item={overviewData.latestAnalysis} /> :
          <EmptyState title="No observation yet" copy="Start with a demonstration scene or bring your own Sentinel-2 bands." action={<Link href="/explorer" className="text-button">Start an analysis <ArrowRight size={14} /></Link>} />}
      </section>
    </div>
    <section className="panel recent-panel">
      <div className="panel-heading"><div><div className="eyebrow">NOTEBOOK</div><h2>Recent analyses</h2></div><Link href="/history" className="text-button">View all <ArrowRight size={14} /></Link></div>
      {analyses.isLoading ? <LoadingPanel /> : analyses.isError ? <QueryError retry={() => analyses.refetch()} /> : recent.length ?
        <div className="analysis-list">{recent.map((item) => <AnalysisRow key={item.id} item={item} />)}</div> :
        <EmptyState title="The notebook is clear" copy="Your saved analyses will appear here once a scene has been processed." action={<Link href="/explorer" className="button button-secondary">Explore imagery</Link>} />}
    </section>
    <EvidenceNote />
  </div>;
}

function Metric({ label, value, note, icon }: { label: string; value: string; note: string; icon: ReactNode }) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><span className="metric-icon">{icon}</span></div><strong>{value}</strong><small>{note}</small></div>;
}

function LatestCard({ item }: { item: AnalysisSummary }) {
  return <Link href={`/analysis/${item.id}`} className="latest-link">
    <div className="latest-meta"><ModeChip mode={item.mode} /><span>{formatDate(item.observationDate ?? item.createdAt)}</span></div>
    <h3>{item.areaLabel}</h3>
    <div className="latest-number">{pct(item.waterCoveragePercent)}<span>candidate water coverage</span></div>
    <div className="coverage-track"><span style={{ width: `${Math.max(1, Math.min(100, item.waterCoveragePercent))}%` }} /></div>
    <div className="latest-detail"><span>{fmt(item.candidateWaterPixels)} candidate pixels</span><ArrowRight size={15} /></div>
    <p className="quality-note">{item.dataQualityNote}</p>
  </Link>;
}

function TrendChart({ observations }: { observations: TrendPoint[] }) {
  const values = observations.map((point) => point.waterCoveragePercent);
  const min = Math.min(...values); const max = Math.max(...values);
  const points = observations.map((point, index) => `${(index / Math.max(1, observations.length - 1)) * 100},${88 - ((point.waterCoveragePercent - min) / (max - min || 1)) * 64}`).join(' ');
  return <div className="trend-chart">
    <div className="chart-values"><span>{pct(max)}</span><span>{pct(min)}</span></div>
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Water coverage trend chart">
      <line x1="0" y1="24" x2="100" y2="24" className="gridline" /><line x1="0" y1="56" x2="100" y2="56" className="gridline" /><line x1="0" y1="88" x2="100" y2="88" className="gridline" />
      <polyline points={points} className="trend-line" /><polygon points={`0,100 ${points} 100,100`} className="trend-fill" />
      {observations.map((point, index) => <circle key={point.analysisId} cx={(index / Math.max(1, observations.length - 1)) * 100} cy={88 - ((point.waterCoveragePercent - min) / (max - min || 1)) * 64} r="1.4" className="trend-point" />)}
    </svg>
    <div className="chart-dates"><span>{formatDate(observations[0]?.observationDate)}</span><span>{formatDate(observations[observations.length - 1]?.observationDate)}</span></div>
  </div>;
}

function AnalysisRow({ item }: { item: AnalysisSummary }) {
  return <Link href={`/analysis/${item.id}`} className="analysis-row" data-testid={`row-analysis-${item.id}`}>
    <span className="row-mark"><Waves size={17} /></span><span className="row-name"><b>{item.areaLabel}</b><small>{formatDate(item.observationDate ?? item.createdAt)} · {item.anomalyCount} flagged regions</small></span>
    <ModeChip mode={item.mode} /><span className="row-coverage">{pct(item.waterCoveragePercent)}<small>coverage</small></span><ArrowRight size={16} className="row-arrow" />
  </Link>;
}

function EvidenceNote() {
  return <div className="evidence-note"><ShieldCheck size={17} /><div><b>Interpretation before inference</b><span>Candidate water is an index-derived mask, not a verified water boundary. Flagged regions warrant review — not a pollution claim.</span></div><Link href="/methodology">How to explain this <ArrowRight size={14} /></Link></div>;
}

function Explorer() {
  const [mode, setMode] = useState<'demo' | 'upload'>('demo');
  const [areaLabel, setAreaLabel] = useState('Godavari River, Nashik');
  const [observationDate, setObservationDate] = useState('');
  const [threshold, setThreshold] = useState(-0.05);
  const [files, setFiles] = useState<Record<string, File | null>>({ blue: null, green: null, red: null, nir: null });
  const [error, setError] = useState('');
  const create = useCreateAnalysis();
  const qc = useQueryClient();
  const [, setLocation] = useLocation();
  const handleFile = (band: string) => (event: ChangeEvent<HTMLInputElement>) => setFiles((current) => ({ ...current, [band]: event.target.files?.[0] ?? null }));
  const submit = (event: FormEvent) => {
    event.preventDefault(); setError('');
    if (mode === 'upload' && Object.values(files).some((file) => !file)) { setError('Choose one file for each required band: blue, green, red and near-infrared.'); return; }
    create.mutate({ data: {
      mode: mode === 'demo' ? 'demo' : 'upload',
      areaLabel: areaLabel.trim() || 'Godavari study area',
      ...(observationDate ? { observationDate } : {}),
      ndwiThreshold: threshold,
      ...(mode === 'upload' ? { blue: files.blue!, green: files.green!, red: files.red!, nir: files.nir! } : {}),
    } }, {
      onSuccess: (analysis) => {
        void qc.invalidateQueries({ queryKey: getGetOverviewQueryKey() });
        void qc.invalidateQueries({ queryKey: getListAnalysesQueryKey() });
        void qc.invalidateQueries({ queryKey: getGetTrendsQueryKey() });
        setLocation(`/analysis/${analysis.id}`);
      },
      onError: () => setError('The analysis could not be created. Check that each uploaded band is readable and try again.'),
    });
  };
  const allSelected = Object.values(files).every(Boolean);
  return <div className="page-wrap">
    <PageTitle eyebrow="IMAGE EXPLORER · INPUT" title="Bring a scene into focus." subtitle="Start with a clearly labeled synthetic example, or inspect a compatible four-band Sentinel-2 scene." />
    <div className="explorer-layout">
      <form className="panel explorer-form" onSubmit={submit}>
        <div className="panel-heading"><div><div className="eyebrow">01 / CONFIGURE</div><h2>Observation setup</h2></div><SlidersHorizontal size={18} className="muted-icon" /></div>
        <div className="mode-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={mode === 'demo'} className={mode === 'demo' ? 'mode-tab selected' : 'mode-tab'} onClick={() => setMode('demo')}><Sparkles size={15} /> Demonstration</button>
          <button type="button" role="tab" aria-selected={mode === 'upload'} className={mode === 'upload' ? 'mode-tab selected' : 'mode-tab'} onClick={() => setMode('upload')}><Upload size={15} /> Upload bands</button>
        </div>
        <label className="field-label" htmlFor="area-label">Study area name</label>
        <input id="area-label" className="field-input" value={areaLabel} onChange={(event) => setAreaLabel(event.target.value)} maxLength={120} data-testid="input-area-label" />
        <label className="field-label" htmlFor="obs-date">Observation date <span>optional</span></label>
        <input id="obs-date" type="date" className="field-input" value={observationDate} onChange={(event) => setObservationDate(event.target.value)} data-testid="input-observation-date" />
        {mode === 'upload' && <div className="upload-band-grid">
          {(['blue', 'green', 'red', 'nir'] as const).map((band) => <label key={band} className="file-pick">
            <span className="file-band">{band === 'nir' ? 'NIR' : band.toUpperCase()}<small>{band === 'green' ? 'B03' : band === 'blue' ? 'B02' : band === 'red' ? 'B04' : 'B08'}</small></span>
            <span className={`file-choose ${files[band] ? 'has-file' : ''}`}>{files[band]?.name ?? 'Choose raster'}<Upload size={14} /></span>
            <input type="file" accept=".tif,.tiff,.jp2,image/*" onChange={handleFile(band)} data-testid={`input-band-${band}`} />
          </label>)}
          <p className="field-hint">All four bands must share compatible dimensions and alignment. GeoTIFF or image rasters accepted by the processor.</p>
        </div>}
        <div className="threshold-block">
          <div className="threshold-heading"><label className="field-label" htmlFor="ndwi-threshold">NDWI threshold</label><span className="threshold-value mono">{threshold.toFixed(2)}</span></div>
          <input id="ndwi-threshold" type="range" min="-1" max="1" step="0.01" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} data-testid="input-ndwi-threshold" />
          <div className="range-labels"><span>−1.00 · permissive</span><span>+1.00 · restrictive</span></div>
          <p className="field-hint">Pixels above this cutoff are marked as candidate water. This changes the mask, not the underlying observation.</p>
        </div>
        {error && <div className="inline-error"><CircleAlert size={15} />{error}</div>}
        <button className="button button-primary button-wide" type="submit" disabled={create.isPending || (mode === 'upload' && !allSelected)} data-testid="button-run-analysis">
          {create.isPending ? <><span className="button-spinner" /> Processing scene…</> : <><ScanLine size={16} /> Run {mode === 'demo' ? 'demonstration' : 'satellite'} analysis <ArrowRight size={15} /></>}
        </button>
        <div className="submit-note"><ShieldCheck size={14} /> {mode === 'demo' ? 'Synthetic values are labeled and excluded from real-observation trends.' : 'Uploaded imagery is analyzed as provided; results need contextual review.'}</div>
      </form>
      <div className="explorer-aside">
        <section className="panel scene-panel">
          <div className="panel-heading"><div><div className="eyebrow">02 / INSPECT</div><h2>Layers after processing</h2></div><Layers3 size={18} className="muted-icon" /></div>
          <div className="layer-preview">
            <div className="preview-topline"><span>PROCESSING SEQUENCE</span><span>4 OUTPUTS</span></div>
            {[
              ['01', 'Natural colour composite', 'B04 · B03 · B02'],
              ['02', 'NDWI index surface', '(Green − NIR) / (Green + NIR)'],
              ['03', 'Thresholded candidate mask', `NDWI > ${threshold.toFixed(2)}`],
            ].map((layer) => <div className="layer-item" key={layer[0]}><span className="layer-number">{layer[0]}</span><div><b>{layer[1]}</b><small>{layer[2]}</small></div><ChevronDown size={14} /></div>)}
            <div className="preview-canvas"><div className="preview-land"><span className="river-thread" /></div><div className="preview-caption"><span>Scene preview appears after analysis</span><span className="preview-cross" /></div></div>
          </div>
        </section>
        <div className="caution-card"><div className="caution-icon"><CircleHelp size={17} /></div><div><b>What this calculation supports</b><p>A reproducible spectral screening step. It does not confirm a waterline, water quality, or the cause of a flagged pattern.</p><Link href="/methodology" className="text-button">Read assumptions <ArrowRight size={13} /></Link></div></div>
      </div>
    </div>
  </div>;
}

function AnalysisDetail() {
  const params = useParams<{ analysisId: string }>();
  const id = params.analysisId ?? '';
  const analysis = useGetAnalysis(id, { query: { enabled: !!id, queryKey: getGetAnalysisQueryKey(id) } });
  if (analysis.isLoading) return <div className="page-wrap"><LoadingPanel label="Loading analysis and image assets" /></div>;
  if (analysis.isError || !analysis.data) return <div className="page-wrap"><PageTitle eyebrow="ANALYSIS / UNAVAILABLE" title="This analysis is out of reach." subtitle="It may have been removed, or the archive may be temporarily unavailable." /><QueryError retry={() => analysis.refetch()} /></div>;
  return <AnalysisView analysis={analysis.data} />;
}

function AnalysisView({ analysis }: { analysis: Analysis }) {
  const [asset, setAsset] = useState<AssetName>('rgb.png');
  const [threshold, setThreshold] = useState(analysis.threshold);
  const [savedNotice, setSavedNotice] = useState('');
  const update = useUpdateAnalysisThreshold();
  const qc = useQueryClient();
  const image = useGetAnalysisAsset(analysis.id, asset, { query: { queryKey: getGetAnalysisAssetQueryKey(analysis.id, asset) } });
  const objectUrl = useMemo(() => image.data ? URL.createObjectURL(image.data) : '', [image.data]);
  const saveThreshold = () => update.mutate({ analysisId: analysis.id, data: { threshold } }, {
    onSuccess: (next) => {
      qc.setQueryData(getGetAnalysisQueryKey(analysis.id), next);
      void qc.invalidateQueries({ queryKey: getGetAnalysisQueryKey(analysis.id) });
      void qc.invalidateQueries({ queryKey: getListAnalysesQueryKey() });
      setSavedNotice('Threshold updated. Candidate mask recalculated.');
    },
    onError: () => setSavedNotice('Threshold could not be updated. Please try again.'),
  });
  return <div className="page-wrap">
    <PageTitle eyebrow={`ANALYSIS RECORD · ${analysis.mode === 'satellite' ? 'SATELLITE' : 'DEMONSTRATION'}`} title={analysis.areaLabel} subtitle={`${analysis.sourceLabel} · ${analysis.width} × ${analysis.height} pixels · ${formatDate(analysis.observationDate ?? analysis.createdAt)}`}
      action={<DownloadActions analysisId={analysis.id} />} />
    <div className="result-summary">
      <div className="result-lead"><ModeChip mode={analysis.mode} /><span className="result-crs">{analysis.georeferenced ? `GEOREFERENCED · ${analysis.crs ?? 'CRS recorded'}` : 'PIXEL COORDINATES ONLY'}</span></div>
      <div className="result-metrics">
        <div><small>Candidate water coverage</small><b>{pct(analysis.waterCoveragePercent)}</b><span>Threshold-derived estimate</span></div>
        <div><small>Valid pixels</small><b>{pct(analysis.validPixelPercent)}</b><span>{fmt(analysis.validPixels)} of {fmt(analysis.totalPixels)}</span></div>
        <div><small>Flagged regions</small><b>{analysis.anomalyCount}</b><span>Review candidates</span></div>
        <div><small>NDWI threshold</small><b>{analysis.threshold.toFixed(2)}</b><span>Current mask cutoff</span></div>
      </div>
      <div className="result-quality"><CircleHelp size={15} />{analysis.dataQualityNote}</div>
    </div>
    <div className="results-grid">
      <section className="panel image-panel">
        <div className="panel-heading"><div><div className="eyebrow">DERIVED IMAGE ASSETS</div><h2>Layer inspection</h2></div><span className="image-dimensions mono">{analysis.width} × {analysis.height}</span></div>
        <div className="asset-tabs">{ASSETS.map((item) => <button key={item} className={`asset-tab ${asset === item ? 'active' : ''}`} onClick={() => setAsset(item)} data-testid={`tab-asset-${item.replace('.png', '')}`}>{assetLabel(item)}</button>)}</div>
        <div className="asset-viewer">
          {image.isLoading ? <div className="asset-loading"><span className="loading-bar" /><span>Loading image asset</span></div> : image.isError ? <div className="asset-error"><FileImage size={26} /><span>Image asset could not be loaded.</span><button className="text-button" onClick={() => image.refetch()}>Retry</button></div> : objectUrl ? <img src={objectUrl} alt={`${assetLabel(asset)} derived analysis`} /> : <div className="asset-error"><FileImage size={24} /><span>No preview available for this asset.</span></div>}
          <div className="asset-overlay-label"><span className="status-dot" />{assetLabel(asset).toUpperCase()}</div>
        </div>
        <p className="asset-caption">Derived visual from the provided bands. Display stretch and classification are for inspection, not ground truth.</p>
      </section>
      <section className="panel threshold-panel">
        <div className="panel-heading"><div><div className="eyebrow">SENSITIVITY CHECK</div><h2>Adjust the cutoff</h2></div><SlidersHorizontal size={17} className="muted-icon" /></div>
        <p className="body-copy">Move the threshold to see how the candidate mask responds. The analysis is recalculated when you apply the change.</p>
        <div className="threshold-control"><div><span>NDWI threshold</span><b className="mono">{threshold.toFixed(2)}</b></div><input aria-label="NDWI threshold" type="range" min="-1" max="1" step="0.01" value={threshold} onChange={(event) => { setThreshold(Number(event.target.value)); setSavedNotice(''); }} data-testid="input-result-threshold" /><div className="range-labels"><span>More permissive</span><span>More restrictive</span></div></div>
        <button className="button button-secondary button-wide" onClick={saveThreshold} disabled={update.isPending || threshold === analysis.threshold} data-testid="button-update-threshold">{update.isPending ? 'Recalculating…' : 'Apply threshold'} <ArrowRight size={15} /></button>
        {savedNotice && <p className="notice-line">{savedNotice}</p>}
        <div className="threshold-ethics"><ShieldCheck size={15} /><span>Thresholds alter which pixels qualify. A higher candidate percentage is not evidence of more water on the ground.</span></div>
      </section>
    </div>
    <section className="panel flagged-panel">
      <div className="panel-heading"><div><div className="eyebrow">REGION REVIEW</div><h2>Flagged regions <span className="count-badge">{analysis.anomalies.length}</span></h2></div><span className="plain-label">Priority is a screening score</span></div>
      {analysis.anomalies.length ? <div className="anomaly-list">{analysis.anomalies.map((region) => <div className="anomaly-row" key={region.id}>
        <div className={`priority-mark priority-${region.priority}`}><CircleAlert size={16} /></div>
        <div className="anomaly-copy"><div><b>{region.priority} review priority</b><span className="score-tag">score {Number(region.score).toFixed(2)}</span></div><p>{region.explanation}</p><small>{region.locationType === 'geographic' && region.coordinates ? `Coordinates ${region.coordinates.map((n) => n.toFixed(5)).join(', ')}` : `Pixel location · row ${region.row}, column ${region.column}`}</small></div>
        <span className="pixel-count">{fmt(region.pixels)}<small>pixels</small></span>
      </div>)}</div> : <EmptyState title="No regions were flagged" copy="No regions crossed the screening criteria for this analysis." />}
      <div className="plain-caution"><CircleHelp size={14} /> Priority labels are not pollution measurements and do not identify a cause.</div>
    </section>
    <section className="limitations-grid">
      <div className="panel limitation-card"><div className="eyebrow">LIMITATIONS TO CARRY FORWARD</div><h2>Claims stay inside the evidence.</h2>
        {analysis.limitations.length ? <ul>{analysis.limitations.map((item, i) => <li key={`${i}-${item}`}><span>{String(i + 1).padStart(2, '0')}</span>{item}</li>)}</ul> : <p className="body-copy">A spectral index is a screening proxy. Verify interpretation against scene context and independent evidence.</p>}
      </div>
      <div className="panel method-card"><div className="eyebrow">CALCULATION</div><h2>NDWI</h2><div className="formula-large">(Green − NIR)<br /><span>──────────────</span><br />(Green + NIR)</div><p>Values above <b>{analysis.threshold.toFixed(2)}</b> are classified as candidate water. Cloud, shadow, built surfaces and mixed pixels can affect the result.</p><Link href="/methodology" className="text-button">Full method notes <ArrowRight size={14} /></Link></div>
    </section>
  </div>;
}

function assetLabel(item: AssetName) {
  return ({ 'rgb.png': 'RGB composite', 'ndwi.png': 'NDWI index', 'mask.png': 'Candidate mask', 'mask-raw.png': 'Raw mask', 'comparison.png': 'Comparison' })[item];
}

function DownloadActions({ analysisId }: { analysisId: string }) {
  const [feedback, setFeedback] = useState('');
  const csv = useExportAnalysisCsv(analysisId, { query: { enabled: false, queryKey: getExportAnalysisCsvQueryKey(analysisId) } });
  const report = useDownloadAnalysisReport(analysisId, { query: { enabled: false, queryKey: getDownloadAnalysisReportQueryKey(analysisId) } });
  const download = async (kind: 'csv' | 'report') => {
    setFeedback('');
    const query = kind === 'csv' ? csv : report;
    const result = await query.refetch();
    if (result.data instanceof Blob) {
      const url = URL.createObjectURL(result.data);
      const link = document.createElement('a');
      link.href = url; link.download = kind === 'csv' ? `hydroscan-${analysisId}.csv` : `hydroscan-${analysisId}.pdf`;
      link.click(); URL.revokeObjectURL(url);
      setFeedback(`${kind.toUpperCase()} export downloaded.`);
    } else setFeedback(`Could not prepare ${kind.toUpperCase()} export.`);
  };
  return <div className="download-actions"><button className="button button-secondary" onClick={() => void download('csv')} disabled={csv.isFetching} data-testid="button-export-csv"><ArrowDownToLine size={15} />{csv.isFetching ? 'Preparing…' : 'Export CSV'}</button><button className="button button-quiet" onClick={() => void download('report')} disabled={report.isFetching} data-testid="button-download-report"><FileText size={15} />PDF report</button>{feedback && <span className="download-feedback">{feedback}</span>}</div>;
}

function MapPage() {
  const overview = useGetOverview({ query: { queryKey: getGetOverviewQueryKey() } });
  const id = overview.data?.latestAnalysis?.id ?? '';
  const analysis = useGetAnalysis(id, { query: { enabled: !!id, queryKey: getGetAnalysisQueryKey(id) } });
  return <div className="page-wrap">
    <PageTitle eyebrow="SPATIAL VIEW · GODAVARI BASIN" title="Location, with provenance." subtitle="Geographic overlays are only meaningful when the source image carries a valid spatial transform." />
    {overview.isLoading || analysis.isLoading ? <LoadingPanel label="Checking source georeferencing" /> :
      overview.isError ? <QueryError retry={() => overview.refetch()} /> :
      !analysis.data ? <div className="panel map-panel"><EmptyState title="No analysis to locate" copy="Run an analysis first. A map overlay will only be shown if its source contains georeferencing metadata." action={<Link href="/explorer" className="button button-primary">Open image explorer <ArrowRight size={15} /></Link>} /></div> :
      <div className="map-layout">
        <section className="panel map-panel">
          <div className="map-head"><div><div className="eyebrow">LATEST ANALYSIS · {analysis.data.areaLabel.toUpperCase()}</div><h2>{analysis.data.georeferenced ? 'Georeferenced overlay' : 'Pixel-space inspection'}</h2></div><span className={`map-status ${analysis.data.georeferenced ? 'status-good' : 'status-muted'}`}>{analysis.data.georeferenced ? 'TRANSFORM AVAILABLE' : 'NO SPATIAL TRANSFORM'}</span></div>
          {analysis.data.georeferenced ? <div className="map-content"><MapOverlay analysis={analysis.data} /></div> :
            <div className="pixel-map"><div className="pixel-grid" /><div className="pixel-frame"><span className="pixel-cross x1" /><span className="pixel-cross x2" /><span className="pixel-cross x3" /></div><div className="pixel-caption"><span>ROW / COLUMN SPACE</span><b>0, 0</b></div></div>}
          <div className="map-explainer">{analysis.data.georeferenced ? <><MapPinned size={16} /><span>Source CRS: <b>{analysis.data.crs ?? 'Recorded in source metadata'}</b>. Coordinates derive from the image transform; confirm alignment before field use.</span></> : <><CircleHelp size={16} /><span>This source has no georeferencing transform. Regions are shown in pixel coordinates only; no geographic location is inferred.</span></>}</div>
        </section>
        <aside className="panel map-side"><div className="eyebrow">REGION INDEX</div><h2>Flagged locations</h2>
          {analysis.data.anomalies.length ? analysis.data.anomalies.slice(0, 7).map((region) => <div className="map-region" key={region.id}><span className={`region-pin priority-${region.priority}`} /><div><b>{region.priority} review</b><small>{region.locationType === 'geographic' && region.coordinates ? region.coordinates.map((n) => n.toFixed(4)).join(', ') : `row ${region.row} · col ${region.column}`}</small></div></div>) : <p className="body-copy">No flagged regions in this analysis.</p>}
          <div className="map-legend"><span className="legend-dot" /> Flagged region <span className="legend-water" /> Candidate water pixels</div>
        </aside>
      </div>}
    <EvidenceNote />
  </div>;
}

function FitAnalysisBounds({ bounds }: { bounds: L.LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds, { padding: [28, 28], maxZoom: 16 });
  }, [map, bounds]);
  return null;
}

function MapOverlay({ analysis }: { analysis: Analysis }) {
  const geographicBounds = (analysis as Analysis & { geographicBounds?: number[] | null }).geographicBounds;
  const boundsAreValid = Array.isArray(geographicBounds) && geographicBounds.length === 4 &&
    geographicBounds.every((value) => Number.isFinite(value)) &&
    geographicBounds[0] >= -180 && geographicBounds[2] <= 180 &&
    geographicBounds[1] >= -90 && geographicBounds[3] <= 90 &&
    geographicBounds[0] < geographicBounds[2] && geographicBounds[1] < geographicBounds[3];
  const assetUrl = analysis.assets?.mask?.trim() ?? '';
  const canRenderMap = analysis.georeferenced && Boolean(analysis.crs?.trim()) && boundsAreValid && Boolean(assetUrl);
  const west = boundsAreValid ? geographicBounds?.[0] ?? null : null;
  const south = boundsAreValid ? geographicBounds?.[1] ?? null : null;
  const east = boundsAreValid ? geographicBounds?.[2] ?? null : null;
  const north = boundsAreValid ? geographicBounds?.[3] ?? null : null;
  const bounds = useMemo<L.LatLngBoundsExpression | null>(() => {
    if (west === null || south === null || east === null || north === null) return null;
    return [[south, west], [north, east]];
  }, [west, south, east, north]);
  const mask = useGetAnalysisAsset(analysis.id, 'mask.png', {
    query: {
      enabled: canRenderMap,
      queryKey: getGetAnalysisAssetQueryKey(analysis.id, 'mask.png'),
    },
  });
  const [maskUrl, setMaskUrl] = useState('');
  useEffect(() => {
    if (!mask.data) {
      setMaskUrl('');
      return;
    }
    const url = URL.createObjectURL(mask.data);
    setMaskUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [mask.data]);

  if (!canRenderMap || !bounds) {
    return <div className="pixel-map" role="status">
      <div className="pixel-grid" />
      <div className="pixel-frame" />
      <div className="pixel-caption"><span>ROW / COLUMN SPACE</span><b>Geographic overlay unavailable</b></div>
      <div className="map-coordinate-corner">PIXEL COORDINATES ONLY</div>
      <div className="map-mapnote">
        {analysis.georeferenced
          ? 'A geographic view needs a CRS, valid geographic bounds, and a candidate-mask asset URL. No geographic map is shown.'
          : 'This source has no georeferencing transform. Locations remain in pixel coordinates; no geographic position is inferred.'}
      </div>
    </div>;
  }

  const geographicRegions = analysis.anomalies.filter((region) => {
    const coordinates = region.coordinates;
    return region.locationType === 'geographic' &&
      Array.isArray(coordinates) && coordinates.length >= 2 &&
      Number.isFinite(coordinates[0]) && Number.isFinite(coordinates[1]) &&
      coordinates[0] >= -180 && coordinates[0] <= 180 &&
      coordinates[1] >= -90 && coordinates[1] <= 90;
  });

  return <div className="georef-overlay">
    <MapContainer
      className="hydroscan-leaflet"
      style={{ width: '100%', height: '100%', minHeight: 280 }}
      bounds={bounds}
      boundsOptions={{ padding: [28, 28], maxZoom: 16 }}
      scrollWheelZoom
      keyboard
      attributionControl
    >
      <FitAnalysisBounds bounds={bounds} />
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {maskUrl && <ImageOverlay
        url={maskUrl}
        bounds={bounds}
        opacity={0.68}
        alt="Candidate water mask overlay"
      />}
      {geographicRegions.map((region) => {
        const [longitude, latitude] = region.coordinates!;
        const markerColor = region.priority === 'high' ? '#d78078' : region.priority === 'moderate' ? '#d8b56d' : '#81c49c';
        const icon = L.divIcon({
          className: '',
          html: `<span style="display:block;width:16px;height:16px;border:2px solid #eaf4e9;border-radius:50%;background:${markerColor};box-shadow:0 1px 8px rgba(3,12,14,.7)"></span>`,
          iconSize: [16, 16],
          iconAnchor: [8, 8],
        });
        const score = Number(region.score);
        return <Marker key={region.id} position={[latitude, longitude]} icon={icon}>
          <Popup>
            <div style={{ minWidth: 190, maxWidth: 270, color: '#203039', fontFamily: 'DM Sans, sans-serif' }}>
              <strong style={{ display: 'block', marginBottom: 5, textTransform: 'capitalize' }}>{region.priority} review priority</strong>
              <span style={{ display: 'block', marginBottom: 7, fontSize: 12 }}>Robust score: {Number.isFinite(score) ? score.toFixed(2) : 'Unavailable'}</span>
              <span style={{ display: 'block', fontSize: 12, lineHeight: 1.45 }}>{region.explanation}</span>
              <span style={{ display: 'block', marginTop: 7, color: '#596c6c', fontSize: 11 }}>Screening priority only; not a pollution measurement.</span>
            </div>
          </Popup>
        </Marker>;
      })}
    </MapContainer>
    <div className="map-coordinate-corner">{analysis.crs}</div>
    {!maskUrl && <div className="map-mapnote">{mask.isError ? 'Candidate mask asset unavailable; map tiles remain visible.' : 'Loading candidate mask overlay…'}</div>}
    {maskUrl && <div className="map-mapnote">Candidate water mask · screening layer, not a verified boundary</div>}
  </div>;
}

function History() {
  const list = useListAnalyses({ query: { queryKey: getListAnalysesQueryKey() } });
  const [search, setSearch] = useState('');
  const [mode, setMode] = useState('all');
  const rows = useMemo(() => (list.data ?? []).filter((item) => item.areaLabel.toLowerCase().includes(search.toLowerCase()) && (mode === 'all' || item.mode === mode)), [list.data, search, mode]);
  return <div className="page-wrap">
    <PageTitle eyebrow="RESEARCH NOTEBOOK" title="Your analysis archive." subtitle="Saved observations, calculations and exports. Demonstration scenes remain distinct from satellite observations." action={<Link href="/explorer" className="button button-primary"><ScanLine size={15} /> New analysis</Link>} />
    <section className="panel history-panel">
      <div className="history-tools"><label className="search-field"><Search size={16} /><input aria-label="Search analyses" placeholder="Search study area…" value={search} onChange={(event) => setSearch(event.target.value)} data-testid="input-history-search" /></label><div className="filter-tabs">{[['all', 'All'], ['satellite', 'Satellite'], ['demonstration', 'Demo']].map(([value, label]) => <button key={value} className={mode === value ? 'filter-tab active' : 'filter-tab'} onClick={() => setMode(value)}>{label}</button>)}</div></div>
      {list.isLoading ? <LoadingPanel /> : list.isError ? <QueryError retry={() => list.refetch()} /> : rows.length ? <>
        <div className="history-table-head"><span>STUDY AREA</span><span>MODE</span><span>OBSERVATION DATE</span><span>COVERAGE</span><span>FLAGGED</span><span>EXPORTS</span></div>
        <div className="history-table">{rows.map((item) => <HistoryRow key={item.id} item={item} />)}</div>
        <div className="history-foot">{rows.length} {rows.length === 1 ? 'record' : 'records'} shown <span>Coverage represents candidate pixels, not a verified boundary.</span></div>
      </> : <EmptyState title="No matching analysis" copy={search ? 'Try a shorter place name, or clear the current filters.' : 'Your analysis archive will build as you inspect scenes.'} action={search || mode !== 'all' ? <button className="text-button" onClick={() => { setSearch(''); setMode('all'); }}>Clear filters <X size={14} /></button> : <Link href="/explorer" className="button button-secondary">Start an analysis</Link>} />}
    </section>
    <EvidenceNote />
  </div>;
}

function HistoryRow({ item }: { item: AnalysisSummary }) {
  return <div className="history-table-row">
    <Link href={`/analysis/${item.id}`} className="history-area"><span className="row-mark"><Waves size={16} /></span><span><b>{item.areaLabel}</b><small>{item.id.slice(0, 12)}</small></span></Link>
    <ModeChip mode={item.mode} /><span className="history-date">{formatDate(item.observationDate ?? item.createdAt)}</span><span className="history-coverage">{pct(item.waterCoveragePercent)}</span><span className="history-count">{item.anomalyCount}</span><DownloadActions analysisId={item.id} />
  </div>;
}

function Methodology() {
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const faqs = [
    ['What does NDWI tell me?', 'NDWI highlights spectral contrast between green and near-infrared reflectance. It is a screening index that can help identify candidate surface water in an image; it is not a direct measurement of depth, water quality, or a surveyed shoreline.'],
    ['Why can a threshold change the result?', 'A threshold is a decision boundary applied to a continuous index. Small changes may include or exclude mixed pixels, shadows, or dark surfaces. Report the chosen value and examine sensitivity rather than presenting one cutoff as universal.'],
    ['What does a high-priority flag mean?', 'It means a region received a comparatively high screening score under this workflow. The score is not a pollution concentration, health risk, or causal explanation. Independent evidence is required for those claims.'],
    ['When can I use map coordinates?', 'Only when a source image includes a usable geospatial transform and coordinate reference system. Without those, locations remain row and column positions in pixel space.'],
  ];
  return <div className="page-wrap">
    <PageTitle eyebrow="FIELD GUIDE · METHODS & CLAIMS" title="A method you can defend." subtitle="The index, assumptions, and limits — in language that works at the bench and in a viva." />
    <div className="method-hero"><div className="method-index">METHOD NOTE <span>01—04</span></div><div className="method-hero-content"><span className="method-symbol">G − NIR</span><h2>One equation.<br /><em>Many reasons to pause.</em></h2><p>HydroScan AI makes a visible, reproducible first pass across satellite bands. It does not replace field observation or expert interpretation.</p></div><div className="method-hero-graphic"><span className="formula-tick t1" /><span className="formula-tick t2" /><span className="formula-tick t3" /><span className="formula-number">1</span></div></div>
    <section className="method-section">
      <div className="section-side"><div className="eyebrow">01 / THE CALCULATION</div><h2>Normalized Difference Water Index</h2><p>McFeeters (1996) formulation</p></div>
      <div className="section-main"><div className="formula-card"><div className="formula">NDWI = <span className="fraction"><span>Green − NIR</span><span>Green + NIR</span></span></div><div className="formula-key"><span><i className="swatch green-swatch" /> Green reflectance</span><span><i className="swatch nir-swatch" /> Near-infrared reflectance</span></div></div>
        <p>Each pixel receives a normalized index value. A user-selected cutoff classifies pixels above the threshold as <b>candidate water</b>. The ratio reduces some illumination effects but does not remove all surface confusion.</p>
        <div className="equation-steps"><div><span>01</span><b>Align bands</b><small>Blue, green, red and NIR source rasters are read as one scene.</small></div><div><span>02</span><b>Calculate index</b><small>NDWI is computed pixel by pixel from green and near-infrared.</small></div><div><span>03</span><b>Apply cutoff</b><small>Pixels above the chosen threshold become a candidate mask.</small></div></div>
      </div>
    </section>
    <section className="method-section dark-section">
      <div className="section-side"><div className="eyebrow">02 / ASSUMPTIONS</div><h2>What the method assumes</h2><p>Inputs shape every output.</p></div>
      <div className="section-main assumption-list">
        <div><span className="assumption-number">A</span><div><b>Comparable band inputs</b><p>Band rasters represent the same observation, with compatible dimensions and alignment.</p></div></div>
        <div><span className="assumption-number">B</span><div><b>Meaningful reflectance</b><p>Input values and any scaling or preprocessing are suitable for a normalized spectral ratio.</p></div></div>
        <div><span className="assumption-number">C</span><div><b>Threshold is contextual</b><p>A single cutoff is not universally correct across seasons, land cover, illumination, or sensor conditions.</p></div></div>
        <div><span className="assumption-number">D</span><div><b>Spatial metadata is real</b><p>Geographic coordinates are presented only when the source carries a valid transform and CRS.</p></div></div>
      </div>
    </section>
    <section className="method-section">
      <div className="section-side"><div className="eyebrow">03 / LIMITATIONS</div><h2>Claims this method cannot support alone</h2><p>Use this list when writing results.</p></div>
      <div className="section-main limit-columns">
        <div><CircleAlert size={17} /><b>A verified shoreline</b><p>Mixed pixels, shadows, vegetation and built surfaces can all affect a candidate water mask.</p></div>
        <div><CircleAlert size={17} /><b>Water quality or pollution</b><p>NDWI is not a chemical or biological water-quality measurement.</p></div>
        <div><CircleAlert size={17} /><b>Cause of an anomaly</b><p>A review priority indicates where to look next, not why a pattern exists.</p></div>
        <div><CircleAlert size={17} /><b>Change over time from demos</b><p>Synthetic demonstrations are excluded from compatible dated satellite trends.</p></div>
      </div>
    </section>
    <section className="method-section architecture-section">
      <div className="section-side"><div className="eyebrow">04 / WORKFLOW</div><h2>From bands to a defensible note</h2><p>Trace the output back to its source.</p></div>
      <div className="section-main">
        <div className="architecture-flow"><div><Satellite size={19} /><b>Source</b><small>Sentinel-2 bands or labeled demo</small></div><ArrowRight size={15} /><div><SlidersHorizontal size={19} /><b>Index & threshold</b><small>NDWI cutoff recorded with result</small></div><ArrowRight size={15} /><div><Layers3 size={19} /><b>Derived layers</b><small>RGB, index, mask, comparison</small></div><ArrowRight size={15} /><div><FileText size={19} /><b>Interpretation</b><small>Evidence plus stated limitations</small></div></div>
        <div className="viva-box"><div className="viva-title"><BookOpen size={18} /><div><span>VIVA PRACTICE</span><b>Try answering this before presenting.</b></div></div><blockquote>“How would your candidate-water estimate change if the NDWI threshold moved by 0.1, and which independent observation would you use to check it?”</blockquote><p>A strong answer explains sensitivity, names likely confounders, and proposes validation — without overstating the mask.</p></div>
      </div>
    </section>
    <section className="faq-section"><div className="eyebrow">QUICK CLARIFICATIONS</div><h2>Questions worth asking</h2>{faqs.map(([question, answer], index) => <div className={`faq-item ${openFaq === index ? 'faq-open' : ''}`} key={question}><button onClick={() => setOpenFaq(openFaq === index ? null : index)} aria-expanded={openFaq === index} data-testid={`button-faq-${index}`}><span>{question}</span><ChevronDown size={17} /></button>{openFaq === index && <p>{answer}</p>}</div>)}</section>
    <EvidenceNote />
  </div>;
}

function Health() {
  const api = useHealthCheck({ query: { queryKey: getHealthCheckQueryKey() } });
  const system = useGetSystemHealth({ query: { queryKey: getGetSystemHealthQueryKey() } });
  return <div className="page-wrap">
    <PageTitle eyebrow="SERVICE STATUS · PROCESSING & STORAGE" title="Know what is ready." subtitle="A direct view of the API, processing dependencies, and local storage available to this workspace." action={<button className="button button-secondary" onClick={() => { void api.refetch(); void system.refetch(); }}><Activity size={15} /> Refresh checks</button>} />
    <div className="health-banner">
      <div className="health-emblem">{system.data?.status === 'ready' ? <Check size={21} /> : <Activity size={21} />}</div>
      <div><div className="eyebrow">PROCESSING ENVIRONMENT</div><h2>{system.data?.status === 'ready' ? 'Ready for analysis' : system.data?.status === 'degraded' ? 'Partially available' : api.isError || system.isError ? 'Status could not be confirmed' : 'Checking system status'}</h2><p>{system.data?.message ?? (api.isError ? 'The API health endpoint could not be reached.' : 'Waiting for system checks to return.')}</p></div>
      <span className={`status-pill ${system.data?.status === 'ready' ? 'pill-ready' : 'pill-check'}`}><span />{system.data?.status ?? 'CHECKING'}</span>
    </div>
    <div className="health-grid">
      <section className="panel health-card"><div className="health-card-icon"><Radio size={18} /></div><div className="eyebrow">API CONNECTIVITY</div><h3>Health endpoint</h3>
        {api.isLoading ? <LoadingPanel label="Request in progress" /> : api.isError ? <StatusLine ok={false} label="Health check failed" /> : <StatusLine ok={api.data?.status === 'ok' || !!api.data?.status} label={api.data?.status ? `Responding · ${api.data.status}` : 'Responding'} />}
        <p>Confirms that the application API can respond to a request.</p>
      </section>
      <section className="panel health-card"><div className="health-card-icon"><Database size={18} /></div><div className="eyebrow">LOCAL STORAGE</div><h3>Analysis archive</h3>
        {system.isLoading ? <LoadingPanel label="Checking storage" /> : system.isError ? <StatusLine ok={false} label="Storage status unavailable" /> : <StatusLine ok={!!system.data?.storageAvailable} label={system.data?.storageAvailable ? 'Available' : 'Unavailable'} />}
        <p>Saved analyses and generated outputs depend on the server storage layer.</p>
      </section>
      <section className="panel health-card dependencies-card"><div className="health-card-icon"><Layers3 size={18} /></div><div className="eyebrow">PROCESSING STACK</div><h3>Dependencies</h3>
        {system.isLoading ? <LoadingPanel label="Inspecting dependencies" /> : system.isError ? <StatusLine ok={false} label="Dependency status unavailable" /> : system.data?.dependencies?.length ? <div className="dependency-list">{system.data.dependencies.map((dep) => <div className="dependency-row" key={dep.name}><StatusLine ok={dep.available} label={dep.name} /><span>{dep.version ?? (dep.available ? 'Available' : 'Unavailable')}</span></div>)}</div> : <div className="dependency-empty">No dependency details returned by the service.</div>}
        <p>Availability is reported by the API, not inferred from the browser.</p>
      </section>
    </div>
    {(api.isError || system.isError) && <QueryError retry={() => { void api.refetch(); void system.refetch(); }} />}
    <div className="health-note"><ShieldCheck size={17} /><div><b>Health checks do not validate scientific results.</b><p>A ready processor confirms operational dependencies only. Each analysis still requires input review and contextual interpretation.</p></div></div>
  </div>;
}

function StatusLine({ ok, label }: { ok: boolean; label: string }) {
  return <div className="status-line"><span className={`status-dot ${ok ? '' : 'dot-error'}`} /><b>{label}</b></div>;
}

function AppRouter() {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}><AppShell><Switch>
    <Route path="/" component={Dashboard} />
    <Route path="/explorer" component={Explorer} />
    <Route path="/analysis/:analysisId" component={AnalysisDetail} />
    <Route path="/map" component={MapPage} />
    <Route path="/history" component={History} />
    <Route path="/methodology" component={Methodology} />
    <Route path="/health" component={Health} />
    <Route component={NotFound} />
  </Switch></AppShell></ErrorBoundary>;
}

function App() {
  return <QueryClientProvider client={queryClient}><TooltipProvider><WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}><AppRouter /></WouterRouter><Toaster /></TooltipProvider></QueryClientProvider>;
}

export default App;
