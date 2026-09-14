"use client";
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

export default function Home() {
  useMarketSocket();

  useEffect(() => {
    document.body.style.overflow = "hidden";
  }, []);

  return (
    <main className="h-screen flex flex-col p-2 gap-2">
      <Header />

      <div className="flex-1 grid grid-cols-12 gap-2 min-h-0">
        {/* Left: Chart + Sphere */}
        <section className="col-span-8 flex flex-col gap-2 min-h-0">
          <div className="panel flex-1 flex flex-col min-h-0">
            <CandlesChart />
          </div>

          <div className="panel h-[300px] flex flex-col">
            <MarketSphere />
          </div>
        </section>

        {/* Right: Heatmap + Order + Positions + Signals/Risk */}
        <aside className="col-span-4 flex flex-col gap-2 min-h-0">
          <div className="panel h-[180px]">
            <Heatmap />
          </div>

          <div className="panel h-[380px] flex flex-col">
            <OrderPanel />
          </div>

          <div className="panel h-[320px] flex flex-col">
            <AIEnginePanel />
          </div>

          <div className="panel flex-1 min-h-0 flex flex-col">
            <PositionsTable />
          </div>
        </aside>
      </div>
    </main>
  );
}