const fs = require('fs');
let content = fs.readFileSync('app/explain/page.tsx', 'utf8');

const target1 = /import \{ BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell \} from "recharts";\s*import \{ useChartPalette \} from "@\/lib\/useChartPalette";/;
const rep1 = `import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { useChartPalette } from "@/lib/useChartPalette";
import dynamic from 'next/dynamic';
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });`;

content = content.replace(target1, rep1);

const target2 = /<h3 className="text-sm font-bold font-mono tracking-widest uppercase text-accent mb-4 flex items-center gap-2">[\s\S]*?<\/ResponsiveContainer>\s*<\/div>/;
const rep2 = `<h3 className="text-sm font-bold font-mono tracking-widest uppercase text-accent mb-4 flex items-center gap-2">
                  <BarChart2 size={16} /> Feature Attribution Subgraph
                </h3>
                <div className="h-64 w-full relative overflow-hidden rounded-sm border border-white/5 bg-black/20" style={{ cursor: 'crosshair' }}>
                  <ForceGraph2D 
                    width={800}
                    height={256}
                    graphData={{
                        nodes: [
                            { id: explanation.symbol, name: explanation.symbol, val: 20, color: 'rgba(var(--accent), 1)' },
                            ...Object.entries(explanation.top_features).map(([k, v]) => ({ id: k, name: k, val: Math.max(2, v * 30), color: 'rgba(100, 116, 139, 0.8)' }))
                        ],
                        links: Object.entries(explanation.top_features).map(([k, v]) => ({ source: k, target: explanation.symbol, value: v }))
                    }}
                    nodeLabel="name"
                    nodeColor="color"
                    nodeRelSize={6}
                    linkColor={() => 'rgba(255,255,255,0.2)'}
                    linkWidth={(link) => link.value * 5}
                    linkDirectionalParticles={3}
                    linkDirectionalParticleWidth={(link) => link.value * 3}
                    linkDirectionalParticleSpeed={(link) => link.value * 0.05}
                    d3AlphaDecay={0.02}
                    d3VelocityDecay={0.3}
                    cooldownTicks={100}
                    backgroundColor="transparent"
                  />
                </div>`;

content = content.replace(target2, rep2);

fs.writeFileSync('app/explain/page.tsx', content);
console.log("Explain Page patched successfully.");
