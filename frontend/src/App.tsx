import { BrowserRouter, Navigate, NavLink, Route, Routes, useParams } from "react-router-dom";
import HomePage from "./pages/HomePage";
import TsumePage from "./pages/TsumePage";
import TimeAttackPage from "./pages/TimeAttackPage";
import ReviewPage from "./pages/ReviewPage";
import HistoryPage from "./pages/HistoryPage";
import ProblemEditorPage from "./pages/ProblemEditorPage";
import OpeningsPage from "./pages/OpeningsPage";
import OpeningStudyPage from "./pages/OpeningStudyPage";
import NextMovePage from "./pages/NextMovePage";
import NextMoveStudyPage from "./pages/NextMoveStudyPage";
import LicensesPage from "./pages/LicensesPage";
import MorePage from "./pages/MorePage";

// 旧URL(/openings/next-move/:id)からの互換リダイレクト。
function LegacyNextMoveRedirect() {
  const { id } = useParams();
  return <Navigate to={`/next-move/${id}`} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      {/* デスクトップは上部ナビ、モバイル(<=720px)は主要4項目+「その他」の下部ナビに切り替わる(CSS制御)。 */}
      <nav className="app-nav" aria-label="メインナビゲーション">
        <NavLink to="/" end>
          ホーム
        </NavLink>
        <NavLink to="/tsume">詰め将棋</NavLink>
        <NavLink to="/openings">
          {/* モバイルでは短縮ラベル「定跡」に切り替える(display:none側はアクセシビリティツリーからも除外される) */}
          <span className="nav-label-full">定跡学習</span>
          <span className="nav-label-short">定跡</span>
        </NavLink>
        <NavLink to="/next-move">次の一手</NavLink>
        <NavLink to="/review" className="nav-secondary">復習</NavLink>
        <NavLink to="/time-attack" className="nav-secondary">タイムアタック</NavLink>
        <NavLink to="/history" className="nav-secondary">履歴</NavLink>
        <NavLink to="/problem-editor" className="nav-secondary">問題作成</NavLink>
        <NavLink to="/licenses" className="nav-secondary">データ出典</NavLink>
        <NavLink to="/more" className="nav-more">その他</NavLink>
      </nav>
      <div className="app-body">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/tsume" element={<TsumePage />} />
          <Route path="/time-attack" element={<TimeAttackPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/openings" element={<OpeningsPage />} />
          <Route path="/openings/next-move/:id" element={<LegacyNextMoveRedirect />} />
          <Route path="/openings/:id" element={<OpeningStudyPage />} />
          <Route path="/next-move" element={<NextMovePage />} />
          <Route path="/next-move/:id" element={<NextMoveStudyPage />} />
          <Route path="/problem-editor" element={<ProblemEditorPage />} />
          <Route path="/problem-editor/:id" element={<ProblemEditorPage />} />
          <Route path="/editor" element={<ProblemEditorPage />} />
          <Route path="/licenses" element={<LicensesPage />} />
          <Route path="/more" element={<MorePage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
