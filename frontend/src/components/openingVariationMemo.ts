export interface VariationNodeMemoProps {
  opening: unknown;
  model: unknown;
  state: "current" | "ancestor" | "other";
  childActivePath: readonly number[] | null;
  onJump: unknown;
  onSwitchMain: unknown;
}

/** React.memo comparator: inactive subtrees receive null and retain stable model/callback identities. */
export function equalVariationNodeProps(previous: VariationNodeMemoProps, next: VariationNodeMemoProps): boolean {
  return previous.opening === next.opening
    && previous.model === next.model
    && previous.state === next.state
    && previous.childActivePath === next.childActivePath
    && previous.onJump === next.onJump
    && previous.onSwitchMain === next.onSwitchMain;
}
