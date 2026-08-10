import { getPieceTheme } from "../../appearance/catalog";
import { resolvePieceAsset } from "../../appearance/pieceResolver";
import type { KingGlyphPolicy } from "../../appearance/piecePresentation";
import type { PieceLocation, PieceThemeId, PieceVisual } from "../../appearance/types";
import ImagePieceFace from "./ImagePieceFace";
import TextPieceFace from "./TextPieceFace";

export type PieceFaceVariant = "board" | "hand" | "plain";
export interface PieceFaceProps { piece: PieceVisual; flipped?: boolean; kingGlyph: KingGlyphPolicy; variant: PieceFaceVariant; pieceTheme?: PieceThemeId; location?: PieceLocation }

export default function PieceFace({ piece, flipped = false, kingGlyph, variant, pieceTheme = "text-standard", location = variant === "hand" ? "hand" : "board" }: PieceFaceProps) {
  const asset = resolvePieceAsset(getPieceTheme(pieceTheme), piece, kingGlyph, location, flipped);
  return asset ? <ImagePieceFace {...{ asset, piece, flipped, kingGlyph, variant }} /> : <TextPieceFace {...{ piece, flipped, kingGlyph, variant }} />;
}
