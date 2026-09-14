"use client";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, Html } from "@react-three/drei";
import { useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import * as THREE from "three";
import { api, HeatmapItem } from "@/lib/api";
import { useStore } from "@/store/useStore";

const SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"];
const SPHERE_RADIUS = 1.15;

// توزيع فيبوناتشي — نقاط متساوية على الكرة
function fibonacciSphere(n: number, radius: number): [number, number, number][] {
  const pts: [number, number, number][] = [];
  const gold = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = gold * i;
    pts.push([
      Math.cos(theta) * r * radius,
      y * radius,
      Math.sin(theta) * r * radius,
    ]);
  }
  return pts;
}

// ============ نواة صغيرة + هالة ============
function Nucleus() {
  const ref = useRef<THREE.Mesh>(null!);
  useFrame((state) => {
    if (ref.current) {
      const s = 1 + Math.sin(state.clock.elapsedTime * 2) * 0.15;
      ref.current.scale.setScalar(s);
    }
  });

  return (
    <group>
      <mesh ref={ref}>
        <sphereGeometry args={[0.08, 32, 32]} />
        <meshBasicMaterial color="#7dffb8" />
      </mesh>
      <pointLight color="#00e08f" intensity={2.5} distance={2.5} />
    </group>
  );
}

// ============ هيكل الكرة: شبكة longitude/latitude ============
function SphereWireframe() {
  const ref = useRef<THREE.Group>(null!);
  useFrame((_, dt) => {
    if (ref.current) ref.current.rotation.y += dt * 0.05;
  });

  return (
    <group ref={ref}>
      {/* شبكة كروية أساسية */}
      <mesh>
        <sphereGeometry args={[SPHERE_RADIUS, 32, 32]} />
        <meshBasicMaterial
          color="#00e08f"
          wireframe
          transparent
          opacity={0.06}
        />
      </mesh>

      {/* شبكة تفصيلية */}
      <mesh>
        <sphereGeometry args={[SPHERE_RADIUS, 16, 16]} />
        <meshBasicMaterial
          color="#3d9cff"
          wireframe
          transparent
          opacity={0.04}
        />
      </mesh>
    </group>
  );
}

// ============ خطوط ربط بين عقد متقاربة ============
function Connections({
  positions,
}: {
  positions: [number, number, number][];
}) {
  const ref = useRef<THREE.Group>(null!);
  useFrame((_, dt) => {
    if (ref.current) ref.current.rotation.y += dt * 0.05;
  });

  // ربط كل عقدة بجارتها (أقرب نقطة)
  const links = useMemo(() => {
    const out: Array<[number, number]> = [];
    for (let i = 0; i < positions.length; i++) {
      let nearest = -1;
      let minDist = Infinity;
      for (let j = 0; j < positions.length; j++) {
        if (i === j) continue;
        const dx = positions[i][0] - positions[j][0];
        const dy = positions[i][1] - positions[j][1];
        const dz = positions[i][2] - positions[j][2];
        const d = dx * dx + dy * dy + dz * dz;
        if (d < minDist) {
          minDist = d;
          nearest = j;
        }
      }
      if (nearest >= 0 && i < nearest) out.push([i, nearest]);
    }
    return out;
  }, [positions]);

  return (
    <group ref={ref}>
      {links.map(([a, b], i) => {
        const p1 = new THREE.Vector3(...positions[a]);
        const p2 = new THREE.Vector3(...positions[b]);
        const mid = p1.clone().add(p2).multiplyScalar(0.5);
        const midLen = mid.length();
        // انحناء نحو السطح
        mid.normalize().multiplyScalar(SPHERE_RADIUS * 0.98);

        // منحنى بيزييه بسيط عبر نقطتين
        const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
        const geo = new THREE.BufferGeometry().setFromPoints(
          curve.getPoints(20)
        );

        return (
          <line key={i}>
            <primitive object={geo} attach="geometry" />
            <lineBasicMaterial color="#00e08f" transparent opacity={0.35} linewidth={1} />
          </line>
        );
      })}
    </group>
  );
}

// ============ عقدة رمز على السطح ============
type NodeProps = {
  position: [number, number, number];
  symbol: string;
  changePct: number;
  index: number;
  frozen: boolean;
};

function SymbolNode({ position, symbol, changePct, index, frozen }: NodeProps) {
  const meshRef = useRef<THREE.Mesh>(null!);
  const haloRef = useRef<THREE.Mesh>(null!);

  const up = changePct >= 0;
  const color = up ? "#00e08f" : "#ff3d5c";
  const intensity = Math.min(Math.abs(changePct) / 2, 1);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const pulse = frozen ? 1 : 1 + Math.sin(t * 2.5 + index * 1.3) * 0.12;
    if (meshRef.current) meshRef.current.scale.setScalar(pulse);
    if (haloRef.current) {
      const hs = 1 + Math.sin(t * 1.5 + index) * 0.2;
      haloRef.current.scale.setScalar(hs);
    }
  });

  const nodeSize = 0.07 + intensity * 0.04;

  return (
    <group position={position}>
      {/* العقدة الصلبة */}
      <mesh ref={meshRef}>
        <sphereGeometry args={[nodeSize, 24, 24]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={2.2}
          roughness={0.2}
          metalness={0.3}
          toneMapped={false}
        />
      </mesh>

      {/* الهالة */}
      <mesh ref={haloRef}>
        <sphereGeometry args={[nodeSize * 2.2, 16, 16]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.18}
          side={THREE.BackSide}
          depthWrite={false}
        />
      </mesh>

      {/* إضاءة محلية */}
      <pointLight color={color} intensity={0.8} distance={0.7} />

      {/* التسمية — تظهر خارج الكرة */}
      <Html
        position={[0, nodeSize + 0.14, 0]}
        center
        distanceFactor={3.2}
        style={{ pointerEvents: "none", userSelect: "none" }}
      >
        <div className="text-center whitespace-nowrap px-1.5 py-0.5 rounded bg-bg-base/70 backdrop-blur-sm">
          <div
            className="text-[10px] font-mono font-bold leading-tight"
            style={{ color }}
          >
            {symbol}
          </div>
          <div
            className="text-[9px] font-mono leading-tight"
            style={{ color: up ? "#7dffb8" : "#ff8a9c" }}
          >
            {up ? "+" : ""}
            {changePct.toFixed(2)}%
          </div>
        </div>
      </Html>
    </group>
  );
}

// ============ المشهد ============
function Scene() {
  const { data } = useQuery({
    queryKey: ["heatmap"],
    queryFn: api.heatmap,
    refetchInterval: 15_000,
  });

  const positions = useMemo(
    () => fibonacciSphere(SYMBOLS.length, SPHERE_RADIUS),
    []
  );

  const itemsMap = useMemo(() => {
    const m: Record<string, HeatmapItem> = {};
    for (const it of data?.items ?? []) m[it.symbol] = it;
    return m;
  }, [data]);

  return (
    <>
      <ambientLight intensity={0.4} />
      <pointLight position={[4, 4, 4]} intensity={0.9} />
      <pointLight position={[-3, -3, -3]} intensity={0.4} color="#3d9cff" />

      <Nucleus />
      <SphereWireframe />
      <Connections positions={positions} />

      {SYMBOLS.map((sym, i) => {
        const it = itemsMap[sym];
        return (
          <SymbolNode
            key={sym}
            position={positions[i]}
            symbol={sym}
            changePct={it?.change_pct ?? 0}
            index={i}
            frozen={false}
          />
        );
      })}
    </>
  );
}

export default function MarketSphere() {
  const { connected } = useStore();

  return (
    <>
      <div className="panel-title flex items-center justify-between">
        <span>Correlation Engine</span>
        <span className="text-text-muted normal-case tracking-normal text-[10px]">
          {connected ? "● live" : "idle"}
        </span>
      </div>
      <div className="flex-1 min-h-0">
        <Canvas
          camera={{ position: [0, 0.5, 4], fov: 45 }}
          dpr={[1, 2]}
          gl={{ antialias: true, alpha: true }}
        >
          <Scene />
          <OrbitControls
            enablePan={false}
            enableZoom={true}
            minDistance={2.5}
            maxDistance={6}
            autoRotate
            autoRotateSpeed={0.5}
          />
        </Canvas>
      </div>
    </>
  );
}