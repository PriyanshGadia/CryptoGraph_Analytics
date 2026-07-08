const fs = require('fs');
const content = fs.readFileSync('app/predictions/page.tsx', 'utf8');

const target1 = /<div className="space-y-1 text-right">\s*<div className="text-\[9px\] text-text-muted uppercase tracking-widest font-bold">Volatility<\/div>\s*<VolatilityChip regime=\{p.volatility_regime \|\| 'medium'\} \/>\s*<\/div>\s*<\/div>/g;

const replacement1 = `<div className="space-y-1 text-right">
                          <div className="text-[9px] text-text-muted uppercase tracking-widest font-bold">Volatility</div>
                          <VolatilityChip regime={p.volatility_regime || 'medium'} />
                        </div>
                      </div>

                      {/* Conformal Prediction Interval Spread */}
                      {p.confidence_interval && (
                        <div className="mt-4 flex items-center justify-between bg-black/20 p-2 rounded-sm border border-white/5">
                            <span className="text-[9px] uppercase tracking-widest font-mono text-text-muted">Expected Spread</span>
                            <span className="text-[10px] font-mono font-bold text-text">
                                [{p.confidence_interval[0].toFixed(1)}% - {p.confidence_interval[1].toFixed(1)}%]
                            </span>
                        </div>
                      )}`;

let newContent = content.replace(target1, replacement1);

// Add Verdict Stamp right over the card. We can put it in a corner or as a large watermark
const target2 = /<div className="absolute top-0 left-0 w-full h-1 bg-white\/5 group-hover:h-1\.5 transition-all"/;
const replacement2 = `
                      {/* VERDICT STAMP */}
                      <div className="absolute top-6 right-6 opacity-0 group-hover:opacity-10 transition-opacity pointer-events-none rotate-[-15deg] scale-[2.5]">
                         {isUp ? <TrendingUp size={64} className="text-success" /> : isDown ? <TrendingDown size={64} className="text-danger" /> : <Minus size={64} className="text-text-muted" />}
                      </div>
                      
                      <div className="absolute top-0 left-0 w-full h-1 bg-white/5 group-hover:h-1.5 transition-all"`;

newContent = newContent.replace(target2, replacement2);

fs.writeFileSync('app/predictions/page.tsx', newContent);
console.log("Predictions Page patched successfully.");
