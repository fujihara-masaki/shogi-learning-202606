import { Link } from "react-router-dom";

const MENU = [
  { to: "/tsume", title: "詰め将棋", desc: "1手詰〜5手詰の問題に挑戦", enabled: true },
  { to: "/time-attack", title: "タイムアタック", desc: "連続出題でタイムを計測", enabled: true },
  { to: "/review", title: "復習", desc: "間違えた問題・お気に入りに再挑戦", enabled: true },
  { to: "/openings", title: "定跡学習", desc: "戦型別に序盤の推奨手を盤面で練習", enabled: true },
  { to: "/history", title: "履歴", desc: "解答履歴とタイムアタック結果", enabled: true },
  { to: "/problem-editor", title: "問題作成", desc: "盤面エディタで詰め将棋問題を作成・編集", enabled: true },
];

export default function HomePage() {
  return (
    <div className="home-page">
      <h1>将棋学習アプリ</h1>
      <p className="muted">詰め将棋で終盤力を鍛えましょう。</p>
      <div className="home-menu">
        {MENU.map((item) =>
          item.enabled ? (
            <Link key={item.to} to={item.to} className="home-card">
              <h2>{item.title}</h2>
              <p>{item.desc}</p>
            </Link>
          ) : (
            <div key={item.to} className="home-card disabled">
              <h2>{item.title}</h2>
              <p>{item.desc}</p>
            </div>
          ),
        )}
      </div>
    </div>
  );
}
