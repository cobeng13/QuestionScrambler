#!/usr/bin/env python3
"""Extract, shuffle, and export MCQ question banks.

Features:
- CLI mode and Tkinter GUI mode (run with ``--gui`` or no args)
- Keeps only valid question blocks from the source text
- Renumbers questions sequentially
- Shuffles A-D choices and rewrites the correct answer letter
- Can export a single combined file or split files (questions + answer key)

This file uses only the Python standard library so it is easy to package as an
EXE with tools such as PyInstaller.
"""

from __future__ import annotations

import argparse
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

QUESTION_START_RE = re.compile(r"^\s*(\d+)\.\s*(.*)$")
CHOICE_RE = re.compile(r"^\s*([A-D])\.\s+(.*)$")
ANSWER_RE = re.compile(r"^\s*answer\s*:\s*([A-D])\s*$", re.IGNORECASE)


class ParseError(ValueError):
    """Raised when a question-like block is malformed."""


@dataclass
class Question:
    stem_lines: List[str]
    choices: List[Tuple[str, str]]  # (orig_letter, choice_text)
    answer_letter: str
    start_line_no: int


@dataclass
class ShuffledQuestion:
    stem_lines: List[str]
    shuffled_choices: List[str]
    new_answer_letter: str


def snippet(lines: Sequence[str], start: int, end: int) -> str:
    lo = max(0, start - 1)
    hi = min(len(lines), end)
    return "\n".join(lines[lo:hi])


def parse_questions(lines: List[str]) -> Tuple[List[Question], int]:
    """Scan file lines and extract only valid MCQ blocks.

    Returns:
        (questions, discarded_non_question_lines)
    """
    questions: List[Question] = []
    discarded_lines = 0
    i = 0
    n = len(lines)

    while i < n:
        qmatch = QUESTION_START_RE.match(lines[i])
        if not qmatch:
            discarded_lines += 1
            i += 1
            continue

        start_idx = i
        start_line_no = i + 1
        first_stem = qmatch.group(2)
        stem_lines = [first_stem] if first_stem else []
        i += 1

        # If numbering line is standalone (e.g., "1."), skip spacer blanks before stem text.
        while i < n and not stem_lines and lines[i].strip() == "":
            i += 1

        # Continue stem until the first choice line.
        while i < n and not CHOICE_RE.match(lines[i]):
            if QUESTION_START_RE.match(lines[i]):
                raise ParseError(
                    f"Malformed question near line {start_line_no}: missing choices before next question start.\n"
                    f"Snippet:\n{snippet(lines, start_line_no, i + 1)}"
                )
            stem_lines.append(lines[i])
            i += 1

        if not stem_lines:
            raise ParseError(
                f"Malformed question near line {start_line_no}: missing question stem text before choices.\n"
                f"Snippet:\n{snippet(lines, start_line_no, min(n, i + 2))}"
            )

        if i >= n:
            raise ParseError(
                f"Malformed question near line {start_line_no}: reached EOF before choices.\n"
                f"Snippet:\n{snippet(lines, start_line_no, min(n, start_idx + 8))}"
            )

        choices: List[Tuple[str, str]] = []
        seen_letters = set()

        while i < n and len(choices) < 4:
            if lines[i].strip() == "":
                i += 1
                continue
            cmatch = CHOICE_RE.match(lines[i])
            if not cmatch:
                raise ParseError(
                    f"Malformed question near line {start_line_no}: expected choice line A-D around line {i + 1}.\n"
                    f"Snippet:\n{snippet(lines, start_line_no, min(n, i + 3))}"
                )
            letter, text = cmatch.group(1), cmatch.group(2)
            if letter in seen_letters:
                raise ParseError(
                    f"Malformed question near line {start_line_no}: duplicate choice letter '{letter}' at line {i + 1}.\n"
                    f"Snippet:\n{snippet(lines, start_line_no, min(n, i + 2))}"
                )
            seen_letters.add(letter)
            choices.append((letter, text))
            i += 1

        if seen_letters != {"A", "B", "C", "D"}:
            raise ParseError(
                f"Malformed question near line {start_line_no}: expected exactly one choice each for A, B, C, and D.\n"
                f"Snippet:\n{snippet(lines, start_line_no, min(n, i + 2))}"
            )

        while i < n and lines[i].strip() == "":
            i += 1

        if i >= n:
            raise ParseError(
                f"Malformed question near line {start_line_no}: missing Answer line before EOF.\n"
                f"Snippet:\n{snippet(lines, start_line_no, min(n, start_idx + 12))}"
            )

        amatch = ANSWER_RE.match(lines[i])
        if not amatch:
            raise ParseError(
                f"Malformed question near line {start_line_no}: expected 'Answer: <A-D>' around line {i + 1}.\n"
                f"Snippet:\n{snippet(lines, start_line_no, min(n, i + 2))}"
            )

        questions.append(
            Question(
                stem_lines=stem_lines,
                choices=choices,
                answer_letter=amatch.group(1).upper(),
                start_line_no=start_line_no,
            )
        )
        i += 1

    return questions, discarded_lines


def shuffle_questions(questions: Sequence[Question], rng: random.Random) -> List[ShuffledQuestion]:
    """Shuffle each question's choices and compute remapped answer letter."""
    shuffled_questions: List[ShuffledQuestion] = []

    for question in questions:
        shuffled = list(question.choices)
        rng.shuffle(shuffled)

        correct_choice = next(c for c in question.choices if c[0] == question.answer_letter)
        correct_idx = next(idx for idx, c in enumerate(shuffled) if c == correct_choice)

        shuffled_questions.append(
            ShuffledQuestion(
                stem_lines=question.stem_lines,
                shuffled_choices=[text for _, text in shuffled],
                new_answer_letter="ABCD"[correct_idx],
            )
        )

    return shuffled_questions


def format_combined(questions: Sequence[ShuffledQuestion]) -> str:
    out: List[str] = []
    for i, q in enumerate(questions, start=1):
        out.append(f"{i}. {q.stem_lines[0]}")
        out.extend(q.stem_lines[1:])
        for letter, text in zip("ABCD", q.shuffled_choices):
            out.append(f"{letter}. {text}")
        out.append("")
        out.append(f"Answer: {q.new_answer_letter}")
        out.append("")
    return "\n".join(out)


def format_questions_only(questions: Sequence[ShuffledQuestion]) -> str:
    out: List[str] = []
    for i, q in enumerate(questions, start=1):
        out.append(f"{i}. {q.stem_lines[0]}")
        out.extend(q.stem_lines[1:])
        for letter, text in zip("ABCD", q.shuffled_choices):
            out.append(f"{letter}. {text}")
        out.append("")
    return "\n".join(out)


def format_answers_only(questions: Sequence[ShuffledQuestion]) -> str:
    out: List[str] = []
    for i, q in enumerate(questions, start=1):
        out.append(f"{i}. {q.new_answer_letter}")
    return "\n".join(out) + ("\n" if out else "")


def _build_default_split_paths(output_path: Path) -> Tuple[Path, Path]:
    base = output_path.with_suffix("")
    return (base.with_name(base.name + "_questions.txt"), base.with_name(base.name + "_answers.txt"))


def process_file(
    input_path: Path,
    output_path: Path,
    *,
    seed: int | None,
    inplace: bool,
    split_outputs: bool,
    questions_out: Path | None,
    answers_out: Path | None,
) -> str:
    raw = input_path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    rng = random.Random(seed)
    parsed, discarded = parse_questions(lines)
    shuffled = shuffle_questions(parsed, rng)

    target_output = input_path if inplace else output_path

    if split_outputs:
        q_path = questions_out
        a_path = answers_out
        if q_path is None or a_path is None:
            q_path, a_path = _build_default_split_paths(target_output)

        q_path.write_text(format_questions_only(shuffled), encoding="utf-8")
        a_path.write_text(format_answers_only(shuffled), encoding="utf-8")

        return (
            f"Questions processed: {len(shuffled)} | "
            f"Discarded non-question lines: {discarded} | "
            f"Questions file: {q_path} | Answers file: {a_path}"
        )

    target_output.write_text(format_combined(shuffled), encoding="utf-8")
    return (
        f"Questions processed: {len(shuffled)} | "
        f"Discarded non-question lines: {discarded} | "
        f"Output: {target_output}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract valid MCQs, shuffle choices, renumber questions, and export outputs."
    )
    parser.add_argument("input", nargs="?", help="Input text file")
    parser.add_argument("output", nargs="?", help="Output text file")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--inplace", action="store_true", help="Overwrite input (combined mode)")
    parser.add_argument("--gui", action="store_true", help="Launch desktop GUI")
    parser.add_argument(
        "--split",
        action="store_true",
        help="Write two files: one with shuffled questions and one answer key",
    )
    parser.add_argument("--questions-out", help="Custom path for split questions output")
    parser.add_argument("--answers-out", help="Custom path for split answer-key output")
    return parser


def launch_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title("MCQ Shuffler")
    root.geometry("760x340")

    input_var = tk.StringVar()
    output_var = tk.StringVar()
    seed_var = tk.StringVar()
    split_var = tk.BooleanVar(value=True)

    def browse_input() -> None:
        path = filedialog.askopenfilename(title="Select input file")
        if path:
            input_var.set(path)
            if not output_var.get():
                output_var.set(str(Path(path).with_name(Path(path).stem + "_shuffled.txt")))

    def browse_output() -> None:
        path = filedialog.asksaveasfilename(title="Select output file")
        if path:
            output_var.set(path)

    def run_now() -> None:
        try:
            input_path = Path(input_var.get().strip())
            output_text = output_var.get().strip()
            if not input_path:
                raise ValueError("Please choose an input file.")
            if not output_text:
                raise ValueError("Please choose an output file path.")
            seed = int(seed_var.get()) if seed_var.get().strip() else None

            msg = process_file(
                input_path=input_path,
                output_path=Path(output_text),
                seed=seed,
                inplace=False,
                split_outputs=split_var.get(),
                questions_out=None,
                answers_out=None,
            )
            messagebox.showinfo("Success", msg)
        except Exception as exc:  # GUI boundary
            messagebox.showerror("Error", str(exc))

    row = 0
    tk.Label(root, text="Input file:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
    tk.Entry(root, textvariable=input_var, width=75).grid(row=row, column=1, padx=6)
    tk.Button(root, text="Browse", command=browse_input).grid(row=row, column=2, padx=10)

    row += 1
    tk.Label(root, text="Output base file:").grid(row=row, column=0, sticky="w", padx=10, pady=8)
    tk.Entry(root, textvariable=output_var, width=75).grid(row=row, column=1, padx=6)
    tk.Button(root, text="Browse", command=browse_output).grid(row=row, column=2, padx=10)

    row += 1
    tk.Label(root, text="Seed (optional):").grid(row=row, column=0, sticky="w", padx=10, pady=8)
    tk.Entry(root, textvariable=seed_var, width=20).grid(row=row, column=1, sticky="w", padx=6)

    row += 1
    tk.Checkbutton(
        root,
        text="Generate separate files: questions + answer key",
        variable=split_var,
    ).grid(row=row, column=1, sticky="w", padx=6, pady=8)

    row += 1
    tk.Button(root, text="Process", command=run_now, width=18).grid(row=row, column=1, sticky="w", padx=6, pady=15)

    tk.Label(
        root,
        text="EXE tip: pyinstaller --onefile --windowed shuffle_mcq.py",
        fg="#555",
    ).grid(row=row + 1, column=0, columnspan=3, sticky="w", padx=10)

    root.mainloop()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.gui or args.input is None:
        launch_gui()
        return

    output_text = args.output
    if output_text is None and not args.inplace:
        raise ValueError("output path is required unless --inplace is used")

    message = process_file(
        input_path=Path(args.input),
        output_path=Path(output_text) if output_text else Path(args.input),
        seed=args.seed,
        inplace=args.inplace,
        split_outputs=args.split,
        questions_out=Path(args.questions_out) if args.questions_out else None,
        answers_out=Path(args.answers_out) if args.answers_out else None,
    )
    print(message)


if __name__ == "__main__":
    main()
