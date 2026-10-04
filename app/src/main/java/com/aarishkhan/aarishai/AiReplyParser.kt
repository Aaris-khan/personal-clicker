package com.aarishkhan.aarishai

import java.util.Locale

/**
 * Provider-independent reply decoder for Teach Your AI.
 *
 * Preferred protocol is one flat JSON object. The scanner deliberately tolerates provider
 * prose / markdown around that object, but still fails closed when two different valid
 * commands for the same request are present. The legacy AARIS:: protocol remains readable
 * so an in-flight/older conversation does not break after upgrading the APK.
 */
internal object AiReplyParser {
    internal data class Command(
        val action: String,
        val element: String = "",
        val payload: String = "",
        val expected: String = "",
        val visual: String = ""
    )

    private val allowedActions = setOf(
        "TAP", "TAP_XY", "LONG_TAP", "SET_TEXT", "SWIPE", "SCROLL",
        "BACK", "HOME", "WAIT", "OPEN_APP", "DONE", "FAIL"
    )

    fun parse(text: String, requestId: String): Command? {
        if (requestId.isBlank() || text.isBlank()) return null

        val jsonCommands = extractJsonObjects(text)
            .mapNotNull(::parseFlatJsonObject)
            .mapNotNull { fields -> commandFromJson(fields, requestId) }
            .distinct()

        if (jsonCommands.size > 1) return null
        if (jsonCommands.size == 1) return jsonCommands.first()

        return parseLegacy(text, requestId)
    }

    private fun commandFromJson(fields: Map<String, String>, requestId: String): Command? {
        val correlated = fields["request_id"] ?: fields["requestId"] ?: return null
        if (correlated != requestId) return null
        val action = fields["action"].orEmpty().trim().uppercase(Locale.US)
        if (action !in allowedActions) return null

        val element = fields["element"].orEmpty().trim()
        val payload = fields["payload"].orEmpty().trim()
        val expected = fields["expected"].orEmpty().trim()
        val visual = fields["visual"].orEmpty().trim()
        if (element.length > 200 || payload.length > 2400 || expected.length > 1400 || visual.length > 80) return null
        return Command(action, element, payload, expected, visual)
    }

    private fun parseLegacy(text: String, requestId: String): Command? {
        val marker = "AARIS::$requestId::"
        val terminator = "::END"

        fun decode(rawInput: String): Command? {
            val start = rawInput.indexOf(marker)
            if (start < 0) return null
            val end = rawInput.indexOf(terminator, startIndex = start + marker.length)
            if (end < 0) return null
            val raw = rawInput.substring(start, (end + terminator.length).coerceAtMost(rawInput.length)).take(5000)
            val parts = raw.split("::", limit = 8)
            if (parts.size != 8 || parts[0].trim() != "AARIS" || parts[1].trim() != requestId) return null
            if (parts[7].trim() != "END") return null

            val action = parts[2].trim().uppercase(Locale.US)
            if (action !in allowedActions) return null
            val element = parts[3].trim()
            val payload = parts[4].trim()
            val expected = parts[5].trim()
            val visual = parts[6].trim()
            if (element.length > 200 || payload.length > 2400 || expected.length > 1400 || visual.length > 80) return null
            return Command(action, element, payload, expected, visual)
        }

        val line = text.lineSequence().map { it.trim() }.lastOrNull {
            it.contains(marker) && it.contains(terminator)
        }
        decode(line.orEmpty())?.let { return it }
        return decode(text.replace(Regex("\\s+"), " ").trim())
    }

    private fun extractJsonObjects(text: String): List<String> {
        val out = ArrayList<String>()
        var start = -1
        var depth = 0
        var inString = false
        var escaped = false

        for (i in text.indices) {
            val ch = text[i]
            if (start < 0) {
                if (ch == '{') {
                    start = i
                    depth = 1
                    inString = false
                    escaped = false
                }
                continue
            }

            if (inString) {
                if (escaped) escaped = false
                else if (ch == '\\') escaped = true
                else if (ch == '"') inString = false
                continue
            }

            when (ch) {
                '"' -> inString = true
                '{' -> depth++
                '}' -> {
                    depth--
                    if (depth == 0) {
                        out.add(text.substring(start, i + 1))
                        start = -1
                        if (out.size >= 12) break
                    }
                }
            }
        }
        return out
    }

    private fun parseFlatJsonObject(raw: String): Map<String, String>? {
        var i = 0
        fun skipWs() { while (i < raw.length && raw[i].isWhitespace()) i++ }

        fun readString(): String? {
            skipWs()
            if (i >= raw.length || raw[i] != '"') return null
            i++
            val out = StringBuilder()
            while (i < raw.length) {
                val ch = raw[i++]
                when (ch) {
                    '"' -> return out.toString()
                    '\\' -> {
                        if (i >= raw.length) return null
                        when (val e = raw[i++]) {
                            '"', '\\', '/' -> out.append(e)
                            'b' -> out.append('\b')
                            'f' -> out.append('\u000C')
                            'n' -> out.append('\n')
                            'r' -> out.append('\r')
                            't' -> out.append('\t')
                            'u' -> {
                                if (i + 4 > raw.length) return null
                                val hex = raw.substring(i, i + 4)
                                val code = hex.toIntOrNull(16) ?: return null
                                out.append(code.toChar())
                                i += 4
                            }
                            else -> return null
                        }
                    }
                    else -> {
                        if (ch.code < 0x20) return null
                        out.append(ch)
                    }
                }
            }
            return null
        }

        fun readScalar(): String? {
            skipWs()
            if (i >= raw.length) return null
            if (raw[i] == '"') return readString()
            if (raw[i] == '{' || raw[i] == '[') return null
            val start = i
            while (i < raw.length && raw[i] != ',' && raw[i] != '}') i++
            val token = raw.substring(start, i).trim()
            if (token.isBlank()) return null
            return when (token) {
                "null" -> ""
                "true", "false" -> token
                else -> token.takeIf { it.toDoubleOrNull() != null }
            }
        }

        skipWs()
        if (i >= raw.length || raw[i] != '{') return null
        i++
        val fields = LinkedHashMap<String, String>()
        skipWs()
        if (i < raw.length && raw[i] == '}') return emptyMap()

        while (i < raw.length) {
            val key = readString() ?: return null
            skipWs()
            if (i >= raw.length || raw[i] != ':') return null
            i++
            val value = readScalar() ?: return null
            fields[key] = value
            skipWs()
            if (i >= raw.length) return null
            when (raw[i]) {
                ',' -> { i++; continue }
                '}' -> {
                    i++
                    skipWs()
                    return fields.takeIf { i == raw.length }
                }
                else -> return null
            }
        }
        return null
    }
}
