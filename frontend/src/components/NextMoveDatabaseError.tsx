import { ApiError } from "../api/client";

export function NextMoveDatabaseError({ error }: { error: ApiError }) {
  return (
    <aside className="next-move-db-error" data-testid="next-move-db-recovery">
      <div className="banner banner-error" role="alert">
        <strong>次の一手データを利用できません</strong>
        <p>{error.detail}</p>
      </div>
      <section aria-labelledby="next-move-db-recovery-heading">
        <h2 id="next-move-db-recovery-heading">次の一手専用DBの復旧手順</h2>
        <p>
          READMEの「<a href="https://github.com/fujihara-masaki/shogi-learning-202606#通常dbと次の一手専用db">通常DBと次の一手専用DB</a>」と
          「<a href="https://github.com/fujihara-masaki/shogi-learning-202606#やねうら王定跡からの学習用サンプル抽出">やねうら王定跡からの学習用サンプル抽出</a>」を参照してください。
        </p>
        <ol>
          <li><code>NEXT_MOVE_DB_PATH</code>が正しい次の一手専用DBを指しているか確認します。</li>
          <li>外部定跡をimportし、学習用サンプルを抽出します。</li>
          <li><code>validate_next_move_db.py</code>で読み取り専用検証を行います。</li>
        </ol>
        <pre><code>{`cd backend

NEXT_MOVE_DB_PATH=./data/next_move.db python -m app.importers.yaneuraou_book <book.db> \\
  --name "YaneuraOu Book" --source-url <URL> --license-name <LICENSE>

NEXT_MOVE_DB_PATH=./data/next_move.db python -m app.scripts.extract_learning_samples \\
  --source-id <ID> --limit 10000 --per-opening-limit 500 --seed 1

python scripts/validate_next_move_db.py ./data/next_move.db \\
  --expected-learning-samples 10000`}</code></pre>
      </section>
    </aside>
  );
}
