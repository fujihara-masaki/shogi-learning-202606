import { useState } from "react";
import type { ResolvedPieceAsset } from "../../appearance/pieceResolver";
import type { PieceVisual } from "../../appearance/types";
import type { KingGlyphPolicy } from "../../appearance/piecePresentation";
import TextPieceFace from "./TextPieceFace";
import type { PieceFaceVariant } from "./PieceFace";

export default function ImagePieceFace({ asset, piece, flipped, kingGlyph, variant }: { asset: ResolvedPieceAsset; piece: PieceVisual; flipped: boolean; kingGlyph: KingGlyphPolicy; variant: PieceFaceVariant }) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  if (failedSrc === asset.src) return <TextPieceFace {...{ piece, flipped, kingGlyph, variant }} />;
  return <img className={`piece-face piece-image piece-image-${variant}${asset.rotate ? " piece-image-rotated" : ""}`} src={asset.src} alt="" draggable={false} onError={() => setFailedSrc(asset.src)} />;
}
