from pathlib import Path

p = Path('app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt')
s = p.read_text(encoding='utf-8')


def once(old: str, new: str, label: str) -> None:
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 occurrence, found {count}')
    s = s.replace(old, new, 1)


if 'AARISH_AI_VISUAL_IMPORTS_V4' not in s:
    once(
        '''import android.graphics.Bitmap
import android.graphics.Path
import android.graphics.Rect
''',
        '''import android.graphics.Bitmap
import android.graphics.Canvas // AARISH_AI_VISUAL_IMPORTS_V4
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Rect
import android.graphics.Typeface
''',
        'visual imports'
    )

if 'AARISH_AI_MISSION_HISTORY_V4' not in s:
    once(
        '''    private var rescueCallback: ((Boolean) -> Unit)? = null
    private var rescueMode = false
''',
        '''    private var rescueCallback: ((Boolean) -> Unit)? = null
    private var rescueMode = false
    // AARISH_AI_MISSION_HISTORY_V4: compact bounded history gives the planner memory without huge prompts.
    private val actionHistory = java.util.ArrayDeque<String>()
''',
        'history field'
    )

    once(
        '''        missionStep = 0
        failureCount = 0
        lastOutcome = "Mission started"
''',
        '''        missionStep = 0
        failureCount = 0
        lastOutcome = "Mission started"
        actionHistory.clear()
        rememberHistory("GOAL: $clean")
''',
        'mission history reset'
    )

    once(
        '''        lastOutcome = "Recorded replay target missing"
        rescueMode = true
''',
        '''        lastOutcome = "Recorded replay target missing"
        actionHistory.clear()
        rememberHistory("RECORDED STEP FAILED: ${target.ifBlank { "unknown target" }}")
        rescueMode = true
''',
        'rescue history reset'
    )

    once(
        '''                            lastOutcome = if (verified) "SUCCESS: $proof" else "UNCERTAIN: $proof"
                            if (!verified) failureCount++ else failureCount = (failureCount - 1).coerceAtLeast(0)
''',
        '''                            lastOutcome = if (verified) "SUCCESS: $proof" else "UNCERTAIN: $proof"
                            rememberHistory("STEP $missionStep ${command.action} ${command.elementKey.ifBlank { "-" }} -> $lastOutcome")
                            if (!verified) failureCount++ else failureCount = (failureCount - 1).coerceAtLeast(0)
''',
        'successful history'
    )

    once(
        '''        failureCount++
        lastOutcome = "FAILED: $reason"
        missionStep++
''',
        '''        failureCount++
        lastOutcome = "FAILED: $reason"
        rememberHistory("STEP $missionStep -> $lastOutcome")
        missionStep++
''',
        'failed history'
    )

    once(
        '''    private fun alive(run: Int): Boolean = missionRunning && generation.get() == run
''',
        '''    private fun rememberHistory(entry: String) {
        val clean = entry.replace(Regex("\\s+"), " ").trim().take(360)
        if (clean.isBlank()) return
        while (actionHistory.size >= 12) actionHistory.removeFirst()
        actionHistory.addLast(clean)
    }

    private fun alive(run: Int): Boolean = missionRunning && generation.get() == run
''',
        'history helper'
    )

    once(
        '''        return buildString {
            appendLine("You are the recovery/planning brain for an Android UI automation agent.")
''',
        '''        val history = actionHistory.joinToString("\\n") { "- $it" }
        return buildString {
            appendLine("You are the recovery/planning brain for an Android UI automation agent.")
''',
        'history variable'
    )

    once(
        '''            appendLine("LAST OUTCOME: $lastOutcome")
            appendLine("VISIBLE ACTIONABLE ELEMENTS:")
''',
        '''            appendLine("LAST OUTCOME: $lastOutcome")
            appendLine("RECENT ACTION HISTORY:")
            appendLine(history.ifBlank { "- none" })
            appendLine("VISIBLE ACTIONABLE ELEMENTS:")
''',
        'history prompt'
    )

if 'AARISH_AI_GROUNDED_SCREENSHOT_V4' not in s:
    once(
        '''            appendLine("A screenshot of this exact target state is attached when Android/provider sharing allows it.")
            appendLine("Choose ONE next action only. Prefer a listed element key over guessing coordinates.")
''',
        '''            appendLine("A screenshot of this exact target state is attached when Android/provider sharing allows it.")
            appendLine("Clickable/editable candidates in the screenshot are visually marked with their E-number (E1, E2, ...). Use those markers plus the element list to ground your choice.")
            appendLine("Choose ONE next action only. Prefer a listed element key over guessing coordinates.")
''',
        'grounding prompt'
    )

    once(
        '''        val windowId = findTargetWindowId(base.packageName)
        captureScreenshot(windowId) { file ->
            if (!alive(run)) return@captureScreenshot
            callback(base.copy(screenshot = file))
        }
''',
        '''        val windowId = findTargetWindowId(base.packageName)
        val windowBounds = findWindowBoundsForPackage(base.packageName)
        captureScreenshot(windowId, windowBounds, base.elements) { file ->
            if (!alive(run)) return@captureScreenshot
            callback(base.copy(screenshot = file))
        }
''',
        'capture target grounding'
    )

    old_capture = '''    private fun captureScreenshot(windowId: Int?, callback: (File?) -> Unit) {
        if (Build.VERSION.SDK_INT < 30) { callback(null); return }
        val cb = object : AccessibilityService.TakeScreenshotCallback {
            override fun onSuccess(screenshot: AccessibilityService.ScreenshotResult) {
                val buffer = screenshot.hardwareBuffer
                try {
                    val hw = Bitmap.wrapHardwareBuffer(buffer, screenshot.colorSpace)
                    val bitmap = hw?.copy(Bitmap.Config.ARGB_8888, false)
                    callback(bitmap?.let { saveBitmap(it) })
                    bitmap?.recycle()
                } catch (_: Throwable) {
                    callback(null)
                } finally {
                    try { buffer.close() } catch (_: Throwable) {}
                }
            }
            override fun onFailure(errorCode: Int) { callback(null) }
        }
        try {
            if (Build.VERSION.SDK_INT >= 34 && windowId != null && windowId >= 0) {
                service.takeScreenshotOfWindow(windowId, service.mainExecutor, cb)
            } else {
                service.takeScreenshot(Display.DEFAULT_DISPLAY, service.mainExecutor, cb)
            }
        } catch (_: Throwable) { callback(null) }
    }
'''
    new_capture = '''    private fun captureScreenshot(
        windowId: Int?,
        windowBounds: Rect?,
        elements: List<UiElement>,
        callback: (File?) -> Unit
    ) {
        if (Build.VERSION.SDK_INT < 30) { callback(null); return }
        val windowCapture = Build.VERSION.SDK_INT >= 34 && windowId != null && windowId >= 0
        val cb = object : AccessibilityService.TakeScreenshotCallback {
            override fun onSuccess(screenshot: AccessibilityService.ScreenshotResult) {
                val buffer = screenshot.hardwareBuffer
                try {
                    val hw = Bitmap.wrapHardwareBuffer(buffer, screenshot.colorSpace)
                    val bitmap = hw?.copy(Bitmap.Config.ARGB_8888, true)
                    val grounded = bitmap?.let { annotateScreenshotForAi(it, elements, if (windowCapture) windowBounds else null) }
                    callback(grounded?.let { saveBitmap(it) })
                    if (grounded !== bitmap) grounded?.recycle()
                    bitmap?.recycle()
                } catch (_: Throwable) {
                    callback(null)
                } finally {
                    try { buffer.close() } catch (_: Throwable) {}
                }
            }
            override fun onFailure(errorCode: Int) { callback(null) }
        }
        try {
            if (windowCapture) {
                service.takeScreenshotOfWindow(windowId!!, service.mainExecutor, cb)
            } else {
                service.takeScreenshot(Display.DEFAULT_DISPLAY, service.mainExecutor, cb)
            }
        } catch (_: Throwable) { callback(null) }
    }
'''
    once(old_capture, new_capture, 'capture screenshot method')

    once(
        '''    private fun saveBitmap(bitmap: Bitmap): File? = try {
''',
        '''    private fun annotateScreenshotForAi(bitmap: Bitmap, elements: List<UiElement>, windowBounds: Rect?): Bitmap {
        // AARISH_AI_GROUNDED_SCREENSHOT_V4: draw sparse E# labels so AI chooses our live candidates, not guessed pixels.
        val out = if (bitmap.isMutable) bitmap else bitmap.copy(Bitmap.Config.ARGB_8888, true)
        val canvas = Canvas(out)
        val density = service.resources.displayMetrics.density.coerceAtLeast(1f)
        val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 2.2f * density
            color = Color.rgb(255, 64, 64)
        }
        val badge = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
            color = Color.argb(225, 15, 15, 15)
        }
        val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
            color = Color.WHITE
            textSize = 12f * density
            typeface = Typeface.DEFAULT_BOLD
        }

        val originX = windowBounds?.left ?: 0
        val originY = windowBounds?.top ?: 0
        val sourceW = (windowBounds?.width() ?: service.resources.displayMetrics.widthPixels).coerceAtLeast(1)
        val sourceH = (windowBounds?.height() ?: service.resources.displayMetrics.heightPixels).coerceAtLeast(1)
        val sx = out.width.toFloat() / sourceW.toFloat()
        val sy = out.height.toFloat() / sourceH.toFloat()
        val maxArea = out.width.toLong() * out.height.toLong()

        elements.asSequence()
            .filter { it.clickable || it.editable }
            .take(70)
            .forEach { e ->
                val left = ((e.bounds.left - originX) * sx).coerceIn(0f, out.width.toFloat())
                val top = ((e.bounds.top - originY) * sy).coerceIn(0f, out.height.toFloat())
                val right = ((e.bounds.right - originX) * sx).coerceIn(0f, out.width.toFloat())
                val bottom = ((e.bounds.bottom - originY) * sy).coerceIn(0f, out.height.toFloat())
                if (right <= left + 2f || bottom <= top + 2f) return@forEach
                val area = ((right - left) * (bottom - top)).toLong()
                if (area > maxArea * 3L / 4L) return@forEach

                canvas.drawRect(left, top, right, bottom, stroke)
                val label = e.key
                val pad = 3f * density
                val badgeW = textPaint.measureText(label) + pad * 2f
                val badgeH = textPaint.textSize + pad * 2f
                val bx = left.coerceAtMost((out.width - badgeW).coerceAtLeast(0f))
                val by = (top - badgeH).takeIf { it >= 0f } ?: top
                canvas.drawRect(bx, by, bx + badgeW, (by + badgeH).coerceAtMost(out.height.toFloat()), badge)
                canvas.drawText(label, bx + pad, (by + badgeH - pad).coerceAtMost(out.height.toFloat()), textPaint)
            }
        return out
    }

    private fun saveBitmap(bitmap: Bitmap): File? = try {
''',
        'annotation method'
    )

    once(
        '''    private fun findTargetWindowId(pkg: String): Int? = findWindowIdForPackage(pkg)
''',
        '''    private fun findTargetWindowId(pkg: String): Int? = findWindowIdForPackage(pkg)

    private fun findWindowBoundsForPackage(pkg: String): Rect? = try {
        var best: Rect? = null
        var bestScore = Int.MIN_VALUE
        for (window in service.windows) {
            val root = window.root ?: continue
            if (root.packageName?.toString() != pkg) continue
            val b = Rect()
            try { root.getBoundsInScreen(b) } catch (_: Throwable) {}
            if (b.width() <= 0 || b.height() <= 0) continue
            var score = b.width() * b.height() / 1000
            if (window.isActive) score += 100000
            if (window.isFocused) score += 120000
            score += window.layer.coerceIn(-100, 100) * 10
            if (score > bestScore) { bestScore = score; best = Rect(b) }
        }
        best
    } catch (_: Throwable) { null }
''',
        'window bounds helper'
    )

p.write_text(s, encoding='utf-8')
print('AI sidecar mission history and visual grounding applied.')
