import { forwardRef, type ComponentPropsWithoutRef } from "react";

type BoardSurfaceProps = ComponentPropsWithoutRef<"div">;

/** The visual board boundary; deliberately renders exactly one existing board element. */
const BoardSurface = forwardRef<HTMLDivElement, BoardSurfaceProps>(function BoardSurface(
  { className = "", ...props },
  ref,
) {
  return <div ref={ref} className={`board-surface ${className}`.trim()} {...props} />;
});

export default BoardSurface;
