import { test } from "node:test";
import assert from "node:assert/strict";
import { sosMultiplier, updateRatingsForGame, carryoverRating, predictSpread } from "./elo.js";
import { NFL_PARAMS } from "./config.js";

test("sosMultiplier clamps a huge opponent rating to the ceiling", () => {
  assert.equal(sosMultiplier(1e6, NFL_PARAMS), NFL_PARAMS.maxSosMultiplier);
});

test("sosMultiplier clamps a tiny opponent rating to the floor", () => {
  assert.equal(sosMultiplier(-1e6, NFL_PARAMS), NFL_PARAMS.minSosMultiplier);
});

test("sosMultiplier is 1 at a league-average opponent", () => {
  assert.equal(sosMultiplier(0, NFL_PARAMS), 1);
});

test("updateRatingsForGame matches a hand-computed case", () => {
  // home rating 2, away rating -1, HFA 1.5 -> expected margin = 2 - (-1) + 1.5 = 4.5
  // home net EPA/play = 0.1 - (-0.05) = 0.15; away net = -0.05 - 0.05 = -0.1
  // perfMarginHome = 25 * (0.15 - (-0.1)) = 6.25; surprise = 6.25 - 4.5 = 1.75
  // homeMult = sosMultiplier(-1) = 0.975; awayMult = sosMultiplier(2) = 1.05
  const result = updateRatingsForGame(
    {
      homeRating: 2,
      awayRating: -1,
      homePerf: { offEpaPlay: 0.1, defEpaPlay: -0.05 },
      awayPerf: { offEpaPlay: -0.05, defEpaPlay: 0.05 },
    },
    NFL_PARAMS,
  );
  assert.ok(Math.abs(result.homeRating - 2.34125) < 1e-9);
  assert.ok(Math.abs(result.awayRating - -1.3675) < 1e-9);
});

test("carryoverRating regresses toward league average (0)", () => {
  assert.equal(carryoverRating(10, NFL_PARAMS), 6);
});

test("predictSpread falls back to pure Elo with no market line", () => {
  const result = predictSpread(
    { homeRating: 3, awayRating: 1, homeGamesPlayed: 4, awayGamesPlayed: 4, marketSpreadHome: null },
    NFL_PARAMS,
  );
  assert.equal(result.eloSpreadHome, -3.5);
  assert.equal(result.modelSpreadHome, -3.5);
  assert.equal(result.modelWeight, 1);
});

test("predictSpread blends toward the market as shrinkage dictates", () => {
  // combinedGames = 8, modelWeight = 8/(8+8) = 0.5 -> 0.5*(-3.5) + 0.5*(-2) = -2.75
  const result = predictSpread(
    { homeRating: 3, awayRating: 1, homeGamesPlayed: 4, awayGamesPlayed: 4, marketSpreadHome: -2 },
    NFL_PARAMS,
  );
  assert.equal(result.modelWeight, 0.5);
  assert.equal(result.modelSpreadHome, -2.75);
});
