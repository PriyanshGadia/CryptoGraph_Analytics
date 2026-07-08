const fs = require('fs');
const content = fs.readFileSync('app/sentiment/page.tsx', 'utf8');

const targetImport = /import \{ useMemo \} from "react";/;
const replacementImport = `import { useMemo, useEffect, useState } from "react";\nimport { apiService } from "@/lib/api";`;

const targetData = /const \{ data: trending/
const replacementData = `  const [synthesis, setSynthesis] = useState<any>(null);
  useEffect(() => {
    apiService.getLatestSynthesis().then(setSynthesis).catch(console.error);
  }, []);

  const { data: trending`;

const targetUI = /\{\/\* SECTION 3 - Dual Axis/;
const replacementUI = `        {/* SECTION 2.5 - Qualitative Synthesis */}
        {synthesis && (
          <GlassCard tier={2} shape="shape-squircle" className="p-8 relative overflow-hidden mb-8 group">
            <div className="absolute top-0 right-0 w-64 h-64 bg-accent/5 rounded-full blur-[80px] pointer-events-none" />
            <h3 className="text-xl font-black text-text tracking-tight flex items-center gap-3 mb-6">
              <div className="w-8 h-8 rounded-full glass bg-accent/10 border border-accent/20 flex items-center justify-center">
                <MessageSquareShare className="text-accent" size={16} />
              </div>
              Swarm Synthesis Readout
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 relative z-10">
              <div className="p-5 bg-surface/50 border border-white/5 rounded-sm hover:border-accent/30 transition-colors">
                <h4 className="text-[10px] font-bold font-mono tracking-widest uppercase text-text-muted mb-3 pb-2 border-b border-white/5">Macro Economist</h4>
                <p className="text-sm text-text/90 leading-relaxed font-light">{synthesis.macro_analysis}</p>
              </div>
              <div className="p-5 bg-surface/50 border border-white/5 rounded-sm hover:border-accent/30 transition-colors">
                <h4 className="text-[10px] font-bold font-mono tracking-widest uppercase text-text-muted mb-3 pb-2 border-b border-white/5">On-Chain Detective</h4>
                <p className="text-sm text-text/90 leading-relaxed font-light">{synthesis.onchain_analysis}</p>
              </div>
              <div className="p-5 bg-surface/50 border border-white/5 rounded-sm hover:border-accent/30 transition-colors">
                <h4 className="text-[10px] font-bold font-mono tracking-widest uppercase text-text-muted mb-3 pb-2 border-b border-white/5">Sentiment Analyst</h4>
                <p className="text-sm text-text/90 leading-relaxed font-light">{synthesis.sentiment_analysis}</p>
              </div>
            </div>
            <div className="mt-4 text-right">
              <span className="text-[9px] uppercase tracking-widest font-mono text-text-muted bg-black/40 px-2 py-1 rounded">Subject Asset: {synthesis.symbol}</span>
            </div>
          </GlassCard>
        )}

        {/* SECTION 3 - Dual Axis`;

let newContent = content.replace(targetImport, replacementImport);
newContent = newContent.replace(targetData, replacementData);
newContent = newContent.replace(targetUI, replacementUI);

fs.writeFileSync('app/sentiment/page.tsx', newContent);
console.log("Success");
