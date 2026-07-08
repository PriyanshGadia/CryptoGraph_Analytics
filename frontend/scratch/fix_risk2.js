const fs = require('fs');
const content = fs.readFileSync('app/risk/page.tsx', 'utf8');

const targetRegex = /\{\[\s*\{\s*label:\s*"Mean Volatility",\s*value:\s*`\$\{data\.average_volatility\?\.toFixed\(2\)\s*\?\?\s*"0"\}%`,\s*icon:\s*Activity,\s*color:\s*"text-accent"\s*\},/g;

const replacement = `{data.average_volatility !== undefined && (
               <RiskLivingGauge 
                  volatility={data.average_volatility} 
                  intervalSpread={
                    preds && preds.length > 0 
                      ? preds.reduce((acc, p) => acc + (p.confidence_interval ? (p.confidence_interval[1] - p.confidence_interval[0]) : 0), 0) / (preds.filter(p => p.confidence_interval).length || 1) 
                      : undefined
                  } 
               />
            )}
            {[`;

if (targetRegex.test(content)) {
  fs.writeFileSync('app/risk/page.tsx', content.replace(targetRegex, replacement));
  console.log("Success");
} else {
  console.log("Target not found");
}
