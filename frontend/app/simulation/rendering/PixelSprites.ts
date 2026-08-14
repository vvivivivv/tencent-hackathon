import * as PIXI from "pixi.js";

export function createCharacterSprite(color: number, isAgent = false): PIXI.Graphics {
  const g = new PIXI.Graphics();
  const scale = 2.6; // bumped up from 2.0 — was too small against the real backgrounds

  g.ellipse(0, 2, 12, 5).fill({ color: 0x000000, alpha: 0.25 });

  if (isAgent) {
    g.roundRect(-scale * 4, -scale * 8, scale * 8, scale * 7, 4).fill(0xffffff).stroke({ color: 0x2b2d42, width: 2 });
    g.roundRect(-scale * 3, -scale * 7, scale * 6, scale * 4, 2).fill(0x1a1a2e);
    g.circle(-scale * 1.2, -scale * 5, scale * 0.5).fill(0x00ffff);
    g.circle(scale * 1.2, -scale * 5, scale * 0.5).fill(0x00ffff);
    g.rect(-0.5, -scale * 11, 1, scale * 3).fill(0x2b2d42);
    g.circle(0, -scale * 11.5, 2).fill(0x00aaff);
    return g;
  }

  // Customer — broader shoulders, and a flat cropped-hair cap instead of
  // the pointed arc shape (that read as an odd triangular ponytail before).
  g.roundRect(-scale * 4, -scale * 7, scale * 8, scale * 7.5, 3).fill(color).stroke({ color: 0x000000, width: 1.5 });
  g.roundRect(-scale * 3.2, -scale * 10.5, scale * 6.4, scale * 4.2, 2.5).fill(0xffdbac).stroke({ color: 0x000000, width: 1.5 });
  g.roundRect(-scale * 3.4, -scale * 11.3, scale * 6.8, scale * 2.4, 2).fill(0x3a2a1e).stroke({ color: 0x000000, width: 1.5 });
  g.rect(-scale * 1.5, -scale * 9.3, 1.3, scale * 1.3).fill(0x000000);
  g.rect(scale * 0.6, -scale * 9.3, 1.3, scale * 1.3).fill(0x000000);
  return g;
}