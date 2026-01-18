from __future__ import annotations

import argparse
import ast
import json
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate text for safe SendKeys execution.")
    parser.add_argument("--mode", choices=["calculator", "text"], required=True)
    parser.add_argument("--text", required=True, help="Expression or text to validate.")
    parser.add_argument("--max-len", type=int, default=None)
    parser.add_argument("--allow-non-ascii", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    parser.add_argument("--out", help="Optional JSON output path.")
    return parser.parse_args()


def _ascii_check(text: str) -> tuple[bool, dict[str, Any]]:
    for idx, ch in enumerate(text):
        if ch in ("\n", "\r", "\t"):
            continue
        code = ord(ch)
        if code < 32 or code > 126:
            return False, {"bad_index": idx, "bad_code": code, "bad_char": ch}
    return True, {}


def _safe_calc_ast(node: ast.AST) -> bool:
    if isinstance(node, ast.Expression):
        return _safe_calc_ast(node.body)
    if isinstance(node, ast.Num):  # pragma: no cover - py<3.8
        return isinstance(node.n, (int, float))
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float))
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.UAdd, ast.USub)):
            return False
        return _safe_calc_ast(node.operand)
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod)):
            return False
        return _safe_calc_ast(node.left) and _safe_calc_ast(node.right)
    return False


def validate_calculator(expr: str, max_len: int | None) -> tuple[bool, str, dict[str, Any]]:
    raw = expr.strip()
    details: dict[str, Any] = {"length": len(raw), "max_len": max_len}
    if not raw:
        return False, "empty_expression", details
    if max_len is not None and len(raw) > max_len:
        return False, "expression_too_long", details
    allowed = set("0123456789+-*/().% ")
    for idx, ch in enumerate(raw):
        if ch not in allowed:
            details.update({"bad_index": idx, "bad_char": ch})
            return False, "invalid_character", details
    try:
        parsed = ast.parse(raw, mode="eval")
    except SyntaxError as exc:
        details["syntax_error"] = str(exc)
        return False, "syntax_error", details
    if not _safe_calc_ast(parsed):
        return False, "unsupported_operator", details
    return True, "", details


def validate_text(
    text: str,
    max_len: int | None,
    allow_non_ascii: bool,
    allow_empty: bool,
) -> tuple[bool, str, dict[str, Any]]:
    details: dict[str, Any] = {"length": len(text), "max_len": max_len}
    if not allow_empty and not text.strip():
        return False, "empty_text", details
    if max_len is not None and len(text) > max_len:
        return False, "text_too_long", details
    if not allow_non_ascii:
        ok, bad = _ascii_check(text)
        if not ok:
            details.update(bad)
            return False, "non_ascii_character", details
    return True, "", details


def main() -> int:
    args = parse_args()
    max_len = args.max_len
    if max_len is None:
        max_len = 64 if args.mode == "calculator" else 2000
    if args.mode == "calculator":
        ok, reason, details = validate_calculator(args.text, max_len)
    else:
        ok, reason, details = validate_text(
            args.text, max_len, args.allow_non_ascii, args.allow_empty
        )
    payload = {
        "ok": ok,
        "mode": args.mode,
        "reason": reason,
        "details": details,
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
