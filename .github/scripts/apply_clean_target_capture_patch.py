from pathlib import Path

ROOT = Path('.')
AI = ROOT / 'app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt'
FCS = ROOT / 'app/src/main/java/com/aarishkhan/aarishai/FloatingControlService.kt'


def fail(msg):
    raise SystemExit(msg)


def replace_once(text, old, new, label):
    if old not in text:
        fail(f'{label}: anchor not found')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# FloatingControlService: make our own chrome disappear only while AI captures
# a screenshot. This matters on Android 11-13 where Accessibility screenshot is
# display-composited and therefore includes TYPE_APPLICATION_OVERLAY windows.
# ---------------------------------------------------------------------------
fcs = FCS.read_text(encoding='utf-8')

if 'fun setAiScreenshotChromeHidden(hidden: Boolean)' not in fcs:
    old = '''    companion object {
        @Volatile var instance: FloatingControlService? = null

        // Android 14 specialUse foreground-service type = 0x40000000.
        // Literal rakha hai taaki compileSdk mismatch par ServiceInfo constant unresolved na ho.
        private const val FGS_TYPE_SPECIAL_USE_COMPAT = 0x40000000
    }
'''
    new = '''    companion object {
        @Volatile var instance: FloatingControlService? = null

        // Android 14 specialUse foreground-service type = 0x40000000.
        // Literal rakha hai taaki compileSdk mismatch par ServiceInfo constant unresolved na ho.
        private const val FGS_TYPE_SPECIAL_USE_COMPAT = 0x40000000

        // AARISH_AI_CLEAN_CAPTURE_V1: Android 11-13 screenshots include overlay chrome.
        // Hide only our visual chrome for the tiny capture window; touch/recording state is untouched.
        fun setAiScreenshotChromeHidden(hidden: Boolean) {
            instance?.applyAiScreenshotChromeHidden(hidden)
        }
    }
'''
    fcs = replace_once(fcs, old, new, 'FCS companion clean-capture bridge')

if 'AARISH_AI_CLEAN_CAPTURE_V1_OVERLAY' not in fcs:
    old = '''    fun isRecordingActive(): Boolean = isRecording
'''
    new = '''    fun isRecordingActive(): Boolean = isRecording

    // AARISH_AI_CLEAN_CAPTURE_V1_OVERLAY
    private var aiCapturePanelAlpha: Float? = null
    private var aiCaptureMemoryPopupAlpha: Float? = null
    private var aiCaptureMemoryStripAlpha: Float? = null

    private fun applyAiScreenshotChromeHidden(hidden: Boolean) {
        fun applyNow() {
            if (hidden) {
                if (aiCapturePanelAlpha == null) aiCapturePanelAlpha = panelView?.alpha
                if (aiCaptureMemoryPopupAlpha == null) aiCaptureMemoryPopupAlpha = memoryPopupView?.alpha
                if (aiCaptureMemoryStripAlpha == null) aiCaptureMemoryStripAlpha = memoryStrip?.alpha
                try { panelView?.alpha = 0f } catch (_: Throwable) {}
                try { memoryPopupView?.alpha = 0f } catch (_: Throwable) {}
                try { memoryStrip?.alpha = 0f } catch (_: Throwable) {}
            } else {
                try { panelView?.alpha = aiCapturePanelAlpha ?: 1f } catch (_: Throwable) {}
                try { memoryPopupView?.alpha = aiCaptureMemoryPopupAlpha ?: 1f } catch (_: Throwable) {}
                try { memoryStrip?.alpha = aiCaptureMemoryStripAlpha ?: 1f } catch (_: Throwable) {}
                aiCapturePanelAlpha = null
                aiCaptureMemoryPopupAlpha = null
                aiCaptureMemoryStripAlpha = null
            }
        }

        if (android.os.Looper.myLooper() == android.os.Looper.getMainLooper()) {
            applyNow()
        } else {
            handler.post { applyNow() }
        }
    }
'''
    fcs = replace_once(fcs, old, new, 'FCS clean-capture implementation')

FCS.write_text(fcs, encoding='utf-8')


# ---------------------------------------------------------------------------
# AiSidecarController: bind screenshot + accessibility state to one package and
# one fingerprint, isolate the target window on pre-Android-14, and prevent the
# physical AI provider from becoming the accidental target in split/floating UI.
# ---------------------------------------------------------------------------
ai = AI.read_text(encoding='utf-8')

# New mission should not inherit target affinity from an earlier run.
if 'lastTargetPackage = "" // AARISH_AI_STATE_OWNERSHIP_V1_START' not in ai:
    ai = replace_once(
        ai,
        '        lastOutcome = "Mission started"\n        resetProviderHealth()\n',
        '        lastOutcome = "Mission started"\n        lastTargetPackage = "" // AARISH_AI_STATE_OWNERSHIP_V1_START\n        resetProviderHealth()\n',
        'AI mission target reset'
    )

# A recorded failure already knows which package owned the step. Use that as
# affinity so a split-screen ChatGPT/Gemini window cannot steal target ownership.
if 'AARISH_AI_STATE_OWNERSHIP_V1_RESCUE' not in ai:
    ai = replace_once(
        ai,
        '        lastOutcome = "Recorded replay target missing"\n        resetProviderHealth()\n',
        '        lastOutcome = "Recorded replay target missing"\n'
        '        gesture.targetPackage?.trim()?.takeIf { it.isNotBlank() }?.let {\n'
        '            lastTargetPackage = it // AARISH_AI_STATE_OWNERSHIP_V1_RESCUE\n'
        '        }\n'
        '        resetProviderHealth()\n',
        'AI rescue target affinity'
    )

# Replace captureTargetScreen with a freshness-validated capture transaction.
if 'AARISH_AI_CAPTURE_TRANSACTION_V2' not in ai:
    old = '''    private fun captureTargetScreen(run: Int, callback: (ScreenState?) -> Unit) {
        val base = captureStateWithoutScreenshot()
        if (base == null) { callback(null); return }
        val windowId = findTargetWindowId(base.packageName)
        val windowBounds = findWindowBoundsForPackage(base.packageName)
        val captureBounds = if (Build.VERSION.SDK_INT >= 34 && windowId != null && windowId >= 0) {
            windowBounds?.let(::Rect)
        } else {
            null
        }
        captureScreenshot(windowId, windowBounds, base.elements) { file ->
            if (!alive(run)) return@captureScreenshot
            callback(base.copy(screenshot = file, captureBounds = captureBounds))
        }
    }
'''
    new = '''    // AARISH_AI_CAPTURE_TRANSACTION_V2
    // UI-tree metadata and pixels must describe the SAME target state. If the
    // package/fingerprint changes while taking the screenshot, discard it and retry.
    private fun captureTargetScreen(
        run: Int,
        callback: (ScreenState?) -> Unit,
        attempt: Int = 0
    ) {
        if (!alive(run)) return
        val base = captureStateWithoutScreenshot()
        if (base == null) { callback(null); return }

        val windowId = findTargetWindowId(base.packageName)
        val windowBounds = findWindowBoundsForPackage(base.packageName)
        // On Android 11-13 we crop a display screenshot to these bounds; on 14+
        // takeScreenshotOfWindow already returns the isolated window. TAP_XY must
        // therefore map normalized image coordinates through the same bounds.
        val captureBounds = windowBounds?.let(::Rect)

        FloatingControlService.setAiScreenshotChromeHidden(true)
        val safetyRestore = Runnable { FloatingControlService.setAiScreenshotChromeHidden(false) }
        handler.postDelayed(safetyRestore, 1800L)

        // Give SurfaceFlinger one frame to remove our overlay before capture.
        handler.postDelayed({
            if (!alive(run)) {
                handler.removeCallbacks(safetyRestore)
                FloatingControlService.setAiScreenshotChromeHidden(false)
                return@postDelayed
            }
            captureScreenshot(windowId, windowBounds, base.elements) { file ->
                handler.removeCallbacks(safetyRestore)
                FloatingControlService.setAiScreenshotChromeHidden(false)

                if (!alive(run)) {
                    try { file?.delete() } catch (_: Throwable) {}
                    return@captureScreenshot
                }

                val after = captureStateWithoutScreenshot()
                val stable = after != null &&
                    after.packageName == base.packageName &&
                    after.fingerprint == base.fingerprint

                if (!stable) {
                    try { file?.delete() } catch (_: Throwable) {}
                    if (attempt < 3) {
                        handler.postDelayed({ captureTargetScreen(run, callback, attempt + 1) }, 180L)
                    } else {
                        rememberHistory("CAPTURE REJECTED: target state kept changing")
                        callback(null)
                    }
                    return@captureScreenshot
                }

                callback(base.copy(screenshot = file, captureBounds = captureBounds))
            }
        }, 90L)
    }
'''
    ai = replace_once(ai, old, new, 'AI capture transaction')

# Insert pre-Android-14 target-window crop helper.
if 'AARISH_AI_TARGET_WINDOW_CROP_V1' not in ai:
    marker = '    private fun annotateScreenshotForAi(bitmap: Bitmap, elements: List<UiElement>, windowBounds: Rect?): Bitmap {'
    pos = ai.find(marker)
    if pos < 0:
        fail('AI annotate marker missing')
    helper = '''    // AARISH_AI_TARGET_WINDOW_CROP_V1
    private fun isolateTargetWindowBitmap(
        source: Bitmap,
        windowBounds: Rect?,
        alreadyWindowCapture: Boolean
    ): Bitmap {
        if (alreadyWindowCapture || windowBounds == null) return source

        val displayW = service.resources.displayMetrics.widthPixels.coerceAtLeast(1)
        val displayH = service.resources.displayMetrics.heightPixels.coerceAtLeast(1)
        val sx = source.width.toFloat() / displayW.toFloat()
        val sy = source.height.toFloat() / displayH.toFloat()

        val left = (windowBounds.left * sx).toInt().coerceIn(0, source.width - 1)
        val top = (windowBounds.top * sy).toInt().coerceIn(0, source.height - 1)
        val right = (windowBounds.right * sx).toInt().coerceIn(left + 1, source.width)
        val bottom = (windowBounds.bottom * sy).toInt().coerceIn(top + 1, source.height)
        val cropW = (right - left).coerceAtLeast(1)
        val cropH = (bottom - top).coerceAtLeast(1)

        // If the target really is full-screen, avoid an unnecessary bitmap copy.
        if (left <= 1 && top <= 1 && right >= source.width - 1 && bottom >= source.height - 1) {
            return source
        }

        return try {
            val view = Bitmap.createBitmap(source, left, top, cropW, cropH)
            val copy = view.copy(Bitmap.Config.ARGB_8888, true)
            if (view !== source) try { view.recycle() } catch (_: Throwable) {}
            copy ?: source
        } catch (_: Throwable) {
            source
        }
    }

'''
    ai = ai[:pos] + helper + ai[pos:]

# Make screenshot callback isolate the target and always annotate in target-window coordinates.
if 'AARISH_AI_PIXEL_OWNERSHIP_V1' not in ai:
    old = '''                    val hw = Bitmap.wrapHardwareBuffer(buffer, screenshot.colorSpace)
                    val bitmap = hw?.copy(Bitmap.Config.ARGB_8888, true)
                    val grounded = bitmap?.let { annotateScreenshotForAi(it, elements, if (windowCapture) windowBounds else null) }
                    callback(grounded?.let { saveBitmap(it) })
                    if (grounded !== bitmap) grounded?.recycle()
                    bitmap?.recycle()
'''
    new = '''                    val hw = Bitmap.wrapHardwareBuffer(buffer, screenshot.colorSpace)
                    val bitmap = hw?.copy(Bitmap.Config.ARGB_8888, true)
                    // AARISH_AI_PIXEL_OWNERSHIP_V1
                    val isolated = bitmap?.let { isolateTargetWindowBitmap(it, windowBounds, windowCapture) }
                    val grounded = isolated?.let { annotateScreenshotForAi(it, elements, windowBounds) }
                    callback(grounded?.let { saveBitmap(it) })
                    if (grounded != null && grounded !== isolated) try { grounded.recycle() } catch (_: Throwable) {}
                    if (isolated != null && isolated !== bitmap) try { isolated.recycle() } catch (_: Throwable) {}
                    try { bitmap?.recycle() } catch (_: Throwable) {}
'''
    ai = replace_once(ai, old, new, 'AI pixel ownership')

# Provider apps are allowed targets, but when we already have a different target
# package they should lose split/floating-window ranking unless truly foreground.
if 'AARISH_AI_PROVIDER_DRIFT_GUARD_V1' not in ai:
    old = '''                var score = (areaRatio * 3000.0).toInt()
                if (window.isActive) score += 10000
                if (window.isFocused) score += 12000
                if (window.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_APPLICATION) score += 2500
                score += window.layer.coerceIn(-100, 100) * 20
                if (pkg == "com.android.systemui" && areaRatio < 0.55) score -= 9000
'''
    new = '''                var score = (areaRatio * 3000.0).toInt()
                if (window.isActive) score += 10000
                if (window.isFocused) score += 12000
                if (window.type == android.view.accessibility.AccessibilityWindowInfo.TYPE_APPLICATION) score += 2500
                score += window.layer.coerceIn(-100, 100) * 20
                if (pkg == "com.android.systemui" && areaRatio < 0.55) score -= 9000

                // AARISH_AI_PROVIDER_DRIFT_GUARD_V1
                // Physical ChatGPT/Gemini can be the user's target, but a provider
                // floating/split window must not steal ownership from the app we
                // were just automating.
                val preferredPkg = lastTargetPackage.trim()
                if (preferredPkg.isNotBlank() && pkg == preferredPkg) score += 15000
                if (preferredPkg.isNotBlank() && pkg != preferredPkg &&
                    Provider.values().any { it.packageName == pkg }
                ) score -= 14000
'''
    ai = replace_once(ai, old, new, 'AI provider drift guard')

# Tell the planner pixels are ownership-validated, not an arbitrary display shot.
if 'Pixels are package-locked' not in ai:
    ai = replace_once(
        ai,
        '            appendLine("A screenshot of this exact target state is attached when Android/provider sharing allows it.")\n',
        '            appendLine("A screenshot of this exact target state is attached when Android/provider sharing allows it. Pixels are package-locked and stale captures are rejected before sending.")\n',
        'AI planner screenshot contract'
    )

AI.write_text(ai, encoding='utf-8')

# Static safety checks.
final_ai = AI.read_text(encoding='utf-8')
final_fcs = FCS.read_text(encoding='utf-8')
required_ai = [
    'AARISH_AI_CAPTURE_TRANSACTION_V2',
    'AARISH_AI_TARGET_WINDOW_CROP_V1',
    'AARISH_AI_PIXEL_OWNERSHIP_V1',
    'AARISH_AI_PROVIDER_DRIFT_GUARD_V1',
]
required_fcs = [
    'AARISH_AI_CLEAN_CAPTURE_V1',
    'AARISH_AI_CLEAN_CAPTURE_V1_OVERLAY',
]
for marker in required_ai:
    if marker not in final_ai:
        fail(f'missing AI marker: {marker}')
for marker in required_fcs:
    if marker not in final_fcs:
        fail(f'missing FCS marker: {marker}')

print('Clean target capture patch applied; static assertions passed.')
