"""Tests for the question detector."""

from agentmux.question_detector import detect_question, extract_question


class TestQuestionMark:
    def test_simple_question(self):
        assert detect_question("Which file should I modify?") is True

    def test_not_a_question(self):
        assert detect_question("I fixed the bug in auth.py") is False

    def test_question_on_internal_line(self):
        text = (
            "Let me ask 3 questions:\n"
            "1. What feature do you want to add?\n"
            "2. Where should it live?\n"
            "Take your time."
        )
        assert detect_question(text) is True

    def test_question_in_markdown_bold(self):
        text = (
            "Sure! I need to know:\n"
            "\n"
            "**What feature do you want to add?**\n"
            "\n"
            "Give me a brief description."
        )
        assert detect_question(text) is True

    def test_question_in_markdown_italic(self):
        assert detect_question("*What do you think?*") is True


class TestNumberedLists:
    def test_numbered_list_with_choice_keyword(self):
        text = "Which option do you prefer?\n1. Option A\n2. Option B"
        assert detect_question(text) is True

    def test_numbered_list_without_choice_keyword(self):
        text = "Steps completed:\n1. Fixed bug\n2. Added test"
        assert detect_question(text) is False


class TestPermissionPatterns:
    def test_y_n_bracket(self):
        assert detect_question("Continue? [Y/n]") is True

    def test_allow_keyword(self):
        assert detect_question("Allow access to the file system") is True

    def test_confirm_keyword(self):
        assert detect_question("Confirm the deletion of this file") is True

    def test_proceed_question(self):
        assert detect_question("Proceed?") is True


class TestShortText:
    def test_too_short(self):
        assert detect_question("ok?") is False
        assert detect_question("y/n") is False

    def test_minimum_length(self):
        assert detect_question("Done?") is True


class TestExtraction:
    def test_extract_question_line(self):
        text = "I found two options.\nWhich one do you prefer?"
        assert extract_question(text) == "Which one do you prefer?"

    def test_extract_permission_pattern(self):
        text = "Ready to proceed.\nContinue? [Y/n]"
        assert extract_question(text) == "Continue? [Y/n]"

    def test_extract_fallback_last_line(self):
        text = "Processing complete.\nAll done."
        assert extract_question(text) == "All done."

    def test_extract_empty(self):
        assert extract_question("") == ""
