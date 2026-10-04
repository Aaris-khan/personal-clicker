package com.aarishkhan.aarishai

import java.util.Locale

internal data class AiProviderSpec(
    val preference: String,
    val customPackage: String = "",
    val valid: Boolean = true
) {
    companion object {
        private val packagePattern = Regex("^[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z][A-Za-z0-9_]*)+$")

        fun parse(raw: String): AiProviderSpec {
            val clean = raw.trim()
            if (clean.isBlank()) return AiProviderSpec("AUTO")
            val upper = clean.uppercase(Locale.US)
            if (upper in setOf("AUTO", "CHATGPT", "GEMINI")) return AiProviderSpec(upper)
            if (clean.startsWith("PKG:", ignoreCase = true)) {
                val pkg = clean.substringAfter(':').trim().take(220)
                return if (pkg.matches(packagePattern)) AiProviderSpec("CUSTOM", pkg)
                else AiProviderSpec("AUTO", valid = false)
            }
            return AiProviderSpec("AUTO", valid = false)
        }
    }
}
