package com.aarishkhan.aarishai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AutonomyCoreTest {

    private val apps = listOf(
        "WhatsApp" to "com.whatsapp",
        "Chrome" to "com.android.chrome",
        "Google Keep" to "com.google.android.keep"
    )

    @Test
    fun parsesSimpleOpenAppGoal() {
        val goal = GoalParser.parse("Open WhatsApp", apps)

        assertEquals(GoalKind.OPEN_APP, goal.kind)
        assertEquals("WhatsApp", goal.appLabel)
        assertEquals("com.whatsapp", goal.appPackage)
    }

    @Test
    fun toleratesRealWorldAppNameTypo() {
        val goal = GoalParser.parse("mera whatsaap open karo", apps)

        assertEquals(GoalKind.OPEN_APP, goal.kind)
        assertEquals("WhatsApp", goal.appLabel)
        assertEquals("com.whatsapp", goal.appPackage)
    }

    @Test
    fun parsesQuotedContactAndMessage() {
        val goal = GoalParser.parse(
            "Open WhatsApp, find \"Alice Sharma\" and send message: \"On my way\"",
            apps
        )

        assertEquals(GoalKind.SEND_MESSAGE, goal.kind)
        assertEquals("com.whatsapp", goal.appPackage)
        assertEquals("Alice Sharma", goal.contact)
        assertEquals("On my way", goal.message)
    }

    @Test
    fun parsesHinglishSendGoal() {
        val goal = GoalParser.parse(
            "WhatsApp kholo, find \"Rahul\" aur message bhejo: \"kal milte hain\"",
            apps
        )

        assertEquals(GoalKind.SEND_MESSAGE, goal.kind)
        assertEquals("Rahul", goal.contact)
        assertEquals("kal milte hain", goal.message)
    }

    @Test
    fun parsesUnquotedEverydaySendGoal() {
        val goal = GoalParser.parse(
            "WhatsApp kholo, find Rahul aur send hello bhai kal milte hain",
            apps
        )

        assertEquals(GoalKind.SEND_MESSAGE, goal.kind)
        assertEquals("com.whatsapp", goal.appPackage)
        assertEquals("Rahul", goal.contact)
        assertEquals("hello bhai kal milte hain", goal.message)
    }

    @Test
    fun similarityHandlesSemanticContainmentAndSmallTypos() {
        assertTrue(AutonomyText.similarity("Send", "Send message") >= 0.90f)
        assertTrue(AutonomyText.similarity("Alice Sharma", "Alice Sharma online") >= 0.90f)
        assertTrue(AutonomyText.similarity("whatsaap", "whatsapp") >= 0.80f)
    }
}
