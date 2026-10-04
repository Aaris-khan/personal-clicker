from pathlib import Path

paths = [
    Path('app/src/main/java/com/aarishkhan/aarishai/AutoActionService.kt'),
    Path('app/src/main/java/com/aarishkhan/aarishai/FloatingControlService.kt'),
]

blocked = '''            try {
                val m = android.app.ActivityOptions::class.java.getDeclaredMethod(
                    "setLaunchWindowingMode",
                    java.lang.Integer.TYPE
                )
                m.isAccessible = true
                m.invoke(opts, if (floating) 5 else 1)
            } catch (_: Throwable) {
            }

'''

for path in paths:
    text = path.read_text(encoding='utf-8')
    if 'setLaunchWindowingMode' not in text:
        continue
    if blocked not in text:
        raise SystemExit(f'blocked windowing block changed in {path}; refusing blind patch')
    text = text.replace(blocked, '', 1)
    path.write_text(text, encoding='utf-8')

for path in paths:
    final = path.read_text(encoding='utf-8')
    if 'setLaunchWindowingMode' in final:
        raise SystemExit(f'blocked API still present in {path}')
