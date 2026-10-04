package com.aarishkhan.aarishai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AiProviderSpecTest {
    @Test fun knownProvidersNormalize() {
        assertEquals("AUTO", AiProviderSpec.parse(" auto ").preference)
        assertEquals("CHATGPT", AiProviderSpec.parse("chatgpt").preference)
        assertEquals("GEMINI", AiProviderSpec.parse("GeMiNi").preference)
    }

    @Test fun customPackageIsPreserved() {
        val spec = AiProviderSpec.parse("PKG:com.example.smart.ai")
        assertTrue(spec.valid)
        assertEquals("CUSTOM", spec.preference)
        assertEquals("com.example.smart.ai", spec.customPackage)
    }

    @Test fun malformedAndUnknownProviderFailClosed() {
        assertFalse(AiProviderSpec.parse("PKG:not a package").valid)
        assertFalse(AiProviderSpec.parse("mystery-brain").valid)
    }
}
