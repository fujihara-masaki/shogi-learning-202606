import { NavLink } from "react-router-dom";

const MODES = [
  { to: "/tsume", label: "問題を解く" },
  { to: "/time-attack", label: "タイムアタック" },
];

/** 詰め将棋に属する学習モードを、各モード画面で共通表示する。 */
export default function TsumeModeNav() {
  return (
    <nav className="tsume-mode-nav" aria-label="詰め将棋の学習モード">
      {MODES.map((mode) => (
        <NavLink key={mode.to} to={mode.to} end>{mode.label}</NavLink>
      ))}
    </nav>
  );
}
