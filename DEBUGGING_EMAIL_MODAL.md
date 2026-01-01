# Debugging Email Detail Modal

## Issue
The `show_email_detail()` function is not being called when clicking on email rows in the table.

## Solution Implemented

### Previous Approach (Not Working)
```python
# Used selection event which didn't trigger properly
email_table.on('selection', on_select)
email_table.props('selection="single"')
```

### New Approach (Working)
```python
# Custom Quasar slot with click handler
table.add_slot('body', r'''
    <q-tr :props="props" @click="() => $parent.$emit('rowClick', props.row)" class="cursor-pointer hover:bg-white/5">
        <q-td v-for="col in props.cols" :key="col.name" :props="props">
            {{ col.value }}
        </q-td>
    </q-tr>
''')

table.on('rowClick', handle_row_click)
```

## How It Works

1. **Custom Slot**: Overrides the default table body rendering
2. **Click Event**: Each row (`q-tr`) has an `@click` handler
3. **Event Emission**: Emits `rowClick` event to parent with row data
4. **Handler**: `handle_row_click` receives the event and opens modal
5. **Visual Feedback**: `hover:bg-white/5` shows row is clickable

## Testing Steps

### 1. Check Browser Console
Open browser DevTools (F12) and check for errors:
```javascript
// Should see no errors when clicking rows
```

### 2. Test Click Handler
Click on any email row in the table. You should see:
- Row highlights on hover (slightly lighter background)
- Cursor changes to pointer
- Modal opens with email details

### 3. Verify Data Flow
```python
# Email data is stored in dictionary
email_data['emails'] = {msg_id: email_object, ...}

# Handler retrieves email
email = email_data['emails'].get(msg_id)

# Modal is shown
show_email_detail(email)
```

## Alternative Approaches (If Still Not Working)

### Approach 1: Add Explicit Button Column
```python
columns = [
    # ... other columns
    {'name': 'actions', 'label': 'Actions', 'field': 'actions', 'align': 'center'},
]

# Add button in custom slot
table.add_slot('body-cell-actions', r'''
    <q-td :props="props">
        <q-btn flat dense icon="visibility" @click="$parent.$emit('viewEmail', props.row.message_id)" />
    </q-td>
''')

table.on('viewEmail', lambda e: show_email_detail(email_data['emails'].get(e.args)))
```

### Approach 2: Use Grid Instead of Table
```python
with ui.column().classes('w-full gap-2'):
    for email in emails:
        with ui.card().classes('w-full cursor-pointer hover:bg-white/5') as card:
            card.on('click', lambda e=email: show_email_detail(e))
            with ui.row().classes('w-full justify-between'):
                ui.label(email['subject']).classes('font-bold')
                ui.label(email['received_at']).classes('text-xs text-gray-400')
```

### Approach 3: Simple List with Buttons
```python
for email in emails:
    with ui.row().classes('w-full items-center gap-4 p-2 hover:bg-white/5 rounded'):
        ui.label(email['subject']).classes('flex-1')
        ui.button('View', on_click=lambda e=email: show_email_detail(e)).props('flat dense')
```

## Debugging Checklist

- [ ] Browser console shows no JavaScript errors
- [ ] Rows show hover effect (background changes)
- [ ] Cursor changes to pointer over rows
- [ ] Click event is registered (check Network tab)
- [ ] `email_data['emails']` contains email objects
- [ ] `show_email_detail()` function is defined
- [ ] Modal dialog is properly configured
- [ ] No Python exceptions in terminal

## Common Issues

### Issue 1: Event Not Firing
**Symptom**: Nothing happens when clicking rows
**Solution**: Check if custom slot is properly rendered
```python
# Verify slot syntax
table.add_slot('body', r'''...''')  # Note the r prefix for raw string
```

### Issue 2: Email Data Not Found
**Symptom**: Modal doesn't open or shows empty data
**Solution**: Verify email_data dictionary is populated
```python
# Add debug logging
def handle_row_click(e):
    msg_id = e.args['message_id']
    print(f"Clicked: {msg_id}")
    print(f"Available: {list(email_data['emails'].keys())}")
    email = email_data['emails'].get(msg_id)
    if email:
        print(f"Found email: {email.get('subject')}")
        show_email_detail(email)
    else:
        print("Email not found!")
```

### Issue 3: Modal Not Showing
**Symptom**: Function is called but modal doesn't appear
**Solution**: Check dialog configuration
```python
def show_email_detail(email: Dict[str, Any]):
    with ui.dialog() as dialog, ui.card():
        # ... content
    dialog.open()  # Make sure this is called!
```

## Testing the Fix

1. Start the server:
```bash
uv run email-archiver --ui --browser
```

2. Navigate to Dashboard tab

3. Click on any email row in the "Intelligence Feed" table

4. Expected result:
   - Modal opens with email details
   - Shows classification, system info, and extraction panels
   - Download button is visible
   - Close button works

## Success Criteria

✅ Rows are visually clickable (hover effect)
✅ Clicking a row opens the modal
✅ Modal shows complete email information
✅ Modal can be closed
✅ No console errors
✅ Works on all rows in the table

## If Still Not Working

1. Check NiceGUI version:
```bash
pip show nicegui
```

2. Try updating NiceGUI:
```bash
pip install --upgrade nicegui
```

3. Check for conflicting event handlers

4. Try one of the alternative approaches above

5. Report issue with:
   - NiceGUI version
   - Browser and version
   - Console errors
   - Steps to reproduce
