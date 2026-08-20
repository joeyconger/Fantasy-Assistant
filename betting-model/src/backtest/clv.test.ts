import { test } from "node:test";
import assert from "node:assert/strict";
import { determinePickSide, computeCovered, computeClv } from "./clv.js";

// This file exists because a sign-convention bug here is exactly the kind
// of thing that looks right on a quick read and is wrong in production --
// every case below was hand-derived from "who actually made money" before
// being written as code, not the other way around.

test("determinePickSide favors home when the model is more negative than the opening line", () => {
  assert.equal(determinePickSide(-5, -3), "home");
});

test("determinePickSide favors away when the model is less negative than the opening line", () => {
  assert.equal(determinePickSide(-1, -3), "away");
});

test("determinePickSide returns null when the model exactly matches the opening line", () => {
  assert.equal(determinePickSide(-3, -3), null);
});

test("CLV is positive for a home pick when the line moves toward home", () => {
  // opening -3 -> closing -5: an early home bettor's -3 is a better number than closing bettors get.
  assert.equal(computeClv("home", -3, -5), 2);
});

test("CLV is negative for an away pick when the line moves toward home", () => {
  assert.equal(computeClv("away", -3, -5), -2);
});

test("CLV is positive for an away pick when the line moves toward away", () => {
  assert.equal(computeClv("away", -5, -3), 2);
});

test("CLV is negative for a home pick when the line moves toward away", () => {
  assert.equal(computeClv("home", -5, -3), -2);
});

test("home covers a big win against a small home favorite", () => {
  assert.equal(computeCovered("home", -3, 10), true);
});

test("home fails to cover a win too small to beat the spread", () => {
  assert.equal(computeCovered("home", -3, 1), false);
});

test("away covers when home wins by less than the spread", () => {
  assert.equal(computeCovered("away", -3, 1), true);
});

test("an exact push returns null for either side", () => {
  assert.equal(computeCovered("home", -3, 3), null);
  assert.equal(computeCovered("away", -3, 3), null);
});

test("covers correctly when away is favored (positive home spread)", () => {
  assert.equal(computeCovered("away", 4, -10), true);
  assert.equal(computeCovered("home", 4, -10), false);
});
