// モバイル下部ナビの「その他」から辿る副次機能メニュー。
import { Link } from "react-router-dom";

const MENU = [
  { to: "/time-attack", title: "タイムアタック", desc: "連続出題でタイムを計測" },
  { to: "/history", title: "履歴", desc: "解答履歴とタイムアタック結果" },
  { to: "/problem-editor", title: "問題作成", desc: "盤面エディタで詰め将棋問題を作成・編集" },
  { to: "/licenses", title: "データ出典", desc: "取り込みデータの出典とライセンス" },
];

export default function MorePage() {
  return (
    <div className="more-page" data-testid="more-page">
      <h1>その他</h1>
      <div className="home-menu">
        {MENU.map((item) => (
          <Link key={item.to} to={item.to} className="home-card">
            <h2>{item.title}</h2>
            <p>{item.desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
