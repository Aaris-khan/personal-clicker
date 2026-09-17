package com.aarishkhan.aarishai

import android.graphics.Rect
import java.util.Locale
import kotlin.math.max

internal enum class AgentAction {
    TAP,
    TAP_XY,
    LONG_TAP,
    SET_TEXT,
    SCROLL,
    BACK,
    HOME,
    WAIT,
    OPEN_APP,
    DONE,
    FAIL
}

internal enum class CommandSource {
    LOCAL,
    EXTERNAL_AI,
    RECOVERY
}

internal data class AgentUiElement(
    val key: String,
    val packageName: String,
    val viewId: String,
    val text: String,
    val desc: String,
    val className: String,
    val bounds: Rect,
    val clickable: Boolean,
    val editable: Boolean,
    val enabled: Boolean,
    val checked: Boolean = false,
    val selected: Boolean = false,
    val focused: Boolean = false,
    val scrollable: Boolean = false,
    val password: Boolean = false,
    val context: String = ""
) {
    fun searchableText(): String = listOf(text, desc, viewId.substringAfterLast('/'), context)
        .filter { it.isNotBlank() }
        .joinToString(" ")
}

internal data class AgentScreenState(
    val packageName: String,
    val elements: List<AgentUiElement>,
    val semanticFingerprint: String,
    val layoutFingerprint: String,
    val screenshot: java.io.File?,
    val captureBounds: Rect? = null
)

internal data class AgentCommand(
    val action: AgentAction,
    val elementKey: String = "",
    val payload: String = "",
    val expected: String = "",
    val source: CommandSource = CommandSource.LOCAL,
    val role: String = ""
)

internal enum class GoalKind {
    OPEN_APP,
    SEND_MESSAGE,
    GENERIC
}

internal data class ParsedGoal(
    val raw: String,
    val kind: GoalKind,
    val appLabel: String = "",
    val appPackage: String = "",
    val contact: String = "",
    val message: String = "",
    val goalTokens: Set<String> = emptySet()
)

internal object AutonomyText {
    private val stopWords = setOf(
        "a", "an", "the", "to", "in", "on", "at", "for", "from", "with", "and", "then", "please",
        "open", "find", "search", "send", "message", "text", "tap", "click", "press", "type", "write",
        "mera", "meri", "mere", "karo", "kar", "do", "aur", "phir", "ko", "me", "mein", "par",
        "this", "that", "it", "app", "application", "person", "contact", "chat"
    )

    fun normalize(raw: String): String = raw
        .lowercase(Locale.US)
        .replace(Regex("[^\\p{L}\\p{N}]+"), " ")
        .replace(Regex("\\s+"), " ")
        .trim()

    fun tokens(raw: String): Set<String> = normalize(raw)
        .split(' ')
        .filter { it.length >= 2 && it !in stopWords }
        .toSet()

    fun similarity(aRaw: String, bRaw: String): Float {
        val a = normalize(aRaw)
        val b = normalize(bRaw)
        if (a.isBlank() || b.isBlank()) return 0f
        if (a == b) return 1f
        if (minOf(a.length, b.length) >= 3 && (a.contains(b) || b.contains(a))) return 0.94f

        val aTokens = a.split(' ').filter { it.isNotBlank() }.toSet()
        val bTokens = b.split(' ').filter { it.isNotBlank() }.toSet()
        val common = aTokens.intersect(bTokens).size.toFloat()
        val tokenScore = if (aTokens.isEmpty() || bTokens.isEmpty()) {
            0f
        } else {
            val coverage = common / minOf(aTokens.size, bTokens.size).toFloat().coerceAtLeast(1f)
            val union = common / aTokens.union(bTokens).size.toFloat().coerceAtLeast(1f)
            max(union, coverage * 0.92f)
        }

        val compactA = a.replace(" ", "")
        val compactB = b.replace(" ", "")
        val charScore = if (
            minOf(compactA.length, compactB.length) >= 4 &&
            maxOf(compactA.length, compactB.length) <= 80 &&
            minOf(compactA.length, compactB.length).toFloat() / maxOf(compactA.length, compactB.length).toFloat() >= 0.55f
        ) {
            editSimilarity(compactA, compactB) * 0.94f
        } else 0f

        return max(tokenScore, charScore).coerceIn(0f, 1f)
    }

    fun editSimilarity(aRaw: String, bRaw: String): Float {
        val a = normalize(aRaw).replace(" ", "").take(80)
        val b = normalize(bRaw).replace(" ", "").take(80)
        if (a.isEmpty() || b.isEmpty()) return 0f
        if (a == b) return 1f
        val distance = damerauLevenshtein(a, b)
        return (1f - distance.toFloat() / maxOf(a.length, b.length).toFloat()).coerceIn(0f, 1f)
    }

    private fun damerauLevenshtein(a: String, b: String): Int {
        val rows = a.length + 1
        val cols = b.length + 1
        val d = Array(rows) { IntArray(cols) }
        for (i in 0 until rows) d[i][0] = i
        for (j in 0 until cols) d[0][j] = j
        for (i in 1 until rows) {
            for (j in 1 until cols) {
                val cost = if (a[i - 1] == b[j - 1]) 0 else 1
                var value = minOf(
                    d[i - 1][j] + 1,
                    d[i][j - 1] + 1,
                    d[i - 1][j - 1] + cost
                )
                if (i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1]) {
                    value = minOf(value, d[i - 2][j - 2] + cost)
                }
                d[i][j] = value
            }
        }
        return d[a.length][b.length]
    }

    fun containsAny(raw: String, words: Collection<String>): Boolean {
        val n = normalize(raw)
        return words.any { word ->
            val w = normalize(word)
            w.isNotBlank() && (n == w || n.contains(" $w ") || n.startsWith("$w ") || n.endsWith(" $w") || n.contains(w))
        }
    }
}

internal object GoalParser {
    private val sendWords = listOf("send", "message", "msg", "text", "bhej", "bhejo", "भेज", "मैसेज", "संदेश")
    private val openWords = listOf("open", "launch", "khol", "kholo", "खोल", "खोलो")

    fun parse(rawGoal: String, installedApps: List<Pair<String, String>>): ParsedGoal {
        val clean = rawGoal.replace(Regex("[\\u0000-\\u001F]+"), " ").trim().take(6000)
        val normalized = AutonomyText.normalize(clean)

        val app = installedApps
            .map { it to appMentionScore(normalized, it.first) }
            .filter { it.second > 0 }
            .maxByOrNull { it.second }
            ?.first

        val quoted = Regex("[\\\"'“”‘’]([^\\\"'“”‘’]{1,1200})[\\\"'“”‘’]")
            .findAll(clean)
            .map { it.groupValues[1].trim() }
            .filter { it.isNotBlank() }
            .toList()

        val mentionsSend = sendWords.any { normalized.contains(AutonomyText.normalize(it)) }
        val mentionsOpen = openWords.any { normalized.contains(AutonomyText.normalize(it)) }
        val kind = when {
            mentionsSend -> GoalKind.SEND_MESSAGE
            app != null && mentionsOpen -> GoalKind.OPEN_APP
            else -> GoalKind.GENERIC
        }

        val message = extractMessage(clean, quoted, mentionsSend)
        val contact = extractContact(clean, quoted, message, app?.first.orEmpty())

        return ParsedGoal(
            raw = clean,
            kind = kind,
            appLabel = app?.first.orEmpty(),
            appPackage = app?.second.orEmpty(),
            contact = contact,
            message = message,
            goalTokens = AutonomyText.tokens(clean)
        )
    }

    private fun appMentionScore(normalizedGoal: String, labelRaw: String): Int {
        val label = AutonomyText.normalize(labelRaw)
        if (label.length < 2) return 0
        when {
            normalizedGoal == label -> return 1000
            normalizedGoal.contains(" $label ") -> return 950
            normalizedGoal.startsWith("$label ") || normalizedGoal.endsWith(" $label") -> return 900
            normalizedGoal.contains(label) && label.length >= 4 -> return 860
        }

        val goalTokens = normalizedGoal.split(' ').filter { it.length >= 3 }
        val labelTokens = label.split(' ').filter { it.length >= 3 }
        if (goalTokens.isEmpty() || labelTokens.isEmpty()) return 0

        val scores = labelTokens.map { wanted ->
            goalTokens.maxOfOrNull { candidate -> AutonomyText.editSimilarity(wanted, candidate) } ?: 0f
        }
        if (scores.any { it < 0.78f }) return 0
        val average = scores.average().toFloat()
        return if (average >= 0.84f) (650 + average * 180f).toInt() else 0
    }

    private fun extractMessage(clean: String, quoted: List<String>, mentionsSend: Boolean): String {
        if (!mentionsSend) return ""
        if (quoted.size >= 2) return quoted.last().take(4000)

        val patterns = listOf(
            Regex("(?is)(?:message|msg|text|संदेश|मैसेज)\\s*(?:is|this|ye|यह)?\\s*[:=\\-]\\s*(.+)$"),
            Regex("(?is)(?:send|bhej(?:o)?|भेज(?:ो)?)\\s+(?:this\\s+)?(?:message|msg|text)?\\s*[:=\\-]\\s*(.+)$"),
            Regex("(?is)(?:and|then|aur|और)?\\s*(?:send|bhej(?:o)?|भेज(?:ो)?)\\s+(?:(?:him|her|them|isko|use|उसको|उसे)\\s+)?(?:(?:a|the|this)\\s+)?(?:message|msg|text|मैसेज|संदेश)?\\s*(?:saying|that|ki|कि)?\\s+(.+)$")
        )
        for (pattern in patterns) {
            val hit = pattern.find(clean)?.groupValues?.getOrNull(1)?.trim().orEmpty()
            if (hit.isNotBlank() && !isOnlyMessageNoun(hit)) return stripQuotes(hit).take(4000)
        }

        if (quoted.size == 1) return quoted.first().take(4000)
        return ""
    }

    private fun isOnlyMessageNoun(value: String): Boolean {
        val n = AutonomyText.normalize(value)
        return n in setOf("message", "msg", "text", "मैसेज", "संदेश")
    }

    private fun extractContact(clean: String, quoted: List<String>, message: String, appLabel: String): String {
        if (quoted.size >= 2) return quoted.first().take(160)

        val patterns = listOf(
            Regex("(?is)(?:find|search(?:\\s+for)?|contact|chat\\s+with|dhoond(?:o)?|dhund(?:o)?|ढूंढ(?:ो)?|खोज(?:ो)?)\\s+([\\p{L}\\p{N} ._+\\-]{2,80}?)(?=\\s+(?:and|then|aur|और|ko|को)?\\s*(?:send|message|msg|text|bhej|भेज)|[,;.]|$)"),
            Regex("(?is)(?:send|message|text|bhej(?:o)?|भेज(?:ो)?)\\s+(?:a\\s+)?(?:message\\s+)?to\\s+([\\p{L}\\p{N} ._+\\-]{2,80}?)(?=\\s+(?:saying|that|message|msg|text)|[,;:]|$)")
        )
        for (pattern in patterns) {
            val hit = pattern.find(clean)?.groupValues?.getOrNull(1)?.trim().orEmpty()
            val cleaned = cleanContact(hit, appLabel, message)
            if (cleaned.isNotBlank()) return cleaned
        }
        return ""
    }

    private fun cleanContact(value: String, appLabel: String, message: String): String {
        val appN = AutonomyText.normalize(appLabel)
        val msgN = AutonomyText.normalize(message)
        return value
            .replace(Regex("(?i)\\b(on|in|via|using)\\s+${Regex.escape(appLabel)}\\b"), " ")
            .replace(Regex("\\s+"), " ")
            .trim(' ', ',', '.', ':', ';', '-', '\"', '\'')
            .take(160)
            .takeIf {
                val n = AutonomyText.normalize(it)
                n.isNotBlank() && n != appN && n != msgN && n !in setOf("this person", "person", "contact", "someone")
            }
            .orEmpty()
    }

    private fun stripQuotes(value: String): String = value
        .trim()
        .trim(' ', '\"', '\'', '“', '”', '‘', '’')
        .trim()
}

internal object LocalMissionPlanner {
    private val searchWords = listOf("search", "find", "lookup", "magnify", "query", "खोज", "ढूंढ")
    private val composerWords = listOf("message", "type a message", "write a message", "chat", "compose", "reply", "मैसेज", "संदेश")
    private val sendButtonWords = listOf("send", "submit", "send message", "भेज", "भेजें")

    fun choose(goal: ParsedGoal, state: AgentScreenState, recentHistory: List<String>): AgentCommand? {
        if (goal.appPackage.isNotBlank() && state.packageName != goal.appPackage) {
            return AgentCommand(
                action = AgentAction.OPEN_APP,
                payload = goal.appLabel.ifBlank { goal.appPackage },
                expected = goal.appPackage,
                source = CommandSource.LOCAL,
                role = "OPEN_TARGET_APP"
            )
        }

        if (goal.kind == GoalKind.OPEN_APP && goal.appPackage.isNotBlank() && state.packageName == goal.appPackage) {
            return AgentCommand(
                action = AgentAction.DONE,
                payload = "Target app is foreground",
                expected = goal.appPackage,
                source = CommandSource.LOCAL,
                role = "GOAL_COMPLETE"
            )
        }

        if (goal.kind == GoalKind.SEND_MESSAGE) {
            return chooseSendMessage(goal, state, recentHistory)
        }

        return chooseGeneric(goal, state, recentHistory)
    }

    private fun chooseSendMessage(goal: ParsedGoal, state: AgentScreenState, recentHistory: List<String>): AgentCommand? {
        if (goal.contact.isBlank() || goal.message.isBlank()) return null

        val elements = state.elements
        val searchEditable = elements
            .filter { it.editable && it.enabled && looksSearchLike(it) }
            .maxByOrNull { semanticRoleScore(it, searchWords) }

        val composer = elements
            .filter { it.editable && it.enabled && !it.password && looksComposerLike(it) }
            .maxByOrNull { semanticRoleScore(it, composerWords) }

        val contactCandidate = elements
            .filter { it.enabled && (it.clickable || it.text.isNotBlank() || it.desc.isNotBlank()) }
            .map { it to maxOf(
                AutonomyText.similarity(goal.contact, it.text),
                AutonomyText.similarity(goal.contact, it.desc),
                AutonomyText.similarity(goal.contact, it.context) * 0.90f
            ) }
            .filter { it.second >= 0.78f }
            .maxByOrNull { it.second }
            ?.first

        val searchControl = elements
            .filter { it.clickable && it.enabled && !it.editable }
            .map { it to semanticRoleScore(it, searchWords) }
            .filter { it.second >= 72 }
            .maxByOrNull { it.second }
            ?.first

        val sendControl = elements
            .filter { it.clickable && it.enabled && !it.editable }
            .map { it to semanticRoleScore(it, sendButtonWords) }
            .filter { it.second >= 82 }
            .maxByOrNull { it.second }
            ?.first

        if (composer != null) {
            val current = composer.text.trim()
            if (AutonomyText.normalize(current) != AutonomyText.normalize(goal.message)) {
                return AgentCommand(
                    action = AgentAction.SET_TEXT,
                    elementKey = composer.key,
                    payload = goal.message,
                    expected = goal.message,
                    source = CommandSource.LOCAL,
                    role = "TYPE_MESSAGE"
                )
            }
            if (sendControl != null) {
                return AgentCommand(
                    action = AgentAction.TAP,
                    elementKey = sendControl.key,
                    expected = goal.message,
                    source = CommandSource.LOCAL,
                    role = "SEND_MESSAGE"
                )
            }
        }

        if (contactCandidate != null && !recentHistory.any { it.contains("CONTACT_OPENED", ignoreCase = true) }) {
            return AgentCommand(
                action = AgentAction.TAP,
                elementKey = contactCandidate.key,
                expected = goal.contact,
                source = CommandSource.LOCAL,
                role = "OPEN_CONTACT"
            )
        }

        if (searchEditable != null) {
            if (AutonomyText.similarity(searchEditable.text, goal.contact) < 0.92f) {
                return AgentCommand(
                    action = AgentAction.SET_TEXT,
                    elementKey = searchEditable.key,
                    payload = goal.contact,
                    expected = goal.contact,
                    source = CommandSource.LOCAL,
                    role = "SEARCH_CONTACT"
                )
            }
            if (contactCandidate != null) {
                return AgentCommand(
                    action = AgentAction.TAP,
                    elementKey = contactCandidate.key,
                    expected = goal.contact,
                    source = CommandSource.LOCAL,
                    role = "OPEN_CONTACT"
                )
            }
        }

        if (searchControl != null) {
            return AgentCommand(
                action = AgentAction.TAP,
                elementKey = searchControl.key,
                expected = goal.contact,
                source = CommandSource.LOCAL,
                role = "OPEN_SEARCH"
            )
        }

        return null
    }

    private fun chooseGeneric(goal: ParsedGoal, state: AgentScreenState, recentHistory: List<String>): AgentCommand? {
        val norm = AutonomyText.normalize(goal.raw)
        if (Regex("(^| )(go )?back( |$)").containsMatchIn(norm) || norm.contains("wapas") || norm.contains("वापस")) {
            return AgentCommand(AgentAction.BACK, source = CommandSource.LOCAL, role = "BACK")
        }

        val candidates = state.elements
            .filter { it.enabled && it.clickable }
            .map { element ->
                val label = element.searchableText()
                val labelTokens = AutonomyText.tokens(label)
                val overlap = labelTokens.intersect(goal.goalTokens).size
                val coverage = if (goal.goalTokens.isEmpty()) 0f else overlap.toFloat() / goal.goalTokens.size.toFloat()
                val direct = AutonomyText.similarity(goal.raw, label)
                element to (coverage * 0.70f + direct * 0.30f)
            }
            .filter { it.second >= 0.66f }
            .sortedByDescending { it.second }

        if (candidates.isNotEmpty()) {
            val top = candidates[0]
            val second = candidates.getOrNull(1)
            if (second == null || top.second - second.second >= 0.10f) {
                val signature = "LOCAL_GENERIC:${top.first.key}:${AutonomyText.normalize(top.first.searchableText()).take(120)}"
                if (recentHistory.none { it.contains(signature, ignoreCase = true) }) {
                    return AgentCommand(
                        action = AgentAction.TAP,
                        elementKey = top.first.key,
                        expected = top.first.text.ifBlank { top.first.desc },
                        source = CommandSource.LOCAL,
                        role = signature
                    )
                }
            }
        }
        return null
    }

    private fun looksSearchLike(element: AgentUiElement): Boolean {
        val s = AutonomyText.normalize(element.searchableText())
        return searchWords.any { s.contains(AutonomyText.normalize(it)) } ||
            element.viewId.lowercase(Locale.US).contains("search")
    }

    private fun looksComposerLike(element: AgentUiElement): Boolean {
        val s = AutonomyText.normalize(element.searchableText())
        if (looksSearchLike(element)) return false
        return composerWords.any { s.contains(AutonomyText.normalize(it)) } ||
            element.viewId.lowercase(Locale.US).let { it.contains("compose") || it.contains("message") || it.contains("entry") || it.contains("input") }
    }

    private fun semanticRoleScore(element: AgentUiElement, words: List<String>): Int {
        val id = AutonomyText.normalize(element.viewId.substringAfterLast('/').replace('_', ' '))
        val text = AutonomyText.normalize(element.text)
        val desc = AutonomyText.normalize(element.desc)
        val context = AutonomyText.normalize(element.context)
        var score = 0
        for (wordRaw in words) {
            val word = AutonomyText.normalize(wordRaw)
            if (word.isBlank()) continue
            if (id == word) score = max(score, 130)
            if (text == word || desc == word) score = max(score, 125)
            if (id.contains(word)) score = max(score, 110)
            if (text.contains(word) || desc.contains(word)) score = max(score, 102)
            if (context.contains(word)) score = max(score, 82)
        }
        if (element.editable) score += 8
        if (element.clickable) score += 5
        return score
    }
}
