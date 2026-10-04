from pathlib import Path
import re

path = Path('app/src/main/java/com/aarishkhan/aarishai/FloatingControlService.kt')
s = path.read_text(encoding='utf-8')

if 'AARISH_AI_TEACH_SCROLL_THROUGH_V32' not in s:
    pattern = re.compile(r'''    fun armAiTeachTapV3\(\n        role: String,\n        providerPackage: String,\n        callback: \(TargetSnapshot\?\) -> Unit\n    \): Boolean \{.*?\n    \}\n\n    // AARISH_AI_RECORDING_EXCLUSION_V4''', re.S)
    replacement = r'''    fun armAiTeachTapV3(
        role: String,
        providerPackage: String,
        callback: (TargetSnapshot?) -> Unit
    ): Boolean {
        if (android.os.Looper.myLooper() != android.os.Looper.getMainLooper()) {
            handler.post { armAiTeachTapV3(role, providerPackage, callback) }
            return true
        }
        if (isRecording) {
            Toast.makeText(this, "Normal recording pehle DONE karo", Toast.LENGTH_LONG).show()
            callback(null)
            return false
        }
        cancelAiTeachTapV3()
        val serial = aiTeachTapSerialV3
        val finished = java.util.concurrent.atomic.AtomicBoolean(false)
        val screenW = resources.displayMetrics.widthPixels.coerceAtLeast(2)
        val screenH = resources.displayMetrics.heightPixels.coerceAtLeast(2)
        val touchSlop = kotlin.math.max(12f, resources.displayMetrics.density * 10f)
        var downX = 0f
        var downY = 0f
        var downAt = 0L
        var maxTravel = 0f
        var replayingSwipe = false

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            aarishAccessOverlayTypeV13(),
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 0
            y = 0
        }

        // AARISH_AI_TEACH_SCROLL_THROUGH_V32
        // Teaching must work even when a long provider reply pushes COPY below the fold.
        // Swipes are relayed through the transparent teaching glass and DO NOT complete
        // the taught tap. Only a low-travel ACTION_UP is treated as SEND/COPY teaching.
        val overlay = android.view.View(this).apply {
            setBackgroundColor(android.graphics.Color.TRANSPARENT)
            setOnTouchListener { view, event ->
                when (event.actionMasked) {
                    android.view.MotionEvent.ACTION_DOWN -> {
                        if (replayingSwipe || finished.get()) return@setOnTouchListener true
                        downX = event.x.coerceIn(1f, (screenW - 1).toFloat())
                        downY = event.y.coerceIn(1f, (screenH - 1).toFloat())
                        downAt = event.eventTime
                        maxTravel = 0f
                        true
                    }

                    android.view.MotionEvent.ACTION_MOVE -> {
                        if (!replayingSwipe && !finished.get()) {
                            maxTravel = kotlin.math.max(
                                maxTravel,
                                kotlin.math.max(
                                    kotlin.math.abs(event.x - downX),
                                    kotlin.math.abs(event.y - downY)
                                )
                            )
                        }
                        true
                    }

                    android.view.MotionEvent.ACTION_CANCEL -> {
                        maxTravel = 0f
                        true
                    }

                    android.view.MotionEvent.ACTION_UP -> {
                        if (replayingSwipe || finished.get()) return@setOnTouchListener true
                        val x = event.x.coerceIn(1f, (screenW - 1).toFloat())
                        val y = event.y.coerceIn(1f, (screenH - 1).toFloat())
                        val moved = kotlin.math.max(
                            maxTravel,
                            kotlin.math.max(kotlin.math.abs(x - downX), kotlin.math.abs(y - downY))
                        ) > touchSlop

                        if (moved) {
                            replayingSwipe = true
                            val duration = (event.eventTime - downAt).coerceIn(80L, 1500L)
                            val swipe = RecordedGesture(
                                delayFromStart = 0L,
                                points = listOf(
                                    GesturePoint(downX, downY, 0L),
                                    GesturePoint(x, y, duration)
                                ),
                                targetPackage = providerPackage,
                                recordedScreenW = screenW,
                                recordedScreenH = screenH
                            )

                            // Make only this teaching glass untouchable while Accessibility
                            // replays the user's swipe into the provider underneath it.
                            params.flags = params.flags or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                            try { aarishAccessWmV13().updateViewLayout(view, params) } catch (_: Throwable) {}
                            AutoActionService.playSingleLiveGestureSafe(swipe) {
                                handler.postDelayed({
                                    replayingSwipe = false
                                    if (
                                        aiTeachTapSerialV3 == serial &&
                                        aiTeachTapOverlayV3 === view &&
                                        !finished.get()
                                    ) {
                                        params.flags = params.flags and WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE.inv()
                                        try { aarishAccessWmV13().updateViewLayout(view, params) } catch (_: Throwable) {}
                                        if (role.equals(AiTeachProfileStore.ROLE_COPY, ignoreCase = true)) {
                                            Toast.makeText(this@FloatingControlService, "↕️ Scroll relayed • ab COPY tap karo", Toast.LENGTH_SHORT).show()
                                        }
                                    }
                                }, 90L)
                            }
                            return@setOnTouchListener true
                        }

                        if (!finished.compareAndSet(false, true)) return@setOnTouchListener true
                        val snapshot = AutoActionService.captureTargetSnapshot(
                            x.toInt(),
                            y.toInt(),
                            screenW.toFloat(),
                            screenH.toFloat()
                        )?.takeIf {
                            it.targetPackage.orEmpty().equals(providerPackage, ignoreCase = true)
                        }
                        cancelAiTeachTapV3()

                        val gesture = RecordedGesture(
                            delayFromStart = 0L,
                            points = listOf(GesturePoint(x, y, 0L)),
                            targetText = snapshot?.targetText,
                            targetDesc = snapshot?.targetDesc,
                            targetId = snapshot?.targetId,
                            targetClass = snapshot?.targetClass,
                            targetPackage = snapshot?.targetPackage ?: providerPackage,
                            targetContextText = snapshot?.targetContextText,
                            targetChildText = snapshot?.targetChildText,
                            targetSiblingText = snapshot?.targetSiblingText,
                            targetRoleFlags = snapshot?.targetRoleFlags,
                            targetTreePath = snapshot?.targetTreePath,
                            targetLeft = snapshot?.targetLeft ?: -1,
                            targetTop = snapshot?.targetTop ?: -1,
                            targetRight = snapshot?.targetRight ?: -1,
                            targetBottom = snapshot?.targetBottom ?: -1,
                            xPercent = snapshot?.xPercent ?: (x / screenW.toFloat()),
                            yPercent = snapshot?.yPercent ?: (y / screenH.toFloat()),
                            targetWPercent = snapshot?.targetWPercent ?: 0f,
                            targetHPercent = snapshot?.targetHPercent ?: 0f,
                            insideXPercent = snapshot?.insideXPercent ?: 0.5f,
                            insideYPercent = snapshot?.insideYPercent ?: 0.5f,
                            recordedScreenW = screenW,
                            recordedScreenH = screenH
                        )
                        handler.postDelayed({
                            AutoActionService.playSingleLiveGestureSafe(gesture) {
                                callback(snapshot)
                            }
                        }, 70L)
                        true
                    }

                    else -> true
                }
            }
        }
        aiTeachTapOverlayV3 = overlay
        return try {
            aarishAccessWmV13().addView(overlay, params)
            Toast.makeText(
                this,
                if (role.equals(AiTeachProfileStore.ROLE_COPY, ignoreCase = true))
                    "🎓 COPY sikhao • zarurat ho to pehle scroll karo"
                else
                    "🎓 $role tap karke sikhao",
                Toast.LENGTH_LONG
            ).show()
            handler.postDelayed({
                if (
                    aiTeachTapSerialV3 == serial &&
                    aiTeachTapOverlayV3 === overlay &&
                    finished.compareAndSet(false, true)
                ) {
                    cancelAiTeachTapV3()
                    callback(null)
                }
            }, 120_000L)
            true
        } catch (_: Throwable) {
            aiTeachTapOverlayV3 = null
            callback(null)
            false
        }
    }

    // AARISH_AI_RECORDING_EXCLUSION_V4'''
    s2, count = pattern.subn(lambda _m: replacement, s, count=1)
    if count != 1:
        raise SystemExit(f'armAiTeachTapV3 replacement count={count}')
    s = s2
    path.write_text(s, encoding='utf-8')

check = path.read_text(encoding='utf-8')
required = [
    'AARISH_AI_TEACH_SCROLL_THROUGH_V32',
    'FLAG_NOT_TOUCHABLE',
    'Scroll relayed',
    'zarurat ho to pehle scroll karo',
]
missing = [item for item in required if item not in check]
if missing:
    raise SystemExit('v3.2 invariants missing: ' + ', '.join(missing))

print('AARISH_UNIVERSAL_AI_TEACH_RELAY_V32_SCROLL_READY')
