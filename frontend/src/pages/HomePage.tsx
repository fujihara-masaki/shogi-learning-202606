import { Link } from "react-router-dom";

const LEARNING = [
  { to: "/tsume", title: "詰め将棋", desc: "問題を解く・タイムアタックで終盤力を鍛える" },
  { to: "/openings", title: "定跡学習", desc: "定跡の手順を一手ずつ盤面でなぞって覚える" },
  { to: "/next-move", title: "次の一手", desc: "実戦形の局面を見て、自分ならどう指すかを考える" },
];

const TOOLS = [
  { to: "/review", title: "復習", desc: "間違えた詰め将棋や次の一手に再挑戦" },
  { to: "/history", title: "学習記録", desc: "詰め将棋などの解答履歴と学習結果を確認" },
  { to: "/problem-editor", title: "作成", desc: "詰め将棋問題を作成・編集" },
];

function CardGroup({ items }: { items: typeof LEARNING }) {
  return <div className="home-menu">{items.map((item) => (
    <Link key={item.to} to={item.to} className="home-card">
      <h3>{item.title}</h3><p>{item.desc}</p>
    </Link>
  ))}</div>;
}

export default function HomePage() {
  return <div className="home-page">
    <h1>将棋学習アプリ</h1>
    <p className="muted">序盤から終盤まで、学びたいテーマを選びましょう。</p>
    <section aria-labelledby="learning-heading"><h2 id="learning-heading">学習対象</h2><CardGroup items={LEARNING} /></section>
    <section className="home-tools" aria-labelledby="tools-heading"><h2 id="tools-heading">学習を支える機能</h2><CardGroup items={TOOLS} /></section>
  </div>;
}
