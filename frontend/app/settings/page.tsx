"use client";

import { useState, useEffect } from "react";
import { apiService } from "@/lib/api";
import axios from "axios";
import { Settings, Key, Save, CheckCircle, AlertCircle, RefreshCcw, Zap, Database, Radio, Globe, Activity } from "lucide-react";
import { useCurrency, CURRENCY_SYMBOLS, Currency } from "@/components/CurrencyContext";
import { GlassCard } from "@/components/ui/GlassCard";
import { usePerformanceMode } from "@/lib/usePerformanceMode";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SettingsPage() {
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [configured, setConfigured] = useState<Record<string, boolean>>({});
  const [dirtyFields, setDirtyFields] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshResult, setRefreshResult] = useState<string | null>(null);
  
  const { currency, setCurrency } = useCurrency();
  const { mode: perfMode, toggleMode: setPerfMode } = usePerformanceMode();

  useEffect(() => {
    axios.get(`${BASE}/api/settings`)
      .then(res => {
        const data = res.data;
        setFormValues(data.values || {});
        setConfigured(data.configured || {});
      })
      .catch(err => {
        console.error("Failed to load settings", err);
      });
  }, []);

  const handleChange = (key: string, value: string) => {
    setFormValues(prev => ({ ...prev, [key]: value }));
    setDirtyFields(prev => new Set(prev).add(key));
  };

  const handleSave = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const changedSettings: Record<string, string> = {};
      dirtyFields.forEach(key => {
        changedSettings[key] = formValues[key] || "";
      });

      if (Object.keys(changedSettings).length === 0) {
        setStatus({ type: "error", message: "No constraints modified." });
        setSaving(false);
        return;
      }

      await axios.post(`${BASE}/api/settings`, { settings: changedSettings });
      setStatus({ type: "success", message: "Neural pathways synchronized." });
      setDirtyFields(new Set());

      const res = await axios.get(`${BASE}/api/settings`);
      setConfigured(res.data.configured || {});
      setFormValues(res.data.values || {});

      setTimeout(() => setStatus(null), 3000);
    } catch (error) {
      console.error(error);
      setStatus({ type: "error", message: "Synchronization failed." });
    } finally {
      setSaving(false);
    }
  };

  const handleRefreshAll = async () => {
    setRefreshing(true);
    setRefreshResult(null);
    try {
      const res = await axios.post(`${BASE}/api/status/refresh-all`);
      const details = res.data.details || {};
      setRefreshResult(
        `✅ Signals: ${details.technicals || 'done'} | Cache: ${details.cache || 'cleared'} | Tensors: ${details.predictions || 'triggered'}`
      );
    } catch (err: any) {
      setRefreshResult(`❌ Sequence failed: ${err.message}`);
    } finally {
      setRefreshing(false);
      setTimeout(() => setRefreshResult(null), 8000);
    }
  };

  const fields = [
    {
      id: "groq_api_key",
      label: "Groq API Key",
      desc: "Enables LLaMA 3.3 70B explanations instead of rule-based templates.",
      sensitive: true,
    },
    {
      id: "binance_api_key",
      label: "Binance API Key",
      desc: "Optional. Unlocks higher rate limits for fetching historical OHLCV data.",
      sensitive: true,
    },
    {
      id: "binance_secret",
      label: "Binance Secret",
      desc: "Required only if using a Binance API Key.",
      sensitive: true,
    },
    {
      id: "fred_api_key",
      label: "FRED API Key",
      desc: "Optional. Unlocks official Federal Reserve data. (Falls back to yfinance if omitted).",
      sensitive: true,
    },
    {
      id: "supabase_url",
      label: "Supabase URL",
      desc: "Optional. Cloud sync destination.",
      sensitive: false,
    },
    {
      id: "supabase_service_role_key",
      label: "Supabase Service Role Key",
      desc: "Optional. Cloud sync authentication.",
      sensitive: true,
    },
    {
      id: "sentry_dsn",
      label: "Sentry DSN",
      desc: "Optional. Enables error tracking.",
      sensitive: true,
    },
    {
      id: "wandb_api_key",
      label: "Weights & Biases API Key",
      desc: "Optional. Enables ML model tracking during training.",
      sensitive: true,
    }
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-10 pt-8 p-6 glass-2 rounded-2xl overflow-hidden relative">
      
      {/* HEADER */}
      <div className="relative">
        <div className="absolute top-[-50px] left-[-50px] w-64 h-64 bg-accent/5 rounded-full blur-[80px] pointer-events-none" />
        <div className="relative z-10">
          <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted flex items-center gap-4 tracking-tight">
            <div className="p-3 glass bg-accent/10 rounded-sm shadow-inner shadow-accent/20">
                <Settings className="text-accent" size={32} />
            </div>
            System Settings
          </h1>
          <p className="text-text-muted mt-3 font-light tracking-wide max-w-xl">
            Manage API keys and external integrations. Keys are stored securely in your local encrypted storage.
          </p>
        </div>
      </div>

      {/* Currency Preferences Section */}
      <GlassCard tier={2} shape="none" className="rounded-xl p-8 relative z-10 group overflow-hidden">
        <div className="absolute top-0 right-0 w-32 h-32 bg-accent/5 rounded-full blur-[50px] group-hover:bg-accent/10 transition-colors pointer-events-none" />
        <h2 className="text-xl font-black text-text flex items-center gap-3 mb-6 tracking-tight relative z-10">
          <Globe className="text-accent" size={24} /> Fiat Reference
        </h2>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
          <div>
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest mb-1">Display Currency</p>
            <p className="text-sm text-text-muted font-light max-w-md leading-relaxed">
              Choose the base currency for displaying prices across the dashboard. Exchange rates are automatically fetched in real-time.
            </p>
          </div>
          <select
            value={currency}
            onChange={(e) => setCurrency(e.target.value as Currency)}
            className="bg-surface/50 border border-text/10 text-text text-sm rounded-sm focus:ring-accent focus:border-accent block p-3.5 w-full md:w-64 font-mono font-bold transition-colors hover:bg-surface/80 outline-none"
          >
            {Object.keys(CURRENCY_SYMBOLS).map((c) => (
              <option key={c} value={c}>
                {c} ({CURRENCY_SYMBOLS[c as Currency]})
              </option>
            ))}
          </select>
        </div>
      </GlassCard>

      {/* Performance Mode Section */}
      <GlassCard tier={2} shape="none" className="rounded-xl p-8 relative z-10 overflow-hidden">
        <div className="absolute top-0 right-0 w-1 bg-gradient-to-b from-success to-transparent h-full" />
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div>
            <h2 className="text-xl font-black text-text flex items-center gap-3 mb-2 tracking-tight">
              <Activity className="text-success" size={24} /> UI Rendering Mode
            </h2>
            <p className="text-text-muted text-sm font-light">Toggle Lite mode to disable glass blur effects and improve battery life on mobile devices.</p>
          </div>
          
          <div className="flex bg-surface/50 rounded-sm border border-text/10 p-1 w-full md:w-auto">
            <button
              onClick={() => setPerfMode("full")}
              className={`flex-1 md:flex-none px-6 py-2.5 text-xs font-bold uppercase tracking-widest transition-all rounded-sm ${
                perfMode === "full" 
                  ? "bg-success/20 text-success border border-success/30 shadow-inner" 
                  : "text-text-muted hover:text-text border border-transparent"
              }`}
            >
              Full
            </button>
            <button
              onClick={() => setPerfMode("lite")}
              className={`flex-1 md:flex-none px-6 py-2.5 text-xs font-bold uppercase tracking-widest transition-all rounded-sm ${
                perfMode === "lite" 
                  ? "bg-warning/20 text-warning border border-warning/30 shadow-inner" 
                  : "text-text-muted hover:text-text border border-transparent"
              }`}
            >
              Lite
            </button>
          </div>
        </div>
      </GlassCard>

      {/* Data Refresh Section */}
      <GlassCard tier={2} shape="none" className="rounded-xl p-8 relative z-10 overflow-hidden">
        <div className="absolute top-0 left-0 w-1 bg-gradient-to-b from-warning to-transparent h-full" />
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div>
            <h2 className="text-xl font-black text-text flex items-center gap-3 tracking-tight">
              <Zap className="text-warning" size={24} /> Force Sync
            </h2>
            <p className="text-sm text-text-muted mt-2 font-light max-w-md leading-relaxed">
              Manually trigger a full data pipeline: fetch live technicals from Binance, clear API cache, and broadcast updated predictions.
            </p>
          </div>
          <button
            onClick={handleRefreshAll}
            disabled={refreshing}
            className="flex items-center gap-3 bg-warning/10 hover:bg-warning/20 text-warning font-black py-3 px-8 rounded-sm border border-warning/30 transition-all disabled:opacity-50 uppercase tracking-widest text-xs shadow-[0_0_15px_rgba(234,179,8,0.1)] hover:shadow-[0_0_25px_rgba(234,179,8,0.2)]"
          >
            {refreshing ? (
              <div className="w-5 h-5 border-2 border-warning/30 border-t-warning rounded-full animate-spin" />
            ) : (
              <RefreshCcw size={20} />
            )}
            {refreshing ? "Synchronizing..." : "Sync Now"}
          </button>
        </div>
        {refreshResult && (
          <div className="mt-6 p-4 glass bg-black/20 border border-text/10 rounded-sm text-sm text-text-muted font-mono border-l-2 border-l-warning">
            {refreshResult}
          </div>
        )}
      </GlassCard>

      {/* API Keys Section */}
      <GlassCard tier={2} shape="none" className="rounded-xl p-0 relative z-10 overflow-hidden">
        <div className="p-8 border-b border-text/5 bg-surface/30">
            <h2 className="text-xl font-black text-text flex items-center gap-3 tracking-tight">
            <Key className="text-accent" size={24} /> Integration Keys
            </h2>
        </div>

        <div className="p-8 space-y-8 bg-surface/10">
            {fields.map(field => (
            <div key={field.id} className="grid grid-cols-1 lg:grid-cols-3 gap-6 border-b border-text/5 pb-8 last:border-0 last:pb-0 group">
                <div className="lg:col-span-1">
                <div className="flex items-center gap-3 mb-2">
                    <label htmlFor={field.id} className="block text-xs font-bold text-text uppercase tracking-widest">
                    {field.label}
                    </label>
                    {configured[field.id] && (
                    <span className="flex items-center gap-1 px-2 py-0.5 bg-success/10 border border-success/20 text-success rounded-sm text-[9px] font-black uppercase tracking-widest shadow-[0_0_10px_rgba(34,197,94,0.1)]">
                        <CheckCircle size={10} /> Active
                    </span>
                    )}
                </div>
                <p className="text-xs text-text-muted font-light leading-relaxed">
                    {field.desc}
                </p>
                </div>
                <div className="lg:col-span-2 relative flex items-center">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                    <Key size={16} className="text-text-muted group-focus-within:text-accent transition-colors" />
                </div>
                <input
                    id={field.id}
                    type={field.sensitive ? "password" : "text"}
                    className="w-full bg-surface/50 border border-text/10 text-text text-sm rounded-sm focus:ring-accent focus:border-accent block pl-12 p-3.5 transition-all font-mono hover:bg-surface/80 outline-none focus:shadow-[0_0_15px_rgba(var(--accent),0.1)]"
                    placeholder={configured[field.id] ? "••••••••  (leave blank to keep current)" : "Enter key hash"}
                    value={formValues[field.id] || ""}
                    onChange={(e) => handleChange(field.id, e.target.value)}
                />
                </div>
            </div>
            ))}

            <div className="pt-6 mt-4 flex flex-col md:flex-row items-center justify-between gap-6 border-t border-text/5">
            {status ? (
                <div className={`flex items-center gap-3 text-sm font-black tracking-widest uppercase px-4 py-2 rounded-sm ${status.type === 'success' ? 'bg-success/10 text-success border border-success/20' : 'bg-danger/10 text-danger border border-danger/20'}`}>
                {status.type === 'success' ? <CheckCircle size={18} /> : <AlertCircle size={18} />}
                {status.message}
                </div>
            ) : (
                <div className="text-[10px] font-bold uppercase tracking-widest text-text-muted bg-text/5 px-3 py-1.5 rounded-sm border border-text/10">
                {dirtyFields.size > 0 ? `${dirtyFields.size} pending modifications` : "System parameters locked"}
                </div>
            )}
            
            <button
                onClick={handleSave}
                disabled={saving || dirtyFields.size === 0}
                className="flex items-center gap-3 bg-accent hover:bg-accent/90 text-white font-black py-3.5 px-8 rounded-sm transition-all disabled:opacity-50 uppercase tracking-widest text-xs shadow-[0_0_20px_rgba(var(--accent),0.3)] hover:shadow-[0_0_30px_rgba(var(--accent),0.5)] w-full md:w-auto justify-center"
            >
                {saving ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                <Save size={20} />
                )}
                {saving ? "Encrypting..." : "Commit Changes"}
            </button>
            </div>
        </div>
      </GlassCard>
    </div>
  );
}

