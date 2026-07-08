import { describe, test, expect } from "vitest";
import { clampToViewport } from "../lib/utils";

describe("clampToViewport utility", () => {
  test("computes correct center position under standard conditions", () => {
    const anchor = { top: 100, left: 100, width: 50, height: 20 };
    const popupW = 100;
    const popupH = 50;

    // Viewport width/height mock implicitly resolved by default values since window is undefined in node env
    const result = clampToViewport(anchor, popupW, popupH, 8);
    
    // left: anchor.left + anchor.width/2 - popupW/2 = 100 + 25 - 50 = 75
    expect(result.left).toBe(75);
    
    // top: anchor.top - popupH - 10 = 100 - 50 - 10 = 40 (>= margin 8)
    expect(result.top).toBe(40);
  });

  test("flips below anchor if top overflows viewport margin", () => {
    // If top boundary is placed very close to viewport top edge (e.g. top = 10)
    const anchor = { top: 20, left: 100, width: 50, height: 20 };
    const popupW = 100;
    const popupH = 50;

    const result = clampToViewport(anchor, popupW, popupH, 8);
    
    // top would be 20 - 50 - 10 = -40 (< margin 8), so it should flip below:
    // top: anchor.top + anchor.height + 10 = 20 + 20 + 10 = 50
    expect(result.top).toBe(50);
  });
});
