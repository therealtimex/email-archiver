# Testing Guide - NiceGUI Dashboard

## Quick Start

```bash
# Start the new NiceGUI dashboard
uv run email-archiver --ui --browser

# Or start the legacy UI for comparison
uv run email-archiver --ui-legacy --browser
```

## Features to Test

### 1. AI Stats Display ✅
**What to test**: Success rate percentages in stats cards

**Steps**:
1. Navigate to Dashboard tab
2. Look at "AI CLASSIFIED" and "DATA ENTITIES" cards
3. If you have processed emails, you should see "Success Rate: X.X%"
4. If no AI processing yet, you'll see descriptive text

**Expected**: 
- Shows percentage when AI stats exist
- Falls back gracefully when no stats

### 2. Advanced Sync Options ✅
**What to test**: After ID, Specific ID inputs

**Steps**:
1. Click "Advanced Options" expansion in Sync section
2. Enter a message ID in "After ID" field
3. Or enter a message ID in "Specific ID" field
4. Click SYNC button

**Expected**:
- Options are hidden by default
- Expand to reveal inputs
- Values are passed to sync operation

### 3. Re-analyze Local Archive ✅
**What to test**: Local-only sync button

**Steps**:
1. Ensure you have some downloaded emails
2. Click "Re-analyze Local Archive" button below SYNC button
3. Watch logs for processing

**Expected**:
- Button only shows when sync is not running
- Triggers local-only sync (no new downloads)
- Re-runs AI classification/extraction on existing emails

### 4. Email Search/Filter ✅
**What to test**: Search functionality

**Steps**:
1. Scroll to "Intelligence Feed" table
2. Enter search term in search box (e.g., "invoice", "meeting")
3. Press Enter or wait for debounce
4. Table should filter results

**Expected**:
- Search filters emails by subject, sender, or content
- Resets to page 1 when searching
- Updates in real-time

### 5. Page Jump Navigation ✅
**What to test**: Jump to specific page

**Steps**:
1. In email table pagination controls
2. Enter page number in "Jump to:" input
3. Click "Go" button

**Expected**:
- Jumps to specified page
- Shows error notification for invalid input
- Works alongside Previous/Next buttons

### 6. Download .eml Button ✅
**What to test**: Email download functionality and enhanced detail modal

**Steps**:
1. Click any email row in the table (row will highlight when selected)
2. Email detail modal opens automatically with comprehensive information
3. Look for "Download EML" button in header (next to date)
4. Click to download

**Expected**:
- Rows are selectable (single selection mode)
- Clicking a row opens the detail modal immediately
- Modal shows full email details including:
  - Classification panel with category and reasoning
  - System Info panel with provider, archived date, and file path
  - Deep Extraction Results with summary, action items, organizations, and people
- Download button appears in header with icon
- Downloads raw .eml file
- File opens in email client
- Modal is scrollable for long content
- Close button (X) in top-right corner
- Selection clears after modal opens

### 7. Provider Secrets JSON Input ✅
**What to test**: Credentials upload

**Steps**:
1. Go to Settings tab
2. Scroll to "Provider Secrets" section
3. Expand "Gmail Credentials"
4. Paste valid JSON (or invalid to test validation)
5. Click "Save Gmail Credentials"

**Expected**:
- Validates JSON format
- Shows error for invalid JSON
- Shows success notification and clears textarea on save
- Saves to `auth/client_secret.json`

**Repeat for M365**:
- Expand "Microsoft 365 Config"
- Test same flow
- Saves to `config/client_secret.json`

### 8. Auto-scroll Logs ✅
**What to test**: Log console scrolling

**Steps**:
1. Start a sync operation
2. Watch the "Process Output" console
3. As logs appear, console should auto-scroll to bottom

**Expected**:
- Latest logs always visible
- No manual scrolling needed
- Smooth scrolling behavior

## Comparison Testing

### Side-by-Side Test
1. Open legacy UI in one browser tab: `http://localhost:8000`
2. Open NiceGUI in another tab: `http://localhost:8001`
3. Compare features and behavior

### Feature Checklist
- [ ] All stats display correctly
- [ ] Sync controls work identically
- [ ] Email table shows same data
- [ ] Search produces same results
- [ ] Settings save correctly
- [ ] Auth flows work
- [ ] Notifications appear properly

## Performance Testing

### Network Traffic
1. Open browser DevTools (F12)
2. Go to Network tab
3. Start legacy UI - observe 2-second polling
4. Start NiceGUI - observe WebSocket connection
5. Compare request counts

**Expected**: NiceGUI uses ~90% less requests

### Responsiveness
1. Trigger a sync operation
2. Observe UI updates
3. Check if stats update in real-time

**Expected**: NiceGUI updates instantly, legacy polls every 2 seconds

## Error Testing

### Invalid Inputs
- [ ] Enter invalid JSON in provider secrets
- [ ] Enter non-numeric page number
- [ ] Try to sync without provider connection
- [ ] Test with invalid LLM credentials

**Expected**: Proper error messages, no crashes

### Edge Cases
- [ ] Empty database (no emails)
- [ ] No AI stats yet
- [ ] Sync already running
- [ ] Network disconnection

**Expected**: Graceful degradation, helpful messages

## Browser Compatibility

Test in multiple browsers:
- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari (macOS)

**Expected**: Works consistently across browsers

## Mobile Testing

1. Open on mobile device or use browser DevTools responsive mode
2. Test all features
3. Check layout and usability

**Expected**: Responsive design, touch-friendly

## Regression Testing

Ensure existing features still work:
- [ ] Gmail OAuth flow
- [ ] M365 device flow
- [ ] Settings save/load
- [ ] Factory reset
- [ ] Webhook configuration
- [ ] LLM presets (OpenAI, Ollama, LM Studio)

## Reporting Issues

If you find bugs, please report:
1. Feature affected
2. Steps to reproduce
3. Expected vs actual behavior
4. Browser and OS
5. Console errors (if any)

## Success Criteria

✅ All 8 new features work as expected
✅ No regressions in existing features
✅ Performance improvements visible
✅ Better UX than legacy UI
✅ No console errors
✅ Responsive on all devices

## Notes

- The NiceGUI dashboard runs on port 8000 by default
- Legacy UI can run on port 8001 with `--ui-legacy --port 8001`
- Both UIs share the same database and backend
- Changes in one UI will reflect in the other after refresh
