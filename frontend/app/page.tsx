"use client";
import { useState } from "react";
import { useEffect } from "react";
import { useMarketSocket } from "@/lib/ws";
import Header from "@/components/Header";
import CandlesChart from "@/components/CandlesChart";
import MarketSphere from "@/components/MarketSphere";
import PositionsTable from "@/components/PositionsTable";
import SignalsFeed from "@/components/SignalsFeed";
import RiskPanel from "@/components/RiskPanel";
import Heatmap from "@/components/Heatmap";
import OrderPanel from "@/components/OrderPanel";
import AIEnginePanel from "@/components/AIEngine";
import ValidationPanel from "@/components/ValidationPanel";

type MainTab = "chart" | "validation";
type SideTab = "positions" | "signals" | "risk";

function Tab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider transition ${
        active ? "bg-white/10 text-text-primary" : "text-text-muted hover:text-text-secondary"
      }`}
    >
      {children}
    </button>
  );
}

export default function Home() {
  useMarketSocket();
  const [mainTab, setMainTab] = useState<MainTab>("chart");
  const [sideTab, setSideTab] = useState<SideTab>("positions");

  useEffect(() => {
    document.body.style.overflow = "hidden";
  }, []);

  return (
    <main className="h-screen flex flex-col p-2 gap-2">
      <Header />

      <div className="flex-1 grid grid-cols-12 gap-2 min-h-0">
        {/* Left: chart / validation + sphere */}
        <section className="col-span-8 flex flex-col gap-2 min-h-0">
          <div className="panel flex-1 flex flex-col min-h-0">
            <div className="flex items-center gap-1 px-2 pt-1.5">
              <Tab active={mainTab === "chart"} onClick={() => setMainTab("chart")}>
                Chart
              </Tab>
              <Tab active={mainTab === "validation"} onClick={() => setMainTab("validation")}>
                Validation
              </Tab>
            </div>
            {mainTab === "chart" ? <CandlesChart /> : <ValidationPanel />}
          </div>

          <div className="panel h-[280px] flex flex-col">
            <MarketSphere />
          </div>
        </section>

        {/* Right: heatmap + order + AI + positions/signals/risk */}
        <aside className="col-span-4 flex flex-col gap-2 min-h-0">
          <div className="panel h-[170px]">
            <Heatmap />
          </div>

          <div className="panel h-[360px] flex flex-col">
            <OrderPanel />
          </div>

          <div className="panel h-[320px] flex flex-col">
            <AIEnginePanel />
          </div>

          <div className="panel flex-1 min-h-0 flex flex-col">
            <div className="flex items-center gap-1 px-2 pt-1.5">
              <Tab active={sideTab === "positions"} onClick={() => setSideTab("positions")}>
                Positions
              </Tab>
              <Tab active={sideTab === "signals"} onClick={() => setSideTab("signals")}>
                Signals
              </Tab>
              <Tab active={sideTab === "risk"} onClick={() => setSideTab("risk")}>
                Risk
              </Tab>
            </div>
            {sideTab === "positions" && <PositionsTable />}
            {sideTab === "signals" && <SignalsFeed />}
            {sideTab === "risk" && <RiskPanel />}
          </div>
        </aside>
      </div>
    </main>
  );
}
