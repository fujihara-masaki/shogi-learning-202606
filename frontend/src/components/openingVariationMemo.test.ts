import { describe, expect, it } from "vitest";
import { equalVariationNodeProps, type VariationNodeMemoProps } from "./openingVariationMemo";

const stableOpening = {};
const stableJump = () => undefined;
const stableSwitch = () => undefined;

function activity(model: object, nodePath: number[], currentPath: number[]): VariationNodeMemoProps {
  const selected = nodePath.every((index, depth) => currentPath[depth] === index);
  const state = !selected ? "other" : nodePath.length === currentPath.length ? "current" : "ancestor";
  return {
    opening: stableOpening,
    model,
    state,
    childActivePath: state === "ancestor" ? currentPath.slice(nodePath.length) : null,
    onJump: stableJump,
    onSwitchMain: stableSwitch,
  };
}

describe("OpeningVariationList subtree memoization", () => {
  it("keeps all 400 unrelated nodes memoized when a 500-node fixture changes root branch", () => {
    const models = Array.from({ length: 500 }, () => ({}));
    const paths = Array.from({ length: 500 }, (_, flatIndex) => {
      const branch = Math.floor(flatIndex / 50);
      const depth = flatIndex % 50;
      return [branch, ...Array.from({ length: depth }, () => 0)];
    });
    const before = [0, ...Array.from({ length: 49 }, () => 0)];
    const after = [1, ...Array.from({ length: 49 }, () => 0)];

    const rerendered = paths.filter((nodePath, index) =>
      !equalVariationNodeProps(activity(models[index], nodePath, before), activity(models[index], nodePath, after)));

    expect(rerendered).toHaveLength(100);
    expect(paths).toHaveLength(500);
    expect(paths.length - rerendered.length).toBe(400);
  });

  it("does not memoize a node whose current or ancestor state changes", () => {
    const model = {};
    expect(equalVariationNodeProps(activity(model, [0], [0, 0]), activity(model, [0], [1, 0]))).toBe(false);
    expect(equalVariationNodeProps(activity(model, [2], [0]), activity(model, [2], [1]))).toBe(true);
  });
});
