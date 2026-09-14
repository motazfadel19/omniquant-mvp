"""
يحذف الإيموجي من ملفات Python تلقائياً.
شغّله مرة واحدة، وحل مشكلة Unicode للأبد.
"""
import re
import pathlib

# خريطة: كل إيموجي → بديل نصي
REPLACEMENTS = {
    "[>>]": "[>>]",
    "[OK]": "[OK]",
    "[X]": "[X]",
    "[!]": "[!]",
    "[!]":  "[!]",
    "[AI]": "[AI]",
    "[STREAM]": "[STREAM]",
    "[LOG]": "[LOG]",
    "[LOAD]": "[LOAD]",
    "[TARGET]": "[TARGET]",
    "[DB]": "[DB]",
    "[REJECT]": "[REJECT]",
    "[STOP]": "[STOP]",
    "[FAST]": "[FAST]",
    "[HOT]": "[HOT]",
    "[STATS]": "[STATS]",
    "[CLEAN]": "[CLEAN]",
    "[SYNC]": "[SYNC]",
    "[DATE]": "[DATE]",
    "[WAVE]": "[WAVE]",
    "[PAUSE]": "[PAUSE]",
    "[UP]": "[UP]",
    "[SAFE]": "[SAFE]",
    "[WAIT]": "[WAIT]",
    "[BLOCK]": "[BLOCK]",
    "-": "-",
    "|": "|",
    "+": "+",
    "+": "+",
    "+": "+",
    "+": "+",
    "+": "+",
}


def clean_file(path: pathlib.Path) -> tuple[int, str]:
    """يحذف الإيموجي من ملف. يرجع (عدد التعديلات، اسم الملف)."""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return 0, f"skip: {e}"

    original = content
    count = 0

    for emoji, replacement in REPLACEMENTS.items():
        if emoji in content:
            count += content.count(emoji)
            content = content.replace(emoji, replacement)

    # حذف أي إيموجي متبقٍ (مجموعة Unicode Emoji blocks)
    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F9FF"  # symbols & pictographs
        "\U0001FA00-\U0001FAFF"  # symbols extended
        "\U0001F1E6-\U0001F1FF"  # flags
        "\u2600-\u27BF"          # misc symbols
        "\uFE0F"                 # variation selector
        "]+",
        flags=re.UNICODE,
    )
    content, n = emoji_pattern.subn("", content)
    count += n

    if content != original:
        path.write_text(content, encoding="utf-8")
        return count, path.name
    return 0, path.name


def main():
    base = pathlib.Path(".")
    total = 0

    print("Cleaning emoji from Python files...")
    print("-" * 50)

    for py_file in base.rglob("*.py"):
        if "venv" in str(py_file) or "site-packages" in str(py_file):
            continue
        if ".next" in str(py_file) or "node_modules" in str(py_file):
            continue

        count, name = clean_file(py_file)
        if count > 0:
            print(f"  {name:30} {count} replacements")
            total += count

    print("-" * 50)
    print(f"Total: {total} replacements")
    print("Done. Restart uvicorn now.")


if __name__ == "__main__":
    main()