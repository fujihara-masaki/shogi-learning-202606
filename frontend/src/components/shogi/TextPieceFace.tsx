import type { PieceVisual } from "../../appearance/types";
import { isPieceUpsideDown, pieceVisualText, type KingGlyphPolicy } from "../../appearance/piecePresentation";
import type { PieceFaceVariant } from "./PieceFace";

export default function TextPieceFace({ piece, flipped = false, kingGlyph, variant }: { piece: PieceVisual; flipped?: boolean; kingGlyph: KingGlyphPolicy; variant: PieceFaceVariant }) {
  const text = pieceVisualText(piece, kingGlyph);
  if (variant === "plain") return <span>{text}</span>;
  return <span className={["piece-face", isPieceUpsideDown(piece, flipped) ? "piece-white" : "piece-black", text.length > 1 ? "piece-narrow" : ""].join(" ")}>{text}</span>;
}
