import { Navigate, useSearchParams } from "react-router-dom";
import OpeningLineStudySection from "../components/OpeningLineStudySection";

export default function OpeningsPage() {
  const [searchParams] = useSearchParams();

  // 旧URL(/openings?mode=next-move)からの互換リダイレクト。
  if (searchParams.get("mode") === "next-move") {
    return <Navigate to="/next-move" replace />;
  }

  return (
    <div className="openings-page" data-testid="openings-page">
      <h1>定跡学習</h1>
      <p className="muted">定跡の手順を一手ずつ盤面でなぞって覚えましょう。</p>

      <section className="opening-source-note" aria-label="データ出典">
        <h2>データ出典</h2>
        <p>
          戦型一覧の初期データは Wikibooks「将棋の戦法一覧」、Wikipedia「将棋の戦法」、Wikipediaカテゴリ「将棋の戦法」を参考に手作業で確認した seed データです。ライセンスは CC BY-SA です。
        </p>
      </section>

      <OpeningLineStudySection />
    </div>
  );
}
