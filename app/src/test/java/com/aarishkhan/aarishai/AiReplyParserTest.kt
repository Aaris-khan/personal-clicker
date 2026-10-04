package com.aarishkhan.aarishai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Test

class AiReplyParserTest {
    private val id = "A123456789abc"

    @Test fun parsesExactJson() {
        val parsed = AiReplyParser.parse(
            """{"request_id":"$id","action":"TAP","element":"E12","payload":"","expected":"Menu opens","visual":"VX88"}""",
            id
        )
        assertNotNull(parsed)
        assertEquals("TAP", parsed!!.action)
        assertEquals("E12", parsed.element)
        assertEquals("Menu opens", parsed.expected)
    }

    @Test fun ignoresProviderProseAndCodeFence() {
        val reply = """
            Sure, here is the next action:
            ```json
            {"request_id":"$id","action":"SWIPE","element":"","payload":"0.5,0.8,0.5,0.3,240","expected":"new rows visible","visual":"NONE"}
            ```
            I hope that helps.
        """.trimIndent()
        val parsed = AiReplyParser.parse(reply, id)
        assertEquals("SWIPE", parsed?.action)
        assertEquals("0.5,0.8,0.5,0.3,240", parsed?.payload)
    }

    @Test fun parsesEscapedTextPayload() {
        val reply = """{"request_id":"$id","action":"SET_TEXT","element":"E2","payload":"Hello \"Aaris\"\nLine2","expected":"text visible","visual":"NONE"}"""
        val parsed = AiReplyParser.parse(reply, id)
        assertEquals("SET_TEXT", parsed?.action)
        assertEquals("Hello \"Aaris\"\nLine2", parsed?.payload)
    }

    @Test fun rejectsWrongRequestId() {
        val reply = """{"request_id":"OLD","action":"TAP","element":"E1","payload":"","expected":"x","visual":"NONE"}"""
        assertNull(AiReplyParser.parse(reply, id))
    }

    @Test fun rejectsUnknownAction() {
        val reply = """{"request_id":"$id","action":"EXEC_SHELL","element":"","payload":"rm","expected":"","visual":"NONE"}"""
        assertNull(AiReplyParser.parse(reply, id))
    }

    @Test fun rejectsConflictingCorrelatedObjects() {
        val reply = """
            {"request_id":"$id","action":"TAP","element":"E1","payload":"","expected":"A","visual":"NONE"}
            {"request_id":"$id","action":"TAP","element":"E2","payload":"","expected":"B","visual":"NONE"}
        """.trimIndent()
        assertNull(AiReplyParser.parse(reply, id))
    }

    @Test fun acceptsDuplicateIdenticalObject() {
        val one = """{"request_id":"$id","action":"BACK","element":"","payload":"","expected":"STATE_CHANGE","visual":"NONE"}"""
        val parsed = AiReplyParser.parse("$one\n$one", id)
        assertEquals("BACK", parsed?.action)
    }

    @Test fun keepsLegacyProtocolCompatible() {
        val legacy = "some prose AARIS::$id::TAP::E4::::Dialog opens::NONE::END trailing"
        val parsed = AiReplyParser.parse(legacy, id)
        assertEquals("TAP", parsed?.action)
        assertEquals("E4", parsed?.element)
    }

    @Test fun ignoresUnrelatedJsonAndUsesCorrelatedOne() {
        val reply = """
            {"foo":"bar"}
            {"request_id":"$id","action":"WAIT","element":"","payload":500,"expected":"","visual":"NONE"}
        """.trimIndent()
        val parsed = AiReplyParser.parse(reply, id)
        assertEquals("WAIT", parsed?.action)
        assertEquals("500", parsed?.payload)
    }
}
