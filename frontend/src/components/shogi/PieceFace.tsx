import type { PieceVisual } from "../../appearance/types";
import {
  isPieceUpsideDown,
  pieceVisualText,
  type KingGlyphPolicy,
} from "../../appearance/piecePresentation";

export type PieceFaceVariant = "board" | "hand" | "plain";

interface PieceFaceProps {
  piece: PieceVisual;
  flipped?: boolean;
  kingGlyph: KingGlyphPolicy;
  variant: PieceFaceVariant;
}

/** Text-only piece rendering. Interaction and accessible names remain on the parent control. */
export default function PieceFace({
  piece,
  flipped = false,
  kingGlyph,
  variant,
}: PieceFaceProps) {
  const text = pieceVisualText(piece, kingGlyph);
  if (variant === "plain") {
    return <span>{text}</span>;
  }
  const className = [
    "piece-face",
    isPieceUpsideDown(piece, flipped) ? "piece-white" : "piece-black",
    text.length > 1 ? "piece-narrow" : "",
  ].join(" ");
  return <span className={className}>{text}</span>;
}
