from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from llama_cpp import Llama
except ImportError as exc:  # pragma: no cover
    raise ImportError("llama_cpp not installed; install via `pip install llama-cpp-python`") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate short demo text using llama.cpp.")
    parser.add_argument("--model", required=True, help="Path to GGUF model.")
    parser.add_argument("--prompt", required=True, help="Prompt to generate text from.")
    parser.add_argument("--max-tokens", type=int, default=120)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-ctx", type=int, default=2048)
    parser.add_argument("--n-threads", type=int, default=None)
    parser.add_argument("--ascii-only", action="store_true", help="Strip non-ASCII from output.")
    return parser.parse_args()


def configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        return


def strip_prompt_echo(text: str, prompt: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith(prompt):
        return stripped[len(prompt) :].lstrip()
    prompt_lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    if not prompt_lines:
        return stripped
    text_lines = stripped.splitlines()
    idx = 0
    while idx < len(text_lines) and idx < len(prompt_lines):
        if text_lines[idx].strip() != prompt_lines[idx]:
            break
        idx += 1
    if idx > 0:
        return "\n".join(text_lines[idx:]).lstrip()
    return stripped


def render_completion(llm: Llama, prompt: str, max_tokens: int, temperature: float) -> str:
    try:
        resp = llm.create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "Write a short plain-text note. Output only the note text, no preamble or role labels.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        resp = llm(prompt, max_tokens=max_tokens, temperature=temperature)
        return resp["choices"][0]["text"].strip()


def main() -> int:
    configure_stdout()
    args = parse_args()
    model_path = Path(args.model)
    if not model_path.exists():
        print(f"Model not found: {model_path}", file=sys.stderr)
        return 1
    llm = Llama(
        model_path=str(model_path),
        n_ctx=args.n_ctx,
        n_threads=args.n_threads,
        seed=args.seed,
    )
    text = render_completion(llm, args.prompt, args.max_tokens, args.temperature)
    text = strip_prompt_echo(text, args.prompt)
    if args.ascii_only:
        text = text.encode("ascii", errors="ignore").decode("ascii").strip()
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
