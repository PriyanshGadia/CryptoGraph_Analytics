const fs = require('fs');
let content = fs.readFileSync('app/page.tsx', 'utf8');

const targetImports = /import \{ Network, Activity, TrendingUp, TrendingDown, Cpu \} from "lucide-react";/;
const repImports = `import { Network, Activity, TrendingUp, TrendingDown, Cpu, BookOpen, CheckCircle } from "lucide-react";`;
content = content.replace(targetImports, repImports);

const targetSWR = /const \{ data: graphData \} = useSWR\("\/api\/graph\/latest", fetcher\);/;
const repSWR = `const { data: graphData } = useSWR("/api/graph/latest", fetcher);
  const { data: portfolio } = useSWR("/api/portfolio", fetcher);`;
content = content.replace(targetSWR, repSWR);

const targetLedger = /\{\/\* Info Cards \*\/\}/;
const repLedger = `{/* The Ledger (Public Verification) */}
        <div className="flex flex-col gap-6 mt-12 relative z-10">
            <h2 className="text-sm font-bold font-mono tracking-widest text-text-muted uppercase flex items-center gap-2">
                <BookOpen size={16} className="text-accent" /> The Ledger: Live Swarm Intelligence
            </h2>
            
            <GlassCard tier={2} shape="shape-squircle" className="p-8 border-accent/20 shadow-[0_0_30px_rgba(var(--accent),0.1)]">
                <div className="flex flex-col md:flex-row gap-8 justify-between">
                    <div className="max-w-md">
                        <h3 className="text-3xl font-black text-text tracking-tight font-sans mb-3 flex items-center gap-3">
                            Autonomous Portfolio
                            <div className="flex items-center gap-1 text-[10px] bg-success/10 text-success border border-success/20 px-2 py-1 rounded-sm uppercase tracking-widest font-mono">
                                <CheckCircle size={10} /> Verified
                            </div>
                        </h3>
                        <p className="text-sm font-light text-text/80 leading-relaxed mb-6">
                            This platform operates an autonomous trading swarm. Our neural networks and MoA agents execute real capital on-chain based on the predictions you see above. This ledger proves our calibration models perform in production.
                        </p>
                    </div>
                    
                    <div className="flex-1 grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="bg-surface/50 border border-white/5 p-4 rounded-sm">
                            <div className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-bold mb-2">Net Alpha (ROI)</div>
                            <div className={\`text-2xl font-black font-sans tracking-tight \${portfolio?.roi_pct > 0 ? 'text-success drop-shadow-[0_0_10px_rgba(34,197,94,0.3)]' : portfolio?.roi_pct < 0 ? 'text-danger' : 'text-text'}\`}>
                                {portfolio?.roi_pct > 0 ? '+' : ''}{portfolio?.roi_pct?.toFixed(2) || '0.00'}%
                            </div>
                        </div>
                        <div className="bg-surface/50 border border-white/5 p-4 rounded-sm">
                            <div className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-bold mb-2">Total Executed</div>
                            <div className="text-2xl font-black font-sans tracking-tight text-text">
                                {portfolio?.total_trades || 0}
                            </div>
                        </div>
                        <div className="bg-surface/50 border border-white/5 p-4 rounded-sm">
                            <div className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-bold mb-2">Win Rate</div>
                            <div className={\`text-2xl font-black font-sans tracking-tight \${portfolio?.win_rate > 50 ? 'text-success' : 'text-warning'}\`}>
                                {portfolio?.win_rate?.toFixed(1) || '0.0'}%
                            </div>
                        </div>
                        <div className="bg-surface/50 border border-white/5 p-4 rounded-sm">
                            <div className="text-[10px] text-text-muted uppercase tracking-widest font-mono font-bold mb-2">Total Value</div>
                            <div className="text-2xl font-black font-sans tracking-tight text-text">
                                \${(portfolio?.total_value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                            </div>
                        </div>
                    </div>
                </div>
            </GlassCard>
        </div>

        {/* Info Cards */}`;
content = content.replace(targetLedger, repLedger);

fs.writeFileSync('app/page.tsx', content);
console.log("Page patched successfully.");
