#!/usr/bin/env python3
"""Goon Integration Test -- run from your laptop while holding two phones.

Prerequisites:
  - Goon server running and deployed
  - GOON_NUMBER set in .env
  - TEST_BUSINESS_PHONE set to your Google Voice number
  - Your main phone ready to text
  - Your test phone (Google Voice) ready to receive calls

This script guides you through each scenario step by step.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

GOON_NUMBER = os.getenv("GOON_NUMBER", "<not set>")
TEST_BUSINESS_PHONE = os.getenv("TEST_BUSINESS_PHONE", "<not set>")
YOUR_PHONE = os.getenv("YOUR_PHONE", "<not set>")

results: dict[str, bool] = {}


def log_result(name: str, result: str) -> None:
    results[name] = result.strip().lower() == "y"


def banner(text: str) -> None:
    print()
    print("=" * 60)
    print(text)
    print("=" * 60)
    print()


def scenario_header(num: int, title: str, tests: str) -> None:
    print(f"--- SCENARIO {num}: {title} ---")
    print(f"Tests: {tests}")
    print()


def main() -> None:
    banner("GOON INTEGRATION TEST")
    print(f"  Goon number:          {GOON_NUMBER}")
    print(f"  Test business phone:  {TEST_BUSINESS_PHONE}")
    print(f"  Your phone:           {YOUR_PHONE}")
    print(f"  Started:              {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print()

    if "<not set>" in (GOON_NUMBER, TEST_BUSINESS_PHONE):
        print("ERROR: Set GOON_NUMBER and TEST_BUSINESS_PHONE in .env first.")
        sys.exit(1)

    input("Press Enter when both phones are ready...")
    print()

    # ------------------------------------------------------------------
    # Scenario 1: Cached answer (no call)
    # ------------------------------------------------------------------
    scenario_header(1, "Cached Answer", "SMS gateway, orchestrator, fact cache, memory")
    print("From your phone, text Goon:")
    print('  "What time does Riley\'s Pizza close?"')
    print()
    print("Expected: An answer about hours (11am-10pm) with NO call.")
    print()
    input("Press Enter after you've sent the text and received a response...")
    result = input("Did you get the correct hours without a phone call? (y/n): ")
    log_result("scenario_1_cached_answer", result)
    print()

    # ------------------------------------------------------------------
    # Scenario 2: Google Places answer (no call)
    # ------------------------------------------------------------------
    scenario_header(2, "Google Places", "SMS gateway, orchestrator, Google Places integration")
    print("From your phone, text Goon:")
    print('  "What time does Whole Foods on Middlefield close?"')
    print()
    print("Expected: Real answer from Google Places (not a test business).")
    print()
    input("Press Enter after response...")
    result = input("Did you get real hours from Google Places? (y/n): ")
    log_result("scenario_2_google_places", result)
    print()

    # ------------------------------------------------------------------
    # Scenario 3: Full circuit (THE BIG ONE)
    # ------------------------------------------------------------------
    scenario_header(3, "FULL CIRCUIT", "Everything -- SMS, orchestrator, Vapi voice call, result delivery")
    print("From your phone, text Goon:")
    print('  "Book me a table at Riley\'s Pizza for 2 tonight at 7"')
    print()
    print("Goon should text back that it's calling.")
    print("Your TEST PHONE (Google Voice) should ring.")
    print("ANSWER IT. Pretend you're the restaurant.")
    print("  - The AI will ask for a reservation")
    print("  - Confirm a time, ask for the name, confirm the booking")
    print()
    input("Press Enter after the call ends and you get a result text...")
    result = input("Did the full circuit work? (y/n): ")
    log_result("scenario_3_full_circuit", result)
    print()

    # ------------------------------------------------------------------
    # Scenario 4: Call failure + retry
    # ------------------------------------------------------------------
    scenario_header(4, "Call Failure + Retry", "No-answer detection, retry system")
    print("From your phone, text Goon:")
    print('  "Does Riley\'s Pizza have any specials tonight?"')
    print()
    print("When your test phone rings, DO NOT ANSWER.")
    print("Wait for Goon to text you about the failure.")
    print("Then wait for the retry (~10 min).")
    print("When it rings again, ANSWER and give a specials list.")
    print()
    input("Press Enter after retry succeeds and you get the result...")
    result = input("Did retry work? (y/n): ")
    log_result("scenario_4_retry", result)
    print()

    # ------------------------------------------------------------------
    # Scenario 5: Voice inbound -> outbound
    # ------------------------------------------------------------------
    scenario_header(5, "Voice Inbound", "Vapi inbound assistant, tool use in voice, outbound call")
    print("CALL the Goon number from your main phone.")
    print("Ask: 'Can Riley's Pizza do a party of 6 Saturday?'")
    print("Goon should say it'll call and text you the result.")
    print("Answer your test phone when it rings.")
    print()
    input("Press Enter after you get the result text...")
    result = input("Did voice inbound -> outbound -> SMS result work? (y/n): ")
    log_result("scenario_5_voice_inbound", result)
    print()

    # ------------------------------------------------------------------
    # Scenario 6: Memory persistence
    # ------------------------------------------------------------------
    scenario_header(6, "Memory", "Memory system across sessions")
    print("Text Goon: 'Remember I'm allergic to shellfish'")
    input("Press Enter after confirmation...")
    print("Now text: 'What should I get at Riley's Pizza?'")
    input("Press Enter after response...")
    result = input("Did it mention avoiding shellfish? (y/n): ")
    log_result("scenario_6_memory", result)
    print()

    # ------------------------------------------------------------------
    # Scenario 7: Proactive nudge
    # ------------------------------------------------------------------
    scenario_header(7, "Proactive Nudge", "Trigger system, scheduled tasks, proactive SMS")
    print("This scenario requires seeding your profile with a scheduled task.")
    print("If you haven't set that up, skip this one.")
    print()
    result = input("Did you receive a proactive nudge? (y/n/skip): ")
    if result.strip().lower() != "skip":
        log_result("scenario_7_proactive", result)
    print()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    banner("TEST SUMMARY")
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")

    total = len(results)
    passed_count = sum(1 for v in results.values() if v)
    failed_count = total - passed_count
    print()
    print(f"  {passed_count}/{total} passed, {failed_count} failed")

    if failed_count == 0:
        print()
        print("  All scenarios passed. The circuit works.")
    else:
        print()
        print("  Some scenarios failed. Check server logs for details.")


if __name__ == "__main__":
    main()
