import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import HomePage from "./pages/HomePage";
import TsumePage from "./pages/TsumePage";
import TimeAttackPage from "./pages/TimeAttackPage";
import ReviewPage from "./pages/ReviewPage";
import HistoryPage from "./pages/HistoryPage";

export default function App() {
  return (
    <BrowserRouter>
      <nav className="app-nav">
        <NavLink to="/" end>
          ホーム
        </NavLink>
        <NavLink to="/tsume">詰め将棋</NavLink>
        <NavLink to="/time-attack">タイムアタック</NavLink>
        <NavLink to="/review">復習</NavLink>
        <NavLink to="/history">履歴</NavLink>
      </nav>
      <div className="app-body">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/tsume" element={<TsumePage />} />
          <Route path="/time-attack" element={<TimeAttackPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/history" element={<HistoryPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
