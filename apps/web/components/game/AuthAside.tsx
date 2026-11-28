import { GamePreview, previewQuestion } from "@/components/game/Preview";
import { t } from "@/lib/copy";
import type { GameRules, Moves } from "@/lib/types";

/**
 * Beside the sign-in and sign-up forms: what playing is like, in three
 * lines, and one live question as the game shows it. Under the form on a
 * phone, where the guest option has already been offered above it.
 */
export function AuthAside({ rules, moves }: { rules: GameRules | null; moves: Moves | null }) {
  const move = previewQuestion(moves);
  return (
    <aside className="gm-auth__aside" aria-labelledby="gm-aside-title">
      <div className="grid gap-4">
        <h2 id="gm-aside-title" className="gm-label">
          {t.authAsideLabel}
        </h2>
        <ul className="gm-auth__lines">
          {t.authAsideLines(rules?.signup_bonus.display ?? null).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
      {move && moves ? <GamePreview move={move} asOf={moves.as_of} rules={rules} /> : null}
    </aside>
  );
}
