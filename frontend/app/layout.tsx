import type { Metadata } from "next";
import { Inter, Space_Mono } from "next/font/google";
import "./globals.css";
import Link from "next/link";
import { Activity, BarChart2, Share2, Shield, TrendingUp, Target, Grid3x3, SlidersHorizontal, Network, Brain } from "lucide-react";
import { StatusIndicator } from "@/components/StatusIndicator";
import { GlobalSearch } from "@/components/GlobalSearch";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const spaceMono = Space_Mono({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-space-mono",
});

export const metadata: Metadata = {
  title: "ST-GCN Crypto Forecasting",
  description: "Advanced crypto forecasting platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} ${spaceMono.variable} antialiased`}>
        <div className="flex h-screen overflow-hidden">
          {/* Sidebar */}
          <aside className="w-64 border-r border-border bg-surface flex flex-col">
            <div className="p-6 border-b border-border">
              <h1 className="text-xl font-bold text-accent">ST-GCN Crypto</h1>
              <p className="text-xs text-[#64748b] mt-1 font-mono">⌘K to search</p>
            </div>
            <nav className="flex-1 p-4 space-y-6 overflow-y-auto">
              
              {/* MARKETS GROUP */}
              <div>
                <h2 className="text-[10px] font-bold text-[#64748b] uppercase tracking-wider px-3 mb-2">Markets</h2>
                <div className="space-y-1">
                  <Link href="/market" className="flex items-center gap-3 px-3 py-2 text-textMuted hover:text-text hover:bg-border/50 rounded-md transition-colors">
                    <BarChart2 size={18} />
                    <span className="text-sm font-medium">Market Data</span>
                  </Link>
                  <Link href="/screener" className="flex items-center gap-3 px-3 py-2 text-textMuted hover:text-text hover:bg-border/50 rounded-md transition-colors">
                    <SlidersHorizontal size={18} />
                    <span className="text-sm font-medium">Screener</span>
                  </Link>
                </div>
              </div>

              {/* ANALYSIS GROUP */}
              <div>
                <h2 className="text-[10px] font-bold text-[#64748b] uppercase tracking-wider px-3 mb-2">Analysis</h2>
                <div className="space-y-1">
                  <Link href="/graph" className="flex items-center gap-3 px-3 py-2 text-textMuted hover:text-text hover:bg-border/50 rounded-md transition-colors">
                    <Network size={18} />
                    <span className="text-sm font-medium">Network Graph</span>
                  </Link>
                  <Link href="/correlations" className="flex items-center gap-3 px-3 py-2 text-textMuted hover:text-text hover:bg-border/50 rounded-md transition-colors">
                    <Grid3x3 size={18} />
                    <span className="text-sm font-medium">Correlations</span>
                  </Link>
                  <Link href="/sentiment" className="flex items-center gap-3 px-3 py-2 text-textMuted hover:text-text hover:bg-border/50 rounded-md transition-colors">
                    <Activity size={18} />
                    <span className="text-sm font-medium">Sentiment</span>
                  </Link>
                  <Link href="/risk" className="flex items-center gap-3 px-3 py-2 text-textMuted hover:text-text hover:bg-border/50 rounded-md transition-colors">
                    <Shield size={18} />
                    <span className="text-sm font-medium">Risk Dashboard</span>
                  </Link>
                </div>
              </div>

              {/* AI & MODELS GROUP */}
              <div>
                <h2 className="text-[10px] font-bold text-[#64748b] uppercase tracking-wider px-3 mb-2">AI & Models</h2>
                <div className="space-y-1">
                  <Link href="/explain" className="flex items-center gap-3 px-3 py-2 text-textMuted hover:text-text hover:bg-border/50 rounded-md transition-colors">
                    <Brain size={18} />
                    <span className="text-sm font-medium">Explain AI</span>
                  </Link>
                  <Link href="/predictions" className="flex items-center gap-3 px-3 py-2 text-textMuted hover:text-text hover:bg-border/50 rounded-md transition-colors">
                    <TrendingUp size={18} />
                    <span className="text-sm font-medium">Predictions</span>
                  </Link>
                  <Link href="/performance" className="flex items-center gap-3 px-3 py-2 text-textMuted hover:text-text hover:bg-border/50 rounded-md transition-colors">
                    <Target size={18} />
                    <span className="text-sm font-medium">Performance</span>
                  </Link>
                </div>
              </div>

            </nav>
            <StatusIndicator />
          </aside>

          {/* Main Content */}
          <main className="flex-1 overflow-y-auto bg-background p-8 relative">
            <GlobalSearch />
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
