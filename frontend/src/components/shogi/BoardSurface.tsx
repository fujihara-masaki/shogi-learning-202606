import { forwardRef, type ComponentPropsWithoutRef, type CSSProperties } from "react";
import { getBoardTheme } from "../../appearance/catalog";
import type { BoardThemeId } from "../../appearance/types";

type BoardSurfaceProps = ComponentPropsWithoutRef<"div"> & { boardTheme?: BoardThemeId };

/** The visual board boundary; deliberately renders exactly one existing board element. */
const BoardSurface = forwardRef<HTMLDivElement, BoardSurfaceProps>(function BoardSurface(
  { className = "", boardTheme = "board-standard", style, ...props },
  ref,
) {
  const theme = getBoardTheme(boardTheme) ?? getBoardTheme("board-standard")!;
  const themeStyle = {
    "--board-fallback-color": theme.fallbackColor,
    "--board-line-color": theme.lineColor,
    "--board-background-image": theme.backgroundImage ? `url("${theme.backgroundImage}")` : "none",
    ...style,
  } as CSSProperties;
  return <div ref={ref} className={`board-surface ${className}`.trim()} data-board-theme={theme.id} data-board-image={theme.backgroundImage ? "true" : undefined} style={themeStyle} {...props} />;
});

export default BoardSurface;
