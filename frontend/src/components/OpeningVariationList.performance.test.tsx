import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import OpeningVariationList from "./OpeningVariationList";
import type { OpeningLine, OpeningMoveNode } from "../shogi/openings";

function fiveHundredNodeOpening(): OpeningLine {
  const roots: OpeningMoveNode[] = [];
  for (let branch = 0; branch < 10; branch += 1) {
    let next: OpeningMoveNode[] | undefined;
    for (let depth = 49; depth >= 0; depth -= 1) {
      const node: OpeningMoveNode = {
        id: `performance-${branch}-${depth}`,
        usi: "7g7f",
        notation: `fixture ${branch}-${depth}`,
        explanation: "fixture",
        aim: "fixture",
        hint: "fixture",
        branchLabel: depth === 0 ? `branch ${branch}` : undefined,
        isMain: branch === 7 || depth > 0,
        sortOrder: branch,
        coverageStatus: "fixture",
        sourceTitle: "Performance fixture",
        sourceUrl: "https://example.test/source",
        next,
      };
      next = [node];
    }
    roots.push(next![0]);
  }
  return {
    id: "performance-500",
    name: "500 node fixture",
    category: "test",
    description: "render measurement only",
    initialSfen: "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1",
    moves: roots,
  };
}

function measure(opening: OpeningLine, expanded: boolean) {
  const start = performance.now();
  const html = renderToStaticMarkup(
    <OpeningVariationList opening={opening} path={[]} steps={[]} onJump={() => undefined} onSwitchMain={() => undefined} defaultExpanded={expanded} />,
  );
  return { milliseconds: performance.now() - start, domNodes: html.match(/<[a-z][^>]*>/g)?.length ?? 0 };
}

describe("OpeningVariationList 500-node render fixture", () => {
  it("records collapsed and expanded render cost without imposing a threshold", () => {
    const opening = fiveHundredNodeOpening();
    const collapsed = measure(opening, false);
    const expanded = measure(opening, true);
    console.info("OpeningVariationList 500-node measurement", { collapsed, expanded });
    expect(collapsed.domNodes).toBeLessThan(10);
    expect(expanded.domNodes).toBeGreaterThan(500);
  });
});
