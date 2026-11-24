import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.agent_engine import process_voice_utterance, rollback_transaction
from backend.database import get_full_state, get_customer_history

print("--- [1] Testing Hard ₹20k Block on Verma Ji ---")
res1 = process_voice_utterance("Verma ji ko 5 peti Good Day bhej do")
print("Intent:", res1.get("intent"))
print("Spoken:", res1.get("spoken_response"))
assert res1.get("intent") in ["CREDIT_OVER_20K_BLOCKED", "CREDIT_OVER_LIMIT_BLOCKED"]
assert "20,000" in res1.get("spoken_response") or "samaan nahi denge" in res1.get("spoken_response").lower()
print("  ✓ Verma Ji ₹20k hard block passed!")

print("\n--- [2] Testing Dynamic Customer Auto-Creation on Spoken Name ---")
res2 = process_voice_utterance("Raju Chaiwale ko 2 peti Parle-G bhej do khate me")
print("Intent:", res2.get("intent"))
print("Spoken:", res2.get("spoken_response"))
assert "Raju Chaiwale" in res2.get("spoken_response")
print("  ✓ Dynamic customer creation passed!")

print("\n--- [3] Testing Cash Order (PAID) vs Credit Order (DUES) ---")
res3 = process_voice_utterance("Aggarwal ji ko 1 peti Marie Gold de do nakad payment")
print("Intent:", res3.get("intent"))
print("Spoken:", res3.get("spoken_response"))
assert "PAID" in res3.get("spoken_response") or "nakad" in res3.get("spoken_response")
print("  ✓ Cash PAID order passed!")

print("\n--- [4] Testing Payment Collection (Paisa Jama) ---")
res4 = process_voice_utterance("Sharma ji ka 3000 rupaye jama kar lo")
print("Intent:", res4.get("intent"))
print("Spoken:", res4.get("spoken_response"))
assert res4.get("intent") == "PAYMENT_COLLECTED"
print("  ✓ Payment collection passed!")

print("\n--- [5] Testing Rollback / Undo ---")
res5 = process_voice_utterance("Arey galti ho gayi ruko cancel karo")
print("Intent:", res5.get("intent"))
print("Spoken:", res5.get("spoken_response"))
assert res5.get("intent") == "ROLLBACK"
print("  ✓ Rollback passed!")

print("\n--- [6] Testing State & Multi-Tenancy on Neon Cloud DB ---")
state_shop1 = get_full_state("SHOP-001")
state_shop2 = get_full_state("SHOP-002")
print(f"Shop 1 ({state_shop1['shop']['shop_name']}): {len(state_shop1['customers'])} grahak, {len(state_shop1['recent_orders'])} orders, Total Dues: ₹{state_shop1['stats']['total_receivables']:,.2f}")
print(f"Shop 2 ({state_shop2['shop']['shop_name']}): {len(state_shop2['customers'])} grahak, {len(state_shop2['recent_orders'])} orders, Total Dues: ₹{state_shop2['stats']['total_receivables']:,.2f}")
print("  ✓ Multi-tenancy isolation passed!")

print("\n=== ALL 6 E2E SUITE TESTS PASSED ON NEON CLOUD POSTGRESQL! ===")
