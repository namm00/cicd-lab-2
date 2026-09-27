import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { api } from './api';
import type { Answer, Quiz, QuizDetail } from './api';

const letters: Answer[] = ['A', 'B', 'C', 'D'];
const message = (error: unknown) => error instanceof Error ? error.message : String(error);

export default function App() {
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [selected, setSelected] = useState<QuizDetail | null>(null);
  const [answers, setAnswers] = useState<Record<number, Answer>>({});
  const [score, setScore] = useState<number | null>(null);
  const [version, setVersion] = useState('đang tải…');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([api<Quiz[]>('/quizzes'), api<{ version: string }>('/version')])
      .then(([list, build]) => { if (active) { setQuizzes(list); setVersion(build.version); } })
      .catch((error: unknown) => { if (active) setError(message(error)); });
    return () => { active = false; };
  }, []);

  async function openQuiz(id: number) {
    setBusy(true); setError('');
    try {
      setSelected(await api<QuizDetail>(`/quizzes/${id}`));
      setAnswers({}); setScore(null);
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }

  async function createQuiz(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const title = String(new FormData(form).get('title')).trim();
    if (!title) return;
    setBusy(true); setError('');
    try {
      const quiz = await api<Quiz>('/quizzes', { title });
      setQuizzes((list) => [quiz, ...list]);
      setSelected({ ...quiz, questions: [] }); setAnswers({}); setScore(null);
      form.reset();
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }

  async function addQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form));
    setBusy(true); setError('');
    try {
      await api(`/quizzes/${selected.id}/questions`, payload);
      setSelected(await api<QuizDetail>(`/quizzes/${selected.id}`));
      setAnswers({}); setScore(null); form.reset();
    } catch (error) { setError(message(error)); }
    finally { setBusy(false); }
  }

  return <main>
    <header>
      <p>CI/CD LAB 2</p>
      <h1>Mini Quiz</h1>
      <p>Tạo quiz, thêm câu hỏi và thử trả lời.</p>
      <small>Frontend: <code>{import.meta.env.VITE_APP_VERSION ?? 'local'}</code><br />
        Backend: <code>{version}</code></small>
    </header>
    {error && <p role="alert" className="error">{error}</p>}
    <section>
      <h2>Tạo quiz</h2>
      <form onSubmit={(event) => void createQuiz(event)}>
        <label>Tiêu đề <input name="title" required maxLength={200} /></label>
        <button disabled={busy}>Tạo quiz</button>
      </form>
      <h2>Danh sách quiz</h2>
      {quizzes.length === 0 && <p>Chưa có quiz. Hãy tạo quiz đầu tiên.</p>}
      <ul>{quizzes.map((quiz) => <li key={quiz.id}>
        <button disabled={busy} onClick={() => void openQuiz(quiz.id)}>{quiz.title}</button>
      </li>)}</ul>
    </section>
    {selected && <section>
      <h2>{selected.title}</h2>
      <details>
        <summary>Thêm câu hỏi</summary>
        <form key={selected.id} onSubmit={(event) => void addQuestion(event)}>
          <label>Câu hỏi <textarea name="question_text" required maxLength={2000} /></label>
          {letters.map((letter) => <label key={letter}>Đáp án {letter}
            <input name={`option_${letter.toLowerCase()}`} required maxLength={500} />
          </label>)}
          <label>Đáp án đúng <select name="correct_answer">
            {letters.map((letter) => <option key={letter}>{letter}</option>)}
          </select></label>
          <button disabled={busy}>Lưu câu hỏi</button>
        </form>
      </details>
      <h3>Làm quiz</h3>
      {selected.questions.length === 0 && <p>Quiz này chưa có câu hỏi.</p>}
      {selected.questions.map((question, index) => <fieldset key={question.id}>
        <legend>{index + 1}. {question.question_text}</legend>
        {letters.map((letter) => <label className="answer" key={letter}>
          <input type="radio" name={`question-${question.id}`}
            checked={answers[question.id] === letter}
            onChange={() => { setAnswers({ ...answers, [question.id]: letter }); setScore(null); }} />
          {letter}. {question[`option_${letter.toLowerCase()}` as 'option_a' | 'option_b' | 'option_c' | 'option_d']}
        </label>)}
      </fieldset>)}
      {selected.questions.length > 0 && <button disabled={busy || selected.questions.some((q) => !answers[q.id])}
        onClick={() => setScore(selected.questions.filter((q) => answers[q.id] === q.correct_answer).length)}>
        Chấm điểm
      </button>}
      {score !== null && <p role="status"><strong>Điểm: {score}/{selected.questions.length}</strong></p>}
    </section>}
  </main>;
}
