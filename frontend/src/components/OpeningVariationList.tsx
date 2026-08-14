import { memo, useCallback, useEffect, useMemo, useRef, useState, type SyntheticEvent } from "react";
import { equalVariationNodeProps } from "./openingVariationMemo";
import {
  countOpeningBranchPoints,
  mainOpeningChoiceIndex,
  openingBranchChoiceLabel,
  openingMainSwitchAccessibleName,
  openingMainPathAt,
  openingNodeJumpAccessibleName,
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

interface VariationLevelModel {
  choices: OpeningMoveNode[];
  parentPath: number[];
  nodes: VariationNodeModel[];
}

interface VariationNodeModel {
  node: OpeningMoveNode;
  index: number;
  path: number[];
  label: string;
  child: VariationLevelModel | null;
}

function buildLevel(choices: OpeningMoveNode[], parentPath: number[]): VariationLevelModel {
  return {
    choices,
    parentPath,
    nodes: choices.map((node, index) => {
      const path = [...parentPath, index];
      return {
        node,
        index,
        path,
        label: openingBranchChoiceLabel(choices, index),
        child: node.next?.length ? buildLevel(node.next, path) : null,
      };
    }),
  };
}

export default function OpeningVariationList({ opening, path, steps, onJump, onSwitchMain, defaultExpanded = false }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const summaryRef = useRef<HTMLElement>(null);
  const onJumpRef = useRef(onJump);
  const onSwitchMainRef = useRef(onSwitchMain);
  useEffect(() => {
    onJumpRef.current = onJump;
    onSwitchMainRef.current = onSwitchMain;
  }, [onJump, onSwitchMain]);
  const stableOnJump = useCallback<Props["onJump"]>((...args) => onJumpRef.current(...args), []);
  const stableOnSwitchMain = useCallback<Props["onSwitchMain"]>((...args) => onSwitchMainRef.current(...args), []);
  const branchCount = useMemo(() => countOpeningBranchPoints(opening), [opening]);
  const tree = useMemo(() => buildLevel(opening.moves, []), [opening]);

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
            <VariationLevel opening={opening} level={tree} activePath={path} onJump={stableOnJump} onSwitchMain={stableOnSwitchMain} />
          </div>
        )}
      </details>
    </section>
  );
}

interface LevelProps extends Pick<Props, "opening" | "onJump" | "onSwitchMain"> {
  level: VariationLevelModel;
  /** Path suffix below this level; null means this entire subtree is unrelated to the current path. */
  activePath: readonly number[] | null;
}

function VariationLevel({ opening, level, activePath, onJump, onSwitchMain }: LevelProps) {
  const mainIndex = mainOpeningChoiceIndex(level.choices);
  const selectedIndex = activePath?.[0] ?? -1;
  return (
    <>
      {level.choices.length > 1 && (
        <div className="opening-variation-branch-action">
          <span>第{level.parentPath.length + 1}手の分岐点</span>
          <button
            type="button"
            aria-label={openingMainSwitchAccessibleName(opening, level.parentPath, selectedIndex === mainIndex)}
            aria-pressed={selectedIndex === mainIndex}
            disabled={selectedIndex === mainIndex}
            onClick={() => onSwitchMain(openingMainPathAt(opening, level.parentPath))}
          >
            {selectedIndex === mainIndex ? "本線を選択中" : "この分岐点の本線へ切り替える"}
          </button>
        </div>
      )}
      <ol className="opening-variation-tree">
        {level.nodes.map((model) => {
          const selected = selectedIndex === model.index;
          const state = !selected ? "other" : activePath!.length === 1 ? "current" : "ancestor";
          return (
            <VariationNode
              key={model.node.id}
              opening={opening}
              model={model}
              state={state}
              childActivePath={selected && activePath!.length > 1 ? activePath!.slice(1) : null}
              onJump={onJump}
              onSwitchMain={onSwitchMain}
            />
          );
        })}
      </ol>
    </>
  );
}

interface NodeProps extends Pick<Props, "opening" | "onJump" | "onSwitchMain"> {
  model: VariationNodeModel;
  state: "current" | "ancestor" | "other";
  childActivePath: readonly number[] | null;
}

const VariationNode = memo(function VariationNode({ opening, model, state, childActivePath, onJump, onSwitchMain }: NodeProps) {
  const { node, path, label, child } = model;
  return (
    <li className={`opening-variation-node ${state}`}>
      <span className="opening-variation-level">第{path.length}手</span>
      <button
        type="button"
        className="opening-variation-jump"
        aria-current={state === "current" ? "step" : undefined}
        aria-label={openingNodeJumpAccessibleName(opening, path)}
        onClick={() => onJump(path, node)}
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
      {child && <VariationLevel opening={opening} level={child} activePath={childActivePath} onJump={onJump} onSwitchMain={onSwitchMain} />}
    </li>
  );
}, equalVariationNodeProps);
