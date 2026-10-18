"""ELI5 (Explain It Like I'm Five) explanation engine.

The tool is *smart*: it knows what's happening, what we're doing, and
why. But it explains everything in plain language, like a friendly
mentor explaining to a beginner. It never uses jargon without explaining
what it means.

Every step, every error, and every result is wrapped in a human-friendly
explanation.
"""

from __future__ import annotations

import random


class ELI5:
    """Explains technical things in plain language.

    Usage:
        eli5 = ELI5()
        print(eli5.explain_read_fault_codes())
        # => "We're going to ask the car's computer for the list of problems it remembered."
    """

    # --- Words the tool uses, mapped to plain-language explanations ---
    def __init__(self):
        self._explanations = {
            "read_data_by_identifier": "reading a numbered item of data from the car's computer",
            "write_data_by_identifier": "writing a number onto a numbered item in the car's computer",
            "read_dtc_information": "asking the car to tell us what problems it found",
            "clear_dtc_information": "erasing the car's list of problems",
            "request_upload": "asking the car to send us a big file",
            "transfer_data": "moving a file in small pieces",
            "transfer_exit": "saying 'that's all' after sending/receiving a file",
            "diagnostic_session_control": "changing the car's 'mode' (like turning on a walkie-talkie)",
            "ecu_reset": "asking the car's computer to restart",
            "security_access": "unlocking the car's computer before we can change protected data",
            "routine_control": "starting or stopping a test the car runs on itself",
            "bus_monitor": "recording everything the car's computers say to each other",
        }

    # --- Explain a generic step ---------------------------------
    def explain_step(self, verb: str, subject: str, detail: str = "") -> str:
        """'We're about to {verb} the {subject}.' with an optional detail."""
        txt = f"We're going to {verb} the {subject}."
        if detail:
            txt += f" That means {detail}."
        return txt

    # --- Explain a read ---------------------------------------------------
    def explain_read(self, item: str, quantity: str = "") -> str:
        return self.explain_step("look at / check", item, self._read_hint(item, quantity))

    def _read_hint(self, item: str, quantity: str = "") -> str:
        if item in ("coding table", "data item"):
            return f"It's like asking a librarian to tell you what's written on page {item}."
        if item in ("fault codes", "DTCs"):
            return f"It's like asking the car 'what problems have you had today?'"
        if item in ("memory", "RAM"):
            return f"It's like reading a page from a giant notebook the car keeps."
        return f"It's like asking {item} to show us what it's holding."

    # --- Explain a write --------------------------------------------------
    def explain_write(self, item: str, value: str, force: bool = False) -> str:
        warn = ""
        if force:
            warn = " (This is a protected item - be very sure before doing this!)"
        return self.explain_step("put", item, f"You will write the number {value} onto the item in the car's computer{warn}.")

    # --- Explain a reset ------------------------------------------------
    def explain_reset(self, mode: str, ecu_name: str = "") -> str:
        mode_names = {
            "hard": "a full restart - like turning the car's computer off and back on",
            "soft": "a gentle restart - keeping the memory but rebooting",
            "keyoffon": "turning the car's power off and back on (like a hard reset)",
        }
        hint = mode_names.get(mode, "a restart of the car's computer")
        return self.explain_step("restart", ecu_name or "the car's computer", hint)

    # --- Explain fault codes --------------------------------------------
    def explain_dtc(self, dct: str, status: str = "") -> str:
        return f"The car has a problem called '{dct}'. It's like a 'check engine' light turned into a number. {status}"

    # --- Explain a connection -------------------------------------------
    def explain_connect(self, adapter: str, ecu: str) -> str:
        return self.explain_step("put on the headphones", "the car's computer", f"We'll talk to it through {adapter}, and we're talking to {ecu}.")

    # --- Explain a flash (upload) ---------------------------------------
    def explain_flash(self, ecu_name: str, file: str) -> str:
        return (f"We're going to put new software onto {ecu_name}, the car's computer. "
                f"It's like updating a phone app - we'll replace the old software with the new "
                f"version so the car works better.")

    # --- Explain a bus monitor ------------------------------------------
    def explain_monitor(self, action: str) -> str:
        if action == "start":
            return "We're going to record everything the car's computers say to each other - like a tape recorder for the car's conversation."
        if action == "stop":
            return "We're done recording. We've saved the car's conversation so we can listen to it later."
        return f"We're going to start/stop recording the car's conversation."

    # --- Translate a technical term -------------------------------------
    def term(self, technical: str) -> str:
        """Give a plain-language explanation of a technical term."""
        # Simple translations
        trans = {
            "CAN": "a special kind of wire network that lets car computers talk to each other",
            "ECU": "one of the car's many small computers, each in charge of a different part (engine, brakes, radio, etc.)",
            "DTC": "a diagnostic trouble code - a number the car makes up when something goes wrong",
            "UDS": "the language car computers use to ask each other questions about diagnostics",
            "SA code": "a 'software accessory' code - like an extra feature the car's computer stores (like parking sensors)",
            "SF11/SF03": "the magic handshake used to upload new software to a car's computer",
            "CBF/SMR-D": "the 'dictionary' files that tell the tool what each car computer knows",
            "seed/key": "a temporary password the car gives us to unlock it for writing",
            "ISO-TP": "a way to send big messages over the CAN network in small pieces",
            "baud rate": "how fast the talking goes - like words-per-minute on a walkie-talkie",
        }
        return trans.get(technical, f"Technical term '{technical}' - I'll explain this in more detail when you run it.")

    # --- Explain a negative response ------------------------------------
    def explain_error(self, nrc: int) -> str:
        """Turn a UDS Negative Response Code into plain language."""
        nrc_names = {
            0x00: "nothing - the request was fine",
            0x10: "the car said 'that service isn't in my toolbox yet'",
            0x21: "the message was too short or missing a byte",
            0x23: "the car is busy - try again in a moment",
            0x31: "the request was out of range (like asking for a page that doesn't exist)",
            0x33: "the conditions aren't right (the car isn't in the right mode)",
            0x38: "we don't have enough permission to do that",
            0x3D: "the request failed to execute (the car couldn't do it)",
            0x7F: "the car answered 'no' with a reason",
        }
        return f"The car said '{nrc:#04x}' which means: {nrc_names.get(nrc, 'the car did not like the request').capitalize()}"
