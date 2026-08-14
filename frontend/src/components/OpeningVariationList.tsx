import { useRef, useState, type SyntheticEvent } from "react";
import {
  countOpeningBranchPoints,
  mainOpeningChoiceIndex,
  openingBranchChoiceLabel,
  openingMainPathAt,
  openingPathState,
  selectedOpeningBranchPath,
  type OpeningLine,
  type OpeningMoveNode,
  type OpeningStep,
} from "../shogi/openings";

interface Props {
  opening: OpeningLine;
  path: number[];
  steps: OpeningStep[];
  onJump: (path: number[], node: OpeningMoveNode) => void;
  onSwitchMain: (path: number[]) => void;
  /** Test/benchmark hook; production keeps the native disclosure collapsed. */
  defaultExpanded?: boolean;
}

export default function OpeningVariationList({ opening, path, steps, onJump, onSwitchMain, defaultExpanded = false }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const summaryRef = useRef<HTMLElement>(null);
  const branchCount = countOpeningBranchPoints(opening);

  function handleToggle(event: SyntheticEvent<HTMLDetailsElement>) {
    const open = event.currentTarget.open;
    if (!open && event.currentTarget.contains(document.activeElement)) summaryRef.current?.focus();
    setExpanded(open);
  }

  return (
    <section className="opening-variation-section" aria-labelledby="opening-variation-heading">
      <details data-testid="opening-variation-disclosure" onToggle={handleToggle} open={expanded || undefined}>
        <summary ref={summaryRef} id="opening-variation-heading">
          <strong>この定跡の変化</strong>
          <span>{branchCount}分岐・現在{path.length}手・{selectedOpeningBranchPath(steps)}</span>
        </summary>
        {expanded && (
          <div className="opening-variation-content">
            <p className="muted">各手を選ぶと、その局面まで盤面・棋譜・出典を移動します。</p>
            <VariationLevel opening={opening} choices={opening.moves} parentPath={[]} currentPath={path} onJump={onJump} onSwitchMain={onSwitchMain} />
          </div>
        )}
      </details>
    </section>
  );
}

interface LevelProps extends Pick<Props, "opening" | "onJump" | "onSwitchMain"> {
  choices: OpeningMoveNode[];
  parentPath: number[];
  currentPath: number[];
}

function VariationLevel({ opening, choices, parentPath, currentPath, onJump, onSwitchMain }: LevelProps) {
  const mainIndex = mainOpeningChoiceIndex(choices);
  const selectedIndex = currentPath.length > parentPath.length && parentPath.every((value, index) => currentPath[index] === value)
    ? currentPath[parentPath.length]
    : -1;
  return (
    <>
      {choices.length > 1 && (
        <div className="opening-variation-branch-action">
          <span>第{parentPath.length + 1}手の分岐点</span>
          <button
            type="button"
            aria-pressed={selectedIndex === mainIndex}
            disabled={selectedIndex === mainIndex}
            onClick={() => onSwitchMain(openingMainPathAt(opening, parentPath))}
          >
            {selectedIndex === mainIndex ? "本線を選択中" : "この分岐点の本線へ切り替える"}
          </button>
        </div>
      )}
      <ol className="opening-variation-tree">
        {choices.map((node, index) => {
          const nodePath = [...parentPath, index];
          const state = openingPathState(nodePath, currentPath);
          const label = openingBranchChoiceLabel(choices, index);
          return (
            <li key={node.id} className={`opening-variation-node ${state}`}>
              <span className="opening-variation-level">第{nodePath.length}手</span>
              <button
                type="button"
                className="opening-variation-jump"
                aria-current={state === "current" ? "step" : undefined}
                aria-label={`${nodePath.length}手目 ${node.notation}、USI ${node.usi}、${label}へ移動`}
                onClick={() => onJump(nodePath, node)}
              >
                <strong>{node.notation}</strong> <code>{node.usi}</code> <span className="branch-badge">{label}</span>
                {state === "current" && <span className="variation-state-label">現在</span>}
                {state === "ancestor" && <span className="variation-state-label"><span className="visually-hidden">現在局面までに通過した手、</span>通過</span>}
              </button>
              {(node.coverageStatus || node.sourceTitle) && (
                <span className="opening-variation-source">
                  {node.coverageStatus && <span className="coverage-badge">{node.coverageStatus}</span>}
                  {node.sourceTitle && (node.sourceUrl ? <a href={node.sourceUrl} target="_blank" rel="noreferrer">出典: {node.sourceTitle}</a> : <span>出典: {node.sourceTitle}</span>)}
                </span>
              )}
              {(node.next?.length ?? 0) > 0 && <VariationLevel opening={opening} choices={node.next!} parentPath={nodePath} currentPath={currentPath} onJump={onJump} onSwitchMain={onSwitchMain} />}
            </li>
          );
        })}
      </ol>
    </>
  );
}
