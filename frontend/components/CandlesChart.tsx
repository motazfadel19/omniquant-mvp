"use client";
import { useEffect, useRef } from "react";
import {
  createChart, IChartApi, ISeriesApi,
  CandlestickSeries, HistogramSeries, ColorType, CrosshairMode,
} from "lightweight-charts";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useStore } from "@/store/useStore";

export default function CandlesChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const { symbol, timeframe } = useStore();

  const { data, isLoading } = useQuery({
    queryKey: ["candles", symbol, timeframe],
    queryFn: () => api.candles(symbol, timeframe, 500),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0f1117" },
        textColor: "#8b94a8",
        fontSize: 10,
        fontFamily: "var(--font-jetbrains)",
      },
      grid: {
        vertLines: { color: "#14171f" },
        horzLines: { color: "#14171f" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: "#1f2430",
        scaleMargins: { top: 0.08, bottom: 0.25 },
      },
      timeScale: {
        borderColor: "#1f2430",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: true,
      handleScale: true,
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#00e08f",
      downColor: "#ff3d5c",
      borderUpColor: "#00e08f",
      borderDownColor: "#ff3d5c",
      wickUpColor: "#00e08f",
      wickDownColor: "#ff3d5c",
    });

    const volume = chart.addSeries(HistogramSeries, {
      color: "#2a3140",
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    volume.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    chartRef.current = chart;
    candleRef.current = candles;
    volumeRef.current = volume;

    const onResize = () => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };
    onResize();
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
    };
  }, []);

  // Update data
  useEffect(() => {
    if (!data?.candles || !candleRef.current || !volumeRef.current) return;

    const candles = data.candles.map(c => ({
      time: c.time as any,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    const volumes = data.candles.map(c => ({
      time: c.time as any,
      value: c.tick_volume,
      color: c.close >= c.open ? "#00e08f33" : "#ff3d5c33",
    }));

    candleRef.current.setData(candles);
    volumeRef.current.setData(volumes);
    chartRef.current?.timeScale().fitContent();
  }, [data]);
  // أضف هذا السطر داخل الـ component
  const chartTimeframeRef = useRef<string>(timeframe);

  useEffect(() => {
    if (chartTimeframeRef.current !== timeframe) {
      chartTimeframeRef.current = timeframe;
      chartRef.current?.timeScale().fitContent();
    }
  }, [timeframe]);

  return (
    <>
      <div className="panel-title flex items-center justify-between">
        <span>{symbol} · {timeframe} · Candles</span>
        <span className="text-text-muted normal-case tracking-normal">
          {isLoading ? "loading…" : `${data?.candles.length ?? 0} bars`}
        </span>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0" />
    </>
  );
}