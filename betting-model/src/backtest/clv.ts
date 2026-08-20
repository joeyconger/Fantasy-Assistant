// Pure scoring functions for one backtested game. Kept separate from the DB
// orchestration in run.ts so they're directly unit-testable with hand-picked
// numbers — this is the part that actually decides whether a pick "won."
//
// Convention throughout: a spread is home-relative, negative = home favored
// (matches odds_snapshots.spread_home). pickSide is determined against the
// OPENING line — the number that would actually have been available to bet
// — never the closing line, which isn't known until after the fact.

export type PickSide = "home" | "away";

export function determinePickSide(modelSpreadHome: number, openingSpreadHome: number): PickSide | null {
  if (modelSpreadHome === openingSpreadHome) return null;
  return modelSpreadHome < openingSpreadHome ? "home" : "away";
}

/**
 * Did the picked side cover a given spread? null on an exact push. This is
 * deliberately generic over which spread you pass in — call it once with
 * the closing line (a diagnostic: "would the model's disagreement with the
 * market have looked right in hindsight against the number that closed")
 * and once with the opening line (the real "did this bet win" answer).
 */
export function computeCovered(pickSide: PickSide, spreadHome: number, actualMarginHome: number): boolean | null {
  const margin = actualMarginHome + spreadHome;
  if (margin === 0) return null;
  return pickSide === "home" ? margin > 0 : margin < 0;
}

/**
 * Closing Line Value: the pure price-movement metric, independent of the
 * game's outcome. Positive means the number moved in the picked side's
 * favor between opening and closing — i.e. a bettor who got the opening
 * price beat the closing price, which is the standard signal that a bet
 * was sharp regardless of whether it ultimately won.
 */
export function computeClv(pickSide: PickSide, openingSpreadHome: number, closingSpreadHome: number): number {
  return pickSide === "home" ? openingSpreadHome - closingSpreadHome : closingSpreadHome - openingSpreadHome;
}
