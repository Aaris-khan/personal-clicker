from pathlib import Path

PATH = Path("app/src/main/java/com/aarishkhan/aarishai/AutoActionService.kt")
s = PATH.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 anchor, found {count}")
    s = s.replace(old, new, 1)


if "AARISH_LOCAL_VISION_FALLBACK_V1_FIELDS" in s:
    print("Local vision upgrade already applied; nothing to do.")
    raise SystemExit(0)

# 1) Runtime state: one VLM request at a time + short-lived target cache for AI WAIT.
replace_once(
'''    @Volatile
    private var isPlayingInternal = false
''',
'''    @Volatile
    private var isPlayingInternal = false

    // AARISH_LOCAL_VISION_FALLBACK_V1_FIELDS
    private data class AarishVisionCache(
        val key: String,
        val xPercent: Float,
        val yPercent: Float,
        val confidence: Float,
        val atMs: Long
    )

    @Volatile
    private var aarishVisionCache: AarishVisionCache? = null
    private val aarishVisionInFlight = java.util.concurrent.atomic.AtomicBoolean(false)
    private val aarishUiMutationSerial = java.util.concurrent.atomic.AtomicLong(0L)
''',
"runtime fields",
)

# 2) Never let a target discovered in an old playback leak into a later run.
replace_once(
'''private fun stopPlaybackInternal(showToast: Boolean = true) {
    isPlayingInternal = false
        releasePlaybackWakeLocks()
''',
'''private fun stopPlaybackInternal(showToast: Boolean = true) {
    isPlayingInternal = false
    aarishVisionCache = null // AARISH_LOCAL_VISION_FALLBACK_V1_STOP_CLEAR
        releasePlaybackWakeLocks()
''',
"stop clear",
)

# 3) Core bridge: Accessibility screenshot -> local-only VLM -> normalized point.
vision_helpers = r'''
    // AARISH_LOCAL_VISION_FALLBACK_V1_START
    private fun aarishVisionKey(g: RecordedGesture): String {
        return listOf(
            g.targetPackage,
            g.targetId,
            g.targetText,
            g.targetDesc,
            g.targetClass,
            g.targetRoleFlags,
            g.targetTreePath
        ).joinToString("\u241F") { value ->
            value.orEmpty()
                .replace(Regex("[\\r\\n\\t]+"), " ")
                .replace(Regex("\\s+"), " ")
                .trim()
                .lowercase(java.util.Locale.US)
                .take(420)
        }.take(2600)
    }

    private fun aarishVisionPackageLooksSafe(g: RecordedGesture): Boolean {
        val saved = g.targetPackage.orEmpty().trim().lowercase(java.util.Locale.US)
        if (saved.isBlank()) return true

        val livePackages = linkedSetOf<String>()
        try {
            rootInActiveWindow?.packageName?.toString()?.trim()?.lowercase(java.util.Locale.US)
                ?.takeIf { it.isNotBlank() && it != packageName.lowercase(java.util.Locale.US) }
                ?.let { livePackages.add(it) }
        } catch (_: Throwable) {}

        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.LOLLIPOP) {
            try {
                windows.forEach { window ->
                    window.root?.packageName?.toString()?.trim()?.lowercase(java.util.Locale.US)
                        ?.takeIf { it.isNotBlank() && it != packageName.lowercase(java.util.Locale.US) }
                        ?.let { livePackages.add(it) }
                }
            } catch (_: Throwable) {}
        }

        return livePackages.isEmpty() || livePackages.contains(saved)
    }

    private fun aarishCacheVisionTarget(
        g: RecordedGesture,
        target: LocalVisionLocator.VisionTarget
    ) {
        if (!target.found || target.confidence < 0.50f) return
        if (target.xPercent !in 0f..1f || target.yPercent !in 0f..1f) return
        if (!aarishVisionPackageLooksSafe(g)) return

        aarishVisionCache = AarishVisionCache(
            key = aarishVisionKey(g),
            xPercent = target.xPercent,
            yPercent = target.yPercent,
            confidence = target.confidence,
            atMs = android.os.SystemClock.elapsedRealtime()
        )
    }

    private fun aarishConsumeCachedVisionPoint(g: RecordedGesture): Pair<Float, Float>? {
        val cached = aarishVisionCache ?: return null
        if (cached.key != aarishVisionKey(g)) return null

        val age = android.os.SystemClock.elapsedRealtime() - cached.atMs
        if (age < 0L || age > 30_000L) {
            aarishVisionCache = null
            return null
        }
        if (cached.confidence < 0.50f || !aarishVisionPackageLooksSafe(g)) {
            aarishVisionCache = null
            return null
        }

        aarishVisionCache = null
        val sw = (resources.displayMetrics.widthPixels.toFloat() - 2f).coerceAtLeast(2f)
        val sh = (resources.displayMetrics.heightPixels.toFloat() - 2f).coerceAtLeast(2f)
        return Pair(
            (cached.xPercent.coerceIn(0f, 1f) * sw).coerceIn(2f, sw),
            (cached.yPercent.coerceIn(0f, 1f) * sh).coerceIn(2f, sh)
        )
    }

    private fun aarishTryCachedVisionTap(g: RecordedGesture, runId: Int): Boolean {
        if (!isSamePlaybackRun(runId)) return false
        val point = aarishConsumeCachedVisionPoint(g) ?: return false
        val token = beginActiveGesture()
        aarishDispatchTapWithToken(
            x = point.first,
            y = point.second,
            runId = runId,
            token = token,
            label = "🧠 Vision AI click",
            tapDurationMs = 105L,
            postGapMs = 90L
        )
        return true
    }

    private fun aarishRequestLocalVisionTarget(
        g: RecordedGesture,
        runId: Int,
        callback: (LocalVisionLocator.VisionTarget?) -> Unit
    ): Boolean {
        if (!isSamePlaybackRun(runId)) return false
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.R) return false
        if (!aarishVisionPackageLooksSafe(g)) return false
        if (!aarishVisionInFlight.compareAndSet(false, true)) return false

        val executor = java.util.concurrent.Executor { runnable -> handler.post(runnable) }
        val delivered = java.util.concurrent.atomic.AtomicBoolean(false)
        var timeoutTask: Runnable? = null

        fun finish(result: LocalVisionLocator.VisionTarget?) {
            if (!delivered.compareAndSet(false, true)) return
            timeoutTask?.let { task ->
                try { handler.removeCallbacks(task) } catch (_: Throwable) {}
                try { scheduledTasks.remove(task) } catch (_: Throwable) {}
            }
            aarishVisionInFlight.set(false)
            handler.post {
                callback(if (isSamePlaybackRun(runId)) result else null)
            }
        }

        timeoutTask = object : Runnable {
            override fun run() {
                scheduledTasks.remove(this)
                finish(null)
            }
        }
        scheduledTasks.add(timeoutTask!!)
        handler.postDelayed(timeoutTask!!, 15_000L)

        return try {
            takeScreenshot(
                android.view.Display.DEFAULT_DISPLAY,
                executor,
                object : android.accessibilityservice.AccessibilityService.TakeScreenshotCallback {
                    override fun onSuccess(
                        screenshot: android.accessibilityservice.AccessibilityService.ScreenshotResult
                    ) {
                        if (!isSamePlaybackRun(runId)) {
                            try { screenshot.hardwareBuffer.close() } catch (_: Throwable) {}
                            finish(null)
                            return
                        }

                        val bitmap = aarishBitmapFromScreenshot(screenshot)
                        if (bitmap == null) {
                            finish(null)
                            return
                        }

                        LocalVisionLocator.locate(
                            context = applicationContext,
                            bitmap = bitmap,
                            gesture = g
                        ) { target ->
                            handler.post { finish(target) }
                        }
                    }

                    override fun onFailure(errorCode: Int) {
                        finish(null)
                    }
                }
            )
            true
        } catch (_: Throwable) {
            finish(null)
            false
        }
    }
    // AARISH_LOCAL_VISION_FALLBACK_V1_END

'''
replace_once(
'''    // AARISH_OCR_TEXT_CLICK_V4_HELPER
    private fun aarishNormOcr(raw: String?): String {
''',
vision_helpers + '''    // AARISH_OCR_TEXT_CLICK_V4_HELPER
    private fun aarishNormOcr(raw: String?): String {
''',
"vision helper insertion",
)

# 4) AI WAIT: after magnetic miss, ask local VLM. Re-run only when UI changes and with a cooldown.
replace_once(
'''    var finished = false
    var currentTask: Runnable? = null
    var lastToastMs = 0L
''',
'''    var finished = false
    var currentTask: Runnable? = null
    var lastToastMs = 0L
    var visionRequestPending = false // AARISH_LOCAL_VISION_AI_WAIT_V1
    var lastVisionSerial = Long.MIN_VALUE
    var lastVisionAt = -10_000L
''',
"AI WAIT state",
)

replace_once(
'''            val elapsed = android.os.SystemClock.elapsedRealtime() - startedAt
            if (elapsed >= maxWaitMs) {
''',
'''            val elapsed = android.os.SystemClock.elapsedRealtime() - startedAt

            // AARISH_LOCAL_VISION_AI_WAIT_V1
            // Magnetic remains first. On a miss, a screenshot is sent only to the SAME-PHONE
            // local VLM. If the screen is still unchanged after a miss, do not spam the model.
            val targetGesture = nextRecordedGesture
            val uiSerial = aarishUiMutationSerial.get()
            if (targetGesture != null &&
                elapsed >= 1_100L &&
                !visionRequestPending &&
                uiSerial != lastVisionSerial &&
                elapsed - lastVisionAt >= 3_500L
            ) {
                visionRequestPending = true
                lastVisionSerial = uiSerial
                lastVisionAt = elapsed

                val launched = aarishRequestLocalVisionTarget(targetGesture, runId) { target ->
                    visionRequestPending = false
                    if (!finished &&
                        isSamePlaybackRun(runId) &&
                        target?.found == true
                    ) {
                        aarishCacheVisionTarget(targetGesture, target)
                        if (aarishVisionCache != null) {
                            showTinyToast("🧠 Local Vision found target")
                            finishWait()
                        }
                    }
                }

                if (!launched) visionRequestPending = false
            }

            if (elapsed >= maxWaitMs) {
''',
"AI WAIT vision hook",
)

# 5) Normal magnetic miss: launch VLM immediately while the existing 160ms magnetic retry continues.
replace_once(
'''        fun tryClickNow(): Boolean {
''',
'''        fun finishWithVision(target: LocalVisionLocator.VisionTarget) {
            if (finished) return
            if (!target.found || target.confidence < 0.50f) return
            if (!aarishVisionPackageLooksSafe(recordedGesture)) return

            finished = true
            currentTask?.let {
                try { scheduledTasks.remove(it) } catch (_: Throwable) {}
                try { handler.removeCallbacks(it) } catch (_: Throwable) {}
            }

            if (!isSamePlaybackRun(runId)) return

            val sw = (resources.displayMetrics.widthPixels.toFloat() - 2f).coerceAtLeast(2f)
            val sh = (resources.displayMetrics.heightPixels.toFloat() - 2f).coerceAtLeast(2f)
            val x = (target.xPercent.coerceIn(0f, 1f) * sw).coerceIn(2f, sw)
            val y = (target.yPercent.coerceIn(0f, 1f) * sh).coerceIn(2f, sh)

            aarishDispatchTapWithToken(
                x = x,
                y = y,
                runId = runId,
                token = token,
                label = "🧠 Vision AI click",
                tapDurationMs = 105L,
                postGapMs = 90L
            )
        }

        // AARISH_LOCAL_VISION_SHORT_SETTLE_V1
        // We are already here because the first magnetic pass missed. Start visual reasoning
        // now; magnetic polling continues in parallel and wins if it resolves first.
        aarishRequestLocalVisionTarget(recordedGesture, runId) { target ->
            if (!finished && target?.found == true) finishWithVision(target)
        }

        fun tryClickNow(): Boolean {
''',
"short-settle vision hook",
)

# 6) AI WAIT stores a visual target for the NEXT recorded tap; consume it before doing fresh search.
replace_once(
'''        val movement = hasRealMovement(points)
        val duration = kotlin.math.max(50L, points.maxOf { it.t.coerceAtLeast(0L) }).coerceAtMost(600000L)

        if (!movement && duration <= 1200L && aarishTryFilesWordNodeClickV2(recordedGesture, runId, "Files click")) {
''',
'''        val movement = hasRealMovement(points)
        val duration = kotlin.math.max(50L, points.maxOf { it.t.coerceAtLeast(0L) }).coerceAtMost(600000L)

        // AARISH_LOCAL_VISION_CACHE_DISPATCH_V1
        if (!movement && duration < 450L && aarishTryCachedVisionTap(recordedGesture, runId)) return

        if (!movement && duration <= 1200L && aarishTryFilesWordNodeClickV2(recordedGesture, runId, "Files click")) {
''',
"cached vision dispatch",
)

# 7) Streaming/scrolling UI changes become the retry signal for AI WAIT's VLM fallback.
replace_once(
'''        val type = event.eventType
        val floating = FloatingControlService.instance

        if (type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
''',
'''        val type = event.eventType
        val floating = FloatingControlService.instance

        // AARISH_LOCAL_VISION_UI_MUTATION_V1
        if (type == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED ||
            type == AccessibilityEvent.TYPE_VIEW_SCROLLED ||
            type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
            type == AccessibilityEvent.TYPE_WINDOWS_CHANGED
        ) {
            aarishUiMutationSerial.incrementAndGet()
        }

        if (type == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
''',
"UI mutation signal",
)

PATH.write_text(s, encoding="utf-8")
print("Applied AARISH_LOCAL_VISION_FALLBACK_V1")
