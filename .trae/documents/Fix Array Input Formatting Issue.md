To fix the comma input issue in array fields, I will modify the event listener in `TaskParams.vue`. The current implementation uses `@input`, which triggers on every keystroke, causing immediate reformatting that prevents typing commas. Switching to `@change` ensures the value is only processed when the user finishes typing (blur or enter), allowing them to type multiple values separated by commas without interruption.

**File:** [TaskParams.vue](file:///home/guv_Analysis/GUV_Analysis_APP/GUV_Analysis/frontend/src/pages/TaskParams.vue)

## Changes
1.  **Modify `array_number` input**: Change `@input` to `@change` (Line 174).
2.  **Modify `array_select` input**: Change `@input` to `@change` (Line 182).

This change will allow users to type "1, 2, 5" freely, with the parsing logic only running once they are done.
