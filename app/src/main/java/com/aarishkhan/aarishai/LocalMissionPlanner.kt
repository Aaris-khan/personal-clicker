package com.aarishkhan.aarishai

import java.util.Locale

/**
 * Fast, deterministic, Android-free planner for common autonomous UI flows.
 *
 * It intentionally handles only high-confidence actions. Anything ambiguous returns null
 * so AiSidecarController can fall back to the external reasoning sidecar. This keeps AUTO
 * useful even with no ChatGPT/Gemini installed for common "open -> find -> type -> send"
 * tasks while avoiding blind coordinate automation.
 */
internal object LocalMissionPlanner {

    data class Element(
        val key: String,
        val viewId: String = "",
        val text: String = "",
        val desc: String = "",
        val className: String = "",
        val context: String = "",
        val clickable: Boolean = false,
        val editable: Boolean = false,
        val enabled: Boolean = true,
        val yCenterPercent: Float = 0.5f
    )

    data class Intent(
        val appLabel: String? = null,
        val recipient: String? = null,
        val message: String? = null,
        val openOnly: Boolean = false
    ) {
        val hasUsefulLocalIntent: Boolean
            get() = appLabel != null || recipient != null || message != null
    }

    data class Command(
        val action: String,
        val elementKey: String = "",
        val payload: String = "",
        val expected: String = "",
        val terminalAfterVerify: Boolean = false,
        val reason: String = ""
    )

    private fun normalize(raw: String): String =
        raw.lowercase(Locale.US)
            .replace(Regex("[^\\p{L}\\p{N}]+"), " ")
            .replace(Regex("\\s+"), " ")
            .trim()

    private fun cleanCapture(raw: String?): String? {
        val cleaned = raw.orEmpty()
            .replace(Regex("\\s+"), " ")
            .trim()
            .trim(',', ';', ':', '-', '–', '—', '.', '!', '?')
            .trim()
        return cleaned.takeIf { it.length in 1..1200 }
    }

    private fun firstCapture(goal: String, patterns: List<Regex>): String? {
        for (pattern in patterns) {
            val value = cleanCapture(pattern.find(goal)?.groupValues?.getOrNull(1))
            if (!value.isNullOrBlank()) return value
        }
        return null
    }

    fun parseIntent(goalRaw: String): Intent {
        val goal = goalRaw
            .replace(Regex("[\\u0000-\\u001F]+"), " ")
            .replace(Regex("\\s+"), " ")
            .trim()

        if (goal.isBlank()) return Intent()

        val app = firstCapture(
            goal,
            listOf(
                Regex(
                    "(?:open|launch|start|kholo|khol|chalao)\\s+([\\p{L}\\p{N}][\\p{L}\\p{N} ._'-]{0,48}?)(?=\\s*(?:,|;|\\bthen\\b|\\band\\b|\\baur\\b|\\bfind\\b|\\bsearch\\b|\\bmessage\\b|\\bsend\\b|\\bbhej\\w*\\b|$))",
                    RegexOption.IGNORE_CASE
                )
            )
        )

        var recipient = firstCapture(
            goal,
            listOf(
                Regex(
                    "(?:find|search(?:\\s+for)?|contact)\\s+([\\p{L}\\p{N}][\\p{L}\\p{N} ._'-]{0,79}?)(?=\\s+(?:and|then|aur)\\s+(?:send|message|bhej\\w*)|,|;|$)",
                    RegexOption.IGNORE_CASE
                ),
                Regex(
                    "(?:message|send\\s+(?:a\\s+)?message\\s+to)\\s+([\\p{L}\\p{N}][\\p{L}\\p{N} ._'-]{0,79}?)(?=\\s+(?:and|then|aur)\\s+|,|;|$)",
                    RegexOption.IGNORE_CASE
                )
            )
        )

        var message = firstCapture(
            goal,
            listOf(
                Regex(
                    "(?:send|bhejo|bhej|message)\\s+(?:this\\s+message\\s*)?[\"“]([^\"”]{1,1200})[\"”]",
                    RegexOption.IGNORE_CASE
                ),
                Regex(
                    "(?:and|then|aur)\\s+(?:send|bhejo|bhej)\\s+(?:this\\s+message\\s*)?(?:[:=~-]\\s*)?(.+)$",
                    RegexOption.IGNORE_CASE
                )
            )
        )

        // Common Hinglish form: "Sameer ko hello bhai bhejo".
        if (recipient == null || message == null) {
            val ko = Regex(
                "([\\p{L}\\p{N}][\\p{L}\\p{N} ._'-]{0,79}?)\\s+ko\\s+(.{1,1200}?)\\s+(?:bhejo|bhej|send)\\b",
                RegexOption.IGNORE_CASE
            ).find(goal)
            if (ko != null) {
                if (recipient == null) recipient = cleanCapture(ko.groupValues.getOrNull(1))
                if (message == null) message = cleanCapture(ko.groupValues.getOrNull(2))
            }
        }

        // If a recipient is already known, "send hello" after it is safe to treat as payload.
        if (message == null && recipient != null) {
            message = firstCapture(
                goal,
                listOf(
                    Regex(
                        "(?:send|bhejo|bhej)\\s+(?:this\\s+message\\s*)?(?:[:=~-]\\s*)?(.+)$",
                        RegexOption.IGNORE_CASE
                    )
                )
            )
        }

        message = message
            ?.replace(Regex("^(?:this\\s+message|message)\\s*[:=~-]?\\s*", RegexOption.IGNORE_CASE), "")
            ?.trim()
            ?.takeIf { it.isNotBlank() }

        val normalizedGoal = normalize(goal)
        val beyondOpen = listOf(
            "find", "search", "send", "message", "type", "write", "reply",
            "dhund", "dhoond", "bhej", "likh", "ढूंढ", "खोज", "भेज", "लिख"
        ).any(normalizedGoal::contains)

        return Intent(
            appLabel = app,
            recipient = recipient,
            message = message,
            openOnly = app != null && !beyondOpen && recipient == null && message == null
        )
    }

    private fun ownLabel(e: Element): String =
        normalize(listOf(e.text, e.desc, e.viewId.substringAfterLast('/')).joinToString(" "))

    private fun allLabel(e: Element): String =
        normalize(listOf(e.text, e.desc, e.viewId.substringAfterLast('/'), e.className, e.context).joinToString(" "))

    private fun containsAny(hay: String, needles: List<String>): Boolean =
        needles.any { needle -> hay == needle || hay.contains(" $needle ") || hay.startsWith("$needle ") || hay.endsWith(" $needle") || hay.contains(needle) }

    private fun recipientScore(e: Element, recipientRaw: String): Int {
        if (!e.enabled || !e.clickable || e.editable) return Int.MIN_VALUE
        val wanted = normalize(recipientRaw)
        if (wanted.length < 2) return Int.MIN_VALUE
        val own = ownLabel(e)
        val all = allLabel(e)
        if (own.isBlank()) return Int.MIN_VALUE
        var score = when {
            own == wanted -> 1000
            own.startsWith("$wanted ") || own.endsWith(" $wanted") -> 900
            wanted.length >= 4 && own.contains(wanted) -> 820
            wanted.length >= 4 && all.contains(wanted) -> 690
            else -> Int.MIN_VALUE
        }
        if (score == Int.MIN_VALUE) return score
        if (containsAny(all, listOf("search", "find", "send", "attach", "settings"))) score -= 260
        return score
    }

    private fun searchEditorScore(e: Element): Int {
        if (!e.enabled || !e.editable) return Int.MIN_VALUE
        val label = allLabel(e)
        var score = 0
        if (containsAny(label, listOf("search", "find", "contact", "recipient"))) score += 650
        if (e.yCenterPercent < 0.42f) score += 130
        if (label.contains("message") || label.contains("reply")) score -= 500
        return score
    }

    private fun composerScore(e: Element): Int {
        if (!e.enabled || !e.editable) return Int.MIN_VALUE
        val label = allLabel(e)
        if (containsAny(label, listOf("search", "find", "recipient"))) return Int.MIN_VALUE
        var score = 120
        if (containsAny(label, listOf("message", "type", "reply", "chat", "composer"))) score += 520
        if (e.className.contains("EditText", ignoreCase = true)) score += 80
        when {
            e.yCenterPercent >= 0.72f -> score += 260
            e.yCenterPercent >= 0.58f -> score += 150
            e.yCenterPercent < 0.35f -> score -= 250
        }
        return score
    }

    private fun searchButtonScore(e: Element): Int {
        if (!e.enabled || !e.clickable || e.editable) return Int.MIN_VALUE
        val label = allLabel(e)
        var score = 0
        if (containsAny(label, listOf("search", "find"))) score += 760
        if (label.contains("contact")) score += 100
        if (containsAny(label, listOf("settings", "help", "share"))) score -= 500
        return score
    }

    private fun sendButtonScore(e: Element): Int {
        if (!e.enabled || !e.clickable || e.editable) return Int.MIN_VALUE
        val label = allLabel(e)
        var score = 0
        if (Regex("(^| )send( |$)").containsMatchIn(label)) score += 900
        if (label.contains("send message") || label.contains("send_message") || label.contains("arrow up")) score += 500
        if (containsAny(label, listOf("share", "feedback", "send to"))) score -= 700
        if (e.yCenterPercent >= 0.58f) score += 100
        return score
    }

    private fun best(elements: List<Element>, score: (Element) -> Int, threshold: Int): Element? =
        elements
            .map { it to score(it) }
            .filter { it.second >= threshold }
            .sortedByDescending { it.second }
            .let { ranked ->
                val first = ranked.firstOrNull() ?: return@let null
                val second = ranked.getOrNull(1)
                if (second != null && first.second - second.second < 45) null else first.first
            }

    fun next(
        intent: Intent,
        currentPackage: String,
        targetAppPackage: String?,
        elements: List<Element>
    ): Command? {
        if (!intent.hasUsefulLocalIntent) return null

        val appLabel = intent.appLabel
        if (appLabel != null && targetAppPackage != null &&
            !currentPackage.equals(targetAppPackage, ignoreCase = true)
        ) {
            return Command(
                action = "OPEN_APP",
                payload = appLabel,
                expected = "PACKAGE=$targetAppPackage",
                terminalAfterVerify = intent.openOnly,
                reason = "explicit app launch"
            )
        }

        if (intent.openOnly && targetAppPackage != null &&
            currentPackage.equals(targetAppPackage, ignoreCase = true)
        ) {
            return Command(
                action = "DONE",
                expected = "PACKAGE=$targetAppPackage",
                terminalAfterVerify = true,
                reason = "requested app already foreground"
            )
        }

        val recipient = intent.recipient
        val message = intent.message
        if (recipient.isNullOrBlank()) return null

        val composer = best(elements, ::composerScore, 360)
        if (message != null && composer != null) {
            val currentText = normalize(composer.text)
            val wanted = normalize(message)
            if (wanted.isNotBlank() && currentText != wanted) {
                return Command(
                    action = "SET_TEXT",
                    elementKey = composer.key,
                    payload = message,
                    expected = message,
                    reason = "message composer ready"
                )
            }

            if (wanted.isNotBlank() && currentText == wanted) {
                val send = best(elements, ::sendButtonScore, 650)
                if (send != null) {
                    return Command(
                        action = "TAP",
                        elementKey = send.key,
                        expected = message,
                        terminalAfterVerify = true,
                        reason = "verified draft ready to send"
                    )
                }
            }
        }

        val recipientNode = best(elements, { recipientScore(it, recipient) }, 690)
        if (recipientNode != null) {
            return Command(
                action = "TAP",
                elementKey = recipientNode.key,
                expected = recipient,
                terminalAfterVerify = message == null,
                reason = "exact recipient visible"
            )
        }

        val searchEditor = best(elements, ::searchEditorScore, 520)
        if (searchEditor != null) {
            val currentText = normalize(searchEditor.text)
            val wanted = normalize(recipient)
            if (wanted.isNotBlank() && currentText != wanted) {
                return Command(
                    action = "SET_TEXT",
                    elementKey = searchEditor.key,
                    payload = recipient,
                    expected = recipient,
                    reason = "recipient search field"
                )
            }
            return null
        }

        val searchButton = best(elements, ::searchButtonScore, 650)
        if (searchButton != null) {
            return Command(
                action = "TAP",
                elementKey = searchButton.key,
                expected = "STATE_CHANGE",
                reason = "open recipient search"
            )
        }

        return null
    }
}
