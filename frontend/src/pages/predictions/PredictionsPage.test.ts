import { describe, expect, it } from "vitest";
import { predictionMachineWindow } from "./PredictionsPage";

describe("predictionMachineWindow", () => {
  it.each([
    [1, { apiPage: 1, offset: 0 }],
    [2, { apiPage: 1, offset: 20 }],
    [5, { apiPage: 1, offset: 80 }],
    [6, { apiPage: 2, offset: 0 }],
    [10, { apiPage: 2, offset: 80 }],
    [11, { apiPage: 3, offset: 0 }],
  ])("maps UI page %i onto the DRF page", (page, expected) => {
    expect(predictionMachineWindow(page)).toEqual(expected);
  });

  it("normalizes invalid page numbers to the first page", () => {
    expect(predictionMachineWindow(0)).toEqual({ apiPage: 1, offset: 0 });
    expect(predictionMachineWindow(Number.NaN)).toEqual({
      apiPage: 1,
      offset: 0,
    });
  });
});
