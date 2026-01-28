To resolve the issue where commas cannot be typed in the array input fields (due to the formatting logic stripping them instantly), I will introduce a temporary editing state. This allows the user to type freely (including trailing commas) while keeping the underlying data model synchronized with valid parsed values.

**File:** [TaskParams.vue](file:///home/guv_Analysis/GUV_Analysis_APP/GUV_Analysis/frontend/src/pages/TaskParams.vue)

## 1. Add State for Input Handling
- Add `editingField` (ref string) to track which input is active.
- Add `tempInputValue` (ref string) to store the raw input text while editing.

## 2. Implement Handler Functions
- `onArrayFocus(groupKey, paramKey)`: Initialize editing state and load current formatted value.
- `onArrayBlur(groupKey, paramKey, type)`: Commit final value and clear editing state.
- `onArrayInput(val, groupKey, paramKey, type)`: Update temp value and try to sync to params (so JSON updates), but keep the input display locked to the temp value.
- `getDisplayValue(groupKey, paramKey)`: Return `tempInputValue` if editing, otherwise `getArrayValueStr`.

## 3. Update Template
- Modify the `el-input` for `array_number` and `array_select` types to use:
  - `:model-value="getDisplayValue(...)"`
  - `@focus="..."`
  - `@blur="..."`
  - `@input="..."`

This ensures a smooth typing experience for "1, 2, 3" without the comma disappearing.
