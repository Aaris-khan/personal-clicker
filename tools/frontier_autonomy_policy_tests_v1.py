from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AI=ROOT/"app/src/main/java/com/aarishkhan/aarishai/AiSidecarController.kt"
AUTO=ROOT/"app/src/main/java/com/aarishkhan/aarishai/AutoActionService.kt"
POLICY=ROOT/"app/src/main/java/com/aarishkhan/aarishai/AutonomyPolicy.kt"
TEST=ROOT/"app/src/test/java/com/aarishkhan/aarishai/AutonomyPolicyTest.kt"
GRADLE=ROOT/"app/build.gradle"

def replace_once(path, old, new, label):
    text=path.read_text(encoding="utf-8")
    count=text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, got {count}")
    path.write_text(text.replace(old,new,1),encoding="utf-8")

POLICY.parent.mkdir(parents=True, exist_ok=True)
POLICY.write_text(r'''package com.aarishkhan.aarishai

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
}
''',encoding="utf-8")

TEST.parent.mkdir(parents=True, exist_ok=True)
TEST.write_text(r'''package com.aarishkhan.aarishai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AutonomyPolicyTest {

    @Test
    fun packageOnlyDone_isAllowedOnlyForOpenOnlyGoals() {
        assertTrue(AutonomyPolicy.allowsPackageOnlyDone("Open WhatsApp"))
        assertTrue(AutonomyPolicy.allowsPackageOnlyDone("mera WhatsApp kholo"))
        assertFalse(AutonomyPolicy.allowsPackageOnlyDone("Open WhatsApp, find Sameer and send hello"))
        assertFalse(AutonomyPolicy.allowsPackageOnlyDone("व्हाट्सऐप खोलो और संदेश भेजो"))
        assertFalse(AutonomyPolicy.allowsPackageOnlyDone("check my messages"))
    }

    @Test
    fun launcherResolution_rejectsExactAndPartialTies() {
        assertTrue(AutonomyPolicy.isUnambiguousLaunchMatch(1000, null))
        assertTrue(AutonomyPolicy.isUnambiguousLaunchMatch(1000, 780))
        assertFalse(AutonomyPolicy.isUnambiguousLaunchMatch(1000, 1000))
        assertFalse(AutonomyPolicy.isUnambiguousLaunchMatch(780, 700))
        assertFalse(AutonomyPolicy.isUnambiguousLaunchMatch(619, null))
    }

    @Test
    fun coordinateFallback_requiresSameAppSimpleTapAndSafeOrientation() {
        assertTrue(
            AutonomyPolicy.allowsRecordedTapCoordinateFallback(
                "com.whatsapp","com.whatsapp",true,false,120L,
                1080,2400,1080,2400
            )
        )
        assertFalse(
            AutonomyPolicy.allowsRecordedTapCoordinateFallback(
                "com.whatsapp","com.android.launcher",true,false,120L,
                1080,2400,1080,2400
            )
        )
        assertFalse(
            AutonomyPolicy.allowsRecordedTapCoordinateFallback(
                "com.whatsapp","com.whatsapp",true,true,120L,
                1080,2400,1080,2400
            )
        )
        assertFalse(
            AutonomyPolicy.allowsRecordedTapCoordinateFallback(
                "com.whatsapp","com.whatsapp",true,false,700L,
                1080,2400,1080,2400
            )
        )
        assertFalse(
            AutonomyPolicy.allowsRecordedTapCoordinateFallback(
                "com.whatsapp","com.whatsapp",true,false,120L,
                1080,2400,2400,1080
            )
        )
        assertTrue(
            AutonomyPolicy.allowsRecordedTapCoordinateFallback(
                "com.whatsapp","COM.WHATSAPP",true,false,120L,
                0,0,1080,2400
            )
        )
    }
}
''',encoding="utf-8")

replace_once(
    AI,
'''    private fun missionAllowsPackageOnlyDone(): Boolean {
        val goal = normalizeUiText(missionGoal)
        if (goal.isBlank()) return false

        val openIntent = listOf(
            "open", "launch", "start", "switch to", "go to",
            "kholo", "khol", "chalao", "खोल", "खोलो", "चलाओ"
        ).any { goal.contains(it) }
        if (!openIntent) return false

        val beyondOpenIntent = listOf(
            "send", "message", "type", "write", "reply", "search", "find",
            "call", "share", "upload", "download", "select", "tap", "click",
            "bhej", "bhejo", "likh", "dhund", "dhoond", "भेज", "लिख",
            "ढूंढ", "खोज", "कॉल", "शेयर"
        ).any { goal.contains(it) }

        return !beyondOpenIntent
    }
''',
'''    private fun missionAllowsPackageOnlyDone(): Boolean =
        AutonomyPolicy.allowsPackageOnlyDone(missionGoal)
''',
    "wire tested DONE policy"
)

replace_once(
    AI,
'''            val winner = ranked.firstOrNull() ?: return null
            if (winner.score < 620) return null
            val runner = ranked.drop(1).firstOrNull()
            if (winner.score < 1000 && runner != null && winner.score - runner.score < 120) {
                // Ambiguous partial app names are safer to re-plan than to launch the
                // wrong application and continue acting there.
                return null
            }
            winner.packageName
''',
'''            val winner = ranked.firstOrNull() ?: return null
            val runner = ranked.drop(1).firstOrNull()
            if (!AutonomyPolicy.isUnambiguousLaunchMatch(winner.score, runner?.score)) {
                // Exact-label ties are ambiguous too (two apps can expose the same
                // launcher label). Re-plan instead of silently picking list order.
                return null
            }
            winner.packageName
''',
    "wire tested launcher ambiguity policy"
)

replace_once(
    AUTO,
'''                    val savedPkg = recordedGesture.targetPackage?.trim().orEmpty()
                    val livePkg = try { aarishBestForegroundPackageForOcr()?.trim().orEmpty() } catch (_: Throwable) { "" }
                    val samePackage = savedPkg.isNotBlank() &&
                        livePkg.isNotBlank() &&
                        savedPkg.equals(livePkg, ignoreCase = true)

                    val screenW = resources.displayMetrics.widthPixels.toFloat().coerceAtLeast(1f)
                    val screenH = resources.displayMetrics.heightPixels.toFloat().coerceAtLeast(1f)
                    val orientationSafe =
                        recordedGesture.recordedScreenW <= 0 ||
                            recordedGesture.recordedScreenH <= 0 ||
                            ((recordedGesture.recordedScreenW > recordedGesture.recordedScreenH) == (screenW > screenH))

                    if (!fallbackMovement &&
                        fallbackDuration < 450L &&
                        hasSavedPercentAnchor(recordedGesture) &&
                        samePackage &&
                        orientationSafe
                    ) {
''',
'''                    val savedPkg = recordedGesture.targetPackage?.trim().orEmpty().ifBlank {
                        try { aarishSavedPackageFromId(recordedGesture).trim() } catch (_: Throwable) { "" }
                    }
                    val livePkg = try { aarishBestForegroundPackageForOcr()?.trim().orEmpty() } catch (_: Throwable) { "" }

                    val screenW = resources.displayMetrics.widthPixels.toFloat().coerceAtLeast(1f)
                    val screenH = resources.displayMetrics.heightPixels.toFloat().coerceAtLeast(1f)
                    val safeCoordinateFallback = AutonomyPolicy.allowsRecordedTapCoordinateFallback(
                        savedPackageRaw = savedPkg,
                        livePackageRaw = livePkg,
                        hasPercentAnchor = hasSavedPercentAnchor(recordedGesture),
                        hasMovement = fallbackMovement,
                        durationMs = fallbackDuration,
                        recordedScreenW = recordedGesture.recordedScreenW,
                        recordedScreenH = recordedGesture.recordedScreenH,
                        liveScreenW = screenW.toInt(),
                        liveScreenH = screenH.toInt()
                    )

                    if (safeCoordinateFallback) {
''',
    "wire tested coordinate fallback policy"
)

gradle=GRADLE.read_text(encoding="utf-8")
needle="    implementation 'com.google.android.material:material:1.11.0'\n"
if "testImplementation 'junit:junit:4.13.2'" not in gradle:
    if gradle.count(needle) != 1:
        raise SystemExit("gradle dependency anchor not unique")
    gradle=gradle.replace(needle,needle+"    testImplementation 'junit:junit:4.13.2'\n",1)
    GRADLE.write_text(gradle,encoding="utf-8")

print("Autonomy policy extraction + executable unit tests installed.")
