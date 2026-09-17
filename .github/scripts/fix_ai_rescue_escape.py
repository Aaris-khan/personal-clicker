from pathlib import Path

path = Path('app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt')
text = path.read_text(encoding='utf-8')
bad = r'Regex("\s+")'
good = r'Regex("\\s+")'
if bad in text:
    text = text.replace(bad, good)
path.write_text(text, encoding='utf-8')

# Refuse to continue if any exact illegal single-backslash whitespace regex remains.
check = path.read_text(encoding='utf-8')
if bad in check:
    raise SystemExit('Kotlin illegal \\s escape still present')
print('Kotlin regex escape repair passed')
