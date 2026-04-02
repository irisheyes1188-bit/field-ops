# FieldOps Mobile v2.3 Gremlin Log

Date: 2026-04-02
Repo: `irisheyes1188-bit/field-ops`

## What broke
During conference-day use, completed **My Ops** tasks were not showing up in **Debrief**. Only completed missions were visible and exported.

## Why that mattered
This created a false daily record. Real work was getting done in My Ops, but the debrief handoff only told half the story. The struggle was real:
- tasks were completed in the app
- Debrief did not show them
- Send to Gabby only exported missions
- user had to rebuild app state and re-check finished work to recover the day

## Fix implemented in v2.3
The v2.3 patch updates the app so Debrief now includes completed My Ops tasks alongside completed missions.

### Confirmed behavior in v2.3
- Debrief count includes done tasks and completed missions
- `renderDebrief()` now renders a separate completed tasks section
- `copyDebriefToGabby()` exports both:
  - MISSIONS
  - COMPLETED TASKS
- toggling a task to `done` immediately refreshes Debrief

## Remaining parser caveat
The universal Agent Input parser still does **not** import `[DONE]` tasks on load. That means completed tasks cannot be restored directly through Agent Input and must be reloaded as active tasks, then checked off again in-app.

## Takeaway
The debrief/export fix is real and useful, but the parser still has a completed-task import limitation.

This note exists to preserve the fact that the workflow did not get here cleanly. The struggle was real, the gremlin was documented, and the fix materially improved FieldOps Mobile.