import type { Metadata } from "next";
import { Inter, Outfit } from "next/font/google";
import "./globals.css";
import Link from "next/link";
import { Sidebar } from "@/components/Sidebar";
import { GlobalSearch } from "@/components/GlobalSearch";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });

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
      <body className={`${inter.variable} ${outfit.variable} font-outfit antialiased`}>
        <div className="flex h-screen overflow-hidden bg-[#050505]">
          {/* Sidebar */}
          <Sidebar />

          {/* Main Content */}
          <main className="flex-1 overflow-y-auto overflow-x-hidden flex flex-col relative" style={{ msOverflowStyle: 'none', scrollbarWidth: 'none' }}>
            <div className="flex-1 p-8">
              <GlobalSearch />
              {children}
            </div>
            
            {/* Mandatory Regulatory Disclaimer */}
            <footer className="w-full bg-surface border-t border-border p-4 text-center mt-auto">
              <p className="text-[10px] leading-relaxed text-textMuted max-w-5xl mx-auto uppercase tracking-wide">
                <strong>IMPORTANT LEGAL DISCLAIMER:</strong> This platform is for educational and research purposes only. 
                The ST-GCN model and AI Swarm outputs do NOT constitute financial, investment, or legal advice. 
                Cryptocurrency trading involves substantial risk of loss and is not suitable for every investor. 
                Simulated PnL does not represent actual trading and may not account for all market factors like severe liquidity crises. 
                Always consult with a licensed financial advisor before making any investment decisions. 
                By using this platform, you agree that ST-GCN and its creators are not liable for any financial losses.
              </p>
            </footer>
          </main>
        </div>
      </body>
    </html>
  );
}
