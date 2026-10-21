"""Tests for the optional AI helper: the saved key, both services (against stand-in servers that
speak their formats), what is and isn't sent, and the chat. No real service is ever contacted."""

import getpass
import http.server
import json
import os
import stat
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_doit import DoitTestCase, doit  # noqa: E402

CLAUDE_KEY = "sk-ant-test-0123456789"
GROK_KEY = "xai-test-0123456789"


class FakeAI:
    """Answers like Anthropic's and xAI's APIs, and remembers each request."""

    def __init__(self):
        self.requests = []
        self.status = 200
        self.reply = "Try the unzip command."
        self.garbage = False
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def handle_any(self, method):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                outer.requests.append({"method": method, "path": self.path, "body": body,
                                       "headers": {k.lower(): v for k, v in self.headers.items()}})
                if outer.garbage:
                    data = b"<html>not json"
                elif outer.status != 200:
                    data = b'{"error": "nope"}'
                elif self.path.startswith("/v1/models"):
                    data = json.dumps({"data": [{"id": m} for m in outer.models]}).encode()
                elif self.path == "/v1/messages":
                    data = json.dumps({"content": [{"type": "text", "text": outer.reply}]}).encode()
                else:
                    data = json.dumps({"choices": [{"message": {"content": outer.reply}}]}).encode()
                self.send_response(outer.status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self.handle_any("GET")

            def do_POST(self):
                self.handle_any("POST")

            def log_message(self, *args):
                pass

        self.models = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class AITestCase(DoitTestCase):
    def setUp(self):
        super().setUp()
        os.environ["no_proxy"] = os.environ["NO_PROXY"] = "127.0.0.1,localhost"
        self.ai = FakeAI()
        os.environ["ALIASMAKER_AI_BASE"] = self.ai.base
        self.addCleanup(os.environ.pop, "ALIASMAKER_AI_BASE", None)
        self.addCleanup(self.ai.stop)

    def set_up_claude(self, **extra):
        config = {"provider": "claude", "key": CLAUDE_KEY, "enabled": True,
                  "model": "claude-sonnet-5-5", "notice_seen": True}
        config.update(extra)
        doit.ai_save(config)
        return config


class TestKeyAndFile(AITestCase):
    def test_the_key_decides_the_service(self):
        self.assertEqual(doit.ai_provider_for_key(CLAUDE_KEY), "claude")
        self.assertEqual(doit.ai_provider_for_key(" " + GROK_KEY + "\n"), "grok")
        self.assertIsNone(doit.ai_provider_for_key("something-else"))
        self.assertIsNone(doit.ai_provider_for_key(""))

    def test_the_file_is_private_to_this_account(self):
        self.set_up_claude()
        mode = stat.S_IMODE(os.stat(doit.ai_path()).st_mode)
        self.assertEqual(mode, 0o600)
        doit.ai_save({"provider": "claude", "key": CLAUDE_KEY})  # saving again keeps it private
        self.assertEqual(stat.S_IMODE(os.stat(doit.ai_path()).st_mode), 0o600)

    def test_forget_deletes_everything_and_is_safe_twice(self):
        self.set_up_claude()
        doit.ai_forget()
        doit.ai_forget()
        self.assertFalse(doit.ai_path().exists())
        self.assertEqual(doit.ai_load(), {})

    def test_a_damaged_file_is_ignored(self):
        doit.ai_path().parent.mkdir(parents=True, exist_ok=True)
        doit.ai_path().write_text("[1, 2]")
        self.assertEqual(doit.ai_load(), {})
        self.assertFalse(doit.ai_ready(doit.ai_load()))

    def test_it_is_only_ready_with_a_key_and_switched_on(self):
        self.assertFalse(doit.ai_ready({}))
        self.assertFalse(doit.ai_ready({"provider": "claude", "key": "k", "enabled": False}))
        self.assertFalse(doit.ai_ready({"provider": "nobody", "key": "k", "enabled": True}))
        self.assertTrue(doit.ai_ready({"provider": "grok", "key": "k", "enabled": True}))

    def test_the_key_is_not_in_the_ordinary_settings(self):
        self.set_up_claude()
        doit.save_settings(doit.load_settings())
        self.assertNotIn(CLAUDE_KEY, (doit.config_dir() / "settings.json").read_text())


class TestServices(AITestCase):
    def test_claude_key_check_uses_its_headers_and_picks_sonnet(self):
        config = {"provider": "claude", "key": CLAUDE_KEY}
        models, chosen = doit.ai_check(config)
        self.assertEqual(chosen, "claude-sonnet-5-5")
        self.assertEqual(models, self.ai.models)
        request = self.ai.requests[0]
        self.assertEqual((request["method"], request["path"].split("?")[0]), ("GET", "/v1/models"))
        self.assertEqual(request["headers"]["x-api-key"], CLAUDE_KEY)
        self.assertEqual(request["headers"]["anthropic-version"], "2023-06-01")
        self.assertNotIn("authorization", request["headers"])

    def test_grok_key_check_uses_a_bearer_token_and_skips_image_models(self):
        self.ai.models = ["grok-image-gen", "grok-text-fast", "grok-text-big"]
        models, chosen = doit.ai_check({"provider": "grok", "key": GROK_KEY})
        self.assertEqual(chosen, "grok-text-fast")
        request = self.ai.requests[0]
        self.assertEqual(request["headers"]["authorization"], "Bearer " + GROK_KEY)
        self.assertNotIn("x-api-key", request["headers"])

    def test_a_chosen_model_is_kept_if_the_key_can_use_it(self):
        _, chosen = doit.ai_check({"provider": "claude", "key": CLAUDE_KEY, "model": "claude-opus-5-5"})
        self.assertEqual(chosen, "claude-opus-5-5")
        _, chosen = doit.ai_check({"provider": "claude", "key": CLAUDE_KEY, "model": "retired-model"})
        self.assertEqual(chosen, "claude-sonnet-5-5")

    def test_no_models_is_an_explained_problem(self):
        self.ai.models = []
        with self.assertRaises(doit.AIError) as caught:
            doit.ai_check({"provider": "claude", "key": CLAUDE_KEY})
        self.assertIn("no AI models", str(caught.exception))

    def test_problems_are_explained_in_plain_words_and_never_show_the_key(self):
        config = {"provider": "claude", "key": CLAUDE_KEY, "model": "m"}
        for status, expect in ((401, "didn't accept that key"), (403, "didn't accept that key"),
                               (404, "isn't available"), (429, "too much"), (503, "having trouble"),
                               (418, "error 418")):
            self.ai.status = status
            with self.assertRaises(doit.AIError) as caught:
                doit.ai_reply(config, [{"role": "user", "content": "hi"}])
            self.assertIn(expect, str(caught.exception), status)
            self.assertNotIn(CLAUDE_KEY, str(caught.exception))
            self.assertNotIn("nope", str(caught.exception))
        self.ai.status = 200
        self.ai.garbage = True
        with self.assertRaises(doit.AIError) as caught:
            doit.ai_reply(config, [{"role": "user", "content": "hi"}])
        self.assertIn("couldn't read", str(caught.exception))

    def test_offline_is_explained(self):
        self.ai.stop()
        self.ai = FakeAI()  # so cleanup has something to stop
        os.environ["ALIASMAKER_AI_BASE"] = "http://127.0.0.1:9"  # nothing listens here
        with self.assertRaises(doit.AIError) as caught:
            doit.ai_models({"provider": "grok", "key": GROK_KEY})
        self.assertIn("couldn't reach", str(caught.exception))


class TestWhatIsSent(AITestCase):
    def test_claude_gets_only_the_chat_and_a_system_note(self):
        config = self.set_up_claude()
        history = [{"role": "user", "content": "how do I unzip?"}]
        self.assertEqual(doit.ai_reply(config, history), "Try the unzip command.")
        request = self.ai.requests[0]
        self.assertEqual(request["path"], "/v1/messages")
        body = request["body"]
        self.assertEqual(set(body), {"model", "max_tokens", "system", "messages"}, "no tools, no files")
        self.assertEqual(body["messages"], history)
        self.assertEqual(body["model"], "claude-sonnet-5-5")

    def test_grok_gets_the_same_and_the_system_note_first(self):
        config = {"provider": "grok", "key": GROK_KEY, "enabled": True, "model": "grok-text"}
        history = [{"role": "user", "content": "hi"}]
        doit.ai_reply(config, history)
        body = self.ai.requests[0]["body"]
        self.assertEqual(self.ai.requests[0]["path"], "/v1/chat/completions")
        self.assertEqual(set(body), {"model", "max_tokens", "messages"})
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(body["messages"][1:], history)

    def test_the_system_note_says_what_it_cannot_do_and_shares_nothing_private(self):
        text = doit.ai_system_prompt()
        self.assertIn("cannot see the person's files", text)
        self.assertIn("cannot run anything", text)
        self.assertIn(doit.detect_os()["name"], text)
        for private in (str(Path.home()), os.environ.get("USER", "\0"), "/home/"):
            self.assertNotIn(private, text)

    def test_nothing_the_ai_says_can_steer_the_terminal(self):
        self.ai.reply = "Hi \x1b[31mred\x1b[0m\x1b]0;pwned\x07 there\x1b[21t\x00\x07 ok\r\nline two"
        config = self.set_up_claude()
        answer = doit.ai_reply(config, [{"role": "user", "content": "x"}])
        self.assertEqual(answer, "Hi red there ok\nline two")
        self.assertNotIn("\x1b", answer)

    def test_an_empty_answer_is_explained(self):
        self.ai.reply = "   "
        with self.assertRaises(doit.AIError):
            doit.ai_reply(self.set_up_claude(), [{"role": "user", "content": "x"}])

    def test_no_model_chosen_is_explained_without_a_request(self):
        with self.assertRaises(doit.AIError):
            doit.ai_reply({"provider": "claude", "key": CLAUDE_KEY}, [{"role": "user", "content": "x"}])
        self.assertEqual(self.ai.requests, [])


class TestChat(AITestCase):
    def sent(self):
        return [r for r in self.ai.requests if r["method"] == "POST"]

    def test_not_set_up_says_where_to_set_it_up_and_asks_nothing_of_the_network(self):
        code, out, _ = self.run_doit(["ai"])
        self.assertEqual(code, 1)
        self.assertIn("☰ → AI", out)
        self.assertEqual(self.ai.requests, [])

    def test_switched_off_is_the_same_as_not_set_up(self):
        self.set_up_claude(enabled=False)
        code, out, _ = self.run_doit(["ai"])
        self.assertEqual(code, 1)
        self.assertEqual(self.ai.requests, [])

    def test_without_a_terminal_it_does_not_chat(self):
        self.set_up_claude()
        code, out, _ = self.run_doit(["ai"], tty=False)
        self.assertEqual(code, 2)
        self.assertEqual(self.ai.requests, [])

    def test_the_first_time_it_says_what_goes_where_and_no_is_respected(self):
        self.set_up_claude(notice_seen=False)
        code, out, prompts = self.run_doit(["ai"], answers=["no"])
        self.assertEqual(code, 0)
        self.assertIn("sent to Anthropic", out)
        self.assertIn("can't run anything", out)
        self.assertIn("isn't saved on your PC", out)
        self.assertEqual(self.ai.requests, [])
        self.assertFalse(doit.ai_load().get("notice_seen"))
        code, out, _ = self.run_doit(["ai"], answers=["yes", "/bye"])
        self.assertTrue(doit.ai_load()["notice_seen"])
        code, out, prompts = self.run_doit(["ai"], answers=["/bye"])
        self.assertNotIn("sent to Anthropic", out, "it only says it once")

    def test_a_chat_remembers_the_conversation_until_you_leave(self):
        self.set_up_claude()
        code, out, prompts = self.run_doit(["ai"], answers=["how do I unzip?", "and a tar file?", "/bye"])
        self.assertEqual(code, 0)
        self.assertIn(doit.AI_BAR + "Try the unzip command.", out)
        self.assertEqual(prompts, [doit.AI_PROMPT] * 3)
        first, second = [r["body"]["messages"] for r in self.sent()]
        self.assertEqual([m["content"] for m in first], ["how do I unzip?"])
        self.assertEqual([m["role"] for m in second], ["user", "assistant", "user"])
        self.assertEqual(second[2]["content"], "and a tar file?")

    def test_a_question_after_doit_ai_starts_the_chat(self):
        self.set_up_claude()
        self.run_doit(["ai", "how", "do", "I", "unzip?"], answers=["/bye"])
        self.assertEqual(self.sent()[0]["body"]["messages"][0]["content"], "how do I unzip?")

    def test_the_first_question_keeps_its_capitals_and_punctuation(self):
        self.set_up_claude()
        self.run_doit(["ai", "How", "do", "I", "open", "Notes.ZIP?"], answers=["/bye"])
        self.assertEqual(self.sent()[0]["body"]["messages"][0]["content"], "How do I open Notes.ZIP?")
        self.run_doit(["/AI", "Is", "ls", "-la", "safe?"], answers=["/bye"])
        self.assertEqual(self.sent()[1]["body"]["messages"][0]["content"], "Is ls -la safe?")

    def test_blank_lines_and_ctrl_d(self):
        self.set_up_claude()
        code, out, prompts = self.run_doit(["ai"], answers=["", "  ", "hello"])  # then Ctrl-D
        self.assertEqual(code, 0)
        self.assertIn("Back at your terminal", out)
        self.assertEqual(len(self.sent()), 1)

    def test_leaving_words(self):
        self.set_up_claude()
        for word in ("/bye", "bye", "exit", "quit", "never mind", "Goodbye"):
            code, out, _ = self.run_doit(["ai"], answers=[word])
            self.assertEqual(code, 0)
            self.assertIn("Back at your terminal", out, word)
        self.assertEqual(self.sent(), [])

    def test_a_failed_question_is_explained_and_not_remembered(self):
        self.set_up_claude()
        self.ai.status = 429
        answers = ["first", "/bye"]
        _, out, _ = self.run_doit(["ai"], answers=answers)
        self.assertIn("too much", out)
        self.ai.status = 200
        self.run_doit(["ai"], answers=["second", "/bye"])
        self.assertEqual([m["content"] for m in self.sent()[-1]["body"]["messages"]], ["second"])

    def test_only_the_recent_turns_are_sent(self):
        self.set_up_claude()
        many = [f"question {n}" for n in range(doit.AI_MAX_TURNS + 8)] + ["/bye"]
        self.run_doit(["ai"], answers=many)
        last = self.sent()[-1]["body"]["messages"]
        self.assertLessEqual(len(last), doit.AI_MAX_TURNS * 2)
        self.assertEqual(last[-1]["content"], f"question {doit.AI_MAX_TURNS + 7}")

    def test_the_chat_is_not_saved_anywhere(self):
        self.set_up_claude()
        doit.save_settings({"logging": True, "yes_words": ["y", "yes"]})
        self.run_doit(["ai"], answers=["my secret question about zebra", "/bye"])
        for folder in (doit.config_dir(), doit.data_dir()):
            for path in folder.rglob("*"):
                if path.is_file():
                    self.assertNotIn("zebra", path.read_text(errors="replace"), str(path))
        self.assertEqual(self.log_lines(), [])

    def test_the_key_is_never_printed(self):
        self.set_up_claude()
        for args, answers in ((["ai", "status"], []), (["ai"], ["hi", "/bye"]), (["ai", "off"], []), (["ai", "on"], [])):
            _, out, _ = self.run_doit(args, answers=answers)
            self.assertNotIn(CLAUDE_KEY, out)

    def test_slash_ai_is_the_same_word(self):
        self.set_up_claude()
        _, out, _ = self.run_doit(["/ai", "hello"], answers=["/bye"])
        self.assertIn(doit.AI_BAR + "Try the unzip command.", out)

    def test_ai_is_one_of_alias_makers_own_words(self):
        self.assertEqual(doit.phrase_problem("ai", {})[0], "reserved")
        self.assertEqual(doit.phrase_problem("ai helper", {})[0], "reserved")


class TestChatIsNotTheTerminal(AITestCase):
    """Talking to the AI and running commands must look different, and the chat never runs anything."""

    def setUp(self):
        super().setUp()
        self.set_up_claude()
        for name in ("ls", "git", "rm", "find", "cat"):
            doit_program = self.programs / name
            doit_program.write_text(f'#!/bin/sh\necho RAN-FOR-REAL-{name} >> "{self.home}/ran.txt"\n')
            doit_program.chmod(0o755)
        self.state = doit.State([], doit.load_settings(), False)

    def sent(self):
        return [r["body"]["messages"] for r in self.ai.requests if r["method"] == "POST"]

    def ran_for_real(self):
        return (self.home / "ran.txt").exists()

    def test_the_chat_says_loudly_that_it_is_not_the_terminal(self):
        _, out, _ = self.run_doit(["ai"], answers=["/bye"])
        self.assertIn("AI CHAT with Claude", out)
        self.assertIn("you are NOT at your terminal prompt", out)
        self.assertIn("Nothing runs as a command", out)
        self.assertIn("Type /bye to go back to your terminal", out)
        self.assertIn("Back at your terminal: commands run again", out)

    def test_the_chat_prompt_never_looks_like_the_shells(self):
        self.assertNotIn("Let'sdostuff", doit.AI_PROMPT)
        self.assertTrue(doit.AI_PROMPT.startswith("AI chat"))
        _, _, prompts = self.run_doit(["ai"], answers=["hello", "/bye"])
        self.assertTrue(all(p == doit.AI_PROMPT for p in prompts[:2]))

    def test_every_line_the_ai_writes_is_marked(self):
        self.ai.reply = "First line.\n\nSecond line."
        _, out, _ = self.run_doit(["ai"], answers=["hello", "/bye"])
        reply = out.split(doit.AI_BAR + "Claude:")[1].split("\u2500\u2500 Back")[0]
        lines = [l for l in reply.splitlines()[1:] if l.strip()]
        self.assertTrue(lines and all(l.startswith(doit.AI_BAR.strip()) for l in lines), lines)

    def test_commands_the_ai_suggests_are_marked_as_text_that_did_not_run(self):
        self.ai.reply = "Run this:\n```\nunzip myfiles.zip\n```\nThen look inside."
        _, out, _ = self.run_doit(["ai"], answers=["how do I unzip", "/bye"])
        self.assertIn("\u258c unzip myfiles.zip", out)
        self.assertIn("just text: nothing here ran", out)
        self.assertNotIn("```", out)
        self.assertFalse(self.ran_for_real())

    def test_indented_commands_are_marked_too_once_per_block(self):
        self.ai.reply = "Install it:\n\n    sudo apt install unzip\n    unzip a.zip\n\nThen:\n\n    ls\n\nDone."
        _, out, _ = self.run_doit(["ai"], answers=["how", "/bye"])
        self.assertEqual(out.count("just text: nothing here ran"), 2)
        self.assertIn("\u258c sudo apt install unzip", out)
        self.assertIn("\u258c unzip a.zip", out)
        self.assertFalse(self.ran_for_real())

    def test_colours_are_used_on_a_real_terminal_and_switched_off_by_no_color(self):
        with mock.patch.object(doit, "color_ok", return_value=True):
            self.assertIn("\x1b[1;35m", doit.paint("hi", "1;35"))
            self.assertIn("\x01", doit.input_prompt(doit.AI_PROMPT, "1;35"))  # so line editing measures right
        with mock.patch.object(doit, "color_ok", return_value=False):
            self.assertEqual(doit.paint("hi", "1;35"), "hi")
            self.assertEqual(doit.input_prompt(doit.AI_PROMPT, "1;35"), doit.AI_PROMPT)

    def test_the_window_title_says_ai_chat_and_is_given_back(self):
        written = []
        fake_out = mock.Mock(write=written.append, flush=lambda: None, isatty=lambda: True)
        with mock.patch.dict(os.environ, {"ALIASMAKER": "1", "NO_COLOR": "1"}), \
                mock.patch.object(doit.sys, "stdout", fake_out):
            doit.set_window_title("AI chat with Claude")
            doit.set_window_title("Let'sdostuff~")
        self.assertEqual(written, ["\x1b]0;AI chat with Claude\x07", "\x1b]0;Let'sdostuff~\x07"])
        written.clear()
        with mock.patch.dict(os.environ, {"ALIASMAKER": "0"}), mock.patch.object(doit.sys, "stdout", fake_out):
            doit.set_window_title("x")
        self.assertEqual(written, [], "other terminals' titles are left alone")

    def test_what_looks_like_a_command(self):
        yes = ["ls -la", "sudo apt update", "cd /tmp", "git status", "rm -rf ~/old", "./run.sh", "cat notes | grep x",
               "ls", "/usr/bin/thing", "find . -name x", "ls > out.txt"]
        no = ["how do I unzip a file?", "find the biggest file", "make a folder for me", "what does ls do",
              "cat my file", "hello", "thanks", "I need help", "why is my wifi slow", "explain git", ""]
        for text in yes:
            self.assertTrue(doit.looks_like_command(text, self.state), text)
        for text in no:
            self.assertFalse(doit.looks_like_command(text, self.state), text)

    def test_one_of_your_own_phrases_counts_as_a_command(self):
        doit.save_custom_command("check my drives", "lsblk", False)
        state = doit.State([], doit.load_settings(), False)
        self.assertTrue(doit.looks_like_command("check my drives", state))

    def test_a_pasted_command_is_never_run_and_not_sent_unless_you_ask(self):
        _, out, prompts = self.run_doit(["ai"], answers=["rm -rf ~/old", "no", "/bye"])
        self.assertIn("That looks like a terminal command. Nothing runs in this chat.", out)
        self.assertIn("leave with /bye and type it at your terminal prompt", out)
        self.assertEqual(self.sent(), [])
        self.assertFalse(self.ran_for_real())

    def test_you_can_ask_the_ai_to_explain_a_pasted_command(self):
        _, out, _ = self.run_doit(["ai"], answers=["ls -la /etc", "yes", "/bye"])
        message = self.sent()[0][0]["content"]
        self.assertIn("Explain in plain words what this terminal command would do", message)
        self.assertIn("Don't pretend to run it", message)
        self.assertTrue(message.endswith("ls -la /etc"))
        self.assertFalse(self.ran_for_real(), "explaining is not running")
        self.assertIn(doit.AI_BAR + "Claude:", out)

    def test_a_first_message_that_is_a_command_gets_the_same_care(self):
        _, out, _ = self.run_doit(["ai", "ls", "-la"], answers=["no", "/bye"])
        self.assertIn("That looks like a terminal command", out)
        self.assertEqual(self.sent(), [])
        self.assertFalse(self.ran_for_real())

    def test_questions_with_command_words_in_them_are_just_sent(self):
        self.run_doit(["ai"], answers=["what does ls -la do?", "find the biggest file", "/bye"])
        self.assertEqual([m[-1]["content"] for m in self.sent()], ["what does ls -la do?", "find the biggest file"])

    def test_the_ai_is_told_the_difference_too(self):
        text = doit.ai_system_prompt()
        self.assertIn("never a command that gets run", text)
        self.assertIn("never pretend it ran", text)
        self.assertIn("fenced code block", text)
        self.assertIn("after leaving this chat with /bye", text)


class TestSetupAndSettings(AITestCase):
    def test_on_off_status_forget(self):
        code, out, _ = self.run_doit(["ai", "on"])
        self.assertEqual(code, 1)
        self.assertIn("no key yet", out)
        self.set_up_claude()
        _, out, _ = self.run_doit(["ai", "status"])
        self.assertIn("on, Claude, model claude-sonnet-5-5", out)
        self.run_doit(["ai", "off"])
        self.assertFalse(doit.ai_load()["enabled"])
        _, out, _ = self.run_doit(["ai", "status"])
        self.assertIn("off, Claude", out)
        self.run_doit(["ai", "on"])
        self.assertTrue(doit.ai_load()["enabled"])
        _, out, _ = self.run_doit(["ai", "forget"])
        self.assertIn("deleted", out)
        self.assertEqual(doit.ai_load(), {})
        _, out, _ = self.run_doit(["ai", "status"])
        self.assertIn("isn't set up", out)

    def test_typing_the_key_in_a_terminal_hides_it_and_checks_it(self):
        with mock.patch.object(getpass, "getpass", return_value=GROK_KEY) as hidden:
            self.ai.models = ["grok-text"]
            code, out, _ = self.run_doit(["ai", "setup"])
        self.assertEqual(code, 0)
        hidden.assert_called_once()
        self.assertNotIn(GROK_KEY, out)
        saved = doit.ai_load()
        self.assertEqual((saved["provider"], saved["key"], saved["model"], saved["enabled"]),
                         ("grok", GROK_KEY, "grok-text", True))
        self.assertIn("never your account password", out)

    def test_a_key_that_does_not_work_is_not_saved(self):
        self.ai.status = 401
        with mock.patch.object(getpass, "getpass", return_value=CLAUDE_KEY):
            code, out, _ = self.run_doit(["ai", "setup"])
        self.assertEqual(code, 1)
        self.assertIn("didn't accept that key", out)
        self.assertEqual(doit.ai_load(), {})

    def test_an_unknown_kind_of_key_asks_which_service(self):
        with mock.patch.object(getpass, "getpass", return_value="mystery-key-123"):
            code, out, prompts = self.run_doit(["ai", "setup"], answers=["grok"])
        self.assertEqual(code, 0)
        self.assertEqual(doit.ai_load()["provider"], "grok")
        with mock.patch.object(getpass, "getpass", return_value="mystery-key-123"):
            code, _, _ = self.run_doit(["ai", "setup"], answers=["what"])
        self.assertEqual(code, 1)

    def test_an_empty_key_saves_nothing(self):
        with mock.patch.object(getpass, "getpass", return_value="  "):
            code, out, _ = self.run_doit(["ai", "setup"])
        self.assertEqual(code, 0)
        self.assertEqual(doit.ai_load(), {})
        self.assertEqual(self.ai.requests, [])

    def test_setup_needs_a_terminal(self):
        code, out, _ = self.run_doit(["ai", "setup"], tty=False)
        self.assertEqual(code, 2)

    def test_it_is_off_until_set_up_and_the_help_mentions_it(self):
        self.assertEqual(doit.ai_load(), {})
        _, out, _ = self.run_doit(["help"])
        self.assertIn("/ai or doit ai", out)


if __name__ == "__main__":
    unittest.main()
