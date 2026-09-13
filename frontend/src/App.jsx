import React, { useState, useEffect, useRef } from 'react';
import {
  Activity,
  Database,
  RefreshCw,
  Upload,
  Download,
  AlertTriangle,
  CheckCircle2,
  Zap,
  Layers,
  ArrowUpRight,
  Search,
  Filter,
  ShieldCheck,
  FileSpreadsheet,
  Flame
} from 'lucide-react';
import DiffModal from './components/DiffModal';

const API_BASE = '/api/v1/cdc';
const VIETFUL_BASE = '/mock-vietful/api/v1';

export default function App() {
  const [activeTab, setActiveTab] = useState('events'); // 'events' | 'products' | 'batches'
  const [stats, setStats] = useState(null);
  const [events, setEvents] = useState([]);
  const [products, setProducts] = useState([]);
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState(null);

  // Filters
  const [sourceFilter, setSourceFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [searchKeyword, setSearchKeyword] = useState('');

  // Upload state
  const [uploadStatus, setUploadStatus] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  // Chaos simulation state
  const [isChaosDown, setIsChaosDown] = useState(false);

  // Fetch Stats & Health
  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/stats`);
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Error fetching stats:', err);
    }
  };

  // Fetch Events
  const fetchEvents = async () => {
    try {
      const params = new URLSearchParams();
      if (sourceFilter) params.append('source', sourceFilter);
      if (typeFilter) params.append('change_type', typeFilter);
      params.append('limit', '50');

      const res = await fetch(`${API_BASE}/events?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setEvents(data);
      }
    } catch (err) {
      console.error('Error fetching events:', err);
    }
  };

  // Fetch Products
  const fetchProducts = async () => {
    try {
      const params = new URLSearchParams();
      if (searchKeyword) params.append('keyword', searchKeyword);
      params.append('limit', '50');

      const res = await fetch(`${API_BASE}/products?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setProducts(data);
      }
    } catch (err) {
      console.error('Error fetching products:', err);
    }
  };

  // Fetch Batches
  const fetchBatches = async () => {
    try {
      const res = await fetch(`${API_BASE}/batches?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setBatches(data);
      }
    } catch (err) {
      console.error('Error fetching batches:', err);
    }
  };

  const refreshAll = async () => {
    setLoading(true);
    await Promise.all([fetchStats(), fetchEvents(), fetchProducts(), fetchBatches()]);
    setLoading(false);
  };

  useEffect(() => {
    refreshAll();
  }, [sourceFilter, typeFilter, searchKeyword]);

  // Auto-refresh interval (every 4 seconds)
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      fetchStats();
      if (activeTab === 'events') fetchEvents();
      if (activeTab === 'products') fetchProducts();
      if (activeTab === 'batches') fetchBatches();
    }, 4000);
    return () => clearInterval(interval);
  }, [autoRefresh, activeTab, sourceFilter, typeFilter, searchKeyword]);

  // Trigger Manual Poll
  const handleTriggerPoll = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/trigger-poll`, { method: 'POST' });
      if (res.ok) {
        await refreshAll();
      }
    } catch (err) {
      alert('Failed to trigger poll: ' + err);
    } finally {
      setLoading(false);
    }
  };

  // Trigger Warehouse Mutation in Mock Vietful
  const handleSimulateMutation = async () => {
    try {
      const res = await fetch(`${VIETFUL_BASE}/simulate/mutate?mutate_ratio=0.15`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        alert(`Warehouse Mutated!\n${data.summary.mutated_count} products modified in Vietful.`);
        await handleTriggerPoll();
      }
    } catch (err) {
      alert('Mutation failed: ' + err);
    }
  };

  // Toggle Chaos Outage in Mock Vietful
  const handleToggleChaos = async () => {
    const nextState = !isChaosDown;
    try {
      const res = await fetch(`${VIETFUL_BASE}/simulate/chaos`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_down: nextState })
      });
      if (res.ok) {
        setIsChaosDown(nextState);
        await handleTriggerPoll();
      }
    } catch (err) {
      alert('Chaos toggle failed: ' + err);
    }
  };

  // Handle Excel Upload
  const handleExcelUpload = async (file) => {
    if (!file) return;
    setIsUploading(true);
    setUploadStatus(null);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE}/upload-excel`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (res.ok) {
        setUploadStatus({
          success: true,
          message: `Excel Ingested! Total: ${data.total_records} | New: ${data.inserted_count} | Updated: ${data.updated_count} | Duplicates Filtered: ${data.duplicate_count}`
        });
        await refreshAll();
      } else {
        setUploadStatus({ success: false, message: data.detail || 'Upload failed' });
      }
    } catch (err) {
      setUploadStatus({ success: false, message: 'Upload error: ' + err });
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-lg font-bold text-white tracking-tight">CDMS</h1>
                <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  Change Data Capture
                </span>
              </div>
              <p className="text-xs text-slate-400">Vietful Inventory Exactly-Once Service</p>
            </div>
          </div>

          <div className="flex items-center space-x-3">
            {/* Poller Status Badge */}
            <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700 text-xs">
              <span className="text-slate-400">Poller:</span>
              <span
                className={`w-2 h-2 rounded-full ${
                  stats?.poller_status?.circuit_state === 'OPEN'
                    ? 'bg-rose-500 animate-ping'
                    : 'bg-emerald-500'
                }`}
              />
              <span
                className={`font-semibold ${
                  stats?.poller_status?.circuit_state === 'OPEN' ? 'text-rose-400' : 'text-emerald-400'
                }`}
              >
                {stats?.poller_status?.circuit_state || 'ACTIVE'}
              </span>
            </div>

            {/* Auto Refresh Toggle */}
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
                autoRefresh
                  ? 'bg-blue-600/10 border-blue-500/30 text-blue-400'
                  : 'bg-slate-800 border-slate-700 text-slate-400'
              }`}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${autoRefresh && loading ? 'animate-spin' : ''}`} />
              <span>Auto-refresh</span>
            </button>

            {/* Manual Refresh */}
            <button
              onClick={refreshAll}
              disabled={loading}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 transition"
              title="Refresh Data"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* KPI Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex items-center space-x-4 shadow-sm">
            <div className="p-3 rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
              <Database className="w-6 h-6" />
            </div>
            <div>
              <span className="text-xs text-slate-400 font-medium">Active Products</span>
              <div className="text-2xl font-extrabold text-white tracking-tight">
                {stats?.total_active_products?.toLocaleString() || 0}
              </div>
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex items-center space-x-4 shadow-sm">
            <div className="p-3 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
              <Activity className="w-6 h-6" />
            </div>
            <div>
              <span className="text-xs text-slate-400 font-medium">Total Change Events</span>
              <div className="text-2xl font-extrabold text-white tracking-tight">
                {stats?.total_change_events?.toLocaleString() || 0}
              </div>
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 flex items-center space-x-4 shadow-sm">
            <div className="p-3 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Layers className="w-6 h-6" />
            </div>
            <div>
              <span className="text-xs text-slate-400 font-medium">Inserts / Updates</span>
              <div className="text-2xl font-extrabold text-white tracking-tight">
                <span className="text-emerald-400">{stats?.total_inserts || 0}</span>
                <span className="text-slate-500 text-lg mx-1.5 font-normal">/</span>
                <span className="text-amber-400">{stats?.total_updates || 0}</span>
              </div>
            </div>
          </div>

          <div className="p-4 rounded-2xl bg-gradient-to-br from-emerald-950/40 to-slate-900 border border-emerald-500/30 flex items-center space-x-4 shadow-sm">
            <div className="p-3 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center space-x-1.5">
                <span className="text-xs text-emerald-300 font-medium">Duplicates Filtered</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 font-bold">
                  EXACTLY-ONCE
                </span>
              </div>
              <div className="text-2xl font-extrabold text-emerald-400 tracking-tight">
                {stats?.total_duplicates_prevented?.toLocaleString() || 0}
              </div>
            </div>
          </div>
        </div>

        {/* Action & Control Deck */}
        <div className="p-5 rounded-2xl bg-slate-900 border border-slate-800 space-y-4">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <h2 className="text-sm font-bold text-white uppercase tracking-wider">Control & Simulation Deck</h2>
              <p className="text-xs text-slate-400">Trigger Polling, Upload Excel files, and test Resilience/Chaos</p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {/* Trigger Manual Poll */}
              <button
                onClick={handleTriggerPoll}
                disabled={loading}
                className="flex items-center space-x-1.5 px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/20 transition"
              >
                <Zap className="w-4 h-4" />
                <span>Trigger Poll Now</span>
              </button>

              {/* Simulate Mutation */}
              <button
                onClick={handleSimulateMutation}
                className="flex items-center space-x-1.5 px-3.5 py-2 rounded-xl bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/30 text-xs font-semibold transition"
              >
                <RefreshCw className="w-4 h-4" />
                <span>Simulate Warehouse Mutation</span>
              </button>

              {/* Chaos Toggle */}
              <button
                onClick={handleToggleChaos}
                className={`flex items-center space-x-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold border transition ${
                  isChaosDown
                    ? 'bg-rose-600 text-white border-rose-500'
                    : 'bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border-rose-500/30'
                }`}
              >
                <Flame className="w-4 h-4" />
                <span>{isChaosDown ? 'Stop Chaos (Restore)' : 'Inject Outage (503)'}</span>
              </button>

              {/* Download Sample Excel */}
              <a
                href={`${API_BASE}/download-sample-excel`}
                download="vietful_sample_products.xlsx"
                className="flex items-center space-x-1.5 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold transition"
              >
                <Download className="w-4 h-4" />
                <span>Sample Excel</span>
              </a>
            </div>
          </div>

          {/* Excel File Drag & Drop Bar */}
          <div className="flex flex-col sm:flex-row items-center gap-3 p-3 rounded-xl bg-slate-950 border border-slate-800">
            <div className="flex items-center space-x-3 text-xs text-slate-300 flex-1">
              <FileSpreadsheet className="w-5 h-5 text-emerald-400" />
              <span>
                <strong>Channel 3 - Excel Ingestion:</strong> Upload .xlsx spreadsheets from REST-based Client
              </span>
            </div>

            <div className="flex items-center space-x-2 w-full sm:w-auto">
              <input
                type="file"
                ref={fileInputRef}
                accept=".xlsx,.xls"
                className="hidden"
                onChange={(e) => handleExcelUpload(e.target.files[0])}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
                className="w-full sm:w-auto flex items-center justify-center space-x-2 px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/20 transition"
              >
                <Upload className="w-3.5 h-3.5" />
                <span>{isUploading ? 'Ingesting...' : 'Select & Upload Excel'}</span>
              </button>
            </div>
          </div>

          {/* Upload Status Toast */}
          {uploadStatus && (
            <div
              className={`p-3 rounded-xl text-xs flex items-center space-x-2 border ${
                uploadStatus.success
                  ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300'
                  : 'bg-rose-500/10 border-rose-500/20 text-rose-300'
              }`}
            >
              {uploadStatus.success ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              ) : (
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
              )}
              <span>{uploadStatus.message}</span>
            </div>
          )}
        </div>

        {/* Tab Navigation & Filters */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800 pb-3">
          <div className="flex space-x-2">
            <button
              onClick={() => setActiveTab('events')}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition ${
                activeTab === 'events'
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              Live Change Events ({events.length})
            </button>
            <button
              onClick={() => setActiveTab('products')}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition ${
                activeTab === 'products'
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              Product Snapshots ({products.length})
            </button>
            <button
              onClick={() => setActiveTab('batches')}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition ${
                activeTab === 'batches'
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              Ingestion Batches ({batches.length})
            </button>
          </div>

          {/* Filters per active tab */}
          {activeTab === 'events' && (
            <div className="flex items-center space-x-2 text-xs">
              <select
                value={sourceFilter}
                onChange={(e) => setSourceFilter(e.target.value)}
                className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-300 focus:outline-none focus:border-blue-500"
              >
                <option value="">All Sources</option>
                <option value="POLLING">Polling</option>
                <option value="WEBHOOK">Webhook</option>
                <option value="EXCEL">Excel Upload</option>
              </select>

              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-300 focus:outline-none focus:border-blue-500"
              >
                <option value="">All Types</option>
                <option value="INSERT">INSERT</option>
                <option value="UPDATE">UPDATE</option>
              </select>
            </div>
          )}

          {activeTab === 'products' && (
            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search SKU or name..."
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
            </div>
          )}
        </div>

        {/* Tab 1: Live Change Events */}
        {activeTab === 'events' && (
          <div className="rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                  <tr>
                    <th className="py-3.5 px-4">Event ID</th>
                    <th className="py-3.5 px-4">SKU</th>
                    <th className="py-3.5 px-4">Type</th>
                    <th className="py-3.5 px-4">Source</th>
                    <th className="py-3.5 px-4">Diff Details</th>
                    <th className="py-3.5 px-4">Ingested At</th>
                    <th className="py-3.5 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {events.length === 0 ? (
                    <tr>
                      <td colSpan="7" className="text-center py-10 text-slate-500">
                        No change events recorded yet. Trigger a poll or push webhook!
                      </td>
                    </tr>
                  ) : (
                    events.map((ev) => {
                      const isUpd = ev.change_type === 'UPDATE';
                      const diffKeys = isUpd && ev.diff_data ? Object.keys(ev.diff_data) : [];
                      return (
                        <tr key={ev.id} className="hover:bg-slate-800/40 transition">
                          <td className="py-3 px-4 font-mono text-slate-400">#{ev.id}</td>
                          <td className="py-3 px-4 font-mono font-bold text-white">{ev.sku}</td>
                          <td className="py-3 px-4">
                            <span
                              className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                                isUpd
                                  ? 'bg-amber-500/10 text-amber-300 border border-amber-500/20'
                                  : 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20'
                              }`}
                            >
                              {ev.change_type}
                            </span>
                          </td>
                          <td className="py-3 px-4">
                            <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[11px] border border-slate-700">
                              {ev.source}
                            </span>
                          </td>
                          <td className="py-3 px-4">
                            {isUpd ? (
                              <span className="text-amber-300 font-mono text-[11px]">
                                Changed: {diffKeys.join(', ')}
                              </span>
                            ) : (
                              <span className="text-slate-500 italic">Initial creation</span>
                            )}
                          </td>
                          <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                            {new Date(ev.ingested_at).toLocaleTimeString()}
                          </td>
                          <td className="py-3 px-4 text-right">
                            <button
                              onClick={() => setSelectedEvent(ev)}
                              className="inline-flex items-center space-x-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-blue-400 text-[11px] font-medium transition"
                            >
                              <span>Inspect Diff</span>
                              <ArrowUpRight className="w-3 h-3" />
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 2: Product Snapshots */}
        {activeTab === 'products' && (
          <div className="rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                  <tr>
                    <th className="py-3.5 px-4">SKU</th>
                    <th className="py-3.5 px-4">Product Name</th>
                    <th className="py-3.5 px-4">Price (VND)</th>
                    <th className="py-3.5 px-4">Stock</th>
                    <th className="py-3.5 px-4">Version</th>
                    <th className="py-3.5 px-4">SHA-256 Hash</th>
                    <th className="py-3.5 px-4">Last Updated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {products.length === 0 ? (
                    <tr>
                      <td colSpan="7" className="text-center py-10 text-slate-500">
                        No product snapshots in database.
                      </td>
                    </tr>
                  ) : (
                    products.map((p) => (
                      <tr key={p.id} className="hover:bg-slate-800/40 transition">
                        <td className="py-3 px-4 font-mono font-bold text-white">{p.sku}</td>
                        <td className="py-3 px-4 font-medium text-slate-200">{p.product_name}</td>
                        <td className="py-3 px-4 font-mono text-emerald-400 font-semibold">
                          {p.price?.toLocaleString()} ₫
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-300">{p.stock_quantity}</td>
                        <td className="py-3 px-4">
                          <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 font-mono text-[11px] font-bold border border-blue-500/20">
                            v{p.version}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono text-slate-500 text-[11px] truncate max-w-[120px]" title={p.content_hash}>
                          {p.content_hash.slice(0, 12)}...
                        </td>
                        <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                          {new Date(p.updated_at).toLocaleTimeString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 3: Ingestion Batches */}
        {activeTab === 'batches' && (
          <div className="rounded-2xl border border-slate-800 bg-slate-900 overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-800">
                  <tr>
                    <th className="py-3.5 px-4">Batch ID</th>
                    <th className="py-3.5 px-4">Source</th>
                    <th className="py-3.5 px-4">Total Ingested</th>
                    <th className="py-3.5 px-4">New (Inserts)</th>
                    <th className="py-3.5 px-4">Updated</th>
                    <th className="py-3.5 px-4">Duplicates Filtered</th>
                    <th className="py-3.5 px-4">Executed At</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {batches.length === 0 ? (
                    <tr>
                      <td colSpan="7" className="text-center py-10 text-slate-500">
                        No batch runs recorded yet.
                      </td>
                    </tr>
                  ) : (
                    batches.map((b) => (
                      <tr key={b.id} className="hover:bg-slate-800/40 transition">
                        <td className="py-3 px-4 font-mono text-slate-400 text-[11px]" title={b.batch_id}>
                          {b.batch_id.slice(0, 8)}...
                        </td>
                        <td className="py-3 px-4">
                          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[11px] border border-slate-700">
                            {b.source}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono font-bold text-white">{b.total_records}</td>
                        <td className="py-3 px-4 font-mono text-emerald-400 font-semibold">{b.inserted_count}</td>
                        <td className="py-3 px-4 font-mono text-amber-400 font-semibold">{b.updated_count}</td>
                        <td className="py-3 px-4 font-mono text-purple-400 font-semibold">{b.duplicate_count}</td>
                        <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                          {new Date(b.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* Visual Diff Modal */}
      {selectedEvent && <DiffModal event={selectedEvent} onClose={() => setSelectedEvent(null)} />}
    </div>
  );
}
