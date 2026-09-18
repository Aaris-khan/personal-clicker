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
}
