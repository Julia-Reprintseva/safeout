# SafeOut Bot — QA Test Prompt

> Use this prompt to test the SafeOut bot end-to-end as an experienced QA engineer or bot developer.

---

## Role

You are a senior Telegram bot developer with 8+ years of experience building safety-critical bots. You are performing a complete QA review of @safeout_dates_bot. Your goal: find any broken flows, confusing UX, missing edge cases, or data leaks before a public launch.

Test systematically. After each step, note whether the bot's response is correct, clear, and appropriate. Flag anything that feels off.

---

## Test Script

### 1. Cold Start — New User

- Open a fresh private chat with the bot (or `/start` if already used)
- **Expected:** Privacy consent notice appears with a clear explanation of what data is stored and an "I agree" button
- Check: is the text readable? Does it mention the Privacy Policy link? Is the button label clear?
- Press "I agree"
- **Expected:** Warm welcome message with a list of commands

---

### 2. Language Selection

- Send `/language`
- Switch to English, then back to Russian (or your preferred language)
- **Expected:** All subsequent messages arrive in the selected language
- Edge case: restart with `/start` — does the language persist?

---

### 3. No Contacts Warning

- Send `/newdate` without adding any contacts first
- **Expected:** Bot warns you that there are no trusted contacts and opting out means no one will be alerted

---

### 4. Create a Date — Full Flow

Go through the entire `/newdate` questionnaire:

| Step | Input to try | What to check |
|------|-------------|---------------|
| Name | `Алексей` | Saved correctly |
| Profile URL | A real social link | Accepted |
| Profile URL | `/skip` | Skipped gracefully |
| Meeting place | `Кафе Мята, ул. Ленина 5` | Saved |
| Next destination | `/skip` | Optional, skipped |
| Car plate | `А123БВ 77` | Saved |
| Extra info | `Высокий, борода` | Saved |
| Return time | `23:00` | Parsed as today's 23:00 (or tomorrow if past) |
| Return time | `через 2 часа` | Parsed as now + 2h |
| Return time | `через 30 минут` | Parsed as now + 30min, NOT 30 hours |
| Return time | `gibberish` | Bot handles gracefully, asks again or proceeds |

---

### 5. Back Navigation

- During the questionnaire, send `/back` at any step
- **Expected:** Returns to the previous question
- Try `/back` at the very first step — should do nothing or explain

---

### 6. File Upload

- After the questionnaire, upload:
  - A photo
  - A voice message
  - A document
- **Expected:** Each upload is acknowledged; the "Done" button stays visible **at the bottom of the chat** (not buried above the files)
- Upload 5+ files in a row — does the button keep moving down?
- Press "Done with files" without uploading anything — should work fine

---

### 7. Checklist — Compact View

- After pressing "Done", the checklist compact screen appears
- **Expected:** Two buttons — "All good, start" and "Something missing — show list"
- Press "All good, start" → date should begin immediately

---

### 8. Checklist — Detailed View

- Create a new date and press "Something missing"
- **Expected:** Numbered list of items is gone; only a header + clickable buttons for each manual item + "Mark all done" + "Start" + "Back"
- Toggle a few items: ⬜ → ✅ → ❌ → ⬜
- Press "Mark all done" → all toggle buttons should show ✅
- Press "Back" → returns to compact view
- Press "Start" from the detailed view → date begins

---

### 9. Active Session — Pings

- Start a date session
- Wait for the first ping (default: 15 minutes) or ask the developer to reduce the interval for testing
- **Expected:** A short check-in message with "I'm okay" and "SOS" buttons
- Press "I'm okay" → next ping scheduled, confirmation message sent
- Miss the ping entirely → escalation should fire

---

### 10. SOS

- During an active session, press SOS (from the active session keyboard or from a ping message)
- **Expected:** Bot confirms SOS is activated
- Check that the trusted contact receives a Telegram message with a link to the alert page
- Open the alert page link — does it show all the date details?

---

### 11. Safe Return

- Press "I'm home, all good" during an active session
- **Expected:** Warm, slightly humorous message confirming the session is closed
- Verify: bot no longer sends pings after this

---

### 12. Trusted Contacts Flow

- Go to `/contacts`
- Add a contact with name + phone + Telegram username
- Copy the invite link and open it in a second Telegram account
- **Expected:** Second account sees a welcome message confirming they're now a trusted contact
- First account receives a notification that the contact connected
- Check the contacts list — contact should show as "connected on Telegram"

---

### 13. Data Clearing

- Send `/clear`
- **Expected:** Confirmation prompt with a warning (irreversible)
- Press "Cancel" → nothing deleted
- Create another date, then send `/clear` again and confirm
- **Expected:** All session data deleted; contacts remain intact
- Send `/newdate` after clearing — should work normally

---

### 14. Edge Cases

- Send random text outside any flow → bot should not crash or respond with an error
- Send `/newdate` during an active session → check what happens
- Send a very long string (500+ chars) in any field → should not crash
- Send an emoji-only string as a name → should be accepted

---

### 15. Privacy Policy

- Open the Privacy Policy link from the consent message
- **Expected:** Page loads, is readable, mentions what data is stored, has a contact email, has a language switch (RU ↔ EN)

---

## What to Report

For each failed step, note:
- What you did
- What you expected
- What actually happened
- Screenshot if possible

Send findings to: julia.vl.reprintseva@gmail.com or via Telegram @juliareprintseva

---

*Prompt written for SafeOut v1 · August 2025*
