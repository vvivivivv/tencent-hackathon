import * as PIXI from "pixi.js";
import { createCharacterSprite } from "../rendering/PixelSprites";
import { randomInZone } from "../entities/WorldLayout";
import type { StoreZone, StoreType } from "../entities/WorldLayout";

export type CustomerState =
  | "entering" | "browsing" | "picking" | "queuing"
  | "checking_out" | "success" | "confused" | "abandoning" | "exiting";

export interface CustomerEmotionUpdate { customerId: string; emoji: string; x: number; y: number; key: string; }
export interface CustomerBubbleUpdate { customerId: string; visible: boolean; text: string; x: number; y: number; }

export class CustomerEntity {
  container: PIXI.Container;
  private body: PIXI.Graphics;
  state: CustomerState = "entering";
  id: string;
  private storeType: StoreType;
  private destroyed = false;

  private targetX: number;
  private targetY: number;
  private speed = 1.6;
  private stateTimer = 0;

  private currentEmoji = "";
  private emojiExpiresAt = 0;

  private onEmotion?: (u: CustomerEmotionUpdate) => void;
  private onBubble?: (u: CustomerBubbleUpdate) => void;

  constructor(
    id: string, color: number, storeType: StoreType,
    startX: number, startY: number,
    onEmotion?: (u: CustomerEmotionUpdate) => void,
    onBubble?: (u: CustomerBubbleUpdate) => void
  ) {
    this.id = id;
    this.storeType = storeType;
    this.onEmotion = onEmotion;
    this.onBubble = onBubble;
    this.targetX = startX;
    this.targetY = startY;

    this.container = new PIXI.Container();
    this.container.x = startX;
    this.container.y = startY;

    this.body = createCharacterSprite(color, false);
    this.container.addChild(this.body);
  }

  moveTo(zone: StoreZone) {
    if (this.destroyed) return;
    const pos = randomInZone(this.storeType, zone);
    this.targetX = pos.x;
    this.targetY = pos.y;
  }

  setTarget(x: number, y: number) {
    if (this.destroyed) return;
    this.targetX = x;
    this.targetY = y;
  }

  showEmotion(emoji: string, durationMs = 1800) {
    if (this.destroyed) return;
    this.currentEmoji = emoji;
    this.emojiExpiresAt = performance.now() + durationMs;
    this.emitEmotion();
  }

  private emitEmotion() {
    if (this.destroyed) return;
    this.onEmotion?.({
      customerId: this.id, emoji: this.currentEmoji,
      x: this.container.x, y: this.container.y - 44,
      key: `${this.id}-${this.currentEmoji}`,
    });
  }

  clearEmotion() {
    if (this.destroyed) return;
    this.currentEmoji = "";
    this.onEmotion?.({ customerId: this.id, emoji: "", x: 0, y: 0, key: `${this.id}-clear` });
  }

  showBubble(text: string) {
    if (this.destroyed) return;
    this.onBubble?.({ customerId: this.id, visible: true, text, x: this.container.x, y: this.container.y - 46 });
  }
  hideBubble() {
    if (this.destroyed) return;
    this.onBubble?.({ customerId: this.id, visible: false, text: "", x: 0, y: 0 });
  }

  setState(s: CustomerState) {
    if (this.destroyed) return;
    this.state = s;
    this.stateTimer = 0;
    if (s === "success") this.showEmotion("😊");
    if (s === "confused") this.showEmotion("🤨");
    if (s === "abandoning") this.showEmotion("😠");
  }

  update(dt: number) {
    if (this.destroyed) return;
    this.stateTimer += dt;

    const dx = this.targetX - this.container.x;
    const dy = this.targetY - this.container.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist > 2) {
      this.container.x += (dx / dist) * this.speed * dt;
      this.container.y += (dy / dist) * this.speed * dt;
      this.container.rotation = dx > 0 ? 0.05 : -0.05;
    } else {
      this.container.rotation = 0;
      this.body.y = Math.sin(this.stateTimer * 0.1) * 1;
    }

    // Re-emit the emoji's position every frame while active, so it tracks
    // the character instead of freezing where showEmotion() was first called.
    if (this.currentEmoji) {
      if (performance.now() > this.emojiExpiresAt) this.clearEmotion();
      else this.emitEmotion();
    }
  }

  destroy() {
    if (this.destroyed) return;
    this.destroyed = true;
    this.clearEmotion();
    this.hideBubble();
    this.container.destroy({ children: true });
  }
}