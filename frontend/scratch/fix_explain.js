const fs = require('fs');
const content = fs.readFileSync('app/explain/page.tsx', 'utf8');

const targetRegex = /\{\s*explanation\.debate_transcript[\s\S]*?(?=\{\s*explanation\.news_sources)/;

const replacement = `            {/* Debate Council UI */}
            {(explanation.bull_case || explanation.bear_case || explanation.risk_case) && (
              <div className="mt-8 pt-6 border-t border-white/10">
                <div className="text-[10px] text-text uppercase tracking-widest font-mono font-bold mb-4 flex items-center gap-2">
                  <Bot size={14} className="text-accent" /> Debate Council (Multi-Agent Consensus)
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {explanation.bull_case && (
                    <div className="p-5 glass bg-success/5 border border-success/20 rounded-sm">
                      <div className="text-xs font-bold font-mono tracking-widest uppercase text-success mb-3 flex items-center gap-2">
                        <TrendingUp size={14} /> Bull Persona
                      </div>
                      <p className="text-sm font-light text-text/80 leading-relaxed">{explanation.bull_case}</p>
                    </div>
                  )}
                  {explanation.bear_case && (
                    <div className="p-5 glass bg-danger/5 border border-danger/20 rounded-sm">
                      <div className="text-xs font-bold font-mono tracking-widest uppercase text-danger mb-3 flex items-center gap-2">
                        <TrendingDown size={14} /> Bear Persona
                      </div>
                      <p className="text-sm font-light text-text/80 leading-relaxed">{explanation.bear_case}</p>
                    </div>
                  )}
                  {explanation.risk_case && (
                    <div className="p-5 glass bg-warning/5 border border-warning/20 rounded-sm">
                      <div className="text-xs font-bold font-mono tracking-widest uppercase text-warning mb-3 flex items-center gap-2">
                        <AlertCircle size={14} /> Risk Overseer
                      </div>
                      <p className="text-sm font-light text-text/80 leading-relaxed">{explanation.risk_case}</p>
                    </div>
                  )}
                </div>
              </div>
            )}
            
            `;

if (targetRegex.test(content)) {
  fs.writeFileSync('app/explain/page.tsx', content.replace(targetRegex, replacement));
  console.log("Success");
} else {
  console.log("Target not found");
}
