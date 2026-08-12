// モバイル下部ナビの「その他」から辿る副次機能メニュー。
import { Link } from "react-router-dom";

const MENU = [
  { to: "/review", title: "復習", desc: "間違えた詰め将棋や次の一手に再挑戦", mobileOnly: true },
  { to: "/history", title: "学習記録", desc: "解答履歴とタイムアタック結果", mobileOnly: true },
  { to: "/problem-editor", title: "問題作成", desc: "詰め将棋問題を作成・編集", mobileOnly: true },
  { to: "/settings", title: "設定", desc: "駒と盤の見た目を変更" },
  { to: "/licenses", title: "データ出典", desc: "取り込みデータの出典とライセンス" },
];

export default function MorePage() {
  return (
    <div className="more-page" data-testid="more-page">
      <h1>その他</h1>
      <div className="home-menu">
        {MENU.map((item) => (
          <Link key={item.to} to={item.to} className={`home-card${item.mobileOnly ? " more-mobile-only" : ""}`}>
            <h2>{item.title}</h2>
            <p>{item.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
