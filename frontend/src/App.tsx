import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import HomePage from "./pages/HomePage";
import TsumePage from "./pages/TsumePage";
import TimeAttackPage from "./pages/TimeAttackPage";
import ReviewPage from "./pages/ReviewPage";
import HistoryPage from "./pages/HistoryPage";
import ProblemEditorPage from "./pages/ProblemEditorPage";
import OpeningsPage from "./pages/OpeningsPage";
import OpeningStudyPage from "./pages/OpeningStudyPage";

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
        <NavLink to="/openings">定跡学習</NavLink>
        <NavLink to="/problem-editor">問題作成</NavLink>
      </nav>
      <div className="app-body">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/tsume" element={<TsumePage />} />
          <Route path="/time-attack" element={<TimeAttackPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/openings" element={<OpeningsPage />} />
          <Route path="/openings/:id" element={<OpeningStudyPage />} />
          <Route path="/problem-editor" element={<ProblemEditorPage />} />
          <Route path="/problem-editor/:id" element={<ProblemEditorPage />} />
          <Route path="/editor" element={<ProblemEditorPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}