export type Answer = 'A' | 'B' | 'C' | 'D';
export type Question = {
  id: number;
  question_text: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  correct_answer: Answer;
};
export type Quiz = { id: number; title: string; created_at: string };
export type QuizDetail = Quiz & { questions: Question[] };

// Relative URLs work from any browser. The frontend container proxies /api.
export async function api<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, payload === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}
