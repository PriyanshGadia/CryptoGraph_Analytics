export function generateStaticParams() {
  return [
    { symbol: 'BTC' },
    { symbol: 'ETH' },
    { symbol: 'SOL' }
  ];
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
