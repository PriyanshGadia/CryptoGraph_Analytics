import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import { Console } from "@/components/Console";
import { GlobalSearch } from "@/components/GlobalSearch";
import { CurrencyProvider } from "@/components/CurrencyContext";
import { ThemeProvider } from "@/components/ThemeProvider";

import { Fraunces, Bricolage_Grotesque, Geist_Mono } from "next/font/google";

const fraunces = Fraunces({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-display", display: "swap" });
const bricolage = Bricolage_Grotesque({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-sans", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-mono", display: "swap" });

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
    <html lang="en" suppressHydrationWarning className={`${fraunces.variable} ${bricolage.variable} ${geistMono.variable}`}>
      <body className="font-sans antialiased">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <CurrencyProvider>
            {/* Background Texture Overlay */}
            <div className="fixed inset-0 z-[-1] pointer-events-none opacity-[0.03] dark:opacity-[0.05] bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0IiBoZWlnaHQ9IjQiPjxyZWN0IHdpZHRoPSI0IiBoZWlnaHQ9IjQiIGZpbGw9IiNmZmYiIGZpbGwtb3BhY2l0eT0iMC4wMSIvPjxwYXRoIGQ9Ik0wIDBMMCA0TDEgNEwxIDBaTTAgM0w0IDNMNCA0TDAgNFoiIGZpbGw9IiMwMDAiIGZpbGwtb3BhY2l0eT0iMC4wNSIvPjwvc3ZnPg==')] mix-blend-overlay"></div>
            
            <div className="flex h-screen overflow-hidden bg-background transition-colors duration-500 p-3 pb-20 md:p-3 md:pl-20">
              {/* Sidebar: Floating */}
              <Console />

              {/* Main Content */}
              <main className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden flex flex-col relative shape-seal glass-1 transition-all duration-500" style={{ msOverflowStyle: 'none', scrollbarWidth: 'none' }}>
                <div className="flex-1 p-8">
                  <GlobalSearch />
                  {children}
                </div>
                
                {/* Mandatory Regulatory Disclaimer */}
                <footer className="w-full bg-surface/50 border-t border-border p-4 text-center mt-auto backdrop-blur-sm">
                  <p className="text-[10px] leading-relaxed text-text-muted max-w-5xl mx-auto uppercase tracking-wide">
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
          </CurrencyProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

