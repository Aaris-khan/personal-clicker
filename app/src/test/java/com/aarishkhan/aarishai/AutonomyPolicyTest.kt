package com.aarishkhan.aarishai

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
    @Test
    fun aiWaitReady_requiresSemanticIdentityAndRejectsWrongPackage() {
        assertTrue(
            AutonomyPolicy.allowsAiWaitTargetReady(
                true, "com.openai.chatgpt", "com.openai.chatgpt"
            )
        )
        assertTrue(
            AutonomyPolicy.allowsAiWaitTargetReady(
                true, "com.openai.chatgpt", ""
            )
        )
        assertFalse(
            AutonomyPolicy.allowsAiWaitTargetReady(
                false, "com.openai.chatgpt", "com.openai.chatgpt"
            )
        )
        assertFalse(
            AutonomyPolicy.allowsAiWaitTargetReady(
                true, "com.openai.chatgpt", "com.android.launcher"
            )
        )
    }

    @Test
    fun forcedXyReliableTap_isOnlyForSimpleTap() {
        assertTrue(AutonomyPolicy.shouldUseReliableForcedXyTap(false, 0L))
        assertTrue(AutonomyPolicy.shouldUseReliableForcedXyTap(false, 449L))
        assertFalse(AutonomyPolicy.shouldUseReliableForcedXyTap(false, 450L))
        assertFalse(AutonomyPolicy.shouldUseReliableForcedXyTap(true, 90L))
    }

    @Test
    fun forcedXyPoint_prefersNormalizedAnchorAndScalesFallback() {
        val normalized = AutonomyPolicy.resolveForcedXyPoint(
            hasPercentAnchor = true,
            xPercent = 0.25f,
            yPercent = 0.75f,
            rawX = 100f,
            rawY = 200f,
            recordedScreenW = 1000,
            recordedScreenH = 2000,
            liveScreenW = 1200,
            liveScreenH = 2400
        )
        org.junit.Assert.assertEquals(300f, normalized.first, 0.01f)
        org.junit.Assert.assertEquals(1800f, normalized.second, 0.01f)

        val scaled = AutonomyPolicy.resolveForcedXyPoint(
            hasPercentAnchor = false,
            xPercent = Float.NaN,
            yPercent = Float.NaN,
            rawX = 250f,
            rawY = 500f,
            recordedScreenW = 1000,
            recordedScreenH = 2000,
            liveScreenW = 1200,
            liveScreenH = 2400
        )
        org.junit.Assert.assertEquals(300f, scaled.first, 0.01f)
        org.junit.Assert.assertEquals(600f, scaled.second, 0.01f)
    }

}
