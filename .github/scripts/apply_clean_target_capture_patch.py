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
# a visual fallback. Semantic-first turns never call this path.
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
# AiSidecarController:
# 1) semantic-first turns avoid screenshots when accessibility data is rich;
# 2) visual fallback captures only a state-locked target window;
# 3) provider composer is controlled directly with SET_TEXT, clipboard PASTE
#    fallback, and semantic Send click -- no coordinate search dance.
# ---------------------------------------------------------------------------
ai = AI.read_text(encoding='utf-8')

if 'lastTargetPackage = "" // AARISH_AI_STATE_OWNERSHIP_V1_START' not in ai:
    ai = replace_once(
        ai,
        '        lastOutcome = "Mission started"\n        resetProviderHealth()\n',
        '        lastOutcome = "Mission started"\n        lastTargetPackage = "" // AARISH_AI_STATE_OWNERSHIP_V1_START\n        resetProviderHealth()\n',
        'AI mission target reset'
    )

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

# Insert semantic-first visual decision helper before captureTargetScreen.
if 'AARISH_AI_SEMANTIC_FIRST_V1' not in ai:
    marker = '    private fun captureTargetScreen(run: Int, callback: (ScreenState?) -> Unit) {'
    pos = ai.find(marker)
    if pos < 0:
        fail('AI captureTargetScreen marker missing')
    helper = '''    // AARISH_AI_SEMANTIC_FIRST_V1
    // Most screens can be reasoned about from accessibility IDs/text/context.
    // Only visual-only/ambiguous screens pay the screenshot cost.
    private fun shouldCaptureVisualForPlanner(state: ScreenState): Boolean {
        if (state.elements.isEmpty()) return true

        fun meaningful(e: UiElement): Boolean {
            return e.editable ||
                e.viewId.isNotBlank() ||
                e.text.isNotBlank() ||
                e.desc.isNotBlank() ||
                e.context.isNotBlank()
        }

        val useful = state.elements.count(::meaningful)
        val unlabeledClickable = state.elements.count { e ->
            e.clickable &&
                e.viewId.isBlank() &&
                e.text.isBlank() &&
                e.desc.isBlank() &&
                e.context.isBlank()
        }

        // Recorded rescue only needs live pixels when the failed step itself had
        // no semantic identity. Existing recorded evidence can still be attached.
        if (rescueMode) {
            val failed = rescueEvidenceSteps.lastOrNull()
            val failedHasSemanticIdentity = failed != null && listOf(
                failed.targetText,
                failed.targetDesc,
                failed.targetId,
                failed.targetContextText,
                failed.targetChildText,
                failed.targetSiblingText
            ).any { !it.isNullOrBlank() }
            if (!failedHasSemanticIdentity) return true
        }

        return useful < 3 || unlabeledClickable > useful
    }

'''
    ai = ai[:pos] + helper + ai[pos:]

# Replace captureTargetScreen with semantic-first + freshness-validated visual fallback.
if 'AARISH_AI_CAPTURE_TRANSACTION_V3' not in ai:
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
    new = '''    // AARISH_AI_CAPTURE_TRANSACTION_V3
    // Callback is last so Kotlin trailing-lambda calls stay valid.
    private fun captureTargetScreen(
        run: Int,
        attempt: Int = 0,
        callback: (ScreenState?) -> Unit
    ) {
        if (!alive(run)) return
        val base = captureStateWithoutScreenshot()
        if (base == null) { callback(null); return }

        val windowBounds = findWindowBoundsForPackage(base.packageName)
        val captureBounds = windowBounds?.let(::Rect)

        // Semantic-first: no bitmap, no temp file, no provider image attachment.
        if (!shouldCaptureVisualForPlanner(base)) {
            rememberHistory("SEMANTIC-FIRST: visual capture skipped for ${base.packageName}")
            callback(base.copy(screenshot = null, captureBounds = captureBounds))
            return
        }

        val windowId = findTargetWindowId(base.packageName)
        FloatingControlService.setAiScreenshotChromeHidden(true)
        val safetyRestore = Runnable { FloatingControlService.setAiScreenshotChromeHidden(false) }
        handler.postDelayed(safetyRestore, 1800L)

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
                        handler.postDelayed({ captureTargetScreen(run, attempt + 1, callback) }, 180L)
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
    ai = replace_once(ai, old, new, 'AI semantic capture transaction')

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
                val preferredPkg = lastTargetPackage.trim()
                if (preferredPkg.isNotBlank() && pkg == preferredPkg) score += 15000
                if (preferredPkg.isNotBlank() && pkg != preferredPkg &&
                    Provider.values().any { it.packageName == pkg }
                ) score -= 14000
'''
    ai = replace_once(ai, old, new, 'AI provider drift guard')

# Direct provider handoff: SET_TEXT first, temporary clipboard paste only if needed.
if 'AARISH_AI_DIRECT_COMPOSER_V1' not in ai:
    marker = '    private fun ensurePromptAndSend(run: Int, provider: Provider, root: AccessibilityNodeInfo, prompt: String, callback: (Boolean) -> Unit) {'
    pos = ai.find(marker)
    if pos < 0:
        fail('AI ensurePromptAndSend marker missing')
    helper = '''    // AARISH_AI_DIRECT_COMPOSER_V1
    // Coordinate-free text injection fallback. Preserve the user's clipboard when possible.
    private fun pastePromptViaClipboard(composer: AccessibilityNodeInfo, prompt: String): Boolean {
        val cm = try {
            service.getSystemService(Context.CLIPBOARD_SERVICE) as? android.content.ClipboardManager
        } catch (_: Throwable) { null } ?: return false

        val previous = try { cm.primaryClip } catch (_: Throwable) { null }
        return try {
            cm.setPrimaryClip(ClipData.newPlainText("Aarish AI prompt", prompt))
            try { composer.performAction(AccessibilityNodeInfo.ACTION_FOCUS) } catch (_: Throwable) {}
            val pasted = try { composer.performAction(AccessibilityNodeInfo.ACTION_PASTE) } catch (_: Throwable) { false }
            handler.postDelayed({
                try {
                    if (previous != null) cm.setPrimaryClip(previous)
                    else cm.setPrimaryClip(ClipData.newPlainText("", ""))
                } catch (_: Throwable) {}
            }, 700L)
            pasted
        } catch (_: Throwable) {
            false
        }
    }

'''
    ai = ai[:pos] + helper + ai[pos:]

if 'AARISH_AI_DIRECT_COMPOSER_V1_SET_OR_PASTE' not in ai:
    old = '''        if (!setOk) {
            val existing = try { composer.text?.toString().orEmpty() } catch (_: Throwable) { "" }
            val proof = prompt.take(96)
            if (proof.isNotBlank() && !existing.contains(proof)) {
                callback(false)
                return
            }
        }
'''
    new = '''        // AARISH_AI_DIRECT_COMPOSER_V1_SET_OR_PASTE
        if (!setOk) {
            val existing = try { composer.text?.toString().orEmpty() } catch (_: Throwable) { "" }
            val proof = prompt.take(96)
            val alreadyThere = proof.isNotBlank() && existing.contains(proof)
            val pasted = if (!alreadyThere) pastePromptViaClipboard(composer, prompt) else true
            if (!alreadyThere && !pasted) {
                callback(false)
                return
            }
        }
'''
    ai = replace_once(ai, old, new, 'AI direct composer set/paste')

# Share payload already uses clipData URI. Make the contract explicit and preserve
# direct attachment as the preferred image transport over UI-driven gallery paste.
if 'AARISH_AI_DIRECT_CONTENT_HANDOFF_V1' not in ai:
    old = '''                val send = Intent(Intent.ACTION_SEND).apply {
                    type = "image/png"
                    setPackage(provider.packageName)
                    putExtra(Intent.EXTRA_STREAM, uri)
                    putExtra(Intent.EXTRA_TEXT, prompt)
                    clipData = ClipData.newUri(service.contentResolver, "Aarish AI screen", uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    if (Build.VERSION.SDK_INT >= 24) addFlags(Intent.FLAG_ACTIVITY_LAUNCH_ADJACENT)
                }
'''
    new = '''                val send = Intent(Intent.ACTION_SEND).apply {
                    // AARISH_AI_DIRECT_CONTENT_HANDOFF_V1
                    // Android grants the provider a temporary content URI directly;
                    // no gallery save and no manual attach/paste/search sequence.
                    type = "image/png"
                    setPackage(provider.packageName)
                    putExtra(Intent.EXTRA_STREAM, uri)
                    putExtra(Intent.EXTRA_TEXT, prompt)
                    clipData = ClipData.newUri(service.contentResolver, "Aarish AI visual evidence", uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    if (Build.VERSION.SDK_INT >= 24) addFlags(Intent.FLAG_ACTIVITY_LAUNCH_ADJACENT)
                }
'''
    ai = replace_once(ai, old, new, 'AI direct content handoff')

if 'Most turns are semantic-first' not in ai:
    old = '            appendLine("A screenshot of this exact target state is attached when Android/provider sharing allows it.")\n'
    new = '            appendLine("Most turns are semantic-first and intentionally have no screenshot. If no image is attached, rely on the UI element list/context. A state-locked target image is attached only for visual-only or ambiguous screens.")\n'
    ai = replace_once(ai, old, new, 'AI planner semantic-first contract')

AI.write_text(ai, encoding='utf-8')

final_ai = AI.read_text(encoding='utf-8')
final_fcs = FCS.read_text(encoding='utf-8')
required_ai = [
    'AARISH_AI_SEMANTIC_FIRST_V1',
    'AARISH_AI_CAPTURE_TRANSACTION_V3',
    'AARISH_AI_TARGET_WINDOW_CROP_V1',
    'AARISH_AI_PIXEL_OWNERSHIP_V1',
    'AARISH_AI_PROVIDER_DRIFT_GUARD_V1',
    'AARISH_AI_DIRECT_COMPOSER_V1',
    'AARISH_AI_DIRECT_COMPOSER_V1_SET_OR_PASTE',
    'AARISH_AI_DIRECT_CONTENT_HANDOFF_V1',
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

print('Semantic-first direct AI handoff patch applied; static assertions passed.')
