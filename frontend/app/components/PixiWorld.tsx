"use client";
import * as PIXI from "pixi.js";
import { useEffect, useRef, useState, useCallback } from "react";
import { WorldEventBus } from "../simulation/WorldEvents";
import { DISPLAY_MAX_W, DISPLAY_MAX_H, ZONE_LAYOUTS_FRACTIONAL, STORE_THEMES } from "../simulation/entities/WorldLayout";
import type { StoreZone } from "../simulation/entities/WorldLayout";
import { CustomerEntity, CustomerBubbleUpdate } from "../simulation/entities/CustomerEntity";
import { AgentEntity, AgentBubbleUpdate } from "../simulation/entities/AgentEntity";
import type { StoreType } from "../simulation/WorldEvents";

interface Emotion { customerId: string; emoji: string; x: number; y: number; }
interface Bubble { text: string; x: number; y: number; }
interface Dims { w: number; h: number; }

export default function PixiWorld({ storeType, debug = false }: { storeType: StoreType; debug?: boolean }) {
  const mountRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<PIXI.Application | null>(null);
  const charLayerRef = useRef<PIXI.Container | null>(null);
  const customersRef = useRef<Map<string, CustomerEntity>>(new Map());
  const agentRef = useRef<AgentEntity | null>(null);
  const storeTypeRef = useRef<StoreType>(storeType);
  const dimsRef = useRef<Dims>({ w: DISPLAY_MAX_W, h: DISPLAY_MAX_H });
  const pendingTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  const [dims, setDims] = useState<Dims>({ w: DISPLAY_MAX_W, h: DISPLAY_MAX_H });
  const [emotions, setEmotions] = useState<Map<string, Emotion>>(new Map());
  const [agentBubble, setAgentBubble] = useState<Bubble & { visible: boolean }>({ visible: false, text: "", x: 0, y: 0 });
  const [customerBubbles, setCustomerBubbles] = useState<Map<string, Bubble>>(new Map());

  // ── Measure the real background image so the display box matches its
  // actual aspect ratio — this is what stops "cover" from zoom-cropping
  // stores whose source image isn't the same shape as the others.
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const aspect = img.naturalWidth / img.naturalHeight;
      let w = DISPLAY_MAX_W, h = Math.round(w / aspect);
      if (h > DISPLAY_MAX_H) { h = DISPLAY_MAX_H; w = Math.round(h * aspect); }
      dimsRef.current = { w, h };
      setDims({ w, h });
    };
    img.src = STORE_THEMES[storeType].bgImage;
  }, [storeType]);

  const zonePx = useCallback((zone: StoreZone): { x: number; y: number } => {
    const f = ZONE_LAYOUTS_FRACTIONAL[storeTypeRef.current][zone];
    const { w, h } = dimsRef.current;
    return { x: f.fx * w, y: f.fy * h };
  }, []);

  const clamp = useCallback((rawX: number, rawY: number) => {
    const { w, h } = dimsRef.current;
    const bw = 170, bh = 60, pad = 8;
    return { x: Math.max(pad, Math.min(w - bw - pad, rawX - bw / 2)), y: Math.max(pad, Math.min(h - bh - pad, rawY - bh)) };
  }, []);

  const track = (id: ReturnType<typeof setTimeout>) => { pendingTimersRef.current.push(id); return id; };
  const clearTrackedTimers = () => { pendingTimersRef.current.forEach(clearTimeout); pendingTimersRef.current = []; };

  const resetWorld = useCallback((type: StoreType, startZone?: StoreZone) => {
    const layer = charLayerRef.current;
    if (!layer) return;

    clearTrackedTimers();
    layer.removeChildren();
    
    customersRef.current.forEach(c => c.destroy());
    customersRef.current.clear();
    agentRef.current?.destroy();

    setTimeout(() => {
      setEmotions(new Map());
      setCustomerBubbles(new Map());
      setAgentBubble({ visible: false, text: "", x: 0, y: 0 });
    }, 0);

    const agent = new AgentEntity(type, (u: AgentBubbleUpdate) => {
      if (!u.visible) setAgentBubble({ visible: false, text: "", x: 0, y: 0 });
      else { 
        const p = clamp(u.x, u.y); 
        setAgentBubble({ visible: true, text: u.text, ...p }); 
      }
    });

    const startPoint = startZone ? zonePx(startZone) : zonePx("agent_desk");
        agent.container.x = startPoint.x; 
        agent.container.y = startPoint.y;
        (agent as any).targetX = startPoint.x;
        (agent as any).targetY = startPoint.y;

        layer.addChild(agent.container);
        agentRef.current = agent;
    }, [clamp, zonePx]);

  useEffect(() => {
    storeTypeRef.current = storeType;
    agentRef.current?.setStoreType(storeType);
    if (appRef.current) resetWorld(storeType);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeType]);

  // rebuild the Pixi app whenever measured dims change size (store switch)
  useEffect(() => {
    let isDestroyed = false;
    const app = new PIXI.Application();

    const setup = async () => {
      await app.init({ width: dims.w, height: dims.h, backgroundAlpha: 0, antialias: true });
      if (isDestroyed) return;
      appRef.current = app;
      mountRef.current?.innerHTML && (mountRef.current.innerHTML = "");
      mountRef.current?.appendChild(app.canvas);
      (app.canvas as HTMLCanvasElement).style.position = "absolute";
      (app.canvas as HTMLCanvasElement).style.inset = "0";

      const layer = new PIXI.Container();
      layer.sortableChildren = true;
      charLayerRef.current = layer;
      app.stage.addChild(layer);

      resetWorld(storeTypeRef.current);

      app.ticker.add((ticker) => {
        agentRef.current?.update(ticker.deltaTime);
        customersRef.current.forEach(c => c.update(ticker.deltaTime));
      });
    };
    setup();

    const bubbleInterval = setInterval(() => {
      if (isDestroyed) return;
      const agent = agentRef.current;
      if (agent) {
        setAgentBubble(prev => {
          if (!prev.visible) return prev;
          const p = clamp(agent.container.x, agent.container.y);
          return { visible: true, text: prev.text, ...p };
        });
      }
      setCustomerBubbles(prev => {
        if (prev.size === 0) return prev;
        let changed = false;
        const next = new Map(prev);
        next.forEach((b, id) => {
          const c = customersRef.current.get(id);
          if (!c) { next.delete(id); changed = true; return; }
          const p = clamp(c.container.x, c.container.y);
          if (p.x !== b.x || p.y !== b.y) { next.set(id, { text: b.text, ...p }); changed = true; }
        });
        return changed ? next : prev;
      });
    }, 60);

    const unsub = WorldEventBus.on((event) => {
      console.log("[PIXI WORLD EVENT]", event);
      const layer = charLayerRef.current;
      if (!layer || isDestroyed) return;

      switch (event.type) {
        case "RESET_WORLD": resetWorld(storeTypeRef.current); break;

        case "CUSTOMER_ENTER": {
          console.log("[PIXI WORLD EVENT]", event);
          const entrance = zonePx("entrance");
          const c = new CustomerEntity(
            event.customerId, event.color, storeTypeRef.current,
            entrance.x + (Math.random() - 0.5) * 40, entrance.y,
            (u) => setEmotions(prev => {
              const next = new Map(prev);
              if (!u.emoji) next.delete(u.customerId);
              else next.set(u.customerId, { customerId: u.customerId, emoji: u.emoji, x: u.x, y: u.y });
              return next;
            }),
            (u: CustomerBubbleUpdate) => setCustomerBubbles(prev => {
              const next = new Map(prev);
              if (!u.visible) next.delete(u.customerId);
              else next.set(u.customerId, { ...clamp(u.x, u.y), text: u.text });
              return next;
            })
          );
          c.container.zIndex = 100;
          customersRef.current.set(event.customerId, c);
          layer.addChild(c.container);
          c.setState("entering");
          break;
        }
        case "CUSTOMER_BROWSE": {
          const c = customersRef.current.get(event.customerId);
          if (c) { c.setState("browsing"); const p = zonePx(event.zone); c.setTarget(p.x + (Math.random()-0.5)*30, p.y + (Math.random()-0.5)*30); }
          break;
        }
        case "CUSTOMER_PICK": customersRef.current.get(event.customerId)?.showEmotion("🛍️"); break;
        case "CUSTOMER_QUEUE": {
          const c = customersRef.current.get(event.customerId);
          if (c) { c.setState("queuing"); const p = zonePx("cashier_queue"); c.setTarget(p.x, p.y); }
          break;
        }
        case "CUSTOMER_CHECKOUT": {
          const c = customersRef.current.get(event.customerId);
          if (c) { c.setState("checking_out"); const p = zonePx("cashier"); c.setTarget(p.x, p.y); }
          break;
        }
        case "CUSTOMER_SUCCESS": customersRef.current.get(event.customerId)?.setState("success"); break;
        case "CUSTOMER_ABANDON": {
          const c = customersRef.current.get(event.customerId);
          if (c) {
            c.setState("confused");
            c.showBubble(event.bubble ?? event.reason);
            track(setTimeout(() => { if (!isDestroyed) c.setState("abandoning"); }, 1200));
            track(setTimeout(() => { if (!isDestroyed) c.hideBubble(); }, 3000));
          }
          break;
        }
        case "CUSTOMER_EXIT": {
          const c = customersRef.current.get(event.customerId);
          if (c) {
            c.setState("exiting");
            const p = zonePx("entrance");
            c.setTarget(p.x, p.y);
            track(setTimeout(() => {
              if (isDestroyed) return;
              layer.removeChild(c.container);
              c.destroy();
              customersRef.current.delete(event.customerId);
            }, 2600));
          }
          break;
        }
        case "AGENT_MOVE": {
          const p = zonePx(event.target);
            if (agentRef.current) {
                agentRef.current.setStoreType(storeTypeRef.current);
                agentRef.current.targetX = p.x; 
                agentRef.current.targetY = p.y;
                agentRef.current.hideBubble();
            }
            break;
        }
        case "AGENT_SPEAK":
          agentRef.current?.showBubble(event.text);
          track(setTimeout(() => { if (!isDestroyed) agentRef.current?.hideBubble(); }, 3200));
          break;
        case "AGENT_FIX_APPLY": {
          const p = zonePx("cashier");
          if (agentRef.current) { (agentRef.current as any).targetX = p.x; (agentRef.current as any).targetY = p.y; }
          const msg = event.label ?? "Applying fix...";
          track(setTimeout(() => { if (!isDestroyed) agentRef.current?.showBubble(msg); }, 500));
          track(setTimeout(() => { if (!isDestroyed) agentRef.current?.hideBubble(); }, 5500));
          break;
        }
        case "AGENT_VERIFY":
          agentRef.current?.showBubble("Verifying fix is live...");
          track(setTimeout(() => { if (!isDestroyed) agentRef.current?.hideBubble(); }, 3000));
          break;
        case "SET_STORE_TYPE":
            resetWorld(event.storeType, event.agentStartZone);
            break;
      }
    });

    return () => {
      isDestroyed = true;
      clearInterval(bubbleInterval);
      clearTrackedTimers();
      unsub();
      if (appRef.current) {
        appRef.current.stage?.destroy({ children: true, texture: true });
        appRef.current.destroy({ removeView: true });
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dims.w, dims.h]); // rebuild when measured size changes

  const theme = STORE_THEMES[storeType];

  const handleDebugClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!debug) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const fx = (e.clientX - rect.left) / rect.width;
    const fy = (e.clientY - rect.top) / rect.height;
    console.log(`{ fx: ${fx.toFixed(3)}, fy: ${fy.toFixed(3)} }`); // click any spot to get its fractional coord
  };

  return (
    <div
      onClick={handleDebugClick}
      style={{
        position: "relative", width: dims.w, height: dims.h,
        backgroundImage: `url(${theme.bgImage})`, backgroundSize: "cover", backgroundPosition: "center",
        borderRadius: 16, overflow: "hidden", border: "4px solid #1a1a2e", boxShadow: "0 20px 50px rgba(0,0,0,0.5)",
        cursor: debug ? "crosshair" : "default",
      }}
    >
      <div ref={mountRef} style={{ position: "absolute", inset: 0 }} />

      {debug && Object.entries(ZONE_LAYOUTS_FRACTIONAL[storeType]).map(([zone, f]) => (
        <div key={zone} style={{ position: "absolute", left: f.fx * dims.w - 4, top: f.fy * dims.h - 4, width: 8, height: 8, borderRadius: "50%", background: "#ff00ff", boxShadow: "0 0 8px #ff00ff", zIndex: 999, pointerEvents: "none" }}>
          <span style={{ position: "absolute", left: 12, top: -6, fontSize: 10, color: "#ff00ff", background: "#000", padding: "1px 4px", whiteSpace: "nowrap" }}>{zone}</span>
        </div>
      ))}

      {Array.from(emotions.values()).map(em => em.emoji ? (
        <div key={em.customerId} style={{ position: "absolute", left: em.x, top: em.y, fontSize: 22, pointerEvents: "none", transform: "translate(-50%,-100%)", filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.6))", zIndex: 300 }}>{em.emoji}</div>
      ) : null)}

      {Array.from(customerBubbles.entries()).map(([id, b]) => (
        <div key={id} style={{ position: "absolute", left: b.x, top: b.y, width: 150, background: "rgba(20,4,4,0.95)", border: "1.5px solid #ff6b6b", borderRadius: 8, padding: "5px 9px", color: "#ffb3b3", fontSize: 10, fontFamily: "monospace", pointerEvents: "none", zIndex: 400, whiteSpace: "pre-wrap" }}>{b.text}</div>
      ))}

      {agentBubble.visible && (
        <div style={{ position: "absolute", left: agentBubble.x, top: agentBubble.y, width: 170, background: "rgba(0,8,28,0.97)", border: "1.5px solid #00aaff", borderRadius: 8, padding: "6px 10px", color: "#00ddff", fontSize: 10, fontFamily: "monospace", lineHeight: 1.4, pointerEvents: "none", zIndex: 500, whiteSpace: "pre-wrap" }}>{agentBubble.text}</div>
      )}
    </div>
  );
}