const fs = require('fs');
const content = fs.readFileSync('app/graph/page.tsx', 'utf8');

const target = /linkDirectionalParticleColor=\{linkColor\}\s*linkDirectionalParticleWidth=\{\(link: any\) => Math\.max\(2, linkWidth\(link\) \* 1\.5\)\}\s*linkDirectionalParticleSpeed=\{0\.015\}/;

const replacement = `linkDirectionalParticleColor={(link: any) => {
              const ms = link.motif_similarity || 0;
              return ms > 0.4 ? "rgba(34, 197, 94, 0.9)" : ms < -0.4 ? "rgba(239, 68, 68, 0.9)" : "rgba(212, 165, 71, 0.8)";
            }}
            linkDirectionalParticleWidth={(link: any) => Math.max(2, (Math.abs(link.motif_similarity || 0.5) * 4))}
            linkDirectionalParticleSpeed={(link: any) => 0.01 + (Math.abs(link.motif_similarity || 0.1) * 0.025)}`;

const newContent = content.replace(target, replacement);

if (newContent !== content) {
    fs.writeFileSync('app/graph/page.tsx', newContent);
    console.log("Graph Page patched successfully.");
} else {
    console.log("Regex mismatch in Graph Page.");
}
