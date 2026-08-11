import type { BoardThemeId, PieceThemeId, PieceVisual } from "../appearance/types";
import BoardSurface from "./shogi/BoardSurface";
import PieceFace from "./shogi/PieceFace";

const pieces: Array<PieceVisual | null> = [
  { side: "white", kind: "rook", promoted: false }, null, { side: "white", kind: "pawn", promoted: false },
  null, { side: "black", kind: "bishop", promoted: true }, null,
  { side: "black", kind: "pawn", promoted: false }, null, { side: "black", kind: "king", promoted: false },
];

export default function AppearancePreview({ pieceTheme, boardTheme }: { pieceTheme: PieceThemeId; boardTheme: BoardThemeId }) {
  return (
    <section className="appearance-preview" aria-labelledby="appearance-preview-title">
      <h2 id="appearance-preview-title">プレビュー</h2>
      <div className="preview-hand"><span>後手の持ち駒</span><PieceFace pieceTheme={pieceTheme} piece={{ side: "white", kind: "silver", promoted: false }} kingGlyph="all-gyoku" variant="hand" /></div>
      <BoardSurface className="preview-board" boardTheme={boardTheme} aria-label="選択した表示テーマの3×3プレビュー">
        {pieces.map((piece, index) => <div className="preview-cell" key={index}>{piece && <PieceFace pieceTheme={pieceTheme} piece={piece} kingGlyph="all-gyoku" variant="board" />}</div>)}
      </BoardSurface>
      <div className="preview-hand"><span>先手の持ち駒</span><PieceFace pieceTheme={pieceTheme} piece={{ side: "black", kind: "gold", promoted: false }} kingGlyph="all-gyoku" variant="hand" /></div>
    </section>
  );
}
