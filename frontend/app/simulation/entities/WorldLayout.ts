export type StoreZone = "entrance" | "aisle_left" | "aisle_center" | "aisle_right" | "cashier_queue" | "cashier" | "agent_desk";
export type StoreType = "bakery" | "flower_shop" | "bookstore";

export interface StoreTheme { type: StoreType; name: string; bgImage: string; }

export const DISPLAY_MAX_W = 900;
export const DISPLAY_MAX_H = 540;

export const ZONE_LAYOUTS: Record<StoreType, Record<StoreZone, { x: number; y: number }>> = {
  bakery: {
    entrance:      { x: 400, y: 520 },
    aisle_left:    { x: 130, y: 330 },
    aisle_center:  { x: 450, y: 300 },
    aisle_right:   { x: 760, y: 260 },
    cashier_queue: { x: 430, y: 250 },
    cashier:       { x: 430, y: 195 },
    agent_desk:    { x: 800, y: 90 },
  },
  bookstore: {
    entrance:      { x: 450, y: 520 },
    aisle_left:    { x: 220, y: 330 },
    aisle_center:  { x: 500, y: 340 },
    aisle_right:   { x: 780, y: 330 },
    cashier_queue: { x: 260, y: 290 },
    cashier:       { x: 240, y: 240 },
    agent_desk:    { x: 800, y: 100 },
  },
  flower_shop: {
    entrance:      { x: 450, y: 520 },
    aisle_left:    { x: 170, y: 340 },
    aisle_center:  { x: 470, y: 330 },
    aisle_right:   { x: 780, y: 340 },
    cashier_queue: { x: 460, y: 250 },
    cashier:       { x: 460, y: 200 },
    agent_desk:    { x: 130, y: 130 },
  },
};

export const ZONE_LAYOUTS_FRACTIONAL: Record<StoreType, Record<StoreZone, { fx: number; fy: number }>> = {
  bakery: {
    entrance:      { fx: 0.35, fy: 0.90 },
    aisle_left:    { fx: 0.12, fy: 0.55 },
    aisle_center:  { fx: 0.50, fy: 0.52 },
    aisle_right:   { fx: 0.88, fy: 0.48 },
    cashier_queue: { fx: 0.47, fy: 0.50 },
    cashier:       { fx: 0.20, fy: 0.40 },
    agent_desk:    { fx: 0.92, fy: 0.14 },
  },
  flower_shop: {
    entrance:      { fx: 0.50, fy: 0.96 },
    aisle_left:    { fx: 0.20, fy: 0.62 },
    aisle_center:  { fx: 0.50, fy: 0.55 },
    aisle_right:   { fx: 0.80, fy: 0.62 },
    cashier_queue: { fx: 0.68, fy: 0.38 },
    cashier:       { fx: 0.72, fy: 0.60 },
    agent_desk:    { fx: 0.10, fy: 0.15 },
  },
  bookstore: {
    entrance:      { fx: 0.13, fy: 0.70 },
    aisle_left:    { fx: 0.45, fy: 0.45 },
    aisle_center:  { fx: 0.68, fy: 0.45 },
    aisle_right:   { fx: 0.90, fy: 0.55 },
    cashier_queue: { fx: 0.15, fy: 0.55 },
    cashier:       { fx: 0.15, fy: 0.55 },
    agent_desk:    { fx: 0.94, fy: 0.16 },
  },
};

export function zonePos(type: StoreType, zone: StoreZone) { return ZONE_LAYOUTS[type][zone]; }
export function randomInZone(type: StoreType, zone: StoreZone, spread = 30) {
  const z = zonePos(type, zone);
  return { x: z.x + (Math.random() - 0.5) * spread, y: z.y + (Math.random() - 0.5) * spread };
}

export const STORE_THEMES: Record<StoreType, StoreTheme> = {
  bakery:      { type: "bakery",      name: "Warm Hearth Bakery", bgImage: "/backgrounds/bakery.png" },
  bookstore:   { type: "bookstore",   name: "Parchment & Pen",    bgImage: "/backgrounds/bookstore.png" },
  flower_shop: { type: "flower_shop", name: "Bloom & Co.",        bgImage: "/backgrounds/flower_shop.png" },
};