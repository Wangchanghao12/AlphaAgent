#!/usr/bin/env python3
"""
对研报 MD 文件中的 - **XXX** 三级标题下内容添加 4 空格缩进（结构可视化）。
用法: python3 indent_report.py <report.md> [<report2.md> ...]
"""
import sys
import re


INDENT = '    '  # 4 空格，与「大盘走势」等块保持一致，编辑器中可见


def indent_third_level_content(text):
    """
    对 - **XXX** 三级标题下的内容添加 4 空格缩进，使结构可视化。
    规则：遇到 - **XXX** 后，直到下一个 - **XXX** 或 ### / ## / --- 之前的所有行都缩进。
    """
    if not text or not text.strip():
        return text
    lines = text.split('\n')
    result = []
    in_section_content = False
    for line in lines:
        stripped = line.strip()
        is_section_header = bool(re.match(r'^-\s+\*\*[^*]+\*\*', stripped))
        is_top_level = stripped.startswith('###') or stripped.startswith('##') or stripped.startswith('---')

        if is_section_header and not is_top_level:
            in_section_content = True
            result.append(line)
        elif is_top_level:
            in_section_content = False
            result.append(line)
        elif in_section_content:
            # 已有 4 空格缩进则不再添加；若为制表符则替换为 4 空格
            if line.startswith(INDENT):
                result.append(line)
            elif line.startswith('\t'):
                result.append(INDENT + line.lstrip('\t'))
            else:
                result.append(INDENT + line)
        else:
            result.append(line)
    return '\n'.join(result)


def main():
    if len(sys.argv) < 2:
        print("用法: python3 indent_report.py <report.md> [<report2.md> ...]")
        print("示例: python3 indent_report.py ../reports/aaa.md")
        sys.exit(1)

    for path in sys.argv[1:]:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            out = indent_third_level_content(content)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(out)
            print(f"✅ 已修复缩进: {path}")
        except Exception as e:
            print(f"❌ 处理失败 {path}: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
