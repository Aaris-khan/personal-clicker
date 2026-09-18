package com.aarishkhan.aarishai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalMissionPlannerTest {

    @Test
    fun parsesCommonWhatsappSendGoal() {
        val intent = LocalMissionPlanner.parseIntent(
            "Open WhatsApp, find Sameer and send hello bhai"
        )
        assertEquals("WhatsApp", intent.appLabel)
        assertEquals("Sameer", intent.recipient)
        assertEquals("hello bhai", intent.message)
        assertFalse(intent.openOnly)
    }

    @Test
    fun openOnlyMission_finishesWithoutExternalPlanner() {
        val intent = LocalMissionPlanner.parseIntent("Open WhatsApp")
        val command = LocalMissionPlanner.next(
            intent = intent,
            currentPackage = "com.whatsapp",
            targetAppPackage = "com.whatsapp",
            elements = emptyList()
        )
        assertNotNull(command)
        assertEquals("DONE", command!!.action)
        assertTrue(command.terminalAfterVerify)
        assertEquals("PACKAGE=com.whatsapp", command.expected)
    }

    @Test
    fun sendFlow_advancesThroughSearchComposeAndSend() {
        val intent = LocalMissionPlanner.parseIntent(
            "Open WhatsApp, find Sameer and send hello bhai"
        )

        val open = LocalMissionPlanner.next(
            intent,
            "com.android.launcher",
            "com.whatsapp",
            emptyList()
        )
        assertEquals("OPEN_APP", open?.action)

        val search = LocalMissionPlanner.next(
            intent,
            "com.whatsapp",
            "com.whatsapp",
            listOf(
                LocalMissionPlanner.Element(
                    key = "E1",
                    desc = "Search",
                    clickable = true,
                    yCenterPercent = 0.08f
                )
            )
        )
        assertEquals("TAP", search?.action)
        assertEquals("E1", search?.elementKey)

        val typeRecipient = LocalMissionPlanner.next(
            intent,
            "com.whatsapp",
            "com.whatsapp",
            listOf(
                LocalMissionPlanner.Element(
                    key = "E2",
                    viewId = "search_input",
                    desc = "Search contacts",
                    className = "android.widget.EditText",
                    editable = true,
                    yCenterPercent = 0.10f
                )
            )
        )
        assertEquals("SET_TEXT", typeRecipient?.action)
        assertEquals("Sameer", typeRecipient?.payload)

        val chooseRecipient = LocalMissionPlanner.next(
            intent,
            "com.whatsapp",
            "com.whatsapp",
            listOf(
                LocalMissionPlanner.Element(
                    key = "E3",
                    text = "Sameer",
                    clickable = true,
                    yCenterPercent = 0.30f
                ),
                LocalMissionPlanner.Element(
                    key = "E2",
                    viewId = "search_input",
                    text = "Sameer",
                    desc = "Search contacts",
                    className = "android.widget.EditText",
                    editable = true,
                    yCenterPercent = 0.10f
                )
            )
        )
        assertEquals("TAP", chooseRecipient?.action)
        assertEquals("E3", chooseRecipient?.elementKey)

        val typeMessage = LocalMissionPlanner.next(
            intent,
            "com.whatsapp",
            "com.whatsapp",
            listOf(
                LocalMissionPlanner.Element(
                    key = "E4",
                    viewId = "message_input",
                    desc = "Type a message",
                    className = "android.widget.EditText",
                    editable = true,
                    yCenterPercent = 0.88f
                )
            )
        )
        assertEquals("SET_TEXT", typeMessage?.action)
        assertEquals("hello bhai", typeMessage?.payload)

        val send = LocalMissionPlanner.next(
            intent,
            "com.whatsapp",
            "com.whatsapp",
            listOf(
                LocalMissionPlanner.Element(
                    key = "E4",
                    viewId = "message_input",
                    text = "hello bhai",
                    desc = "Type a message",
                    className = "android.widget.EditText",
                    editable = true,
                    yCenterPercent = 0.88f
                ),
                LocalMissionPlanner.Element(
                    key = "E5",
                    viewId = "send",
                    desc = "Send",
                    clickable = true,
                    yCenterPercent = 0.88f
                )
            )
        )
        assertEquals("TAP", send?.action)
        assertEquals("E5", send?.elementKey)
        assertTrue(send?.terminalAfterVerify == true)
        assertEquals("hello bhai", send?.expected)
    }

    @Test
    fun ambiguousScreen_returnsNullInsteadOfGuessing() {
        val intent = LocalMissionPlanner.parseIntent(
            "Open WhatsApp, find Sameer and send hello"
        )
        val command = LocalMissionPlanner.next(
            intent,
            "com.whatsapp",
            "com.whatsapp",
            listOf(
                LocalMissionPlanner.Element(key = "E1", desc = "Settings", clickable = true),
                LocalMissionPlanner.Element(key = "E2", desc = "Camera", clickable = true)
            )
        )
        assertNull(command)
    }
}
