"use client";

import { useState, useEffect } from "react";
import { apiService } from "@/lib/api";
import { Settings, Key, Save, CheckCircle, AlertCircle } from "lucide-react";

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);

  useEffect(() => {
    // Load existing settings on mount
    apiService.getSettings()
      .then(res => {
        setSettings(res || {});
      })
      .catch(err => {
        console.error("Failed to load settings", err);
      });
  }, []);

  const handleChange = (key: string, value: string) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    setStatus(null);
    try {
      await apiService.updateSettings(settings);
      setStatus({ type: "success", message: "Settings saved successfully!" });
      setTimeout(() => setStatus(null), 3000);
    } catch (error) {
      console.error(error);
      setStatus({ type: "error", message: "Failed to save settings." });
    } finally {
      setSaving(false);
    }
  };

  const fields = [
    {
      id: "groq_api_key",
      label: "Groq API Key",
      desc: "Enables LLaMA 3.3 70B explanations instead of rule-based templates."
    },
    {
      id: "binance_api_key",
      label: "Binance API Key",
      desc: "Optional. Unlocks higher rate limits for fetching historical OHLCV data."
    },
    {
      id: "binance_secret",
      label: "Binance Secret",
      desc: "Required only if using a Binance API Key."
    },
    {
      id: "fred_api_key",
      label: "FRED API Key",
      desc: "Optional. Unlocks official Federal Reserve data. (Falls back to yfinance if omitted)."
    },
    {
      id: "supabase_url",
      label: "Supabase URL",
      desc: "Optional. Cloud sync destination."
    },
    {
      id: "supabase_service_role_key",
      label: "Supabase Service Role Key",
      desc: "Optional. Cloud sync authentication."
    },
    {
      id: "sentry_dsn",
      label: "Sentry DSN",
      desc: "Optional. Enables error tracking."
    },
    {
      id: "wandb_api_key",
      label: "Weights & Biases API Key",
      desc: "Optional. Enables ML model tracking during training."
    }
  ];

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-text flex items-center gap-3">
          <Settings className="text-accent" /> System Settings
        </h1>
        <p className="text-textMuted mt-1">
          Manage API keys and external integrations. Keys are stored securely in your local SQLite database.
        </p>
      </div>

      <div className="bg-surface border border-border rounded-xl p-6 space-y-6">
        {fields.map(field => (
          <div key={field.id} className="grid grid-cols-1 md:grid-cols-3 gap-4 border-b border-border pb-6 last:border-0 last:pb-0">
            <div className="md:col-span-1">
              <label htmlFor={field.id} className="block text-sm font-bold text-text mb-1">
                {field.label}
              </label>
              <p className="text-xs text-textMuted leading-relaxed">
                {field.desc}
              </p>
            </div>
            <div className="md:col-span-2 relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Key size={16} className="text-textMuted" />
              </div>
              <input
                id={field.id}
                type="text"
                className="w-full bg-background border border-border text-text text-sm rounded-lg focus:ring-accent focus:border-accent block pl-10 p-2.5"
                placeholder={settings[field.id] ? "••••••••••••••••" : "Leave blank to use keyless fallback"}
                value={settings[field.id] || ""}
                onChange={(e) => handleChange(field.id, e.target.value)}
              />
            </div>
          </div>
        ))}

        <div className="pt-4 flex items-center justify-between">
          {status ? (
            <div className={`flex items-center gap-2 text-sm font-medium ${status.type === 'success' ? 'text-success' : 'text-danger'}`}>
              {status.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
              {status.message}
            </div>
          ) : <div />}
          
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 bg-accent hover:bg-accent/90 text-white font-bold py-2 px-6 rounded-lg transition-colors disabled:opacity-50"
          >
            {saving ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Save size={18} />
            )}
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </div>
      </div>
    </div>
  );
}
