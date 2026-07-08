const fs = require('fs');
const content = fs.readFileSync('app/risk/page.tsx', 'utf8');

const target = `          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {[
              { label: "Mean Volatility", value: \`\${data.average_volatility?.toFixed(2) ?? "0"}%\`, icon: Activity, color: "text-accent" },`;

const replacement = `          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {data.average_volatility !== undefined && (
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

if (content.includes(target)) {
  fs.writeFileSync('app/risk/page.tsx', content.replace(target, replacement));
  console.log("Success");
} else {
  console.log("Target not found");
}
