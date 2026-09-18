package com.aarishkhan.aarishai

import java.util.Locale

/**
 * Pure, deterministic guardrails used by both Autonomous AI and recorded replay.
 *
 * Keeping these decisions Android-free makes the safety-critical fallback rules
 * directly unit-testable instead of burying them inside Accessibility callbacks.
 */
internal object AutonomyPolicy {

    private fun normalize(raw: String): String =
        raw.lowercase(Locale.US)
            .replace(Regex("[^\\p{L}\\p{N}]+"), " ")
            .replace(Regex("\\s+"), " ")
            .trim()

    fun allowsPackageOnlyDone(goalRaw: String): Boolean {
        val goal=normalize(goalRaw)
        if (goal.isBlank()) return false

        val openIntent=listOf(
            "open","launch","start","switch to","go to",
            "kholo","khol","chalao","खोल","खोलो","चलाओ"
        ).any { goal.contains(it) }
        if (!openIntent) return false

        val beyondOpenIntent=listOf(
            "send","message","type","write","reply","search","find",
            "call","share","upload","download","select","tap","click",
            "bhej","bhejo","likh","dhund","dhoond","भेज","लिख",
            "ढूंढ","खोज","कॉल","शेयर"
        ).any { goal.contains(it) }

        return !beyondOpenIntent
    }

    fun isUnambiguousLaunchMatch(winnerScore: Int, runnerScore: Int?): Boolean {
        if (winnerScore < 620) return false
        if (runnerScore == null) return true
        return winnerScore - runnerScore >= 120
    }

    fun allowsRecordedTapCoordinateFallback(
        savedPackageRaw: String,
        livePackageRaw: String,
        hasPercentAnchor: Boolean,
        hasMovement: Boolean,
        durationMs: Long,
        recordedScreenW: Int,
        recordedScreenH: Int,
        liveScreenW: Int,
        liveScreenH: Int
    ): Boolean {
        val savedPackage=savedPackageRaw.trim()
        val livePackage=livePackageRaw.trim()
        if (savedPackage.isBlank() || livePackage.isBlank()) return false
        if (!savedPackage.equals(livePackage, ignoreCase=true)) return false
        if (!hasPercentAnchor || hasMovement || durationMs >= 450L) return false
        if (liveScreenW <= 0 || liveScreenH <= 0) return false

        val orientationSafe=
            recordedScreenW <= 0 ||
                recordedScreenH <= 0 ||
                ((recordedScreenW > recordedScreenH) == (liveScreenW > liveScreenH))

        return orientationSafe
    }
    /**
     * AI WAIT may unlock only from a semantic matcher result, never from raw coordinates.
     * If both packages are known they must agree, preventing a similarly-labelled control
     * in a provider/launcher window from accidentally releasing the wait gate.
     */
    fun allowsAiWaitTargetReady(
        hasSemanticIdentity: Boolean,
        savedPackageRaw: String,
        livePackageRaw: String
    ): Boolean {
        if (!hasSemanticIdentity) return false
        val savedPackage = savedPackageRaw.trim()
        val livePackage = livePackageRaw.trim()
        if (savedPackage.isNotBlank() && livePackage.isNotBlank() &&
            !savedPackage.equals(livePackage, ignoreCase = true)
        ) return false
        return true
    }

    fun shouldUseReliableForcedXyTap(
        hasMovement: Boolean,
        durationMs: Long
    ): Boolean = !hasMovement && durationMs.coerceAtLeast(0L) < 450L

    fun resolveForcedXyPoint(
        hasPercentAnchor: Boolean,
        xPercent: Float,
        yPercent: Float,
        rawX: Float,
        rawY: Float,
        recordedScreenW: Int,
        recordedScreenH: Int,
        liveScreenW: Int,
        liveScreenH: Int
    ): Pair<Float, Float> {
        val liveW = liveScreenW.coerceAtLeast(1).toFloat()
        val liveH = liveScreenH.coerceAtLeast(1).toFloat()

        val percentValid =
            hasPercentAnchor &&
                !xPercent.isNaN() && !xPercent.isInfinite() && xPercent in 0f..1f &&
                !yPercent.isNaN() && !yPercent.isInfinite() && yPercent in 0f..1f

        val x = if (percentValid) {
            xPercent * liveW
        } else if (recordedScreenW > 0) {
            rawX * (liveW / recordedScreenW.toFloat())
        } else {
            rawX
        }

        val y = if (percentValid) {
            yPercent * liveH
        } else if (recordedScreenH > 0) {
            rawY * (liveH / recordedScreenH.toFloat())
        } else {
            rawY
        }

        val maxX = (liveW - 2f).coerceAtLeast(2f)
        val maxY = (liveH - 2f).coerceAtLeast(2f)
        return x.coerceIn(2f, maxX) to y.coerceIn(2f, maxY)
    }

}
