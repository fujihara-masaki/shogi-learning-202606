import { describe, expect, it } from "vitest";
import { Color } from "tsshogi";
import {
  OPENING_LINES,
  applyOpeningPath,
  continueOpeningMainLine,
  countMainLineMoves,
  expectedOpeningMove,
  flattenMainLine,
  findOpeningChoiceIndex,
  mainOpeningChoice,
  mainOpeningChoiceIndex,
  enumerateOpeningTree,
  countOpeningBranchPoints,
  openingMainPathAt,
  openingPathState,
  openingFromImportedLine,
  openingBranchChoiceLabel,
  pathBeforePreviousBranch,
  selectedOpeningBranchPath,
  type OpeningLine,
  type OpeningMoveNode,
} from "./openings";

describe("opening sample data", () => {
  it("contains fixed sample openings with tree-shaped moves", () => {
    expect(OPENING_LINES.length).toBeGreaterThanOrEqual(3);
    for (const opening of OPENING_LINES) {
      expect(opening.moves.length).toBeGreaterThan(0);
      expect(countMainLineMoves(opening)).toBe(flattenMainLine(opening).length);
    }
  });

  it("can create and advance positions with legal main-line moves", () => {
    for (const opening of OPENING_LINES) {
      const result = applyOpeningPath(opening, flattenMainLine(opening).map(() => 0));
      expect(result.moves).toHaveLength(countMainLineMoves(opening));
    }
  });
});

describe("opening learning helpers", () => {
  const opening = OPENING_LINES[0];

  it("returns the expected next move for the current path", () => {
    expect(expectedOpeningMove(opening, [])?.usi).toBe("7g7f");
    expect(expectedOpeningMove(opening, [0])?.usi).toBe("3c3d");
  });

  it("finds every registered choice and rejects a move outside three choices", () => {
    const choices = ["7g7f", "2g2f", "5g5f"].map((usi, index) => ({ usi, id: String(index) })) as OpeningMoveNode[];
    expect(findOpeningChoiceIndex(choices, { usi: "7g7f" })).toBe(0);
    expect(findOpeningChoiceIndex(choices, { usi: "2g2f" })).toBe(1);
    expect(findOpeningChoiceIndex(choices, { usi: "5g5f" })).toBe(2);
    expect(findOpeningChoiceIndex(choices, { usi: "6g6f" })).toBe(-1);
  });

  it("undo path restores the previous side to move", () => {
    const advanced = applyOpeningPath(opening, [0, 0]);
    expect(advanced.position.color).toBe(Color.BLACK);
    const undone = applyOpeningPath(opening, [0]);
    expect(undone.position.color).toBe(Color.WHITE);
  });
});

describe("opening branch path helpers", () => {
  const node = (id: string, usi: string, next?: OpeningMoveNode[]): OpeningMoveNode => ({
    id, usi, notation: usi, explanation: id, aim: id, hint: id, next,
  });
  const fixture: OpeningLine = {
    id: "three-choices", name: "three choices", category: "test", description: "test",
    initialSfen: "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1",
    moves: [
      node("zero", "7g7f", [node("zero-next", "3c3d")]),
      node("one", "2g2f", [node("one-next", "8c8d")]),
      node("two", "5g5f", [node("two-next", "5c5d")]),
    ],
  };

  it.each([[0, "zero"], [1, "one"], [2, "two"]])("replays path index %i as node %s", (index, id) => {
    expect(applyOpeningPath(fixture, [index]).steps[0].node.id).toBe(id);
  });

  it("keeps the selected path when continuing along first choices", () => {
    expect(continueOpeningMainLine(fixture, [2])).toEqual([2, 0]);
    expect(applyOpeningPath(fixture, continueOpeningMainLine(fixture, [2])).moves.map((move) => move.usi)).toEqual(["5g5f", "5c5d"]);
  });

  it("uses the explicit semantic main index consistently for display and playback", () => {
    const choices = fixture.moves.map((choice, index) => ({ ...choice, isMain: index === 1 }));
    const explicitMainFixture = { ...fixture, moves: choices };

    expect(mainOpeningChoice(choices)?.id).toBe("one");
    expect(mainOpeningChoiceIndex(choices)).toBe(1);
    expect(expectedOpeningMove(explicitMainFixture, [])?.id).toBe("one");
    expect(continueOpeningMainLine(explicitMainFixture, [])).toEqual([1, 0]);
    expect(applyOpeningPath(explicitMainFixture, [mainOpeningChoiceIndex(choices)]).steps[0].node.id).toBe("one");
  });

  it("labels only traversed branch points using semantic branch labels", () => {
    const linear = node("linear", "7g7f");
    const unlabeledVariation = { ...node("variation", "2g2f"), isMain: false };
    const explicitMain = { ...node("main", "5g5f"), isMain: true, branchLabel: "本線", sortOrder: 1 };
    const rootChoices = [unlabeledVariation, explicitMain];

    expect(selectedOpeningBranchPath([{ node: unlabeledVariation, choices: rootChoices }])).toBe("分岐1");
    expect(selectedOpeningBranchPath([{ node: explicitMain, choices: rootChoices }])).toBe("本線");
    expect(selectedOpeningBranchPath([{ node: linear, choices: [linear] }])).toBe("本線");
  });

  it("preserves human labels across nested branch points", () => {
    const branchA = { ...node("a", "7g7f"), branchLabel: "A", isMain: true };
    const branchB = { ...node("b", "2g2f"), branchLabel: "B", isMain: false };
    const nestedVariation = { ...node("a-variation", "3c3d"), isMain: false };
    const nestedMain = { ...node("a-main", "8c8d"), isMain: true };

    expect(selectedOpeningBranchPath([
      { node: branchA, choices: [branchB, branchA] },
      { node: nestedVariation, choices: [nestedMain, nestedVariation] },
    ])).toBe("A → 分岐2");
    expect(selectedOpeningBranchPath([{ node: branchB, choices: [branchB, branchA] }])).toBe("B");
  });

  it("returns to immediately before the previous branch", () => {
    expect(pathBeforePreviousBranch(fixture, [2, 0])).toEqual([]);
    expect(pathBeforePreviousBranch(fixture, [])).toEqual([]);
  });

  it("enumerates every node as a root-relative path for forward, backward, and sibling jumps", () => {
    expect(enumerateOpeningTree(fixture).map(({ node, path }) => [node.id, path])).toEqual([
      ["zero", [0]], ["zero-next", [0, 0]],
      ["one", [1]], ["one-next", [1, 0]],
      ["two", [2]], ["two-next", [2, 0]],
    ]);
    expect(applyOpeningPath(fixture, [0, 0]).steps.at(-1)?.node.id).toBe("zero-next");
    expect(applyOpeningPath(fixture, [0]).steps.at(-1)?.node.id).toBe("zero");
    expect(applyOpeningPath(fixture, [2, 0]).steps.at(-1)?.node.id).toBe("two-next");
    expect(countOpeningBranchPoints(fixture)).toBe(1);
  });

  it("distinguishes only the current node from its ancestors", () => {
    expect(openingPathState([0], [0, 0])).toBe("ancestor");
    expect(openingPathState([0, 0], [0, 0])).toBe("current");
    expect(openingPathState([1], [0, 0])).toBe("other");
    expect(openingPathState([0, 0, 0], [0, 0])).toBe("other");
  });

  it("switches semantic main at multiple depths and discards the later path", () => {
    const nestedMain = { ...node("nested-main", "3c3d"), isMain: true, sortOrder: 2 };
    const nestedVariation = { ...node("nested-var", "8c8d"), isMain: false, sortOrder: 0 };
    const rootVariation = { ...node("root-var", "2g2f"), isMain: false, sortOrder: 0 };
    const rootMain = { ...node("root-main", "7g7f", [nestedVariation, nestedMain]), isMain: true, sortOrder: 1 };
    const semanticFixture = { ...fixture, moves: [rootVariation, rootMain] };

    expect(openingMainPathAt(semanticFixture, [])).toEqual([1]);
    expect(openingMainPathAt(semanticFixture, [1])).toEqual([1, 1]);
    expect(openingMainPathAt(semanticFixture, [1, 0])).toEqual([1, 0]);
  });

  it("enumerates a 500-node deep tree without losing paths", () => {
    let next: OpeningMoveNode[] = [];
    for (let index = 499; index >= 0; index -= 1) next = [node(`deep-${index}`, "7g7f", next)];
    const deep = { ...fixture, moves: next };
    const entries = enumerateOpeningTree(deep);
    expect(entries).toHaveLength(500);
    expect(entries.at(-1)?.path).toHaveLength(500);
  });
});

describe("openingFromImportedLine", () => {
  it("converts imported linear moves into the existing opening tree shape", () => {
    const opening = openingFromImportedLine({
      id: 12,
      name: "imported nakabisha",
      opening_type: "中飛車",
      initial_sfen: "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1",
      moves: [{ usi: "7g7f" }, { usi: "3c3d" }, { usi: "2h5h", comment: "中飛車へ" }],
      tags: [{ tag: "nakabisha", label: "中飛車" }],
      source: { name: "sample", license_name: "CC0", license_url: "" },
    });
    expect(opening.id).toBe("12");
    expect(opening.category).toBe("中飛車");
    expect(flattenMainLine(opening).map((move) => move.usi)).toEqual(["7g7f", "3c3d", "2h5h"]);
  });

  it("builds direct-parent multi-level trees, keeps transpositions separate, and follows explicit main", () => {
    const move = (id: number, parent_move_id: number | null, usi: string, sort_order: number, is_main: boolean, to_sfen: string) => ({
      id, parent_move_id, usi, sort_order, is_main, move_key: `m${id}`,
      from_sfen: "position", to_sfen, variation_group: is_main ? "main" : `v${id}`,
    });
    const opening = openingFromImportedLine({
      id: 101, name: "tree", opening_type: "test", initial_sfen: "position",
      moves: [
        move(1, null, "7g7f", 0, true, "p1"),
        move(2, 1, "3c3d", 0, false, "transposed"),
        move(3, 1, "8c8d", 1, false, "p-b"),
        move(4, 1, "4a3b", 2, true, "p-main"),
        move(5, 2, "2g2f", 0, true, "a1"),
        move(6, 2, "5g5f", 1, false, "a2"),
        move(7, 3, "6g6f", 0, true, "transposed"),
        move(8, 3, "9g9f", 1, false, "b2"),
      ], source: { name: "fixture", license_name: "CC0", license_url: "" },
    });
    expect(opening.moves[0].next?.map((node) => node.id)).toEqual([
      "imported-101-m2", "imported-101-m3", "imported-101-m4",
    ]);
    expect(expectedOpeningMove(opening, [0])?.id).toBe("imported-101-m4");
    expect(continueOpeningMainLine(opening, [])).toEqual([0, 2]);
    expect(opening.moves[0].next?.[0].next?.[0]).not.toBe(opening.moves[0].next?.[1].next?.[0]);
  });

  it("uses persisted branch display labels rather than internal stable keys", () => {
    const opening = openingFromImportedLine({
      id: 102, name: "labels", opening_type: "test", initial_sfen: "position",
      moves: [
        { id: 1, parent_move_id: null, usi: "7g7f", sort_order: 0, is_main: true,
          move_key: "m1", variation_group: "main" },
        { id: 2, parent_move_id: 1, usi: "2g2f", sort_order: 0, is_main: false,
          move_key: "b", variation_group: "B" },
        { id: 3, parent_move_id: 1, usi: "6g6f", sort_order: 1, is_main: true,
          move_key: "a", variation_group: "A" },
      ], source: { name: "fixture", license_name: "CC0", license_url: "" },
    });

    const choices = opening.moves[0].next!;
    expect(choices.map((choice) => choice.branchLabel)).toEqual(["B", "A"]);
    expect(choices.map((choice) => choice.branchLabel)).not.toContain("a");
    expect(choices.map((choice) => choice.branchLabel)).not.toContain("b");
    expect(mainOpeningChoice(choices)?.id).toBe("imported-102-a");
  });

  it("derives fallback branch labels from semantic main status", () => {
    const opening = openingFromImportedLine({
      id: 103, name: "semantic labels", opening_type: "test", initial_sfen: "position",
      moves: [
        { id: 1, parent_move_id: null, usi: "7g7f", sort_order: 0, is_main: true,
          move_key: "root", variation_group: "main" },
        { id: 2, parent_move_id: 1, usi: "2g2f", sort_order: 0, is_main: false,
          move_key: "variation", variation_group: "main" },
        { id: 3, parent_move_id: 1, usi: "6g6f", sort_order: 1, is_main: true,
          move_key: "explicit-main", variation_group: "main" },
      ], source: { name: "fixture", license_name: "CC0", license_url: "" },
    });

    const choices = opening.moves[0].next!;
    expect(choices.map((choice) => choice.branchLabel)).toEqual([undefined, "本線"]);
    expect(mainOpeningChoiceIndex(choices)).toBe(1);
    expect(choices.map((_, index) => openingBranchChoiceLabel(choices, index))).toEqual(["分岐1", "本線"]);
    expect(`変化 ${openingBranchChoiceLabel(choices, 0)}`).not.toBe("変化 本線");

    const branchHistory = choices.map((_, index) => openingBranchChoiceLabel(choices, index));
    expect(branchHistory[0]).not.toBe("本線");
    expect(expectedOpeningMove(opening, [0])?.id).toBe("imported-103-explicit-main");
  });
});

it("builds branch choices from imported moves and can switch back to the branch point", () => {
  const start = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1";
  const after76 = "lnsgkgsnl/1r5b1/ppppppppp/9/9/2P6/PP1PPPPPP/1B5R1/LNSGKGSNL w - 2";
  const opening = openingFromImportedLine({
    id: 99,
    name: "branch sample",
    opening_type: "角換わり",
    initial_sfen: start,
    moves: [
      { usi: "7g7f", from_sfen: start, to_sfen: after76, variation_group: "main", sort_order: 0 },
      { usi: "3c3d", from_sfen: after76, to_sfen: "lnsgkgsnl/1r5b1/pppppp1pp/6p2/9/2P6/PP1PPPPPP/1B5R1/LNSGKGSNL b - 3", variation_group: "main", sort_order: 0 },
      { usi: "8c8d", from_sfen: after76, to_sfen: "lnsgkgsnl/1r5b1/ppppppppp/9/1p7/2P6/PP1PPPPPP/1B5R1/LNSGKGSNL b - 3", variation_group: "△8四歩型", sort_order: 1 },
    ],
    source: { name: "Wikipedia", license_name: "CC BY-SA", license_url: "", source_url: "https://ja.wikipedia.org/wiki/角換わり" },
  });

  const branchPoint = applyOpeningPath(opening, [0]);
  expect(branchPoint.steps.at(-1)?.node.next).toHaveLength(2);
  expect(branchPoint.steps.at(-1)?.node.next?.map((node) => node.branchLabel)).toEqual(["本線", "△8四歩型"]);
  expect(applyOpeningPath(opening, [0, 0]).moves.map((move) => move.usi)).toEqual(["7g7f", "3c3d"]);
  expect(applyOpeningPath(opening, [0, 1]).moves.map((move) => move.usi)).toEqual(["7g7f", "8c8d"]);
  expect(applyOpeningPath(opening, [0]).position.sfen).toBe(branchPoint.position.sfen);
});
