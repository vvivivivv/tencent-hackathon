// simulation/entities/AgentEntity.ts
import * as PIXI from "pixi.js";
import { createCharacterSprite } from "../rendering/PixelSprites";
import { zonePos } from "../entities/WorldLayout";
import type { StoreZone, StoreType } from "../entities/WorldLayout";

export interface AgentBubbleUpdate { visible: boolean; text: string; x: number; y: number; }

export class AgentEntity {
  container: PIXI.Container;
  private body: PIXI.Graphics;
  public targetX: number = 0;
  public targetY: number = 0;
  private speed = 2.2;
  private timer = 0;
  private onBubble?: (u: AgentBubbleUpdate) => void;
  private storeType: StoreType;
  private destroyed = false;

  constructor(storeType: StoreType, onBubble?: (u: AgentBubbleUpdate) => void) {
    this.onBubble = onBubble;
    this.storeType = storeType;
    this.container = new PIXI.Container();
    this.body = createCharacterSprite(0x00aaff, true);
    this.container.addChild(this.body);
  }

  // Update store type when scenario switches
  setStoreType(storeType: StoreType) { 
    this.storeType = storeType;
  }

  moveTo(zone: StoreZone) {
    if (this.destroyed) return;
    const z = zonePos(this.storeType, zone);
    this.targetX = z.x;
    this.targetY = z.y;
  }

  home() {
    this.moveTo("agent_desk");
  }

  showBubble(text: string) {
    if (this.destroyed) return;
    this.onBubble?.({ visible: true, text, x: this.container.x, y: this.container.y - 54 });
  }

  hideBubble() {
    if (this.destroyed) return;
    this.onBubble?.({ visible: false, text: "", x: 0, y: 0 });
  }

  update(dt: number) {
    if (this.destroyed) return;
    this.timer += dt;
    const dx = this.targetX - this.container.x;
    const dy = this.targetY - this.container.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist > 2) {
      this.container.x += (dx / dist) * this.speed * dt;
      this.container.y += (dy / dist) * this.speed * dt;
      this.container.rotation = dx > 0 ? 0.08 : -0.08;
    } else {
      this.container.rotation = 0;
      this.body.y = Math.sin(this.timer * 0.05) * 3;
    }
  }

  destroy() {
    if (this.destroyed) return;
    this.destroyed = true;
    this.hideBubble();
    this.container.destroy({ children: true });
  }
}