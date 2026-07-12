import { useSearchParams } from "react-router-dom";
import NextMoveProblemList from "../components/NextMoveProblemList";
import OpeningLineStudySection from "../components/OpeningLineStudySection";

type OpeningsMode = "lines" | "next-move";

export default function OpeningsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const mode: OpeningsMode = searchParams.get("mode") === "next-move" ? "next-move" : "lines";

  function switchMode(next: OpeningsMode) {
    if (next === mode) return;
    setSearchParams(next === "lines" ? {} : { mode: next }, { replace: true });
  }

  return (
    <div className="openings-page" data-testid="openings-page">
      <h1>定跡学習</h1>
      <p className="muted">学び方を選んでください。手順をなぞって覚えるモードと、局面から一手を考えるモードがあります。</p>

      <section className="opening-source-note" aria-label="データ出典">
        <h2>データ出典</h2>
        <p>
          戦型一覧の初期データは Wikibooks「将棋の戦法一覧」、Wikipedia「将棋の戦法」、Wikipediaカテゴリ「将棋の戦法」を参考に手作業で確認した seed データです。ライセンスは CC BY-SA です。次の一手の問題は、取り込み済みの定跡DB(出典・ライセンスは各問題に表示)から作成しています。
        </p>
      </section>

      <div className="opening-mode-switch" role="group" aria-label="学習モード選択" data-testid="opening-mode-switch">
        <button
          type="button"
          className={mode === "lines" ? "opening-mode-button active" : "opening-mode-button"}
          aria-pressed={mode === "lines"}
          onClick={() => switchMode("lines")}
          data-testid="opening-mode-lines"
        >
          <strong>定跡手順を学ぶ</strong>
          <span>定跡の手順を一手ずつなぞって覚える</span>
        </button>
        <button
          type="button"
          className={mode === "next-move" ? "opening-mode-button active" : "opening-mode-button"}
          aria-pressed={mode === "next-move"}
          onClick={() => switchMode("next-move")}
          data-testid="opening-mode-next-move"
        >
          <strong>次の一手に挑戦する</strong>
          <span>局面を見て自分で一手を考える</span>
        </button>
      </div>

      {mode === "lines" ? <OpeningLineStudySection /> : <NextMoveProblemList />}
    </div>
  );
}
