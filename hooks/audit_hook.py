#!/usr/bin/env python3
"""Stop hook: audit the assistant's last answer against the personal concept graph.

Off by default. Turn it on with `/calibrate:audit-hook on [block]`, which creates
$PERSONAL_KG_DIR/.audit_on (its content is the mode):
    warn   show the findings to the user, never interrupt (default)
    block  ask the assistant to add the missing glosses before finishing
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "calibrate" / "scripts"))
import kg  # noqa: E402


def last_assistant_text(data):
    message = data.get("last_assistant_message")
    if isinstance(message, str) and message.strip():
        return message
    path = data.get("transcript_path")
    if not path or not Path(path).is_file():
        return ""
    texts = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        content = (record.get("message") or {}).get("content")
        if record.get("type") == "user":
            # a real user turn starts a new answer; tool results do not
            blocks = content if isinstance(content, list) else []
            if isinstance(content, str) or any(
                    isinstance(b, dict) and b.get("type") == "text" for b in blocks):
                texts = []
        elif record.get("type") == "assistant" and isinstance(content, list):
            texts += [b.get("text", "") for b in content
                      if isinstance(b, dict) and b.get("type") == "text"]
    return "\n\n".join(texts)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    flag = kg.DATA_DIR / ".audit_on"
    if not flag.is_file():
        return
    mode = flag.read_text(encoding="utf-8").strip() or "warn"
    text = last_assistant_text(data)
    if not text.strip():
        return
    result = kg.run_audit(text)
    if not result["failures"] and not result["warnings"]:
        return

    lines = []
    if result["failures"]:
        names = "、".join(f["term"] for f in result["failures"])
        lines.append(f"Calibrate: 这些你标记为没看懂的概念首次出现时没有行内注释：{names}")
    if result["warnings"]:
        names = "、".join(w["term"] for w in result["warnings"][:8])
        lines.append(f"疑似未登记术语（图谱里没有，也没注释）：{names}。"
                     "可用 /calibrate:unclear 或 /calibrate:learned 登记")
    message = "\n".join(lines)

    if mode == "block" and result["failures"] and not data.get("stop_hook_active"):
        print(json.dumps({
            "decision": "block",
            "reason": message + "\n请在这些概念首次出现处补上一句话的行内注释（括号形式），"
                                "不要改动其他内容，然后简短说明已补充。",
        }, ensure_ascii=False))
    else:
        print(json.dumps({"systemMessage": message}, ensure_ascii=False))


if __name__ == "__main__":
    main()
