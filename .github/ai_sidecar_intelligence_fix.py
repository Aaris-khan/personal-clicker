from pathlib import Path

p = Path('app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt')
s = p.read_text(encoding='utf-8')

bad = r'Regex("\s+")'
good = r'Regex("\\s+")'
count = s.count(bad)
if count > 1:
    raise SystemExit(f'Unexpected invalid whitespace-regex count: {count}')
if count == 1:
    s = s.replace(bad, good, 1)
    p.write_text(s, encoding='utf-8')
    print('Repaired generated Kotlin whitespace regex.')
else:
    print('Whitespace regex already valid.')
